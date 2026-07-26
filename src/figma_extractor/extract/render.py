"""Rebuild screen images locally from ``design/`` trees — no Figma API, no AI.

Each screen tree becomes a static HTML document that reuses the extracted
tokens, bitmaps, and decoded vector outlines, then Chromium captures it as a
PNG.

Example::

    from figma_extractor.extract import render_screenshots

    render_screenshots(Path("out"), limit=5)
    # -> out/screenshot/<page>__<screen>.png
    # -> out/design/preview/<page>__<screen>.html
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

import orjson
from rich.console import Console

from figma_extractor.paths import design_dir
from figma_extractor.util import first_solid_fill, write_json

console = Console(stderr=True)

_SCALE_MODE = {
    "FILL": "cover",
    "FIT": "contain",
    "STRETCH": "100% 100%",
    "TILE": "auto",
}
_FONT_FALLBACK = 'Inter, "Liberation Sans", "DejaVu Sans", Arial, Helvetica, sans-serif'
# Chromium refuses to capture beyond this; taller screens are clipped.
_MAX_CAPTURE_HEIGHT = 30_000


def _asset_map(design: Path) -> dict[str, str]:
    manifest = design / "assets" / "manifest.json"
    if not manifest.is_file():
        return {}
    mapping: dict[str, str] = {}
    for row in orjson.loads(manifest.read_bytes()):
        if row.get("hash") and row.get("file"):
            mapping[str(row["hash"])] = str(row["file"])
    return mapping


def _first_solid(fills: list[dict[str, Any]] | None) -> str | None:
    return first_solid_fill(fills)


def _paint_color(fills: list[dict[str, Any]] | None) -> str | None:
    """Best single colour for a vector outline: solid first, else a gradient stop."""
    solid = _first_solid(fills)
    if solid:
        return solid
    for fill in fills or []:
        if fill.get("type") == "gradient":
            stops = fill.get("stops") or []
            if stops:
                return str(stops[0].get("color"))
    return None


def _paint_plan(node: dict[str, Any]) -> dict[str, Any]:
    """
    Decide whether a node paints through an inline SVG or a CSS box.

    Rectangles carry outline geometry too, so anything with an image fill (or no
    resolvable colour) is painted as a box instead of a black silhouette.
    """
    fills = node.get("fills") or []
    has_outline = bool(node.get("paths") or node.get("strokePaths"))
    has_image = any(fill.get("type") == "image" for fill in fills)
    color = _paint_color(fills)
    stroke_color = _first_solid((node.get("stroke") or {}).get("paints"))
    use_svg = has_outline and not has_image and bool(color or stroke_color)
    return {"use_svg": use_svg, "color": color or stroke_color}


def _gradient_css(fill: dict[str, Any]) -> str:
    stops = ", ".join(
        f"{stop['color']} {round(float(stop.get('at', 0)) * 100, 2)}%"
        for stop in fill.get("stops") or []
    )
    kind = str(fill.get("kind") or "")
    if kind in ("GRADIENT_RADIAL", "GRADIENT_DIAMOND"):
        cx = float(fill.get("cx") if fill.get("cx") is not None else 0.5)
        cy = float(fill.get("cy") if fill.get("cy") is not None else 0.5)
        return (
            f"radial-gradient(circle at {round(cx * 100, 2)}% {round(cy * 100, 2)}%, {stops})"
        )
    if kind == "GRADIENT_ANGULAR":
        return f"conic-gradient({stops})"
    angle = fill.get("angle")
    heading = f"{angle}deg" if angle is not None else "180deg"
    return f"linear-gradient({heading}, {stops})"


def _background(fills: list[dict[str, Any]] | None, assets: dict[str, str]) -> list[str]:
    """
    Stack Figma fills in paint order (index 0 = topmost).

    Multiple ``background-color`` / ``background-image`` declarations overwrite
    each other in CSS, so everything is composed into one layered ``background``.
    """
    fills = fills or []
    if not fills:
        return []
    if len(fills) == 1 and fills[0].get("type") == "solid" and fills[0].get("color"):
        return [f"background-color:{fills[0]['color']}"]

    layers: list[str] = []
    for fill in fills:
        kind = fill.get("type")
        if kind == "solid" and fill.get("color"):
            color = fill["color"]
            layers.append(f"linear-gradient(0deg, {color}, {color})")
        elif kind == "image":
            relative = assets.get(str(fill.get("hash") or ""))
            if not relative:
                continue
            size = _SCALE_MODE.get(str(fill.get("scaleMode")), "cover")
            repeat = "repeat" if fill.get("scaleMode") == "TILE" else "no-repeat"
            layers.append(f"url('../assets/{relative}') center / {size} {repeat}")
        elif kind == "gradient":
            layers.append(_gradient_css(fill))
    if not layers:
        return []
    return [f"background:{', '.join(layers)}"]


def _radius_css(radius: Any) -> str | None:
    if radius is None:
        return None
    if isinstance(radius, list):
        return "border-radius:" + " ".join(f"{value}px" for value in radius)
    return f"border-radius:{radius}px"


def _box_effects(stroke: dict[str, Any] | None, shadows: list[dict[str, Any]] | None) -> list[str]:
    """
    Compose strokes and shadows into one ``box-shadow`` list.

    Figma strokes must not suppress drop shadows (the previous renderer dropped
    shadows whenever a stroke was present, which flattened cards and pills).
    """
    layers: list[str] = []
    if stroke:
        color = _first_solid(stroke.get("paints"))
        if color:
            weight = stroke.get("weight") or 1
            # INSIDE strokes inset; CENTER/OUTSIDE paint outside the box edge.
            inset = "inset " if stroke.get("align") == "INSIDE" else ""
            layers.append(f"{inset}0 0 0 {weight}px {color}")
    filters: list[str] = []
    backdrops: list[str] = []
    for shadow in shadows or []:
        kind = shadow.get("type")
        if kind == "blur":
            filters.append(f"blur({shadow.get('blur', 0)}px)")
            continue
        if kind == "backdrop":
            backdrops.append(f"blur({shadow.get('blur', 0)}px)")
            continue
        inset = "inset " if kind == "inner" else ""
        layers.append(
            f"{inset}{shadow.get('x', 0)}px {shadow.get('y', 0)}px "
            f"{shadow.get('blur', 0)}px {shadow.get('spread', 0)}px {shadow.get('color')}"
        )
    styles: list[str] = []
    if layers:
        styles.append("box-shadow:" + ", ".join(layers))
    if filters:
        styles.append("filter:" + " ".join(filters))
    if backdrops:
        styles.append("backdrop-filter:" + " ".join(backdrops))
        styles.append("-webkit-backdrop-filter:" + " ".join(backdrops))
    return styles


def _text_css(text: dict[str, Any], fills: list[dict[str, Any]] | None) -> list[str]:
    styles = [f"color:{_paint_color(fills) or '#181818'}"]
    if text.get("singleLine"):
        styles.append("white-space:pre")
    else:
        styles.append("white-space:pre-wrap")
        styles.append("word-break:break-word")
    if text.get("size") is not None:
        styles.append(f"font-size:{text['size']}px")
    family = text.get("family")
    if family:
        styles.append(f"font-family:{json.dumps(family)}, {_FONT_FALLBACK}")
    styles.append(f"font-weight:{text.get('weight', 400)}")
    if text.get("italic"):
        styles.append("font-style:italic")
    if text.get("lineHeight"):
        styles.append(f"line-height:{text['lineHeight']}px")
    elif text.get("lineHeightRatio"):
        styles.append(f"line-height:{text['lineHeightRatio']}")
    spacing = text.get("letterSpacing") or {}
    if spacing.get("value"):
        unit = "em" if spacing.get("units") == "PERCENT" else "px"
        value = spacing["value"] / 100 if unit == "em" else spacing["value"]
        styles.append(f"letter-spacing:{round(value, 4)}{unit}")
    if text.get("alignH"):
        styles.append(f"text-align:{text['alignH']}")
    if text.get("underline"):
        styles.append("text-decoration:underline")
    text_case = text.get("textCase")
    if text_case == "UPPER":
        styles.append("text-transform:uppercase")
    elif text_case == "LOWER":
        styles.append("text-transform:lowercase")
    elif text_case == "TITLE":
        styles.append("text-transform:capitalize")
    elif text_case == "SMALL_CAPS":
        styles.append("font-variant-caps:small-caps")
    styles.append("display:flex")
    styles.append("flex-direction:column")
    styles.append(f"justify-content:{text.get('alignV', 'flex-start')}")
    return styles


def _svg(node: dict[str, Any], color: str) -> str:
    width = node.get("w") or 0
    height = node.get("h") or 0
    if not width or not height:
        return ""
    fill = color
    stroke = node.get("stroke") or {}
    stroke_color = _first_solid(stroke.get("paints"))
    stroke_weight = stroke.get("weight") or 0
    parts = [
        f'<svg width="100%" height="100%" viewBox="0 0 {width} {height}" '
        'preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg" '
        'style="display:block;overflow:visible">'
    ]
    for outline in node.get("paths") or []:
        attrs = [
            f'd="{html.escape(outline["d"], quote=True)}"',
            f'fill="{fill}"',
            f'fill-rule="{outline.get("rule", "nonzero")}"',
        ]
        # When Figma did not expand stroke geometry, stroke the fill path.
        if stroke_color and stroke_weight and not node.get("strokePaths"):
            attrs.append(f'stroke="{stroke_color}"')
            attrs.append(f'stroke-width="{stroke_weight}"')
            attrs.append('vector-effect="non-scaling-stroke"')
        parts.append(f"<path {' '.join(attrs)}/>")
    for outline in node.get("strokePaths") or []:
        paint = stroke_color or fill
        parts.append(
            f'<path d="{html.escape(outline["d"], quote=True)}" fill="{paint}" '
            f'fill-rule="{outline.get("rule", "nonzero")}"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _collect_paths(node: dict[str, Any], *, depth: int = 0) -> list[dict[str, str]]:
    """Gather SVG outlines from a mask node or its shallow descendants."""
    found: list[dict[str, str]] = []
    if node.get("paths"):
        found.extend(node["paths"])
    if found or depth >= 2:
        return found
    for child in node.get("children") or []:
        found.extend(_collect_paths(child, depth=depth + 1))
        if len(found) >= 8:
            break
    return found


def _mask_shortcut(mask: dict[str, Any]) -> dict[str, Any]:
    """Pick a cheap CSS clip when the mask is a circle or rounded rect."""
    width = float(mask.get("w") or 0)
    height = float(mask.get("h") or 0)
    radius = mask.get("radius")
    node_type = mask.get("type")
    luminance = str(mask.get("maskType") or "") == "LUMINANCE"
    if node_type == "ELLIPSE" and width > 0 and height > 0:
        return {"kind": "ellipse", "luminance": luminance}
    if isinstance(radius, (int, float)) and width > 0 and abs(float(radius) - min(width, height) / 2) < 0.75:
        return {"kind": "ellipse", "luminance": luminance}
    if radius:
        return {"kind": "radius", "radius": radius, "luminance": luminance}
    paths = _collect_paths(mask)
    if paths:
        return {"kind": "path", "paths": paths, "luminance": luminance}
    return {"kind": "box", "luminance": luminance}


def _offset_tree(node: dict[str, Any], dx: float, dy: float) -> dict[str, Any]:
    """Shallow-copy a node with its origin shifted (for mask-local coordinates)."""
    clone = dict(node)
    clone["x"] = float(node.get("x") or 0) - dx
    clone["y"] = float(node.get("y") or 0) - dy
    clone["absolute"] = True
    return clone


def _masked_html(
    mask: dict[str, Any],
    content: list[dict[str, Any]],
    assets: dict[str, str],
) -> str:
    """
    Clip ``content`` siblings to the mask shape.

    Figma paints the mask invisibly and clips every following sibling. We build a
    positioned wrapper at the mask's box and re-base child coordinates into it.
    """
    width = float(mask.get("w") or 0)
    height = float(mask.get("h") or 0)
    left = mask.get("x") or 0
    top = mask.get("y") or 0
    shortcut = _mask_shortcut(mask)
    styles = [
        "position:absolute",
        f"left:{left}px",
        f"top:{top}px",
        f"width:{width}px",
        f"height:{height}px",
        "overflow:hidden",
        "box-sizing:border-box",
    ]
    defs = ""
    uid = abs(hash((mask.get("id"), width, height))) % 10_000_000
    if shortcut["kind"] == "ellipse":
        # ``ellipse()`` respects non-1:1 aspect ratios; ``border-radius:50%``
        # alone was painting oversized white ovals on wide header masks.
        styles.append("clip-path:ellipse(50% 50% at 50% 50%)")
        styles.append("border-radius:50%")
    elif shortcut["kind"] == "radius":
        radius = _radius_css(shortcut["radius"])
        if radius:
            styles.append(radius)
    elif shortcut["kind"] == "path":
        clip_id = f"clip-{uid}"
        path_bits = []
        for outline in shortcut["paths"]:
            rule = outline.get("rule", "nonzero")
            path_bits.append(
                f'<path d="{html.escape(outline["d"], quote=True)}" '
                f'fill-rule="{rule}" clip-rule="{rule}"/>'
            )
        if shortcut.get("luminance"):
            mask_id = f"luma-{uid}"
            styles.append(f"mask:url(#{mask_id})")
            styles.append(f"-webkit-mask:url(#{mask_id})")
            defs = (
                f'<svg width="0" height="0" style="position:absolute">'
                f"<defs><mask id=\"{mask_id}\" maskUnits=\"userSpaceOnUse\" "
                f'x="0" y="0" width="{width}" height="{height}">'
                f'<rect width="{width}" height="{height}" fill="black"/>'
                f'<g fill="white">{"".join(path_bits)}</g></mask></defs></svg>'
            )
        else:
            styles.append(f"clip-path:url(#{clip_id})")
            defs = (
                f'<svg width="0" height="0" style="position:absolute">'
                f'<defs><clipPath id="{clip_id}" clipPathUnits="userSpaceOnUse">'
                f'{"".join(path_bits)}</clipPath></defs></svg>'
            )

    inner = [defs]
    for child in content:
        local = _offset_tree(child, float(left), float(top))
        inner.append(_node_html(local, assets, is_root=False, in_flex=False))
    name = html.escape(str(mask.get("name") or "mask"), quote=True)
    return f'<div data-mask="{name}" style="{";".join(styles)}">{"".join(inner)}</div>'


def _node_css(
    node: dict[str, Any],
    assets: dict[str, str],
    *,
    is_root: bool,
    in_flex: bool,
    use_svg: bool,
) -> str:
    styles = ["box-sizing:border-box"]
    width, height = node.get("w"), node.get("h")

    if is_root:
        styles.append("position:relative")
    elif in_flex and not node.get("absolute"):
        styles.append("position:relative")
        styles.append(f"flex:{node.get('grow', 0)} 0 auto")
    else:
        styles.append("position:absolute")
        styles.append(f"left:{node.get('x', 0)}px")
        styles.append(f"top:{node.get('y', 0)}px")

    if width is not None:
        # Zero-size Figma groups still host absolute children; forcing 0×0
        # collapses them. Let the children define the painted bounds instead.
        if not (width == 0 and height == 0 and not is_root):
            styles.append(f"width:{width}px")
    if height is not None:
        if not (width == 0 and height == 0 and not is_root):
            styles.append(f"height:{height}px")
    if width == 0 and height == 0 and not is_root:
        styles.append("width:0")
        styles.append("height:0")
        styles.append("overflow:visible")

    opacity = node.get("opacity")
    if opacity is not None:
        styles.append(f"opacity:{opacity}")
    blend = node.get("blend")
    if blend:
        styles.append(f"mix-blend-mode:{blend}")

    layout = node.get("layout")
    if layout:
        styles.append("display:flex")
        styles.append(f"flex-direction:{layout.get('dir', 'column')}")
        if layout.get("gap") is not None:
            styles.append(f"gap:{layout['gap']}px")
        pad = layout.get("pad")
        if pad:
            styles.append(f"padding:{pad[0]}px {pad[1]}px {pad[2]}px {pad[3]}px")
        if layout.get("justify"):
            styles.append(f"justify-content:{layout['justify']}")
        if layout.get("align"):
            styles.append(f"align-items:{layout['align']}")
        if layout.get("wrap"):
            styles.append("flex-wrap:wrap")

    radius = _radius_css(node.get("radius"))
    if radius:
        styles.append(radius)

    text = node.get("text")
    if text:
        styles.extend(_text_css(text, node.get("fills")))
    elif not use_svg:
        styles.extend(_background(node.get("fills"), assets))
        # Leaf image fills can carry paint opacity without fading children.
        fills = node.get("fills") or []
        if (
            not node.get("children")
            and not node.get("text")
            and len(fills) == 1
            and fills[0].get("type") == "image"
            and fills[0].get("opacity") is not None
            and float(fills[0]["opacity"]) < 0.999
            and node.get("opacity") is None
        ):
            styles.append(f"opacity:{fills[0]['opacity']}")

    if not use_svg:
        styles.extend(_box_effects(node.get("stroke"), node.get("shadows")))
    else:
        styles.extend(_box_effects(None, node.get("shadows")))

    # Clip frame contents, including the screen root when Figma clipped it.
    # Zero-size absolute hosts must stay overflow:visible or children vanish.
    if node.get("clip") and not (width == 0 and height == 0 and not is_root):
        styles.append("overflow:hidden")
    return ";".join(styles)


def _node_html(node: dict[str, Any], assets: dict[str, str], *, is_root: bool, in_flex: bool) -> str:
    # Mask shapes are invisible; they only clip following siblings.
    if node.get("mask") and not is_root:
        return ""

    plan = _paint_plan(node)
    style = _node_css(node, assets, is_root=is_root, in_flex=in_flex, use_svg=plan["use_svg"])
    inner: list[str] = []

    if plan["use_svg"]:
        inner.append(_svg(node, str(plan["color"])))
    text = node.get("text")
    if text and text.get("content"):
        inner.append(f"<span>{html.escape(str(text['content']))}</span>")

    child_in_flex = bool(node.get("layout"))
    children = node.get("children") or []
    index = 0
    while index < len(children):
        child = children[index]
        if child.get("mask"):
            end = index + 1
            while end < len(children) and not children[end].get("mask"):
                end += 1
            masked = children[index + 1 : end]
            if masked:
                inner.append(_masked_html(child, masked, assets))
            index = end
            continue
        inner.append(_node_html(child, assets, is_root=False, in_flex=child_in_flex))
        index += 1

    name = html.escape(str(node.get("name") or ""), quote=True)
    return f'<div data-name="{name}" style="{style}">{"".join(inner)}</div>'


def _screen_backdrop(tree: dict[str, Any]) -> str:
    """Backdrop for regions the screen frame does not paint itself."""
    return (
        _first_solid(tree.get("fills"))
        or str(tree.get("inheritedBackground") or "")
        or str(tree.get("pageBackground") or "")
        or "#ffffff"
    )


def tree_to_html(tree: dict[str, Any], assets: dict[str, str], *, tokens_href: str) -> str:
    width = tree.get("w") or 1440
    title = html.escape(str(tree.get("name") or "screen"))
    backdrop = _screen_backdrop(tree)
    body = _node_html(tree, assets, is_root=True, in_flex=False)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{title}</title>
<link rel="stylesheet" href="{html.escape(tokens_href, quote=True)}" />
<style>
  html, body {{ margin:0; padding:0; background:{backdrop}; }}
  body {{ width:{width}px; font-family:{_FONT_FALLBACK}; }}
  div, span {{ font-family:inherit; }}
  span {{ display:block; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def render_screenshots(
    out: Path,
    *,
    limit: int | None = None,
    scale: float = 1.0,
    page: str | None = None,
) -> dict[str, Any]:
    """
    Render ``design/trees/*.json`` into ``<out>/screenshot/*.png`` plus HTML
    previews in ``design/preview/``.

    ``limit`` renders only the first N screens; ``page`` filters by page name.
    """
    design = design_dir(out)
    screens_path = design / "screens.json"
    if not screens_path.is_file():
        raise FileNotFoundError(f"Missing {screens_path}")

    screens: list[dict[str, Any]] = orjson.loads(screens_path.read_bytes())
    assets = _asset_map(design)
    preview_dir = design / "preview"
    shot_dir = out / "screenshot"
    preview_dir.mkdir(parents=True, exist_ok=True)
    shot_dir.mkdir(parents=True, exist_ok=True)

    jobs: list[dict[str, Any]] = []
    for screen in screens:
        if page and str(screen.get("page") or "").lower() != page.lower():
            continue
        tree_rel, name = screen.get("tree"), screen.get("slug")
        if not tree_rel or not name:
            continue
        tree_path = design / str(tree_rel)
        if not tree_path.is_file():
            continue
        jobs.append(
            {
                "screen": screen,
                "tree_path": tree_path,
                "slug": name,
                "html_path": preview_dir / f"{name}.html",
                "png_path": shot_dir / f"{name}.png",
            }
        )
        if limit is not None and len(jobs) >= limit:
            break

    if not jobs:
        raise FileNotFoundError(
            "No screen trees found. Re-run extract so design/trees/ is generated."
        )

    for job in jobs:
        tree = orjson.loads(job["tree_path"].read_bytes())
        job["html_path"].write_text(
            tree_to_html(tree, assets, tokens_href="../tokens/tokens.css"),
            encoding="utf-8",
        )
        job["width"] = int(tree.get("w") or 1440)
        job["height"] = int(tree.get("h") or 900)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for local rendering. "
            "Install with: pip install playwright && playwright install chromium"
        ) from exc

    rendered = 0
    failed = 0
    manifest: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--force-color-profile=srgb"])
        # One context/page reused across screens; viewport resized per job.
        context = browser.new_context(device_scale_factor=scale)
        page_obj = context.new_page()
        try:
            for index, job in enumerate(jobs, start=1):
                screen = job["screen"]
                row: dict[str, Any] = {
                    "id": screen.get("id"),
                    "name": screen.get("name"),
                    "page": screen.get("page"),
                    "file": f"screenshot/{job['slug']}.png",
                    "preview": f"design/preview/{job['slug']}.html",
                    "width": job["width"],
                    "height": job["height"],
                }
                try:
                    # Viewport must cover the full clip region — Chromium truncates
                    # screenshots to the viewport when clip exceeds it (tall pages).
                    clip_width = max(min(job["width"], 8192), 1)
                    clip_height = max(min(job["height"], _MAX_CAPTURE_HEIGHT), 1)
                    page_obj.set_viewport_size({"width": clip_width, "height": clip_height})
                    page_obj.goto(job["html_path"].resolve().as_uri(), wait_until="load")
                    # Fonts/images finish after DOMContentLoaded on many kits.
                    page_obj.evaluate("() => document.fonts ? document.fonts.ready : null")
                    page_obj.wait_for_timeout(50)
                    page_obj.screenshot(
                        path=str(job["png_path"]),
                        clip={"x": 0, "y": 0, "width": clip_width, "height": clip_height},
                        type="png",
                    )
                    screen["localScreenshot"] = row["file"]
                    screen["preview"] = row["preview"]
                    screen.pop("localScreenshotError", None)
                    row["ok"] = True
                    row["bytes"] = job["png_path"].stat().st_size
                    rendered += 1
                except Exception as exc:  # noqa: BLE001 - report per-screen failures
                    failed += 1
                    screen.pop("localScreenshot", None)
                    screen["localScreenshotError"] = str(exc)
                    row["ok"] = False
                    row["error"] = str(exc)
                manifest.append(row)
                if index % 10 == 0 or index == len(jobs):
                    console.print(f"Render progress {index}/{len(jobs)}")
        finally:
            context.close()
            browser.close()

    write_json(screens_path, screens)
    summary = {
        "requested": len(jobs),
        "rendered": rendered,
        "failed": failed,
        "scale": scale,
        "output": str(shot_dir),
    }
    write_json(shot_dir / "manifest.json", {"screens": manifest, "summary": summary})
    console.print(
        f"[green]Local screenshots[/] {rendered}/{len(jobs)} → {shot_dir} ({failed} failed)"
    )
    return summary
