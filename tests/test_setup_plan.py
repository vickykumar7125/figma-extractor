"""setup.py selects a torch profile from the host without installing anything."""

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
    path, note = setup.torch_file_for("cuda", "linux", "x86_64")
    assert path is not None
    assert path.name == "cuda.txt"


def test_linux_rocm_without_nvidia_selects_rocm(monkeypatch) -> None:
    monkeypatch.setattr(setup, "nvidia_present", lambda: False)
    monkeypatch.setattr(setup, "rocm_present", lambda: True)
    assert setup.detect_accelerator("linux", "x86_64") == "rocm"


def test_macos_does_not_select_cuda(monkeypatch) -> None:
    monkeypatch.setattr(setup, "nvidia_present", lambda: True)
    assert setup.detect_accelerator("darwin", "arm64") == "mps"
    path, note = setup.torch_file_for("mps", "darwin", "arm64")
    assert path is not None and path.name == "macos.txt"
    assert "CUDA" in note


def test_macos_intel_skips_torch() -> None:
    path, note = setup.torch_file_for("mps", "darwin", "x86_64")
    assert path is None
    assert "Intel" in note


def test_plan_commands_keep_torch_in_a_second_pip_call(monkeypatch) -> None:
    monkeypatch.setattr(setup, "detect_accelerator", lambda system, machine: "cuda")
    plan = setup.build_plan(include_llm=True, include_torch=True)
    commands = setup.pip_commands(plan)
    assert len(commands) == 4
    assert commands[0][-1] == ".[all-llm]"
    assert str(commands[1][-1]).endswith("cuda.txt")
    assert str(commands[2][-1]).endswith("huggingface-local.txt")
    assert str(commands[3][-1]).endswith("huggingface-quant.txt")
    assert "--index-url" not in " ".join(commands[0])


def test_core_plan_has_no_extras(monkeypatch) -> None:
    monkeypatch.setattr(setup, "detect_accelerator", lambda system, machine: "cpu")
    plan = setup.build_plan(include_llm=False, include_torch=False)
    assert plan.extras == ()
    assert plan.torch_file is None
    assert setup.pip_commands(plan)[0][-1] == "."
