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

JUSTIFY = {
    "MIN": "flex-start",
    "CENTER": "center",
    "MAX": "flex-end",
    "SPACE_BETWEEN": "space-between",
    "SPACE_EVENLY": "space-evenly",
    "SPACE_AROUND": "space-around",
}

# Raw Figma field names → stable styleRef field. Prefer inherit* then styleIdFor*.
STYLE_REF_SOURCES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fill", ("inheritFillStyleID", "styleIdForFill", "fillStyleId")),
    ("stroke", ("inheritFillStyleIDForStroke", "styleIdForStrokeFill", "strokeStyleId")),
    ("text", ("inheritTextStyleID", "styleIdForText", "textStyleId")),
    ("effect", ("inheritEffectStyleID", "styleIdForEffect", "effectStyleId")),
    ("background", ("inheritFillStyleIDForBackground",)),
    ("grid", ("inheritGridStyleID", "styleIdForGrid")),
)


def style_id_value(value: Any) -> str | None:
    """Normalize a raw style id (guid, nested guid, or library assetRef key)."""
    if value is None or value == "" or value == 0 or value == {}:
        return None
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return None
    if "sessionID" in value and "localID" in value:
        return gid(value)
    nested = value.get("guid")
    if isinstance(nested, dict):
        return gid(nested)
    asset = value.get("assetRef")
    if isinstance(asset, dict) and asset.get("key"):
        return str(asset["key"])
    return None


def collect_style_refs(raw: dict[str, Any]) -> list[dict[str, str]]:
    """Emit ``styleRefs`` as ``{field, id}`` from inherit*/styleIdFor* raw keys."""
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for field, keys in STYLE_REF_SOURCES:
        for key in keys:
            if key not in raw:
                continue
            ref_id = style_id_value(raw.get(key))
            if ref_id and field not in seen:
                refs.append({"field": field, "id": ref_id})
                seen.add(field)
                break
    return refs


def collect_variable_refs(raw: dict[str, Any]) -> list[dict[str, str]] | None:
    """Emit ``variableRefs`` from ``variableConsumptionMap`` entry aliases."""
    variable_map = raw.get("variableConsumptionMap")
    if not isinstance(variable_map, dict) or not variable_map:
        return None
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    entries = variable_map.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            field = str(entry.get("variableField") or "")
            data = entry.get("variableData")
            value = data.get("value") if isinstance(data, dict) else None
            var_id = _variable_id_from_value(value)
            if not var_id:
                continue
            key = (var_id, field)
            if key in seen:
                continue
            seen.add(key)
            item: dict[str, str] = {"id": var_id}
            if field:
                item["field"] = field
            refs.append(item)
    else:
        # Older maps: field name → guid / alias payload.
        for field, payload in variable_map.items():
            var_id = _variable_id_from_value(payload)
            if not var_id:
                continue
            key = (var_id, str(field))
            if key in seen:
                continue
            seen.add(key)
            refs.append({"id": var_id, "field": str(field)})

    refs.sort(key=lambda item: (item.get("field") or "", item["id"]))
    return refs or None


def _variable_id_from_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return None
    direct = style_id_value(value)
    if direct:
        return direct
    alias = value.get("alias")
    if isinstance(alias, dict):
        return style_id_value(alias.get("guid") if isinstance(alias.get("guid"), dict) else alias)
    nested = value.get("guid")
    if isinstance(nested, dict):
        return gid(nested)
    return None
ALIGN = {
    "MIN": "flex-start",
    "CENTER": "center",
    "MAX": "flex-end",
    "BASELINE": "baseline",
    "STRETCH": "stretch",
}
TEXT_ALIGN = {"LEFT": "left", "CENTER": "center", "RIGHT": "right", "JUSTIFIED": "justify"}
VERTICAL_ALIGN = {"TOP": "flex-start", "CENTER": "center", "BOTTOM": "flex-end"}
GEOMETRY_TYPES = {
    "VECTOR",
    "ELLIPSE",
    "REGULAR_POLYGON",
    "STAR",
    "BOOLEAN_OPERATION",
    "LINE",
    "ROUNDED_RECTANGLE",
    "RECTANGLE",
}
SKIP_TYPES = {"DOCUMENT", "CANVAS", "SLICE"}
# Bookkeeping fields on instance overrides that are not node properties.
OVERRIDE_META = {
    "guidPath",
    "overrideLevel",
    "pluginData",
    "proportionsConstrained",
    "fontVersion",
    "textUserLayoutVersion",
    "textBidiVersion",
}
# Expanded instances can multiply node counts; keep one screen bounded.
NODE_BUDGET = 60_000
MAX_DEPTH = 60


def weight_from_style(style: str, fallback: int | None, family: str | None = None) -> int:
    return font_weight_from_name(style, fallback, family)


def paint(paint: dict[str, Any]) -> dict[str, Any] | None:
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
        angle = gradient_angle(paint.get("transform"))
        if angle is not None and kind == "GRADIENT_LINEAR":
            summary["angle"] = angle
        center = gradient_center(paint.get("transform"))
        if center is not None and kind in ("GRADIENT_RADIAL", "GRADIENT_DIAMOND"):
            summary["cx"] = center[0]
            summary["cy"] = center[1]
        return summary
    return None


def gradient_angle(transform: dict[str, Any] | None) -> float | None:
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


def gradient_center(transform: dict[str, Any] | None) -> tuple[float, float] | None:
    """Normalized radial center (0–1) from the gradient transform translation."""
    if not transform:
        return None
    cx = float(transform.get("m02") or 0.0)
    cy = float(transform.get("m12") or 0.0)
    return (round_num(cx, 3), round_num(cy, 3))


def paints(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    result = []
    for item in items or []:
        summary = paint(item)
        if summary:
            result.append(summary)
    return result


def shadows(effects: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
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
            original = float(effect.get("radius") or 0)
            clamped = min(original, 40.0)
            entry: dict[str, Any] = {
                "type": "backdrop",
                "blur": round_num(clamped, 2),
            }
            if original > 40.0:
                entry["clamped"] = True
                entry["originalRadius"] = round_num(original, 2)
            result.append(entry)
        elif kind in ("LAYER_BLUR", "FOREGROUND_BLUR"):
            radius = float(effect.get("radius") or 0)
            # Huge “foreground blurs” with a colour are soft drop-shadows in this
            # file format; treating them as filter:blur() would erase the layer.
            if color and (offset.get("x") or offset.get("y") or radius >= 40):
                clamped = min(radius, 80.0)
                entry = {
                    "type": "drop",
                    "x": round_num(offset.get("x", 0), 2),
                    "y": round_num(offset.get("y", 0), 2),
                    "blur": round_num(clamped, 2),
                    "spread": round_num(effect.get("spread", 0), 2),
                    "color": color,
                }
                if radius > 80.0:
                    entry["clamped"] = True
                    entry["originalRadius"] = round_num(radius, 2)
                result.append(entry)
            elif radius > 0:
                clamped = min(radius, 24.0)
                entry = {"type": "blur", "blur": round_num(clamped, 2)}
                if radius > 24.0:
                    entry["clamped"] = True
                    entry["originalRadius"] = round_num(radius, 2)
                result.append(entry)
    return result


BLEND = {
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


def radius(raw: dict[str, Any]) -> Any:
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


def layout(raw: dict[str, Any]) -> dict[str, Any] | None:
    mode = raw.get("stackMode")
    if mode not in ("HORIZONTAL", "VERTICAL"):
        return None
    layout: dict[str, Any] = {"dir": "row" if mode == "HORIZONTAL" else "column"}
    if raw.get("stackSpacing") is not None:
        layout["gap"] = round_num(raw["stackSpacing"], 2)
    top = raw.get("stackVerticalPadding")
    right = raw.get("stackPaddingRight")
    bottom = raw.get("stackPaddingBottom")
    left = raw.get("stackHorizontalPadding")
    padding = [top, right, bottom, left]
    if any(value is not None for value in padding):
        layout["pad"] = [round_num(value or 0, 2) for value in padding]
        layout["padding"] = {
            "top": round_num(top or 0, 2),
            "right": round_num(right or 0, 2),
            "bottom": round_num(bottom or 0, 2),
            "left": round_num(left or 0, 2),
        }
    justify = JUSTIFY.get(str(raw.get("stackPrimaryAlignItems") or ""))
    if justify:
        layout["justify"] = justify
    align = ALIGN.get(str(raw.get("stackCounterAlignItems") or ""))
    if align:
        layout["align"] = align
    if raw.get("stackWrap") == "WRAP":
        layout["wrap"] = True
    return layout


def constraints(raw: dict[str, Any]) -> dict[str, str] | None:
    horizontal = raw.get("horizontalConstraint")
    vertical = raw.get("verticalConstraint")
    if not horizontal and not vertical:
        return None
    result: dict[str, str] = {}
    if isinstance(horizontal, str) and horizontal:
        result["horizontal"] = horizontal
    if isinstance(vertical, str) and vertical:
        result["vertical"] = vertical
    return result or None


def layout_sizing(*, hug_main: bool, hug_cross: bool, grow: Any) -> dict[str, str] | None:
    sizing: dict[str, str] = {}
    if hug_main:
        sizing["main"] = "hug"
    elif grow:
        sizing["main"] = "grow"
    if hug_cross:
        sizing["cross"] = "hug"
    return sizing or None


def transform_extras(transform: dict[str, Any]) -> dict[str, Any] | None:
    """Store rotation/scale when the matrix is not a pure translation."""
    m00 = float(transform.get("m00") or 1.0)
    m01 = float(transform.get("m01") or 0.0)
    m10 = float(transform.get("m10") or 0.0)
    m11 = float(transform.get("m11") or 1.0)
    if abs(m00 - 1.0) < 1e-9 and abs(m11 - 1.0) < 1e-9 and abs(m01) < 1e-9 and abs(m10) < 1e-9:
        return None

    extras: dict[str, Any] = {
        "matrix": {
            "m00": round_num(m00, 5),
            "m01": round_num(m01, 5),
            "m10": round_num(m10, 5),
            "m11": round_num(m11, 5),
        }
    }
    scale_x = math.hypot(m00, m10)
    scale_y = math.hypot(m01, m11)
    if abs(scale_x - 1.0) > 1e-6 or abs(scale_y - 1.0) > 1e-6:
        extras["scale"] = {"x": round_num(scale_x, 4), "y": round_num(scale_y, 4)}
    angle = math.degrees(math.atan2(m10, m00))
    if abs(angle) > 1e-3:
        extras["rotation"] = round_num(angle, 3)
    return extras


def stroke_details(raw: dict[str, Any], paints_list: list[dict[str, Any]]) -> dict[str, Any]:
    stroke: dict[str, Any] = {
        "paints": paints_list,
        "weight": round_num(raw.get("strokeWeight", 1), 2),
        "align": raw.get("strokeAlign") or "INSIDE",
    }
    cap = raw.get("strokeCap")
    if isinstance(cap, str) and cap and cap != "NONE":
        stroke["cap"] = cap
    join = raw.get("strokeJoin")
    if isinstance(join, str) and join:
        stroke["join"] = join
    dash = raw.get("dashPattern")
    if isinstance(dash, list) and dash:
        stroke["dash"] = [round_num(item, 2) for item in dash if item is not None]
    sides = {
        "top": raw.get("strokeTopWeight"),
        "right": raw.get("strokeRightWeight"),
        "bottom": raw.get("strokeBottomWeight"),
        "left": raw.get("strokeLeftWeight"),
    }
    if any(value is not None for value in sides.values()):
        stroke["weights"] = {
            side: round_num(value if value is not None else stroke["weight"], 2)
            for side, value in sides.items()
        }
    return stroke


def text(raw: dict[str, Any]) -> dict[str, Any] | None:
    data = raw.get("textData") or {}
    characters = data.get("characters")
    if characters is None:
        return None
    font = raw.get("fontName") or {}
    derived = raw.get("derivedTextData") or {}
    meta = (derived.get("fontMetaData") or [{}])[0]
    style = str(font.get("style") or "")
    family = font.get("family")
    meta_weight = meta.get("fontWeight")
    text: dict[str, Any] = {
        "content": characters,
        "weight": weight_from_style(style, meta_weight, family if isinstance(family, str) else None),
        "weightSource": "font-metadata" if meta_weight is not None else "font-style-name",
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
    align_h = TEXT_ALIGN.get(str(raw.get("textAlignHorizontal") or ""))
    if align_h:
        text["alignH"] = align_h
    align_v = VERTICAL_ALIGN.get(str(raw.get("textAlignVertical") or ""))
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


class TreeBuilder:
    """Turn the decoded node stream into renderable per-screen trees."""

    def __init__(self, nodes_file: Path, paths: PathStore | None) -> None:
        self.paths = paths
        self.raw: dict[str, dict[str, Any]] = {}
        self.children: dict[str, list[str]] = defaultdict(list)
        self.canvas_background: dict[str, str] = {}
        # Node budget is per-screen; reset by build() before each walk.
        self.budget = NODE_BUDGET
        self.truncated_events: list[dict[str, Any]] = []
        self.unsupported_events: list[dict[str, Any]] = []

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
            if raw.get("type") in SKIP_TYPES:
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
        blend = BLEND.get(str(raw.get("blendMode") or ""))
        if blend:
            node["blend"] = blend

        fills = paints(raw.get("fillPaints"))
        if fills:
            node["fills"] = fills
        stroke_paints = paints(raw.get("strokePaints"))
        if stroke_paints:
            node["stroke"] = stroke_details(raw, stroke_paints)
        shadow_items = shadows(raw.get("effects"))
        if shadow_items:
            node["shadows"] = shadow_items

        corner_radius = radius(raw)
        if corner_radius:
            node["radius"] = corner_radius

        layout_box = layout(raw)
        if layout_box:
            node["layout"] = layout_box
        grow = None
        if raw.get("stackChildPrimaryGrow"):
            grow = round_num(raw["stackChildPrimaryGrow"], 2)
            node["grow"] = grow
        if raw.get("stackPositioning") == "ABSOLUTE":
            node["absolute"] = True
        hug_main = raw.get("stackPrimarySizing") == "RESIZE_TO_FIT_WITH_IMPLICIT_SIZE"
        hug_cross = raw.get("stackCounterSizing") == "RESIZE_TO_FIT_WITH_IMPLICIT_SIZE"
        if hug_main:
            node["hugMain"] = True
        if hug_cross:
            node["hugCross"] = True
        sizing = layout_sizing(hug_main=hug_main, hug_cross=hug_cross, grow=grow)
        if sizing:
            if "layout" not in node:
                node["layout"] = {}
            node["layout"]["sizing"] = sizing
        constraint_box = constraints(raw)
        if constraint_box:
            node["constraints"] = constraint_box
        extras = transform_extras(transform)
        if extras:
            node["transform"] = extras
        style_refs = collect_style_refs(raw)
        if style_refs:
            node["styleRefs"] = style_refs
        variable_refs = collect_variable_refs(raw)
        if variable_refs:
            node["variableRefs"] = variable_refs
        # Frames mask their children unless the mask is explicitly disabled.
        if node_type in ("FRAME", "SECTION") and not raw.get("frameMaskDisabled"):
            node["clip"] = True
        if raw.get("mask"):
            node["mask"] = True
            if raw.get("maskType"):
                node["maskType"] = raw["maskType"]
        if node_type == "BOOLEAN_OPERATION" and raw.get("booleanOperation"):
            node["booleanOp"] = raw["booleanOperation"]

        text_style = text(raw)
        if text_style:
            node["text"] = text_style

        if self.paths and node_type in GEOMETRY_TYPES:
            fill_geometry = raw.get("fillGeometry")
            outlines = self.paths.outlines(fill_geometry)
            if outlines:
                node["paths"] = outlines
            elif fill_geometry:
                self.unsupported_events.append(
                    {
                        "nodeId": node_id,
                        "type": node_type,
                        "field": "fillGeometry",
                        "reason": "outline-compile-failed",
                    }
                )
            stroke_geometry = raw.get("strokeGeometry")
            stroke_outlines = self.paths.outlines(stroke_geometry)
            if stroke_outlines:
                node["strokePaths"] = stroke_outlines
            elif stroke_geometry:
                self.unsupported_events.append(
                    {
                        "nodeId": node_id,
                        "type": node_type,
                        "field": "strokeGeometry",
                        "reason": "outline-compile-failed",
                    }
                )
        return node

    @staticmethod
    def override_map(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
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
                    if key not in OVERRIDE_META and value not in (None, [])
                }
                if fields:
                    overrides.setdefault(target, {}).update(fields)
        return overrides

    def build(self, root_id: str, *, budget: int | None = None) -> tuple[dict[str, Any] | None, int]:
        initial_budget = NODE_BUDGET if budget is None else max(0, int(budget))
        self.budget = initial_budget
        self._initial_budget = initial_budget
        self.truncated_events = []
        self.unsupported_events = []
        tree = self.walk(root_id, depth=0, overrides={}, symbol_stack=(), force_visible=True)
        if tree:
            if self.truncated_events:
                tree["truncated"] = True
            from figma_extractor.extract.semantic import attach_semantic

            attach_semantic(tree)
        return tree, initial_budget - self.budget

    def walk(
        self,
        node_id: str,
        *,
        depth: int,
        overrides: dict[str, dict[str, Any]],
        symbol_stack: tuple[str, ...],
        force_visible: bool = False,
    ) -> dict[str, Any] | None:
        base = self.raw.get(node_id)
        if base is None:
            return None
        if self.budget <= 0:
            self.truncated_events.append(
                {
                    "nodeId": node_id,
                    "reason": "node-budget",
                    "budget": getattr(self, "_initial_budget", NODE_BUDGET),
                }
            )
            return None
        override = overrides.get(node_id)
        raw = {**base, **override} if override else base
        if not force_visible and raw.get("visible") is False:
            return None

        self.budget -= 1
        node = self.node(node_id, raw)

        if depth >= MAX_DEPTH:
            self.truncated_events.append(
                {"nodeId": node_id, "reason": "max-depth", "depth": depth}
            )
            node["truncated"] = True
            return node

        node_type = raw.get("type")
        # Boolean ops ship a resolved outline; drawing the operand children too
        # produces oversized silhouettes on top of the correct shape.
        if node_type == "BOOLEAN_OPERATION" and node.get("paths"):
            node["childrenOmitted"] = "resolved-outline"
            return node

        if node_type == "INSTANCE":
            symbol_id = gid(
                raw.get("overriddenSymbolID") or (raw.get("symbolData") or {}).get("symbolID")
            )
            local_overrides = self.override_map(raw)
            if local_overrides:
                node["overrides"] = [
                    {"targetId": target, "keys": sorted(fields)}
                    for target, fields in sorted(local_overrides.items())
                ]
            assignments = raw.get("componentPropAssignments")
            if isinstance(assignments, list) and assignments:
                node["componentPropAssignments"] = assignments
            prop_refs = raw.get("componentPropRefs")
            if isinstance(prop_refs, list) and prop_refs:
                node["componentPropRefs"] = prop_refs
            if symbol_id and symbol_id in self.raw and symbol_id not in symbol_stack:
                merged = {target: dict(fields) for target, fields in overrides.items()}
                for target, fields in local_overrides.items():
                    merged.setdefault(target, {}).update(fields)
                master = self.walk(
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
            child = self.walk(
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

    builder = TreeBuilder(nodes_file, paths)
    trees_dir = design / "trees"
    trees_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    total_nodes = 0
    used_names: set[str] = set()
    truncated_records: list[dict[str, Any]] = []
    unsupported_records: list[dict[str, Any]] = []
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
        from figma_extractor.extract.semantic import screen_semantic

        semantic = screen_semantic(screen, tree)
        if semantic:
            screen["semantic"] = semantic
        if builder.truncated_events:
            truncated_records.append(
                {
                    "screenId": node_id,
                    "tree": f"trees/{candidate}.json",
                    "nodesWritten": node_count,
                    "events": list(builder.truncated_events),
                }
            )
        unsupported_records.extend(
            {**event, "screenId": node_id} for event in builder.unsupported_events
        )
        write_json(trees_dir / f"{candidate}.json", tree)
        screen["tree"] = f"trees/{candidate}.json"
        screen["slug"] = candidate
        screen["renderNodes"] = node_count
        written += 1
        total_nodes += node_count

    write_json(screens_path, screens)
    summary = {"screens": len(screens), "trees": written, "nodes": total_nodes}
    write_json(
        trees_dir / "index.json",
        {"schemaVersion": 2, "screens": screens, "summary": summary},
    )
    write_tree_diagnostics(design, truncated_records, unsupported_records)
    write_layout_diagnostics(design, builder)
    console.print(
        f"[green]Trees[/] {written} screens · {total_nodes:,} render nodes → {trees_dir}"
    )

    # Tall kit boards (Auth - Branded, My Account - Pages, …) become one screen
    # per nested UI so each tree holds exactly one interface.
    summary["split"] = split_screen_boards(out)
    attach_image_files_to_trees(design)
    return summary


def attach_image_files_to_trees(design: Path) -> None:
    """Join image paint hashes to manifest ``file`` paths after trees are written."""
    manifest = orjson.loads((design / "assets" / "manifest.json").read_bytes()) if (design / "assets" / "manifest.json").is_file() else []
    if not isinstance(manifest, list) or not manifest:
        return
    by_hash = {
        str(row.get("hash")): str(row.get("file"))
        for row in manifest
        if isinstance(row, dict)
        and row.get("hash")
        and row.get("file")
        and row.get("kind") not in {"vector", "svg"}
    }
    if not by_hash:
        return
    trees_dir = design / "trees"
    if not trees_dir.is_dir():
        return
    for path in trees_dir.glob("*.json"):
        if path.name == "index.json":
            continue
        tree = orjson.loads(path.read_bytes())
        if isinstance(tree, dict) and _attach_image_files(tree, by_hash):
            write_json(path, tree)


def _attach_image_files(node: dict[str, Any], by_hash: dict[str, str]) -> bool:
    changed = False
    for fill in node.get("fills") or []:
        if not isinstance(fill, dict) or fill.get("type") != "image":
            continue
        hash_name = fill.get("hash")
        file_path = by_hash.get(str(hash_name)) if hash_name else None
        if file_path and fill.get("file") != file_path:
            fill["file"] = file_path
            changed = True
    for child in node.get("children") or []:
        if isinstance(child, dict) and _attach_image_files(child, by_hash):
            changed = True
    return changed


def write_tree_diagnostics(
    design: Path,
    truncated: list[dict[str, Any]],
    unsupported: list[dict[str, Any]],
) -> None:
    diagnostics = design / "diagnostics"
    write_json(diagnostics / "truncated.json", truncated)
    write_json(diagnostics / "unsupported.json", unsupported)
    missing = load_missing_assets(design)
    write_json(diagnostics / "assets.json", missing)


def load_missing_assets(design: Path) -> list[dict[str, Any]]:
    path = design / "assets" / "missing-hashes.json"
    if not path.is_file():
        return []
    payload = orjson.loads(path.read_bytes())
    if isinstance(payload, list):
        return [{"hash": item, "reason": "missing-bytes"} for item in payload if item]
    if isinstance(payload, dict):
        rows = payload.get("missing") or payload.get("hashes") or []
        if isinstance(rows, list):
            return [
                {"hash": item.get("hash") if isinstance(item, dict) else item, "reason": "missing-bytes"}
                for item in rows
                if item
            ]
    return []


def write_layout_diagnostics(design: Path, builder: TreeBuilder) -> None:
    """Count constraint and auto-layout facts present on the raw node stream."""
    horizontal: dict[str, int] = defaultdict(int)
    vertical: dict[str, int] = defaultdict(int)
    counts: dict[str, Any] = {
        "nodes": 0,
        "horizontalConstraint": 0,
        "verticalConstraint": 0,
        "stackWrap": 0,
        "stackChildPrimaryGrow": 0,
        "absolute": 0,
        "horizontalConstraintValues": {},
        "verticalConstraintValues": {},
        "breakpoints": None,
        "note": (
            "No breakpoint table is written. Responsive facts come only from "
            "constraints, wrap, grow, hug, and absolute positioning in the file."
        ),
    }
    for raw in builder.raw.values():
        counts["nodes"] += 1
        h = raw.get("horizontalConstraint")
        v = raw.get("verticalConstraint")
        if h:
            counts["horizontalConstraint"] += 1
            horizontal[str(h)] += 1
        if v:
            counts["verticalConstraint"] += 1
            vertical[str(v)] += 1
        if raw.get("stackWrap") == "WRAP":
            counts["stackWrap"] += 1
        if raw.get("stackChildPrimaryGrow"):
            counts["stackChildPrimaryGrow"] += 1
        if raw.get("stackPositioning") == "ABSOLUTE":
            counts["absolute"] += 1
    counts["horizontalConstraintValues"] = dict(sorted(horizontal.items()))
    counts["verticalConstraintValues"] = dict(sorted(vertical.items()))
    write_json(design / "diagnostics" / "layout.json", counts)
