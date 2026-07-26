"""Build ``design/tokens``: CSS variables, colour styles, typography, effects."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from rich.console import Console

from figma_extractor.paths import design_dir, nodes_path, require_file
from figma_extractor.util import (
    gid,
    iter_ndjson,
    round_num,
    slug,
    to_css_color,
    write_json,
    write_text,
)

console = Console(stderr=True)


def _paint_to_css(paint: dict[str, Any] | None) -> str | None:
    if not paint or paint.get("visible") is False:
        return None
    ptype = paint.get("type")
    if ptype == "SOLID":
        return to_css_color(paint.get("color"), paint.get("opacity"))
    if isinstance(ptype, str) and ptype.startswith("GRADIENT"):
        stops = [
            f"{to_css_color(s.get('color'))} {round_num((s.get('position') or 0) * 100, 1)}%"
            for s in (paint.get("stops") or [])
            if to_css_color(s.get("color"))
        ]
        if not stops:
            return None
        kind = "radial-gradient(circle" if ptype == "GRADIENT_RADIAL" else "linear-gradient(180deg"
        return f"{kind}, {', '.join(stops)})"
    if ptype == "IMAGE":
        image = paint.get("image") or {}
        return f"image({image.get('hash')})" if image.get("hash") else None
    return None


def _line_height_css(lh: dict[str, Any] | None) -> Any:
    if not lh:
        return None
    units = lh.get("units")
    value = lh.get("value")
    if units == "PIXELS":
        return f"{round_num(value)}px"
    if units == "PERCENT":
        return round_num(value / 100, 3)
    if units == "RAW":
        return round_num(value, 3)
    return None


def _letter_spacing_css(ls: dict[str, Any] | None) -> str:
    if not ls or not ls.get("value"):
        return "0"
    if ls.get("units") == "PIXELS":
        return f"{round_num(ls['value'])}px"
    # Figma PERCENT letter-spacing is percent-of-em (100 → 1em).
    return f"{round_num(float(ls['value']) / 100.0, 4)}em"


def _effect_to_css(effect: dict[str, Any]) -> Any:
    if effect.get("visible") is False:
        return None
    offset = effect.get("offset") or {}
    x = round_num(offset.get("x") or 0)
    y = round_num(offset.get("y") or 0)
    blur = round_num(effect.get("radius") or 0)
    spread = round_num(effect.get("spread") or 0)
    color = to_css_color(effect.get("color"))
    etype = effect.get("type")
    if etype == "DROP_SHADOW":
        return f"{x}px {y}px {blur}px {spread}px {color}"
    if etype == "INNER_SHADOW":
        return f"inset {x}px {y}px {blur}px {spread}px {color}"
    if etype in ("FOREGROUND_BLUR", "LAYER_BLUR"):
        return {"filter": f"blur({blur}px)"}
    if etype == "BACKGROUND_BLUR":
        return {"backdropFilter": f"blur({blur}px)"}
    return None


def _resolve_variable_value(
    variable: dict[str, Any],
    mode_id: str | None,
    by_id: dict[str, dict[str, Any]],
    depth: int = 0,
) -> Any:
    entries = ((variable.get("variableDataValues") or {}).get("entries")) or []
    entry = next((e for e in entries if gid(e.get("modeID")) == mode_id), None) or (
        entries[0] if entries else None
    )
    if not entry:
        return None
    val = ((entry.get("variableData") or {}).get("value")) or {}
    if "colorValue" in val:
        return to_css_color(val["colorValue"])
    if "floatValue" in val:
        return val["floatValue"]
    if "boolValue" in val:
        return val["boolValue"]
    if "textValue" in val:
        return val["textValue"]
    alias = val.get("alias")
    if alias and depth < 8:
        target = by_id.get(gid(alias.get("guid")) or "")
        if target:
            return {
                "alias": target.get("name"),
                "value": _resolve_variable_value(target, mode_id, by_id, depth + 1),
            }
    return None


def build_tokens(out: Path) -> dict[str, Any]:
    nodes_file = require_file(
        nodes_path(out),
        "Decoded nodes not found. Run figma-extractor extract first.",
    )

    fill_styles: list[dict[str, Any]] = []
    text_styles: list[dict[str, Any]] = []
    effect_styles: list[dict[str, Any]] = []
    variables: list[dict[str, Any]] = []
    variable_sets: list[dict[str, Any]] = []

    for node in iter_ndjson(nodes_file):
        if node.get("isSoftDeleted") or node.get("isSoftDeletedStyle"):
            continue
        style_type = node.get("styleType")
        if style_type == "FILL":
            fill_styles.append(node)
        elif style_type == "TEXT":
            text_styles.append(node)
        elif style_type == "EFFECT":
            effect_styles.append(node)
        if node.get("type") == "VARIABLE":
            variables.append(node)
        elif node.get("type") == "VARIABLE_SET":
            variable_sets.append(node)

    # --- colors ---
    color_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    color_flat: dict[str, Any] = {}
    for style in fill_styles:
        paints = [
            p
            for p in (style.get("fillPaints") or [])
            if p.get("visible") is not False
        ]
        css_paints = [c for c in (_paint_to_css(p) for p in paints) if c]
        if not css_paints:
            continue
        parts = style.get("name", "").split("/")
        group = parts[0] if parts else "Default"
        entry: dict[str, Any] = {
            "name": style.get("name"),
            "key": style.get("key"),
            "id": gid(style.get("guid")),
            "value": css_paints[0],
        }
        if len(css_paints) > 1:
            entry["layers"] = css_paints
        if paints and paints[0].get("type") != "SOLID":
            entry["paintType"] = paints[0].get("type")
        color_groups[group].append(entry)
        color_flat[style.get("name", "")] = entry["value"]

    # --- variables ---
    by_id = {gid(v.get("guid")): v for v in variables if gid(v.get("guid"))}
    sets_out = [
        {
            "id": gid(s.get("guid")),
            "name": s.get("name"),
            "modes": [
                {"id": gid(m.get("id")), "name": m.get("name")}
                for m in (s.get("variableSetModes") or [])
            ],
        }
        for s in variable_sets
    ]
    vars_out = []
    for variable in variables:
        set_id = gid((variable.get("variableSetID") or {}).get("guid"))
        vset = next((s for s in sets_out if s["id"] == set_id), None)
        modes: dict[str, Any] = {}
        mode_list = (vset or {}).get("modes") or [{"id": None, "name": "default"}]
        for mode in mode_list:
            resolved = _resolve_variable_value(variable, mode.get("id"), by_id)
            if isinstance(resolved, dict) and "alias" in resolved:
                modes[mode["name"]] = resolved.get("value")
                modes[f"{mode['name']}__aliasOf"] = resolved.get("alias")
            else:
                modes[mode["name"]] = resolved
        vars_out.append(
            {
                "id": gid(variable.get("guid")),
                "name": variable.get("name"),
                "type": variable.get("variableResolvedType"),
                "set": (vset or {}).get("name"),
                "modes": modes,
            }
        )
    variables_payload = {"sets": sets_out, "variables": vars_out}

    # --- typography ---
    typography: dict[str, list[dict[str, Any]]] = defaultdict(list)
    fonts: dict[str, set[int]] = defaultdict(set)
    for style in text_styles:
        meta = (((style.get("derivedTextData") or {}).get("fontMetaData")) or [{}])[0]
        font_name = style.get("fontName") or {}
        entry = {
            "name": style.get("name"),
            "key": style.get("key"),
            "id": gid(style.get("guid")),
            "fontFamily": font_name.get("family"),
            "fontStyleName": font_name.get("style"),
            "fontWeight": meta.get("fontWeight"),
            "fontStyle": "italic" if meta.get("fontStyle") == "ITALIC" else "normal",
            "fontSize": round_num(style["fontSize"]) if style.get("fontSize") is not None else None,
            "lineHeight": _line_height_css(style.get("lineHeight")),
            "letterSpacing": _letter_spacing_css(style.get("letterSpacing")),
        }
        if style.get("textCase"):
            entry["textCase"] = style["textCase"]
        if style.get("textDecoration"):
            entry["textDecoration"] = style["textDecoration"]
        if style.get("paragraphSpacing"):
            entry["paragraphSpacing"] = round_num(style["paragraphSpacing"])
        group = style.get("name", "").split("/")[0] if "/" in style.get("name", "") else "Default"
        typography[group].append(entry)
        if entry["fontFamily"] and entry["fontWeight"]:
            fonts[entry["fontFamily"]].add(int(entry["fontWeight"]))

    # --- effects ---
    effects_out = []
    for style in effect_styles:
        parts = [_effect_to_css(e) for e in (style.get("effects") or [])]
        parts = [p for p in parts if p]
        shadows = [p for p in parts if isinstance(p, str)]
        filters = [p for p in parts if isinstance(p, dict)]
        entry = {
            "name": (style.get("name") or "").strip(),
            "key": style.get("key"),
            "id": gid(style.get("guid")),
            "raw": [
                {
                    "type": e.get("type"),
                    "x": round_num((e.get("offset") or {}).get("x") or 0),
                    "y": round_num((e.get("offset") or {}).get("y") or 0),
                    "radius": round_num(e.get("radius") or 0),
                    "spread": round_num(e.get("spread") or 0),
                    "color": to_css_color(e.get("color")),
                }
                for e in (style.get("effects") or [])
            ],
        }
        if shadows:
            entry["boxShadow"] = ", ".join(shadows)
        if filters:
            entry["filters"] = filters
        effects_out.append(entry)

    css, conflicts = _build_css(color_groups, variables_payload, typography, effects_out)

    tokens_dir = design_dir(out) / "tokens"
    write_json(tokens_dir / "color-styles.json", dict(color_groups))
    write_json(tokens_dir / "color-styles.flat.json", color_flat)
    write_json(tokens_dir / "color-styles.conflicts.json", conflicts)
    write_json(tokens_dir / "variables.json", variables_payload)
    write_json(tokens_dir / "typography.json", dict(typography))
    write_json(tokens_dir / "effects.json", effects_out)
    write_json(
        tokens_dir / "fonts.json",
        [
            {"family": family, "weights": sorted(weights)}
            for family, weights in sorted(fonts.items())
        ],
    )
    write_text(tokens_dir / "tokens.css", css)

    summary = {
        "colorStyles": sum(len(v) for v in color_groups.values()),
        "colorGroups": len(color_groups),
        "variables": len(vars_out),
        "variableSets": len(sets_out),
        "textStyles": sum(len(v) for v in typography.values()),
        "effectStyles": len(effects_out),
        "fonts": list(fonts),
        "conflicts": len(conflicts),
    }
    console.print(
        f"[green]Tokens[/] {summary['colorStyles']} colors · "
        f"{summary['variables']} vars · {summary['textStyles']} text · "
        f"{summary['effectStyles']} effects → {tokens_dir}"
    )
    return summary


def _build_css(
    color_groups: dict[str, list[dict[str, Any]]],
    variables: dict[str, Any],
    typography: dict[str, list[dict[str, Any]]],
    effects: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    lines = [
        "/* Generated by figma-extractor */",
        ":root {",
    ]
    seen_leaves: set[str] = set()
    dark_lines: list[str] = []

    for variable in variables.get("variables") or []:
        if variable.get("type") != "COLOR":
            continue
        segments = (variable.get("name") or "").split("/")
        leaf = slug(segments[-1])
        if leaf in seen_leaves:
            continue
        seen_leaves.add(leaf)
        modes = variable.get("modes") or {}
        light = modes.get("Light", modes.get("Mode 1", modes.get("default")))
        if light is None:
            continue
        lines.append(f"  --{leaf}: {light};")
        dark = modes.get("Dark")
        if dark is not None and dark != light:
            dark_lines.append(f"  --{leaf}: {dark};")

    # Prefer the most common value when the same style name appears more than once.
    style_values: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for entries in color_groups.values():
        for entry in entries:
            value = entry.get("value")
            if not isinstance(value, str) or value.startswith("image("):
                continue
            style_values[f"--style-{slug(entry['name'])}"][value] += 1

    conflicts: dict[str, list[dict[str, Any]]] = {}
    lines.append("")
    lines.append("  /* Color styles */")
    for name, tally in style_values.items():
        ranked = sorted(tally.items(), key=lambda kv: kv[1], reverse=True)
        lines.append(f"  {name}: {ranked[0][0]};")
        if len(ranked) > 1:
            conflicts[name] = [{"value": v, "count": c} for v, c in ranked]

    shadow_names: set[str] = set()
    lines.append("")
    lines.append("  /* Effect styles */")
    for effect in effects:
        box = effect.get("boxShadow")
        if not box:
            continue
        name = f"--shadow-{slug(effect['name'])}"
        if name in shadow_names:
            continue
        shadow_names.add(name)
        lines.append(f"  {name}: {box};")

    lines.append("}")

    if dark_lines:
        lines.append("")
        lines.append('[data-theme="dark"], .dark {')
        lines.extend(dark_lines)
        lines.append("}")

    lines.append("")
    lines.append("/* Typography styles */")
    text_classes: set[str] = set()
    for entries in typography.values():
        for text in entries:
            cls = f".text-{slug(text['name'])}"
            if cls in text_classes:
                continue
            text_classes.add(cls)
            lines.append(f"{cls} {{")
            if text.get("fontFamily"):
                lines.append(f'  font-family: "{text["fontFamily"]}", sans-serif;')
            if text.get("fontWeight"):
                lines.append(f"  font-weight: {text['fontWeight']};")
            if text.get("fontStyle") == "italic":
                lines.append("  font-style: italic;")
            if text.get("fontSize") is not None:
                lines.append(f"  font-size: {text['fontSize']}px;")
            if text.get("lineHeight") is not None:
                lines.append(f"  line-height: {text['lineHeight']};")
            if text.get("letterSpacing") and text["letterSpacing"] != "0":
                lines.append(f"  letter-spacing: {text['letterSpacing']};")
            if text.get("textCase") == "UPPER":
                lines.append("  text-transform: uppercase;")
            elif text.get("textCase") == "LOWER":
                lines.append("  text-transform: lowercase;")
            elif text.get("textCase") == "TITLE":
                lines.append("  text-transform: capitalize;")
            if text.get("textDecoration") == "UNDERLINE":
                lines.append("  text-decoration: underline;")
            elif text.get("textDecoration") == "STRIKETHROUGH":
                lines.append("  text-decoration: line-through;")
            lines.append("}")

    return "\n".join(lines) + "\n", conflicts
