"""Packaging checks that do not need a network or a built wheel."""

from __future__ import annotations

import tomllib
from pathlib import Path

import figma_extractor

ROOT = Path(__file__).resolve().parents[1]


def test_version_comes_from_the_package():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in data["project"]
    assert data["project"]["dynamic"] == ["version"]
    assert data["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "figma_extractor.__version__"
    assert figma_extractor.__version__ == "2.2.1"
    assert data["project"]["name"] == "figma-extractor"
    assert data["project"]["license"] == "MIT"


def test_core_dependencies_do_not_include_torch():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names = " ".join(data["project"]["dependencies"]).lower()
    assert "torch" not in names
    assert "bitsandbytes" not in names
