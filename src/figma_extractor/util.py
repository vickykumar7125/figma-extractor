"""Shared helpers: IDs, colours, JSON / NDJSON serialization."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

import orjson

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_ASCII_RE = re.compile(r"[^\x20-\x7E]+")
# Longest tokens first so "extralight" wins over "light", "semibold" over "bold".
_WEIGHT_TOKENS: tuple[tuple[str, int], ...] = (
    ("extralight", 200),
    ("ultralight", 200),
    ("extrabold", 800),
    ("ultrabold", 800),
    ("semibold", 600),
    ("demibold", 600),
    ("thin", 100),
    ("light", 300),
    ("regular", 400),
    ("book", 400),
    ("medium", 500),
    ("black", 900),
    ("heavy", 900),
    ("bold", 700),
)
_WEIGHT_RE = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(token) for token, _ in _WEIGHT_TOKENS) + r")(?![a-z])",
    re.I,
)
_WEIGHT_LOOKUP = dict(_WEIGHT_TOKENS)


def gid(guid: dict[str, Any] | None) -> str | None:
    """Format a Figma GUID as ``sessionID:localID``."""
    if not guid or not isinstance(guid, dict):
        return None
    session = guid.get("sessionID")
    local = guid.get("localID")
    if session is None or local is None:
        return None
    return f"{session}:{local}"


def slug(text: str) -> str:
    return _SLUG_RE.sub("-", text.strip().lower()).strip("-") or "unnamed"


def ascii_name(text: str) -> str:
    return _ASCII_RE.sub("", text).strip() or text


def unique_slug(base: str, used: set[str]) -> str:
    """Return ``base`` or ``base-2``, ``base-3``, … and record it in ``used``."""
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def font_weight_from_name(
    style: str | None = None,
    fallback: int | None = None,
    family: str | None = None,
) -> int:
    """
    Map a Figma font style / family token to a CSS weight.

    Uses word-boundary matching so ``Highlight`` does not become weight 300.
    Family names like ``Gilroy-Bold`` are checked when style is empty.
    """
    for source in (style or "", family or ""):
        lowered = source.lower().replace(" ", "")
        match = _WEIGHT_RE.search(lowered)
        if match:
            return _WEIGHT_LOOKUP[match.group(1).lower()]
    return int(fallback) if fallback else 400


def first_solid_fill(fills: list[dict[str, Any]] | None) -> str | None:
    for fill in fills or []:
        if fill.get("type") == "solid" and fill.get("color"):
            return str(fill["color"])
    return None


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
