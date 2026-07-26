"""Unpack a Figma ``.fig`` ZIP archive."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from rich.console import Console

console = Console(stderr=True)


def unzip_fig(fig_path: Path, dest: Path) -> Path:
    """
    Extract ``fig_path`` into ``dest``.

    Expected archive members: ``canvas.fig``, ``meta.json``, optional ``images/``.
    """
    if not fig_path.is_file():
        raise FileNotFoundError(f"Fig file not found: {fig_path}")

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(fig_path) as archive:
        archive.extractall(dest)

    canvas = dest / "canvas.fig"
    if not canvas.is_file():
        raise ValueError(f"{fig_path.name} is not a Figma design archive (missing canvas.fig)")

    images = dest / "images"
    image_count = sum(1 for _ in images.iterdir()) if images.is_dir() else 0
    console.print(
        f"[green]Unzipped[/] {fig_path.name} → {dest} "
        f"(canvas.fig, meta.json, {image_count} images)"
    )
    return dest
