"""Write standalone SVG files for vector nodes that already have path data.

The screen tree stays the source. These files are extra assets, not a replacement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import orjson


def write_vector_svgs(directory: Path, *, limit: int = 400) -> list[dict[str, Any]]:
    """Write ``assets/svg/*.svg`` from screen trees. Returns the asset refs."""
    root = Path(directory)
    screens = _load(root / "screens.json", [])
    if not isinstance(screens, list):
        return []
    destination = root / "assets" / "svg"
    image_files = _image_file_map(root)
    written: list[dict[str, Any]] = []
    for screen in screens:
        if not isinstance(screen, dict) or not screen.get("tree"):
            continue
        tree = _load(root / str(screen["tree"]), None)
        if isinstance(tree, dict):
            _walk(tree, screen.get("id"), destination, written, limit, image_files)
        if len(written) >= limit:
            break
    return written


def svg_markup(node: dict[str, Any], *, image_files: dict[str, str] | None = None) -> str:
    """One SVG document for a node that has ``paths`` or ``strokePaths``."""
    width = _number(node.get("w"), 1)
    height = _number(node.get("h"), 1)
    defs: list[str] = []
    fill = _paint_ref(node.get("fills"), width, height, defs, image_files=image_files)
    stroke_paint = _stroke_paint(node)
    clip_id = _clip_def(node, width, height, defs)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}">'
    ]
    if defs:
        parts.append("<defs>" + "".join(defs) + "</defs>")
    body: list[str] = []
    for path in node.get("paths") or []:
        if not isinstance(path, dict) or not path.get("d"):
            continue
        rule = "evenodd" if path.get("rule") == "evenodd" else "nonzero"
        body.append(
            f'<path d="{escape(str(path["d"]))}" fill="{escape(fill)}" fill-rule="{rule}"/>'
        )
    stroke_attrs = _stroke_attrs(node, stroke_paint)
    for path in node.get("strokePaths") or []:
        if not isinstance(path, dict) or not path.get("d"):
            continue
        body.append(
            f'<path d="{escape(str(path["d"]))}" fill="none"{stroke_attrs}/>'
        )
    content = "".join(body)
    if clip_id:
        content = f'<g clip-path="url(#{clip_id})">{content}</g>'
    parts.append(_wrap_chrome(content, node))
    parts.append("</svg>")
    return "\n".join(parts)


def _stroke_paint(node: dict[str, Any]) -> str:
    stroke = node.get("stroke")
    if isinstance(stroke, dict):
        paints = stroke.get("paints")
        if isinstance(paints, list):
            for paint in paints:
                if isinstance(paint, dict) and paint.get("type") == "solid" and paint.get("color"):
                    return str(paint["color"])
        if stroke.get("color"):
            return str(stroke["color"])
    # Fall back to fill color when stroke paint is absent.
    fills = node.get("fills")
    if isinstance(fills, list):
        for fill in fills:
            if isinstance(fill, dict) and fill.get("type") == "solid" and fill.get("color"):
                return str(fill["color"])
    return "currentColor"


def _stroke_attrs(node: dict[str, Any], color: str) -> str:
    attrs = [f' stroke="{escape(color)}"']
    stroke = node.get("stroke") if isinstance(node.get("stroke"), dict) else {}
    weight = stroke.get("weight") if isinstance(stroke, dict) else None
    if weight is None:
        weight = node.get("strokeWeight")
    if weight is not None:
        try:
            attrs.append(f' stroke-width="{float(weight)}"')
        except (TypeError, ValueError):
            pass
    cap = stroke.get("cap") if isinstance(stroke, dict) else None
    if isinstance(cap, str) and cap:
        attrs.append(f' stroke-linecap="{escape(cap.lower())}"')
    join = stroke.get("join") if isinstance(stroke, dict) else None
    if isinstance(join, str) and join:
        attrs.append(f' stroke-linejoin="{escape(join.lower())}"')
    dash = stroke.get("dash") if isinstance(stroke, dict) else None
    if isinstance(dash, list) and dash:
        try:
            pattern = " ".join(str(float(item)) for item in dash)
            attrs.append(f' stroke-dasharray="{escape(pattern)}"')
        except (TypeError, ValueError):
            pass
    return "".join(attrs)


def _walk(
    node: dict[str, Any],
    screen_id: Any,
    destination: Path,
    written: list[dict[str, Any]],
    limit: int,
    image_files: dict[str, str],
) -> None:
    if len(written) >= limit:
        return
    paths = node.get("paths") or node.get("strokePaths")
    if node.get("id") and paths:
        markup = svg_markup(node, image_files=image_files)
        if "<path " in markup:
            destination.mkdir(parents=True, exist_ok=True)
            filename = str(node["id"]).replace(":", "_") + ".svg"
            (destination / filename).write_text(markup, encoding="utf-8")
            written.append(
                {
                    "assetId": node.get("id"),
                    "type": "svg",
                    "format": "image/svg+xml",
                    "localPath": f"svg/{filename}",
                    "screenId": screen_id,
                    "kind": "derived",
                    "source": "vector-paths",
                }
            )
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _walk(child, screen_id, destination, written, limit, image_files)


def _paint_ref(
    fills: Any,
    width: float,
    height: float,
    defs: list[str],
    *,
    image_files: dict[str, str] | None = None,
) -> str:
    if not isinstance(fills, list):
        return "currentColor"
    for fill in fills:
        if not isinstance(fill, dict):
            continue
        if fill.get("type") == "image" and fill.get("hash") and image_files:
            rel = image_files.get(str(fill["hash"]))
            if rel:
                pattern_id = f"p{len(defs)}"
                href = escape(f"../{rel}")
                defs.append(
                    f'<pattern id="{pattern_id}" patternContentUnits="objectBoundingBox" '
                    f'width="1" height="1"><image href="{href}" width="{width}" height="{height}" '
                    f'preserveAspectRatio="xMidYMid slice"/></pattern>'
                )
                return f"url(#{pattern_id})"
        if fill.get("type") == "solid" and fill.get("color"):
            return str(fill["color"])
        if fill.get("type") == "gradient" and fill.get("stops"):
            grad_id = f"g{len(defs)}"
            kind = str(fill.get("kind") or "")
            stops_xml = "".join(
                f'<stop offset="{_offset(stop.get("at"))}" stop-color="{escape(str(stop.get("color") or "currentColor"))}"/>'
                for stop in fill.get("stops") or []
                if isinstance(stop, dict)
            )
            if kind == "GRADIENT_LINEAR":
                angle = float(fill.get("angle") or 0)
                x1, y1, x2, y2 = _linear_endpoints(angle, width, height)
                defs.append(
                    f'<linearGradient id="{grad_id}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
                    f"{stops_xml}</linearGradient>"
                )
            elif kind in ("GRADIENT_RADIAL", "GRADIENT_DIAMOND"):
                cx = _number(fill.get("cx"), 0.5) * width
                cy = _number(fill.get("cy"), 0.5) * height
                defs.append(
                    f'<radialGradient id="{grad_id}" cx="{cx}" cy="{cy}" r="{max(width, height) / 2}">'
                    f"{stops_xml}</radialGradient>"
                )
            else:
                defs.append(f'<linearGradient id="{grad_id}">{stops_xml}</linearGradient>')
            return f"url(#{grad_id})"
    return "currentColor"


def _linear_endpoints(angle: float, width: float, height: float) -> tuple[str, str, str, str]:
    import math

    radians = math.radians(angle)
    dx = math.sin(radians)
    dy = -math.cos(radians)
    cx, cy = width / 2, height / 2
    half = max(width, height) / 2
    return (
        str(round(cx - dx * half, 3)),
        str(round(cy - dy * half, 3)),
        str(round(cx + dx * half, 3)),
        str(round(cy + dy * half, 3)),
    )


def _clip_def(
    node: dict[str, Any],
    width: float,
    height: float,
    defs: list[str],
) -> str | None:
    """Emit a clipPath when the node clips to bounds or is a mask layer."""
    if not (node.get("clip") or node.get("mask")):
        return None
    clip_id = f"c{len(defs)}"
    rx, ry = _corner_radii(node.get("radius"))
    if rx or ry:
        defs.append(
            f'<clipPath id="{clip_id}">'
            f'<rect x="0" y="0" width="{width}" height="{height}" '
            f'rx="{rx}" ry="{ry}"/>'
            f"</clipPath>"
        )
    else:
        defs.append(
            f'<clipPath id="{clip_id}">'
            f'<rect x="0" y="0" width="{width}" height="{height}"/>'
            f"</clipPath>"
        )
    return clip_id


def _corner_radii(radius: Any) -> tuple[float, float]:
    if isinstance(radius, (int, float)):
        value = max(0.0, float(radius))
        return value, value
    if isinstance(radius, list) and radius:
        try:
            values = [max(0.0, float(item or 0)) for item in radius[:4]]
        except (TypeError, ValueError):
            return 0.0, 0.0
        # SVG rect only has one rx/ry; use the largest authored corner.
        value = max(values) if values else 0.0
        return value, value
    return 0.0, 0.0


def _wrap_chrome(inner: str, node: dict[str, Any]) -> str:
    attrs: list[str] = []
    opacity = node.get("opacity")
    if opacity is not None:
        attrs.append(f'opacity="{escape(str(opacity))}"')
    blend = node.get("blend")
    if isinstance(blend, str) and blend:
        attrs.append(f'style="mix-blend-mode:{escape(blend)}"')
    if not attrs:
        return inner
    return f'<g {" ".join(attrs)}>{inner}</g>'


def _offset(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"
    if number <= 1:
        return f"{round(number * 100, 2)}%"
    return str(round(number, 3))


def _number(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _load(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return orjson.loads(path.read_bytes())


def _image_file_map(root: Path) -> dict[str, str]:
    payload = _load(root / "assets" / "manifest.json", [])
    rows = payload if isinstance(payload, list) else (payload.get("images") if isinstance(payload, dict) else [])
    if not isinstance(rows, list):
        return {}
    found: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        hash_name = row.get("hash")
        file_path = row.get("file")
        if hash_name and file_path:
            found[str(hash_name)] = str(file_path).lstrip("/")
    return found
