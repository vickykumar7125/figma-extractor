"""Requirement profiles are unpinned and split by accelerator."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQ = ROOT / "requirements"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_core_file_has_no_llm_torch_or_versions() -> None:
    root = text(ROOT / "requirements.txt")
    assert "langchain" not in root
    assert "torch" not in root
    assert ">=" not in root
    assert "==" not in root
    pyproject = text(ROOT / "pyproject.toml")
    start = pyproject.split("[project.optional-dependencies]")[0]
    assert "langchain" not in start
    assert "torch" not in start


def test_accelerator_files_keep_indexes_separate() -> None:
    cuda132 = text(REQ / "cuda132.txt")
    cuda130 = text(REQ / "cuda130.txt")
    cuda129 = text(REQ / "cuda129.txt")
    cpu = text(REQ / "cpu.txt")
    xpu = text(REQ / "xpu.txt")
    gpu = text(REQ / "gpu.txt")
    macos = text(REQ / "macos.txt")
    common = text(REQ / "common.txt")
    for body in (cpu, xpu, gpu, macos, common):
        assert "==" not in body
        assert ">=" not in body
    assert "whl/cu132" in cuda132 and "torch==2.14.1+cu132" in cuda132
    assert "torchvision==0.29.1+cu132" in cuda132 and "bitsandbytes" in cuda132
    assert "cu130" not in cuda132 and "cu129" not in cuda132
    assert "whl/cu130" in cuda130 and "torch==2.14.1+cu130" in cuda130
    assert "torchvision==0.29.1+cu130" in cuda130 and "bitsandbytes" in cuda130
    assert "cu132" not in cuda130 and "cu129" not in cuda130
    assert "whl/cu129" in cuda129
    assert "torch==2.13.0+cu129" in cuda129 and "torchvision==0.28.0+cu129" in cuda129
    assert "torch==2.8.0+cu129" in cuda129 and "torchvision==0.23.0+cu129" in cuda129
    assert "sys_platform" in cuda129
    assert "whl/cpu" in cpu and "cu132" not in cpu
    assert "whl/xpu" in xpu and "cu132" not in xpu
    assert "rocm7.1" in gpu and "cu132" not in gpu and "bitsandbytes" not in gpu
    assert "--index-url" not in macos and "cu132" not in macos
    assert "langchain-openai" in common and "transformers" in common
    assert "torch" not in common


def test_provider_packages_live_in_the_shared_file() -> None:
    common = text(REQ / "common.txt")
    assert "langchain-openai" in common
    assert "langchain-anthropic" in common
    assert "anthropic[vertex]" in common
    assert "langchain-deepseek" in common
    assert not (REQ / "providers").exists()
    assert not (REQ / "torch").exists()
