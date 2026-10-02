"""Requirement profiles stay separated."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQ = ROOT / "requirements"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_base_install_has_no_llm_or_torch() -> None:
    base = text(REQ / "base.txt")
    root = text(ROOT / "requirements.txt")
    assert "langchain" not in base
    assert "torch" not in base
    assert "requirements/base.txt" in root
    pyproject = text(ROOT / "pyproject.toml")
    start = pyproject.split("[project.optional-dependencies]")[0]
    assert "langchain" not in start
    assert "torch" not in start


def test_cuda_profile_is_cu132_and_not_macos() -> None:
    cuda = text(REQ / "torch" / "cuda.txt")
    assert "https://download.pytorch.org/whl/cu132" in cuda
    assert "torch==2.14.1+cu132" in cuda
    assert "torchvision==0.29.1+cu132" in cuda
    assert "macos" not in cuda.lower() or "No macOS" in cuda


def test_profiles_do_not_share_indexes() -> None:
    cpu = text(REQ / "torch" / "cpu.txt")
    rocm = text(REQ / "torch" / "rocm.txt")
    xpu = text(REQ / "torch" / "xpu.txt")
    macos = text(REQ / "torch" / "macos.txt")
    assert "whl/cpu" in cpu
    assert "+cpu" in cpu
    assert "cu132" not in cpu
    assert "rocm7.1" in rocm
    assert "whl/cu132" not in rocm
    assert "torch==2.13.0+rocm7.1" in rocm
    assert "torchvision==0.28.0+rocm7.1" in rocm
    assert "whl/xpu" in xpu
    assert "+xpu" in xpu
    assert "cu132" not in xpu
    assert "--index-url" not in macos
    assert "torch==2.14.1\n" in macos
    assert "cu132" not in macos


def test_provider_files_are_not_pulled_into_llm_runtime() -> None:
    runtime = text(REQ / "llm.txt")
    assert "langchain-openai" not in runtime
    assert "langgraph" in runtime
    openai = text(REQ / "providers" / "openai.txt")
    assert "-r ../llm.txt" in openai
    assert "langchain-openai" in openai
    vertex = text(REQ / "providers" / "vertex.txt")
    assert "anthropic[vertex]" in vertex
    anthropic = text(REQ / "providers" / "anthropic.txt")
    assert "langchain-anthropic" in anthropic
    assert "vertex" not in anthropic
