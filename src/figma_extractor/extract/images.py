"""Export image assets with real extensions and a usage manifest.

Images usually live in ``source/images/`` (ZIP ``.fig`` archives). Bare
``fig-kiwi`` files embed the same bytes in decoded blobs, referenced from paints
via ``image.hash`` + ``image.dataBlob``.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import orjson
from PIL import Image
from rich.console import Console

from figma_extractor.paths import design_dir, extracted_dir, nodes_path, require_file, source_dir
from figma_extractor.util import gid, iter_ndjson, write_json

console = Console(stderr=True)


def _detect(buf: bytes) -> tuple[str, str]:
    if len(buf) >= 8 and buf[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if len(buf) >= 3 and buf[0] == 0xFF and buf[1] == 0xD8 and buf[2] == 0xFF:
        return "jpg", "image/jpeg"
    if buf[:3] == b"GIF":
        return "gif", "image/gif"
    if buf[:4] == b"RIFF" and buf[8:12] == b"WEBP":
        return "webp", "image/webp"
    head = buf[:400].decode("utf-8", errors="ignore")
    if "<svg" in head:
        return "svg", "image/svg+xml"
    if b"ftyp" in buf[4:12]:
        return "mp4", "video/mp4"
    return "bin", "application/octet-stream"


def _dimensions(path: Path, ext: str) -> dict[str, int] | None:
    if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
        return None
    try:
        with Image.open(path) as img:
            width, height = img.size
            return {"width": width, "height": height}
    except Exception:
        return None


def _collect_image_refs(nodes_file: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    """Return (usage_by_hash, hash → preferred dataBlob index)."""
    usage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    hash_to_blob: dict[str, int] = {}

    for node in iter_ndjson(nodes_file):
        paints: list[dict[str, Any]] = []
        paints.extend(node.get("fillPaints") or [])
        paints.extend(node.get("strokePaints") or [])
        paints.extend(node.get("backgroundPaints") or [])
        for paint in paints:
            image = paint.get("image") or {}
            hash_name = image.get("hash")
            if not hash_name:
                continue
            usage[hash_name].append(
                {
                    "id": gid(node.get("guid")),
                    "name": node.get("name") or "",
                    "type": node.get("type"),
                    "scaleMode": paint.get("imageScaleMode"),
                }
            )
            blob = image.get("dataBlob")
            if isinstance(blob, int) and hash_name not in hash_to_blob:
                hash_to_blob[hash_name] = blob

            thumb = paint.get("imageThumbnail") or {}
            thumb_hash = thumb.get("hash")
            thumb_blob = thumb.get("dataBlob")
            if (
                isinstance(thumb_hash, str)
                and isinstance(thumb_blob, int)
                and thumb_hash not in hash_to_blob
            ):
                hash_to_blob[thumb_hash] = thumb_blob

    return usage, hash_to_blob


def _materialize_from_blobs(
    out: Path,
    hash_to_blob: dict[str, int],
    destination: Path,
) -> int:
    """Write ``destination/<hash>`` files from extracted blobs. Returns count written."""
    index_path = extracted_dir(out) / "blobs-index.json"
    blobs_path = extracted_dir(out) / "blobs.bin"
    if not index_path.is_file() or not blobs_path.is_file():
        return 0

    blob_index = orjson.loads(index_path.read_bytes())
    if not isinstance(blob_index, list):
        return 0

    destination.mkdir(parents=True, exist_ok=True)
    blobs = blobs_path.read_bytes()
    written = 0
    for hash_name, blob_i in hash_to_blob.items():
        if blob_i < 0 or blob_i >= len(blob_index):
            continue
        entry = blob_index[blob_i]
        offset = int(entry.get("offset", 0))
        length = int(entry.get("length", 0))
        if length <= 0:
            continue
        dest = destination / hash_name
        if dest.is_file():
            continue
        dest.write_bytes(blobs[offset : offset + length])
        written += 1
    return written


def build_images(out: Path) -> dict[str, Any]:
    nodes_file = require_file(
        nodes_path(out),
        "Decoded nodes not found. Run figma-extractor extract first.",
    )
    usage, hash_to_blob = _collect_image_refs(nodes_file)

    images_src = source_dir(out) / "images"
    if not images_src.is_dir():
        images_src.mkdir(parents=True, exist_ok=True)

    # Prefer ZIP-extracted files; fill gaps from embedded kiwi blobs.
    existing = {p.name for p in images_src.iterdir() if p.is_file() and not p.name.startswith(".")}
    missing = {h: i for h, i in hash_to_blob.items() if h not in existing}
    if missing:
        n = _materialize_from_blobs(out, missing, images_src)
        if n:
            console.print(f"[cyan]Images[/] materialized {n} from blobs → {images_src}")

    out_images = design_dir(out) / "assets" / "images"
    out_images.mkdir(parents=True, exist_ok=True)

    files = [p for p in images_src.iterdir() if p.is_file() and not p.name.startswith(".")]
    manifest: list[dict[str, Any]] = []
    by_ext: dict[str, int] = defaultdict(int)

    for src in files:
        buf = src.read_bytes()
        ext, mime = _detect(buf)
        out_name = f"{src.name[:12]}.{ext}"
        dest = out_images / out_name
        dest.write_bytes(buf)
        dims = _dimensions(dest, ext)
        users = usage.get(src.name, [])
        by_ext[ext] += 1
        entry: dict[str, Any] = {
            "hash": src.name,
            "file": f"images/{out_name}",
            "mime": mime,
            "bytes": src.stat().st_size,
            "usedBy": [
                {
                    "node": u["id"],
                    "name": u["name"],
                    "type": u["type"],
                    "scaleMode": u["scaleMode"],
                }
                for u in users[:8]
            ],
            "usageCount": len(users),
        }
        if dims:
            entry.update(dims)
        manifest.append(entry)

    manifest.sort(key=lambda m: (-m["usageCount"], -m["bytes"]))
    write_json(design_dir(out) / "assets" / "manifest.json", manifest)

    orphan = sorted(set(usage) - {p.name for p in files})
    write_json(design_dir(out) / "assets" / "missing-hashes.json", orphan)

    summary = {
        "copied": len(manifest),
        "byFormat": dict(by_ext),
        "referenced": sum(1 for m in manifest if m["usageCount"] > 0),
        "missingHashes": len(orphan),
    }
    console.print(
        f"[green]Images[/] {summary['copied']} copied "
        f"({summary['referenced']} referenced) → {out_images}"
    )
    return summary
