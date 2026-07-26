"""Shared helpers: IDs, colours, JSON / NDJSON serialization."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

import orjson

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_ASCII_RE = re.compile(r"[^\x20-\x7E]+")


def gid(guid: dict[str, Any] | None) -> str | None:
    """Format a Figma GUID as ``sessionID:localID``."""
    if not guid:
        return None
    return f"{guid['sessionID']}:{guid['localID']}"


def slug(text: str) -> str:
    return _SLUG_RE.sub("-", text.strip().lower()).strip("-") or "unnamed"


def ascii_name(text: str) -> str:
    return _ASCII_RE.sub("", text).strip() or text


def clamp255(value: float) -> int:
    return max(0, min(255, round(value * 255)))


def to_hex(color: dict[str, Any] | None) -> str | None:
    if not color:
        return None
    return "#" + "".join(f"{clamp255(color[channel]):02X}" for channel in ("r", "g", "b"))


def to_css_color(color: dict[str, Any] | None, opacity: float | None = 1.0) -> str | None:
    if not color:
        return None
    alpha = float(color.get("a", 1.0)) * (1.0 if opacity is None else float(opacity))
    if alpha >= 0.999:
        return to_hex(color)
    return (
        f"rgba({clamp255(color['r'])}, {clamp255(color['g'])}, "
        f"{clamp255(color['b'])}, {round(alpha, 3)})"
    )


def round_num(value: Any, places: int = 2) -> Any:
    if isinstance(value, float):
        return round(value, places)
    return value


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2) + b"\n")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def sanitize_for_json(obj: Any) -> Any:
    """Recursively convert bytes to hex for JSON serialization."""
    if isinstance(obj, (bytes, bytearray, memoryview)):
        return bytes(obj).hex()
    if isinstance(obj, dict):
        return {key: sanitize_for_json(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(value) for value in obj]
    return obj


def to_ndjson_line(obj: Any) -> str:
    """Serialize one object as a single NDJSON line.

    Escapes U+2028 / U+2029 so line-oriented readers do not split mid-record.
    """
    raw = orjson.dumps(sanitize_for_json(obj)).decode("utf-8")
    return raw.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def iter_ndjson(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8", buffering=4 * 1024 * 1024) as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield orjson.loads(line)
