"""Build per-screen layout trees into ``trees/`` for LLM / UI rebuild.

Each tree is a self-contained description of one screen: auto-layout, paints,
strokes, shadows, text styling, and decoded vector outlines. Component
instances are expanded from their master symbol so screens contain real
content instead of empty placeholder boxes.

Example::

    from figma_extractor.extract import build_screen_trees

    build_screen_trees(Path("out"))
    # -> out/trees/<page>__<screen>.json
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import orjson
from rich.console import Console

from figma_extractor.fig import PathStore
from figma_extractor.extract.split import split_screen_boards
from figma_extractor.paths import design_dir, extracted_dir, nodes_path, require_file
from figma_extractor.util import (
    ascii_name,
    font_weight_from_name,
    gid,
    iter_ndjson,
    round_num,
    slug,
    to_css_color,
    unique_slug,
    write_json,
)

console = Console(stderr=True)

_JUSTIFY = {
    "MIN": "flex-start",
    "CENTER": "center",
    "MAX": "flex-end",
    "SPACE_BETWEEN": "space-between",
    "SPACE_EVENLY": "space-evenly",
    "SPACE_AROUND": "space-around",
}
_ALIGN = {
    "MIN": "flex-start",
    "CENTER": "center",
    "MAX": "flex-end",
    "BASELINE": "baseline",
    "STRETCH": "stretch",
}
_TEXT_ALIGN = {"LEFT": "left", "CENTER": "center", "RIGHT": "right", "JUSTIFIED": "justify"}
_VERTICAL_ALIGN = {"TOP": "flex-start", "CENTER": "center", "BOTTOM": "flex-end"}
_GEOMETRY_TYPES = {
    "VECTOR",
    "ELLIPSE",
    "REGULAR_POLYGON",
    "STAR",
    "BOOLEAN_OPERATION",
    "LINE",
    "ROUNDED_RECTANGLE",
    "RECTANGLE",
}
_SKIP_TYPES = {"DOCUMENT", "CANVAS", "SLICE"}
# Bookkeeping fields on instance overrides that are not node properties.
_OVERRIDE_META = {
    "guidPath",
    "overrideLevel",
    "pluginData",
    "proportionsConstrained",
    "fontVersion",
    "textUserLayoutVersion",
    "textBidiVersion",
}
# Expanded instances can multiply node counts; keep one screen bounded.
_NODE_BUDGET = 60_000
_MAX_DEPTH = 60


def _weight_from_style(style: str, fallback: int | None, family: str | None = None) -> int:
    return font_weight_from_name(style, fallback, family)


def _paint(paint: dict[str, Any]) -> dict[str, Any] | None:
    if paint.get("visible") is False:
        return None
    kind = paint.get("type")
    opacity = paint.get("opacity", 1)
    if kind in ("SOLID", "COLOR"):
        color = to_css_color(paint.get("color"), opacity)
        return {"type": "solid", "color": color} if color else None
    if kind == "IMAGE":
        hash_name = (paint.get("image") or {}).get("hash")
        if not hash_name:
            return None
        return {
            "type": "image",
            "hash": hash_name,
            "scaleMode": paint.get("imageScaleMode") or "FILL",
            "opacity": round_num(opacity, 3),
        }
    if kind and kind.startswith("GRADIENT"):
        stops = []
        for stop in paint.get("stops") or paint.get("gradientStops") or []:
            color = to_css_color(stop.get("color"), opacity)
            if color:
                stops.append({"at": round_num(stop.get("position", 0), 3), "color": color})
        if not stops:
            return None
        summary: dict[str, Any] = {"type": "gradient", "kind": kind, "stops": stops}
        angle = _gradient_angle(paint.get("transform"))
        if angle is not None and kind == "GRADIENT_LINEAR":
            summary["angle"] = angle
        center = _gradient_center(paint.get("transform"))
        if center is not None and kind in ("GRADIENT_RADIAL", "GRADIENT_DIAMOND"):
            summary["cx"] = center[0]
            summary["cy"] = center[1]
        return summary
    return None


def _gradient_angle(transform: dict[str, Any] | None) -> float | None:
    """
    CSS angle for a Figma gradient transform.

    Figma stores the gradient axis in the matrix' first column (object space, y
    down). CSS measures clockwise from "to top", hence ``atan2(dx, -dy)``.
    """
    if not transform:
        return None
    dx = float(transform.get("m00") or 0.0)
    dy = float(transform.get("m10") or 0.0)
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    angle = math.degrees(math.atan2(dx, -dy))
    return round_num(angle % 360.0, 1)


def _gradient_center(transform: dict[str, Any] | None) -> tuple[float, float] | None:
    """Normalized radial center (0–1) from the gradient transform translation."""
    if not transform:
        return None
    cx = float(transform.get("m02") or 0.0)
    cy = float(transform.get("m12") or 0.0)
    return (round_num(cx, 3), round_num(cy, 3))


def _paints(paints: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    result = []
    for paint in paints or []:
        summary = _paint(paint)
        if summary:
            result.append(summary)
    return result


def _shadows(effects: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for effect in effects or []:
        if effect.get("visible") is False:
            continue
        kind = effect.get("type")
        color = to_css_color(effect.get("color"), 1)
        offset = effect.get("offset") or {}
        if kind in ("DROP_SHADOW", "INNER_SHADOW") and color:
            result.append(
                {
                    "type": "inner" if kind == "INNER_SHADOW" else "drop",
                    "x": round_num(offset.get("x", 0), 2),
                    "y": round_num(offset.get("y", 0), 2),
                    "blur": round_num(effect.get("radius", 0), 2),
                    "spread": round_num(effect.get("spread", 0), 2),
                    "color": color,
                }
            )
        elif kind == "BACKGROUND_BLUR":
            result.append(
                {
                    "type": "backdrop",
                    "blur": round_num(min(float(effect.get("radius") or 0), 40.0), 2),
                }
            )
        elif kind in ("LAYER_BLUR", "FOREGROUND_BLUR"):
            radius = float(effect.get("radius") or 0)
            # Huge “foreground blurs” with a colour are soft drop-shadows in this
            # file format; treating them as filter:blur() would erase the layer.
            if color and (offset.get("x") or offset.get("y") or radius >= 40):
                result.append(
                    {
                        "type": "drop",
                        "x": round_num(offset.get("x", 0), 2),
                        "y": round_num(offset.get("y", 0), 2),
                        "blur": round_num(min(radius, 80.0), 2),
                        "spread": round_num(effect.get("spread", 0), 2),
                        "color": color,
                    }
                )
            elif radius > 0:
                result.append({"type": "blur", "blur": round_num(min(radius, 24.0), 2)})
    return result


_BLEND = {
    "MULTIPLY": "multiply",
    "SCREEN": "screen",
    "OVERLAY": "overlay",
    "DARKEN": "darken",
    "LIGHTEN": "lighten",
    "COLOR_DODGE": "color-dodge",
    "COLOR_BURN": "color-burn",
    "HARD_LIGHT": "hard-light",
    "SOFT_LIGHT": "soft-light",
    "DIFFERENCE": "difference",
    "EXCLUSION": "exclusion",
    "HUE": "hue",
    "SATURATION": "saturation",
    "COLOR": "color",
    "LUMINOSITY": "luminosity",
    "LINEAR_BURN": "plus-darker",
    "LINEAR_DODGE": "plus-lighter",
}

def _radius(raw: dict[str, Any]) -> Any:
    corners = [
        raw.get("rectangleTopLeftCornerRadius"),
        raw.get("rectangleTopRightCornerRadius"),
        raw.get("rectangleBottomRightCornerRadius"),
        raw.get("rectangleBottomLeftCornerRadius"),
    ]
    if any(value is not None for value in corners):
        rounded = [round_num(value or 0, 2) for value in corners]
        if len(set(rounded)) == 1:
            return rounded[0] or None
        return rounded
    radius = raw.get("cornerRadius")
    return round_num(radius, 2) if radius else None


def _layout(raw: dict[str, Any]) -> dict[str, Any] | None:
    mode = raw.get("stackMode")
    if mode not in ("HORIZONTAL", "VERTICAL"):
        return None
    layout: dict[str, Any] = {"dir": "row" if mode == "HORIZONTAL" else "column"}
    if raw.get("stackSpacing") is not None:
        layout["gap"] = round_num(raw["stackSpacing"], 2)
    padding = [
        raw.get("stackVerticalPadding"),
        raw.get("stackPaddingRight"),
        raw.get("stackPaddingBottom"),
        raw.get("stackHorizontalPadding"),
    ]
    if any(value is not None for value in padding):
        layout["pad"] = [round_num(value or 0, 2) for value in padding]
    justify = _JUSTIFY.get(str(raw.get("stackPrimaryAlignItems") or ""))
    if justify:
        layout["justify"] = justify
    align = _ALIGN.get(str(raw.get("stackCounterAlignItems") or ""))
    if align:
        layout["align"] = align
    if raw.get("stackWrap") == "WRAP":
        layout["wrap"] = True
    return layout


def _text(raw: dict[str, Any]) -> dict[str, Any] | None:
    data = raw.get("textData") or {}
    characters = data.get("characters")
    if characters is None:
        return None
    font = raw.get("fontName") or {}
    derived = raw.get("derivedTextData") or {}
    meta = (derived.get("fontMetaData") or [{}])[0]
    style = str(font.get("style") or "")
    family = font.get("family")
    text: dict[str, Any] = {
        "content": characters,
        "weight": _weight_from_style(style, meta.get("fontWeight"), family if isinstance(family, str) else None),
    }
    if family:
        text["family"] = family
    if raw.get("fontSize") is not None:
        text["size"] = round_num(raw["fontSize"], 2)
    if "italic" in style.lower() or meta.get("fontStyle") == "ITALIC":
        text["italic"] = True
    line_height = raw.get("lineHeight") or {}
    if line_height.get("value"):
        if line_height.get("units") == "PIXELS":
            text["lineHeight"] = round_num(line_height["value"], 2)
        elif line_height.get("units") == "PERCENT":
            text["lineHeightRatio"] = round_num(line_height["value"] / 100.0, 3)
    letter = raw.get("letterSpacing") or {}
    if letter.get("value"):
        text["letterSpacing"] = {
            "value": round_num(letter["value"], 3),
            "units": letter.get("units", "PIXELS"),
        }
    align_h = _TEXT_ALIGN.get(str(raw.get("textAlignHorizontal") or ""))
    if align_h:
        text["alignH"] = align_h
    align_v = _VERTICAL_ALIGN.get(str(raw.get("textAlignVertical") or ""))
    if align_v:
        text["alignV"] = align_v
    if raw.get("textDecoration") == "UNDERLINE":
        text["underline"] = True
    text_case = raw.get("textCase") or raw.get("fontCase")
    if text_case in {"UPPER", "LOWER", "TITLE", "SMALL_CAPS", "ORIGINAL"}:
        text["textCase"] = text_case
    # Figma already laid the text out; a single-line run must not re-wrap when
    # the local font metrics differ slightly from the design's.
    baselines = derived.get("baselines")
    if isinstance(baselines, list) and len(baselines) == 1:
        text["singleLine"] = True
    return text


class _TreeBuilder:
    """Turn the decoded node stream into renderable per-screen trees."""

    def __init__(self, nodes_file: Path, paths: PathStore | None) -> None:
        self.paths = paths
        self.raw: dict[str, dict[str, Any]] = {}
        self.children: dict[str, list[str]] = defaultdict(list)
        self.canvas_background: dict[str, str] = {}

        for raw in iter_ndjson(nodes_file):
            node_id = gid(raw.get("guid"))
            if not node_id:
                continue
            if raw.get("type") == "CANVAS" and raw.get("backgroundEnabled") is not False:
                background = to_css_color(
                    raw.get("backgroundColor"), raw.get("backgroundOpacity", 1)
                )
                if background:
                    self.canvas_background[node_id] = background
            if raw.get("type") in _SKIP_TYPES:
                continue
            self.raw[node_id] = raw
            parent = raw.get("parentIndex") or {}
            parent_id = gid(parent.get("guid"))
            if parent_id:
                self.children[parent_id].append(node_id)

        for kids in self.children.values():
            kids.sort(key=lambda cid: (self.raw[cid].get("parentIndex") or {}).get("position") or "")

    def node(self, node_id: str, raw: dict[str, Any]) -> dict[str, Any]:
        size = raw.get("size") or {}
        transform = raw.get("transform") or {}
        node_type = raw.get("type")
        node: dict[str, Any] = {
            "id": node_id,
            "type": node_type,
            "name": raw.get("name") or "",
            "w": round_num(size.get("x"), 2),
            "h": round_num(size.get("y"), 2),
            "x": round_num(transform.get("m02", 0), 2),
            "y": round_num(transform.get("m12", 0), 2),
        }
        opacity = raw.get("opacity", 1)
        if opacity is not None and opacity != 1:
            node["opacity"] = round_num(opacity, 3)
        blend = _BLEND.get(str(raw.get("blendMode") or ""))
        if blend:
            node["blend"] = blend

        fills = _paints(raw.get("fillPaints"))
        if fills:
            node["fills"] = fills
        strokes = _paints(raw.get("strokePaints"))
        if strokes:
            node["stroke"] = {
                "paints": strokes,
                "weight": round_num(raw.get("strokeWeight", 1), 2),
                "align": raw.get("strokeAlign") or "INSIDE",
            }
        shadows = _shadows(raw.get("effects"))
        if shadows:
            node["shadows"] = shadows

        radius = _radius(raw)
        if radius:
            node["radius"] = radius

        layout = _layout(raw)
        if layout:
            node["layout"] = layout
        if raw.get("stackChildPrimaryGrow"):
            node["grow"] = round_num(raw["stackChildPrimaryGrow"], 2)
        if raw.get("stackPositioning") == "ABSOLUTE":
            node["absolute"] = True
        if raw.get("stackPrimarySizing") == "RESIZE_TO_FIT_WITH_IMPLICIT_SIZE":
            node["hugMain"] = True
        if raw.get("stackCounterSizing") == "RESIZE_TO_FIT_WITH_IMPLICIT_SIZE":
            node["hugCross"] = True
        # Frames mask their children unless the mask is explicitly disabled.
        if node_type in ("FRAME", "SECTION") and not raw.get("frameMaskDisabled"):
            node["clip"] = True
        if raw.get("mask"):
            node["mask"] = True
            if raw.get("maskType"):
                node["maskType"] = raw["maskType"]
        if node_type == "BOOLEAN_OPERATION" and raw.get("booleanOperation"):
            node["booleanOp"] = raw["booleanOperation"]

        text = _text(raw)
        if text:
            node["text"] = text

        if self.paths and node_type in _GEOMETRY_TYPES:
            outlines = self.paths.outlines(raw.get("fillGeometry"))
            if outlines:
                node["paths"] = outlines
            stroke_outlines = self.paths.outlines(raw.get("strokeGeometry"))
            if stroke_outlines:
                node["strokePaths"] = stroke_outlines
        return node

    @staticmethod
    def _override_map(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """
        Per-descendant overrides for one instance, keyed by target node id.

        ``symbolOverrides`` holds authored changes (text, paints, radius,
        visibility) and ``derivedSymbolData`` holds Figma's resolved layout and
        vector geometry. Resolved data wins because it already accounts for the
        authored values.
        """
        overrides: dict[str, dict[str, Any]] = {}
        symbol_data = raw.get("symbolData") or {}
        for source in (symbol_data.get("symbolOverrides"), raw.get("derivedSymbolData")):
            for entry in source or []:
                guids = (entry.get("guidPath") or {}).get("guids") or []
                if not guids:
                    continue
                target = gid(guids[-1])
                if not target:
                    continue
                fields = {
                    key: value
                    for key, value in entry.items()
                    if key not in _OVERRIDE_META and value not in (None, [])
                }
                if fields:
                    overrides.setdefault(target, {}).update(fields)
        return overrides

    def build(self, root_id: str) -> tuple[dict[str, Any] | None, int]:
        self._budget = _NODE_BUDGET
        tree = self._walk(root_id, depth=0, overrides={}, symbol_stack=(), force_visible=True)
        return tree, _NODE_BUDGET - self._budget

    def _walk(
        self,
        node_id: str,
        *,
        depth: int,
        overrides: dict[str, dict[str, Any]],
        symbol_stack: tuple[str, ...],
        force_visible: bool = False,
    ) -> dict[str, Any] | None:
        base = self.raw.get(node_id)
        if base is None or self._budget <= 0:
            return None
        override = overrides.get(node_id)
        raw = {**base, **override} if override else base
        if not force_visible and raw.get("visible") is False:
            return None

        self._budget -= 1
        node = self.node(node_id, raw)

        if depth >= _MAX_DEPTH:
            return node

        node_type = raw.get("type")
        # Boolean ops ship a resolved outline; drawing the operand children too
        # produces oversized silhouettes on top of the correct shape.
        if node_type == "BOOLEAN_OPERATION" and node.get("paths"):
            return node

        if node_type == "INSTANCE":
            symbol_id = gid(
                raw.get("overriddenSymbolID") or (raw.get("symbolData") or {}).get("symbolID")
            )
            if symbol_id and symbol_id in self.raw and symbol_id not in symbol_stack:
                merged = {target: dict(fields) for target, fields in overrides.items()}
                for target, fields in self._override_map(raw).items():
                    merged.setdefault(target, {}).update(fields)
                master = self._walk(
                    symbol_id,
                    depth=depth + 1,
                    overrides=merged,
                    symbol_stack=symbol_stack + (symbol_id,),
                    force_visible=True,
                )
                if master:
                    # Keep the instance box, adopt the master's content + chrome.
                    node["instanceOf"] = symbol_id
                    node["layout"] = master.get("layout") or node.get("layout")
                    if master.get("children"):
                        node["children"] = master["children"]
                    for key in (
                        "fills",
                        "paths",
                        "strokePaths",
                        "radius",
                        "stroke",
                        "text",
                        "shadows",
                        "clip",
                        "blend",
                        "opacity",
                        "mask",
                        "maskType",
                    ):
                        if not node.get(key) and master.get(key) is not None:
                            node[key] = master[key]
                return node

        children = []
        for child_id in self.children.get(node_id, []):
            child = self._walk(
                child_id,
                depth=depth + 1,
                overrides=overrides,
                symbol_stack=symbol_stack,
            )
            if child:
                children.append(child)
        if children:
            node["children"] = children
        return node


def build_screen_trees(out: Path) -> dict[str, Any]:
    """
    Write one layout JSON tree per screen under ``trees/`` and record
    ``tree`` / ``slug`` on every entry in ``screens.json``.
    """
    nodes_file = require_file(
        nodes_path(out),
        "Decoded nodes not found. Run figma-extractor extract first.",
    )
    design = design_dir(out)
    screens_path = design / "screens.json"
    if not screens_path.is_file():
        raise FileNotFoundError(f"Missing {screens_path}; run structure extract first.")

    screens: list[dict[str, Any]] = orjson.loads(screens_path.read_bytes())
    paths = PathStore.load(extracted_dir(out))
    if paths is None:
        console.print("[yellow]No blobs.bin found; vector outlines will be skipped[/]")

    builder = _TreeBuilder(nodes_file, paths)
    trees_dir = design / "trees"
    trees_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    total_nodes = 0
    used_names: set[str] = set()
    for screen in screens:
        node_id = str(screen.get("id") or "")
        if node_id not in builder.raw:
            continue
        page_slug = slug(ascii_name(str(screen.get("page") or "page")))
        name_slug = slug(str(screen.get("name") or node_id))
        candidate = unique_slug(f"{page_slug}__{name_slug}", used_names)

        tree, node_count = builder.build(node_id)
        if not tree:
            continue
        # Frames without their own fill show the Figma page canvas behind them.
        page_background = builder.canvas_background.get(str(screen.get("pageId") or ""))
        if page_background:
            tree["pageBackground"] = page_background
        write_json(trees_dir / f"{candidate}.json", tree)
        screen["tree"] = f"trees/{candidate}.json"
        screen["slug"] = candidate
        screen["renderNodes"] = node_count
        written += 1
        total_nodes += node_count

    write_json(screens_path, screens)
    summary = {"screens": len(screens), "trees": written, "nodes": total_nodes}
    write_json(trees_dir / "index.json", {"screens": screens, "summary": summary})
    console.print(
        f"[green]Trees[/] {written} screens · {total_nodes:,} render nodes → {trees_dir}"
    )

    # Tall kit boards (Auth - Branded, My Account - Pages, …) become one screen
    # per nested UI so each screenshot is a single interface.
    summary["split"] = split_screen_boards(out)
    return summary
