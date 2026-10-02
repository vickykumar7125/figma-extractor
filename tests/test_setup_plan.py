"""setup.py selects one requirements profile from the host without installing."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import setup


def test_linux_nvidia_selects_cuda(monkeypatch) -> None:
    monkeypatch.setattr(setup, "nvidia_present", lambda: True)
    monkeypatch.setattr(setup, "rocm_present", lambda: False)
    monkeypatch.setattr(setup, "xpu_present", lambda: False)
    assert setup.detect_accelerator("linux", "x86_64") == "cuda"
    path, note = setup.profile_for("cuda", "linux", "x86_64", (13, 2))
    assert path is not None
    assert path.name == "cuda132.txt"
    assert "13.2" in note
    path, note = setup.profile_for("cuda", "linux", "x86_64", (13, 0))
    assert path is not None and path.name == "cuda130.txt"
    path, note = setup.profile_for("cuda", "windows", "amd64", (12, 9))
    assert path is not None and path.name == "cuda129.txt"
    assert setup.profile_for("cuda", "linux", "x86_64", (12, 8))[0] is None


def test_linux_rocm_without_nvidia_selects_gpu_file(monkeypatch) -> None:
    monkeypatch.setattr(setup, "nvidia_present", lambda: False)
    monkeypatch.setattr(setup, "rocm_present", lambda: True)
    assert setup.detect_accelerator("linux", "x86_64") == "gpu"
    path, note = setup.profile_for("gpu", "linux", "x86_64")
    assert path is not None and path.name == "gpu.txt"


def test_macos_does_not_select_cuda(monkeypatch) -> None:
    monkeypatch.setattr(setup, "nvidia_present", lambda: True)
    assert setup.detect_accelerator("darwin", "arm64") == "macos"
    path, note = setup.profile_for("macos", "darwin", "arm64")
    assert path is not None and path.name == "macos.txt"
    assert "PyPI" in note


def test_macos_intel_skips_the_profile() -> None:
    path, note = setup.profile_for("macos", "darwin", "x86_64")
    assert path is None
    assert "Intel" in note


def test_full_plan_installs_the_cuda_file(monkeypatch) -> None:
    monkeypatch.setattr(setup.platform, "system", lambda: "Linux")
    monkeypatch.setattr(setup.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(setup, "detect_accelerator", lambda system, machine: "cuda")
    monkeypatch.setattr(setup, "cuda_driver_version", lambda: (13, 1))
    plan = setup.build_plan(include_llm=True, include_torch=True)
    commands = setup.pip_commands(plan)
    assert len(commands) == 2
    assert commands[0][-2:] == ["-e", "."]
    assert str(commands[1][-1]).endswith("cuda130.txt")
    assert "--index-url" not in commands[0]


def test_core_plan_is_the_editable_package_only(monkeypatch) -> None:
    monkeypatch.setattr(setup, "detect_accelerator", lambda system, machine: "cpu")
    plan = setup.build_plan(include_llm=False, include_torch=False)
    assert plan.profile is None
    assert setup.pip_commands(plan) == [[sys.executable, "-m", "pip", "install", "-e", "."]]


def test_xpu_plan_uses_the_xpu_file(monkeypatch) -> None:
    monkeypatch.setattr(setup.platform, "system", lambda: "Linux")
    monkeypatch.setattr(setup.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(setup, "detect_accelerator", lambda system, machine: "xpu")
    plan = setup.build_plan(include_llm=True, include_torch=True)
    assert plan.profile is not None
    assert plan.profile.name == "xpu.txt"
