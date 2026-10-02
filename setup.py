"""Install figma-extractor for this operating system and accelerator.

``pip install -e .`` stays extraction-only. Run this file for the full profile::

    python setup.py
    python setup.py --dry-run

Profiles, under ``requirements/``:

    cuda132.txt  NVIDIA driver CUDA 13.2 or newer
    cuda130.txt  NVIDIA driver CUDA 13.0 or 13.1
    cuda129.txt  NVIDIA driver CUDA 12.9
    cpu.txt      Linux or Windows without a GPU stack
    xpu.txt      Linux or Windows with Intel XPU
    gpu.txt      Linux with AMD ROCm and no NVIDIA GPU
    macos.txt    macOS Apple Silicon

Each profile includes the shared package list and the matching PyTorch index.
CUDA profiles pin the torch and torchvision wheel pair. CPU, XPU, ROCm, and
macOS profiles stay unpinned. The package itself is installed from PyPI first
so the accelerator index does not hide the project. This file is the machine
installer. ``python -m build`` reads ``pyproject.toml`` and does not upload
anywhere.
"""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REQ = ROOT / "requirements"
MIN_PYTHON = (3, 11)

PROFILE_FILES = {
    "cpu": REQ / "cpu.txt",
    "cuda132": REQ / "cuda132.txt",
    "cuda130": REQ / "cuda130.txt",
    "cuda129": REQ / "cuda129.txt",
    "gpu": REQ / "gpu.txt",
    "xpu": REQ / "xpu.txt",
    "macos": REQ / "macos.txt",
}

UPCOMING = (
    "HTML building from an extract is planned. It will turn screen trees, tokens, "
    "and components into HTML, using the optional LLM when it is enabled."
)


@dataclass
class InstallPlan:
    system: str
    machine: str
    accelerator: str
    profile: Path | None
    common_only: bool = False
    torch_only: bool = False
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.profile is None and self.common_only:
            chosen = "requirements/common.txt"
        elif self.profile is None:
            chosen = "extraction only"
        else:
            chosen = str(self.profile.relative_to(ROOT))
        lines = [
            f"system: {self.system}",
            f"machine: {self.machine}",
            f"python: {sys.version.split()[0]}",
            f"accelerator: {self.accelerator}",
            f"requirements: {chosen}",
        ]
        lines.extend(f"note: {note}" for note in self.notes)
        lines.append(f"upcoming: {UPCOMING}")
        return "\n".join(lines)


def python_is_supported() -> bool:
    return sys.version_info >= MIN_PYTHON


def command_works(name: str, args: tuple[str, ...] = ()) -> bool:
    path = shutil.which(name)
    if path is None:
        return False
    try:
        completed = subprocess.run(
            [path, *args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def nvidia_present() -> bool:
    return command_works("nvidia-smi", ("-L",))


def cuda_driver_version() -> tuple[int, int] | None:
    """Read the CUDA version nvidia-smi prints for the installed driver."""
    path = shutil.which("nvidia-smi")
    if path is None:
        return None
    try:
        completed = subprocess.run(
            [path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
            text=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"CUDA Version:\s*(\d+)\.(\d+)", completed.stdout + completed.stderr)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def cuda_profile_name(version: tuple[int, int] | None) -> str | None:
    """Highest CUDA requirements file this driver can load."""
    if version is None:
        return "cuda132"
    if version >= (13, 2):
        return "cuda132"
    if version >= (13, 0):
        return "cuda130"
    if version >= (12, 9):
        return "cuda129"
    return None


def rocm_present() -> bool:
    return command_works("rocm-smi") or Path("/opt/rocm").is_dir()


def xpu_present() -> bool:
    return command_works("xpu-smi") or shutil.which("sycl-ls") is not None


def detect_accelerator(system: str, machine: str) -> str:
    """Pick cuda, gpu (ROCm), xpu, macos, or cpu. macOS never selects CUDA."""
    if system == "darwin":
        return "macos"
    if system == "linux" and rocm_present() and not nvidia_present():
        return "gpu"
    if system in {"linux", "windows"} and nvidia_present():
        return "cuda"
    if system in {"linux", "windows"} and xpu_present():
        return "xpu"
    return "cpu"


def profile_for(
    accelerator: str,
    system: str,
    machine: str,
    cuda_version: tuple[int, int] | None = None,
) -> tuple[Path | None, str]:
    normalized = machine.lower()
    if accelerator == "macos":
        if normalized not in {"arm64", "aarch64"}:
            return None, "macOS Intel has no profile under requirements/macos.txt."
        return PROFILE_FILES["macos"], "macOS uses the PyPI wheel in requirements/macos.txt."
    if accelerator == "gpu":
        if system != "linux" or normalized not in {"x86_64", "amd64"}:
            return None, "requirements/gpu.txt is the Linux x86_64 ROCm profile."
        return PROFILE_FILES["gpu"], "requirements/gpu.txt is AMD ROCm, not NVIDIA CUDA."
    if accelerator == "xpu":
        if normalized not in {"x86_64", "amd64"}:
            return None, "requirements/xpu.txt is published for x86_64."
        return PROFILE_FILES["xpu"], "requirements/xpu.txt is the Intel XPU profile."
    if accelerator == "cuda":
        if system == "darwin":
            return None, "CUDA profiles are not used on macOS."
        name = cuda_profile_name(cuda_version)
        if name is None:
            return None, (
                "The NVIDIA driver reports CUDA older than 12.9. "
                "cuda129.txt, cuda130.txt, and cuda132.txt need a newer driver."
            )
        notes = {
            "cuda132": "requirements/cuda132.txt is torch 2.14.1+cu132 for CUDA 13.2 or newer.",
            "cuda130": "requirements/cuda130.txt is torch 2.14.1+cu130 for CUDA 13.0 or 13.1.",
            "cuda129": "requirements/cuda129.txt is the CUDA 12.9 pair. Linux uses torch 2.13.0+cu129. Windows uses torch 2.8.0+cu129.",
        }
        text = notes[name]
        if cuda_version is None:
            text += " The driver version was not read, so 13.2 was selected."
        return PROFILE_FILES[name], text
    return PROFILE_FILES["cpu"], "requirements/cpu.txt is the Linux and Windows CPU profile."


def build_plan(*, include_llm: bool, include_torch: bool) -> InstallPlan:
    system = platform.system().lower()
    machine = platform.machine().lower()
    accelerator = detect_accelerator(system, machine)
    notes: list[str] = []
    profile = None
    common_only = False
    torch_only = False
    if include_torch:
        cuda_version = cuda_driver_version() if accelerator == "cuda" else None
        profile, reason = profile_for(accelerator, system, machine, cuda_version)
        notes.append(reason)
        if profile is None:
            accelerator = "unavailable"
        elif not include_llm:
            torch_only = True
            notes.append("LLM packages are skipped. The install still uses the accelerator index for torch and torchvision.")
    elif include_llm:
        common_only = True
        notes.append("PyTorch is skipped. requirements/common.txt installs the chat providers.")
    else:
        notes.append("Extraction only. requirements.txt lists those packages.")
    if system == "windows" and accelerator == "gpu":
        notes.append("Windows has no ROCm profile.")
    return InstallPlan(
        system=system,
        machine=machine,
        accelerator=accelerator,
        profile=profile,
        common_only=common_only,
        torch_only=torch_only,
        notes=notes,
    )


def pip_commands(plan: InstallPlan) -> list[list[str]]:
    commands = [[sys.executable, "-m", "pip", "install", "-e", "."]]
    if plan.common_only:
        commands.append(
            [sys.executable, "-m", "pip", "install", "-r", str(REQ / "common.txt")]
        )
        return commands
    if plan.profile is None:
        return commands
    if plan.torch_only and plan.profile is not None:
        index = index_url(plan.profile)
        packages = torch_packages(plan.profile, plan.system)
        command = [sys.executable, "-m", "pip", "install", *packages]
        if index is not None:
            command.extend(["--index-url", index, "--extra-index-url", "https://pypi.org/simple"])
        commands.append(command)
        return commands
    commands.append(
        [sys.executable, "-m", "pip", "install", "-r", str(plan.profile)]
    )
    return commands


def torch_packages(profile: Path, system: str) -> list[str]:
    """Pinned torch lines for this OS. Files without markers apply everywhere."""
    want = "win32" if system == "windows" else "linux"
    chosen: list[str] = []
    for raw in profile.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        body, separator, marker = line.partition(";")
        body = body.strip()
        if not body.startswith(("torch==", "torchvision==")):
            continue
        if separator and want not in marker:
            continue
        chosen.append(body)
    return chosen or ["torch", "torchvision"]


def index_url(profile: Path) -> str | None:
    for line in profile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("--index-url "):
            return stripped.split(maxsplit=1)[1]
    return None


def format_command(command: list[str]) -> str:
    shown: list[str] = []
    for arg in command:
        if any(character in arg for character in " []"):
            shown.append(repr(arg))
        else:
            shown.append(arg)
    return " ".join(shown)


def run_install(plan: InstallPlan) -> int:
    for command in pip_commands(plan):
        print("+", format_command(command), flush=True)
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode != 0:
            return completed.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install figma-extractor using the requirements file for this machine."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="install",
        choices=["install"],
        help="Install the detected profile. This is the default.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and pip commands.")
    parser.add_argument("--core", action="store_true", help="Install extraction only.")
    parser.add_argument("--no-llm", action="store_true", help="Install torch only, from the detected index.")
    parser.add_argument("--no-torch", action="store_true", help="Install requirements/common.txt and skip PyTorch.")
    args = parser.parse_args(argv)

    if not python_is_supported():
        print(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required. "
            f"This interpreter is {sys.version.split()[0]}.",
            file=sys.stderr,
        )
        return 1
    if not (ROOT / "pyproject.toml").is_file():
        print(f"pyproject.toml was not found next to {Path(__file__).name}.", file=sys.stderr)
        return 1

    plan = build_plan(
        include_llm=not (args.core or args.no_llm),
        include_torch=not (args.core or args.no_torch),
    )
    print(plan.summary())
    if args.dry_run:
        for command in pip_commands(plan):
            print("+", format_command(command))
        return 0
    return run_install(plan)


SETUPTOOLS_COMMANDS = {
    "alias",
    "bdist",
    "bdist_egg",
    "bdist_wheel",
    "build",
    "build_clib",
    "build_ext",
    "build_py",
    "develop",
    "dist_info",
    "editable_wheel",
    "egg_info",
    "install_data",
    "install_egg_info",
    "install_lib",
    "install_scripts",
    "rotate",
    "sdist",
    "upload",
}


if __name__ == "__main__":
    if any(arg in SETUPTOOLS_COMMANDS for arg in sys.argv[1:]):
        from setuptools import setup

        setup()
    else:
        raise SystemExit(main())
