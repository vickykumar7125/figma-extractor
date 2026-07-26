"""Decode Figma vector path blobs into SVG path data.

A ``.fig`` document stores vector outlines outside the node stream: each
geometry entry carries a ``commandsBlob`` index into ``blobs.bin``. Every blob
is a flat sequence of ``<command byte><float32 args>`` records.

Command encoding
----------------
=======  =====  ======
Command  Args   SVG
=======  =====  ======
0        0      ``Z``
1        2      ``M``
2        2      ``L``
3        4      ``Q``
4        6      ``C``
=======  =====  ======

Example::

    store = PathStore.load(Path("out/extracted"))
    store.svg_path(108)
    'M 12 6 C 12 9.31 9.31 12 6 12 Z'
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import orjson

_ARG_COUNT = {0: 0, 1: 2, 2: 2, 3: 4, 4: 6}
_LETTER = {0: "Z", 1: "M", 2: "L", 3: "Q", 4: "C"}


def _fmt(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def decode_commands(raw: bytes) -> str | None:
    """Convert one command blob into an SVG ``d`` string, or ``None`` if invalid."""
    parts: list[str] = []
    offset = 0
    size = len(raw)
    while offset < size:
        command = raw[offset]
        offset += 1
        arg_count = _ARG_COUNT.get(command)
        if arg_count is None:
            return None
        needed = arg_count * 4
        if offset + needed > size:
            return None
        if arg_count:
            values = struct.unpack_from("<" + "f" * arg_count, raw, offset)
            offset += needed
            parts.append(_LETTER[command] + " " + " ".join(_fmt(value) for value in values))
        else:
            parts.append(_LETTER[command])
    return " ".join(parts) if parts else None


class PathStore:
    """Random access to decoded vector outlines for one extraction."""

    def __init__(self, blobs: bytes, index: list[dict[str, Any]]) -> None:
        self._blobs = blobs
        self._index = index
        self._cache: dict[int, str | None] = {}

    @classmethod
    def load(cls, extracted: Path) -> PathStore | None:
        """Load ``blobs.bin`` + ``blobs-index.json``; ``None`` when absent."""
        blobs_file = extracted / "blobs.bin"
        index_file = extracted / "blobs-index.json"
        if not blobs_file.is_file() or not index_file.is_file():
            return None
        return cls(blobs_file.read_bytes(), orjson.loads(index_file.read_bytes()))

    def svg_path(self, blob_index: int | None) -> str | None:
        if blob_index is None or not 0 <= blob_index < len(self._index):
            return None
        if blob_index in self._cache:
            return self._cache[blob_index]
        entry = self._index[blob_index]
        offset = int(entry.get("offset", 0))
        length = int(entry.get("length", 0))
        decoded = decode_commands(self._blobs[offset : offset + length])
        self._cache[blob_index] = decoded
        return decoded

    def outlines(self, geometry: list[dict[str, Any]] | None) -> list[dict[str, str]]:
        """Map a node's ``fillGeometry`` / ``strokeGeometry`` list to SVG paths."""
        result: list[dict[str, str]] = []
        for entry in geometry or []:
            path = self.svg_path(entry.get("commandsBlob"))
            if not path:
                continue
            rule = (
                "evenodd"
                if entry.get("windingRule") in ("EVENODD", "ODD")
                else "nonzero"
            )
            result.append({"d": path, "rule": rule})
        return result
