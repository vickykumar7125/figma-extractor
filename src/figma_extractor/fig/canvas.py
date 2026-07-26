"""Decode ``canvas.fig`` (fig-kiwi binary) into NDJSON nodes and blob sidecars."""

from __future__ import annotations

import zlib
from pathlib import Path
from typing import Any

import zstandard as zstd
from rich.console import Console

from figma_extractor.kiwi import compile_schema, decode_binary_schema, pretty_print_schema
from figma_extractor.util import sanitize_for_json, to_ndjson_line, write_json, write_text

console = Console(stderr=True)

FIG_KIWI_MAGIC = b"fig-kiwi"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
_WRITE_BUFFER = 8 << 20


def read_chunks(buf: bytes) -> tuple[int, list[bytes]]:
    if buf[:8] != FIG_KIWI_MAGIC:
        raise ValueError(f"Not a fig-kiwi file (magic={buf[:8]!r})")
    version = int.from_bytes(buf[8:12], "little")
    offset = 12
    chunks: list[bytes] = []
    while offset < len(buf):
        size = int.from_bytes(buf[offset : offset + 4], "little")
        offset += 4
        chunks.append(buf[offset : offset + size])
        offset += size
    return version, chunks


def decompress_chunk(chunk: bytes) -> bytes:
    if chunk.startswith(ZSTD_MAGIC):
        return zstd.ZstdDecompressor().decompress(chunk)
    try:
        return zlib.decompress(chunk, -zlib.MAX_WBITS)
    except zlib.error:
        try:
            return zlib.decompress(chunk)
        except zlib.error:
            return chunk


def decode_canvas(canvas_path: Path, out_dir: Path) -> dict[str, Any]:
    """
    Decode ``canvas_path`` into ``out_dir``.

    Writes ``nodes.ndjson``, ``blobs.bin``, ``blobs-index.json``,
    ``document-meta.json``, and ``schema.kiwi``.
    """
    buf = canvas_path.read_bytes()
    version, chunks = read_chunks(buf)
    if len(chunks) < 2:
        raise ValueError(f"Expected at least 2 kiwi chunks, got {len(chunks)}")

    console.print(
        f"fig-kiwi v{version} · chunks: " + ", ".join(str(len(chunk)) for chunk in chunks)
    )

    schema_bin = decompress_chunk(chunks[0])
    data_bin = decompress_chunk(chunks[1])
    console.print(f"schema {len(schema_bin):,} B · data {len(data_bin):,} B")

    schema = decode_binary_schema(schema_bin)
    message = compile_schema(schema).decode_message(data_bin)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_text(out_dir / "schema.kiwi", pretty_print_schema(schema))

    node_changes: list[dict[str, Any]] = message.get("nodeChanges") or []
    blobs: list[dict[str, Any]] = message.get("blobs") or []

    with (out_dir / "nodes.ndjson").open("w", encoding="utf-8", buffering=_WRITE_BUFFER) as handle:
        buffer: list[str] = []
        buffer_len = 0
        for node in node_changes:
            line = to_ndjson_line(node) + "\n"
            buffer.append(line)
            buffer_len += len(line)
            if buffer_len > _WRITE_BUFFER:
                handle.write("".join(buffer))
                buffer.clear()
                buffer_len = 0
        if buffer:
            handle.write("".join(buffer))

    blob_index: list[dict[str, int]] = []
    blob_offset = 0
    with (out_dir / "blobs.bin").open("wb") as blob_handle:
        for index, blob in enumerate(blobs):
            raw = blob.get("bytes") or b""
            if isinstance(raw, str):
                raw = bytes.fromhex(raw)
            elif not isinstance(raw, (bytes, bytearray)):
                raw = bytes(raw)
            blob_handle.write(raw)
            blob_index.append({"index": index, "offset": blob_offset, "length": len(raw)})
            blob_offset += len(raw)

    write_json(out_dir / "blobs-index.json", blob_index)

    meta = {key: value for key, value in message.items() if key not in ("nodeChanges", "blobs")}
    meta["_counts"] = {"nodeChanges": len(node_changes), "blobs": len(blobs)}
    write_json(out_dir / "document-meta.json", sanitize_for_json(meta))

    console.print(
        f"[green]Decoded[/] {len(node_changes):,} nodes, "
        f"{len(blobs):,} blobs ({blob_offset:,} B) → {out_dir}"
    )
    return {
        "version": version,
        "nodeChanges": len(node_changes),
        "blobs": len(blobs),
        "blobBytes": blob_offset,
        "out": str(out_dir),
    }
