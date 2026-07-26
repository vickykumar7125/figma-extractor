"""Unpack a Figma ``.fig`` archive.

A ``.fig`` file is usually a ZIP containing ``canvas.fig`` + ``meta.json`` +
``images/``. Some exports (and older saves) are a bare ``fig-kiwi`` binary —
those are accepted by wrapping them as ``canvas.fig`` inside the output folder.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from rich.console import Console

console = Console(stderr=True)

_FIG_KIWI_MAGIC = b"fig-kiwi"


def _is_zip(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(4) == b"PK\x03\x04"


def _is_fig_kiwi(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(len(_FIG_KIWI_MAGIC)) == _FIG_KIWI_MAGIC


def unzip_fig(fig_path: Path, dest: Path) -> Path:
    """
    Extract ``fig_path`` into ``dest``.

    Accepts:
    - ZIP archives with ``canvas.fig`` (standard Figma local save)
    - Raw ``fig-kiwi`` binaries (copied to ``dest/canvas.fig``)
    """
    if not fig_path.is_file():
        raise FileNotFoundError(f"Fig file not found: {fig_path}")

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    if _is_zip(fig_path):
        with zipfile.ZipFile(fig_path) as archive:
            dest_resolved = dest.resolve()
            for member in archive.infolist():
                target = (dest / member.filename).resolve()
                if not str(target).startswith(str(dest_resolved) + "/") and target != dest_resolved:
                    raise ValueError(f"Blocked zip path traversal: {member.filename}")
            archive.extractall(dest)
        canvas = dest / "canvas.fig"
        if not canvas.is_file():
            raise ValueError(
                f"{fig_path.name} is not a Figma design archive (missing canvas.fig)"
            )
        images = dest / "images"
        image_count = sum(1 for _ in images.iterdir()) if images.is_dir() else 0
        console.print(
            f"[green]Unzipped[/] {fig_path.name} → {dest} "
            f"(canvas.fig, meta.json, {image_count} images)"
        )
        return dest

    if _is_fig_kiwi(fig_path):
        # Bare kiwi document — no embedded image folder in the wrapper.
        shutil.copy2(fig_path, dest / "canvas.fig")
        (dest / "meta.json").write_text(
            json.dumps(
                {
                    "file_name": fig_path.name,
                    "client_meta": {"render_coordinates_scale": 1},
                }
            ),
            encoding="utf-8",
        )
        console.print(
            f"[green]Loaded[/] bare fig-kiwi {fig_path.name} → {dest}/canvas.fig"
        )
        return dest

    raise ValueError(
        f"{fig_path.name} is not a Figma archive (expected ZIP or fig-kiwi magic)"
    )
