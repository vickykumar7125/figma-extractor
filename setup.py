"""Install figma-extractor with the richest profile this machine can use.

``pip install .`` stays the extraction-only install. Run this file when you
want optional LLM providers and a matching PyTorch build as well::

    python setup.py
    python setup.py --dry-run

Torch is installed in a second pip command. Its ``--index-url`` would hide
PyPI if it were combined with the package install.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIN_PYTHON = (3, 11)

TORCH_FILES = {
    "cpu": ROOT / "requirements" / "torch" / "cpu.txt",
    "cuda": ROOT / "requirements" / "torch" / "cuda.txt",
    "rocm": ROOT / "requirements" / "torch" / "rocm.txt",
    "xpu": ROOT / "requirements" / "torch" / "xpu.txt",
    "mps": ROOT / "requirements" / "torch" / "macos.txt",
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
    extras: tuple[str, ...]
    torch_file: Path | None
    local_requirements: tuple[Path, ...] = ()
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"system: {self.system}",
            f"machine: {self.machine}",
            f"python: {sys.version.split()[0]}",
            f"accelerator: {self.accelerator}",
            f"extras: {', '.join(self.extras) if self.extras else 'core extraction only'}",
            f"torch: {self.torch_file.relative_to(ROOT) if self.torch_file else 'skipped'}",
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


def rocm_present() -> bool:
    return command_works("rocm-smi") or Path("/opt/rocm").is_dir()


def xpu_present() -> bool:
    return command_works("xpu-smi") or shutil.which("sycl-ls") is not None


def detect_accelerator(system: str, machine: str) -> str:
    """Pick CUDA, ROCm, XPU, MPS, or CPU. macOS never selects a CUDA wheel."""
    if system == "darwin":
        return "mps"
    if system == "linux" and rocm_present() and not nvidia_present():
        return "rocm"
    if system in {"linux", "windows"} and nvidia_present():
        return "cuda"
    if system in {"linux", "windows"} and xpu_present():
        return "xpu"
    return "cpu"


def torch_file_for(accelerator: str, system: str, machine: str) -> tuple[Path | None, str]:
    normalized = machine.lower()
    if accelerator == "mps":
        if normalized not in {"arm64", "aarch64"}:
            return None, "macOS Intel has no torch 2.14 wheel in requirements/torch/macos.txt."
        return TORCH_FILES["mps"], "macOS wheel includes Metal Performance Shaders. It is not CUDA."
    if accelerator == "rocm":
        if system != "linux" or normalized not in {"x86_64", "amd64"}:
            return None, "ROCm 7.1 wheels are published for Linux x86_64 only."
        return TORCH_FILES["rocm"], "ROCm profile is torch 2.13.0, the newest pair on that index."
    if accelerator == "xpu":
        if normalized not in {"x86_64", "amd64"}:
            return None, "Intel XPU wheels are published for x86_64 only."
        return TORCH_FILES["xpu"], "XPU wheels are published for Linux and Windows."
    if accelerator == "cuda":
        if system == "darwin":
            return None, "CUDA wheels are not published for macOS."
        return TORCH_FILES["cuda"], "CUDA 13.2 wheels are published for Linux and Windows."
    return TORCH_FILES["cpu"], "CPU wheels are published for Linux and Windows. macOS uses macos.txt."


def build_plan(*, include_llm: bool, include_torch: bool) -> InstallPlan:
    system = platform.system().lower()
    machine = platform.machine().lower()
    accelerator = detect_accelerator(system, machine)
    notes: list[str] = []
    extras: tuple[str, ...] = ("all-llm",) if include_llm else ()
    local_requirements: list[Path] = []
    if include_llm:
        local_requirements.append(ROOT / "requirements" / "providers" / "huggingface-local.txt")
        if accelerator == "cuda":
            local_requirements.append(ROOT / "requirements" / "providers" / "huggingface-quant.txt")
            notes.append(
                "BitsAndBytes 4-bit and 8-bit are installed for NVIDIA CUDA. Other backends stay full precision."
            )
    if include_llm:
        notes.append(
            "all-llm installs every chat provider. Extraction still runs with no provider configured."
        )
    torch_file = None
    if include_torch:
        torch_file, reason = torch_file_for(accelerator, system, machine)
        notes.append(reason)
        if torch_file is None:
            accelerator = "unavailable"
    if system == "windows" and accelerator == "rocm":
        notes.append("Windows has no ROCm wheel.")
    return InstallPlan(
        system=system,
        machine=machine,
        accelerator=accelerator,
        extras=extras,
        torch_file=torch_file,
        local_requirements=tuple(local_requirements),
        notes=notes,
    )


def pip_commands(plan: InstallPlan) -> list[list[str]]:
    extra = ""
    if plan.extras:
        extra = "[" + ",".join(plan.extras) + "]"
    package = [sys.executable, "-m", "pip", "install", "-e", f".{extra}"]
    commands = [package]
    if plan.torch_file is not None:
        commands.append(
            [sys.executable, "-m", "pip", "install", "-r", str(plan.torch_file)]
        )
    for requirement in plan.local_requirements:
        commands.append(
            [sys.executable, "-m", "pip", "install", "-r", str(requirement)]
        )
    return commands


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
        description="Install figma-extractor with the richest supported profile."
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
    parser.add_argument("--no-llm", action="store_true", help="Skip LangChain provider packages.")
    parser.add_argument("--no-torch", action="store_true", help="Skip the PyTorch profile.")
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


if __name__ == "__main__":
    raise SystemExit(main())
