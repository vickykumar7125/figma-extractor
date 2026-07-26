"""Split multi-UI board frames into one screen (and PNG) per UI.

Metronic-style kits stack many full pages inside one tall board, e.g.
``Auth - Branded`` contains ``Sign In``, ``Sign Up``, ``2FA``, … This module
detects those boards from the render trees and replaces each board entry with
its individual UI children so ``screenshot/`` gets one image per UI.

Example::

    from figma_extractor.extract import split_screen_boards

    split_screen_boards(Path("out"))
    # screens.json now lists Sign In / Sign Up / … instead of one tall board
"""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path
from typing import Any

import orjson
from rich.console import Console

from figma_extractor.paths import design_dir
from figma_extractor.util import ascii_name, first_solid_fill, slug, unique_slug, write_json

console = Console(stderr=True)

_FRAME_TYPES = {"FRAME", "INSTANCE", "SYMBOL", "COMPONENT", "SECTION"}
_GENERIC_NAMES = {
    "item",
    "frame",
    "group",
    "container",
    "col",
    "row",
    "column",
    "bg",
    "background",
    "content",
    "wrapper",
    "inner",
    "outer",
    "mask",
    "clip",
    "rectangle",
    "vector",
}
_GENERIC_RE = re.compile(r"^(frame|group|rectangle|vector|ellipse)\s*\d*$", re.I)
_SECTION_NAMES = {
    "header",
    "footer",
    "fotter",
    "hero",
    "banner",
    "nav",
    "navbar",
    "sidebar",
    "side bar",
    "content",
    "body",
    "main",
    "section",
    "cta",
    "testimonial",
    "services",
    "service",
    "portfolio",
    "contact",
    "blog",
    "team",
    "about",
    "pricing",
    "faq",
    "clients",
    "client",
    "partners",
    "process",
    "gallery",
    "join",
    "message",
    "awards",
    "video",
    "tab",
    "tabs",
    "divider",
    "info",
    "post",
    "menu",
    "comment",
    "leave",
    "popular",
    "address",
    "more",
    "img",
    "image",
    "text",
    "box",
    "countries",
    "country",
    "visa",
    "coaching",
    "success story",
    "story",
    "newsletter",
    "subscribe",
    "features",
    "feature",
    "stats",
    "statistic",
    "map",
    "form",
}
_MIN_UI_W = 280.0
_MIN_UI_H = 400.0
_MAX_DEPTH = 3


def _meaningful_name(name: str | None) -> bool:
    text = (name or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered in _GENERIC_NAMES:
        return False
    return _GENERIC_RE.match(text) is None


def _title_from_tree(node: dict[str, Any]) -> str | None:
    """Pull a label from a short header strip (Metronic board pattern)."""
    for child in node.get("children") or []:
        text = (child.get("text") or {}).get("content")
        if child.get("type") == "TEXT" and text:
            return str(text).strip()[:80] or None
        height = child.get("h") or 0
        if height and height <= 140:
            for nested in child.get("children") or []:
                nested_text = (nested.get("text") or {}).get("content")
                if nested.get("type") == "TEXT" and nested_text:
                    return str(nested_text).strip()[:80] or None
    return None


def _child_label(node: dict[str, Any], index: int) -> str:
    name = str(node.get("name") or "").strip()
    if _meaningful_name(name):
        return name
    titled = _title_from_tree(node)
    if titled:
        return titled
    return f"screen-{index + 1}"


def _ui_children(tree: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for child in tree.get("children") or []:
        if child.get("type") not in _FRAME_TYPES:
            continue
        width = float(child.get("w") or 0)
        height = float(child.get("h") or 0)
        if width >= _MIN_UI_W and height >= _MIN_UI_H:
            result.append(child)
    return result


def _is_section_name(name: str | None) -> bool:
    text = re.sub(r"[\W_]+", " ", (name or "").strip().lower()).strip()
    if not text:
        return False
    if text in _SECTION_NAMES:
        return True
    # "01 Home" / "Home Section" style landing blocks still count as sections
    # when the meaningful token is a known section word.
    tokens = [token for token in text.split() if token and not token.isdigit()]
    return bool(tokens) and all(token in _SECTION_NAMES for token in tokens)


def _height_cv(heights: list[float]) -> float:
    if not heights:
        return 0.0
    mean = sum(heights) / len(heights)
    if mean <= 0:
        return 0.0
    var = sum((height - mean) ** 2 for height in heights) / len(heights)
    return (var**0.5) / mean


def _looks_like_landing_sections(parent: dict[str, Any], kids: list[dict[str, Any]]) -> bool:
    """
    True when children are stacked page sections (Header/Hero/Footer), not peer UIs.

    Marketing kits put one long page in a frame; admin kits put many full pages on
    a board (sometimes in a grid). Splitting the former destroys the screens we
    need to compare; the latter must still split.
    """
    if len(kids) < 2:
        return False

    parent_w = float(parent.get("w") or 0)
    parent_h = float(parent.get("h") or 0)

    # Named chrome sections (Header/Footer/Post/…) on single-page-width frames.
    # Skip this on mega artboards (Modernize Applications is ~12k wide) where
    # peer screens may also be named Blog/Contact/etc.
    if parent_w < 2800:
        sectionish = sum(1 for child in kids if _is_section_name(str(child.get("name") or "")))
        if sectionish >= max(2, int(len(kids) * 0.5)):
            return True

    # Landing sections are full-bleed strips. Grid boards place peer UIs in
    # columns — those must not be treated as sections.
    stacked = [
        child
        for child in kids
        if parent_w <= 0 or float(child.get("w") or 0) >= parent_w * 0.75
    ]
    if len(stacked) < 2:
        return False

    sectionish_stacked = sum(
        1 for child in stacked if _is_section_name(str(child.get("name") or ""))
    )
    if sectionish_stacked >= max(2, int(len(stacked) * 0.5)):
        return True

    heights = [float(child.get("h") or 0) for child in stacked]
    total_h = sum(heights)
    # Contiguous sections usually cover most of the parent height.
    if parent_h > 0 and total_h >= parent_h * 0.7:
        # Peer UI boards also sum high — require heterogeneous heights.
        if _height_cv(heights) >= 0.28:
            return True
    # Wide + very tall with a few full-bleed chrome sections.
    if parent_w >= 1280 and parent_h >= 3000 and len(stacked) <= 8 and sectionish_stacked >= 1:
        return True
    return False


def _is_grid_of_peers(parent: dict[str, Any], candidates: list[dict[str, Any]]) -> bool:
    """True when peer UIs sit in multiple columns (wide artboard, ~one row tall)."""
    if len(candidates) < 2:
        return False
    parent_w = float(parent.get("w") or 0)
    widths = sorted(float(child.get("w") or 0) for child in candidates)
    median_w = widths[len(widths) // 2]
    if median_w <= 0:
        return False
    xs = sorted(float(child.get("x") or 0) for child in candidates)
    x_span = xs[-1] - xs[0]
    # Side-by-side peers span at least half a child width across columns.
    if x_span < median_w * 0.45:
        return False
    # Grid boards are typically much wider than one child page.
    return parent_w >= median_w * 1.6


def _split_targets(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return child trees that should become their own screens.

    Prefers meaningfully named peer UIs (``Sign In``, ``Dashboard - Widgets``).
    Falls back to similarly sized full-width peers so light/dark ``item`` stacks
    still split. Never splits stacked landing-page sections into fake screens.
    """
    kids = _ui_children(tree)
    if len(kids) < 2:
        return []

    if _looks_like_landing_sections(tree, kids):
        return []

    named = [child for child in kids if _meaningful_name(str(child.get("name") or ""))]
    candidates = named if len(named) >= 2 else []

    if not candidates:
        parent_w = float(tree.get("w") or 0)
        if parent_w <= 0:
            return []
        full = [child for child in kids if float(child.get("w") or 0) >= parent_w * 0.85]
        if len(full) < 2:
            return []
        heights = sorted(float(child.get("h") or 0) for child in full)
        median = heights[len(heights) // 2]
        if median < _MIN_UI_H:
            return []
        peers = [
            child
            for child in full
            if abs(float(child.get("h") or 0) - median) <= median * 0.45
        ]
        if len(peers) >= 2 and len(peers) >= max(2, int(len(full) * 0.6)):
            candidates = peers

    if len(candidates) < 2:
        return []

    parent_h = float(tree.get("h") or 0)
    median_h = sorted(float(child.get("h") or 0) for child in candidates)[
        len(candidates) // 2
    ]
    # Parent ~one page tall usually means layout regions — unless peers form a
    # multi-column grid (Modernize Applications-style artboards).
    if parent_h > 0 and median_h > 0 and parent_h < median_h * 1.55:
        if not _is_grid_of_peers(tree, candidates):
            return []

    if _looks_like_landing_sections(tree, candidates):
        return []

    # Prefer similarly sized peer pages (admin boards) over mixed sections.
    # Named peers may still vary in height (short auth + tall dashboard).
    heights = [float(child.get("h") or 0) for child in candidates]
    cv = _height_cv(heights)
    if cv > 0.75:
        return []
    if cv > 0.55 and not all(
        _meaningful_name(str(child.get("name") or "")) for child in candidates
    ):
        return []

    return candidates


def _solid_fill(node: dict[str, Any]) -> str | None:
    return first_solid_fill(node.get("fills"))


def _inherit_background(child: dict[str, Any], parent: dict[str, Any]) -> None:
    """
    Carry the board's backdrop onto a split child.

    A nested UI frame often has no fill of its own because the surrounding board
    supplies it; without this the child would render on white.
    """
    if parent.get("pageBackground") and not child.get("pageBackground"):
        child["pageBackground"] = parent["pageBackground"]
    inherited = _solid_fill(parent) or parent.get("inheritedBackground")
    if inherited and not _solid_fill(child):
        child["inheritedBackground"] = inherited


def _count_nodes(tree: dict[str, Any], *, cap: int | None = None) -> int:
    total = 0
    stack = [tree]
    while stack:
        node = stack.pop()
        total += 1
        if cap is not None and total >= cap:
            return total
        stack.extend(node.get("children") or [])
    return total


def _expand_screen(
    screen: dict[str, Any],
    tree: dict[str, Any],
    *,
    depth: int,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Recursively expand one board into leaf UI screens + their trees."""
    if depth >= _MAX_DEPTH:
        return [(screen, tree)]

    targets = _split_targets(tree)
    if not targets:
        return [(screen, tree)]

    board_name = str(screen.get("name") or tree.get("name") or "board")
    board_id = screen.get("id")
    board_chain = list(screen.get("boards") or [])
    board_chain.append(board_name)

    expanded: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for index, child_tree in enumerate(targets):
        _inherit_background(child_tree, tree)
        label = _child_label(child_tree, index)
        child_screen = {
            "page": screen.get("page"),
            "pageId": screen.get("pageId"),
            "id": child_tree.get("id") or f"{board_id}:{index}",
            "type": child_tree.get("type") or "FRAME",
            "name": label,
            "width": child_tree.get("w"),
            "height": child_tree.get("h"),
            "board": board_name,
            "boardId": board_id,
            "boards": board_chain,
            "sourceBoard": screen.get("sourceBoard") or board_name,
        }
        expanded.extend(_expand_screen(child_screen, child_tree, depth=depth + 1))
    return expanded


_CROP_MIN_W = 480.0
_CROP_MAX_W = 1400.0
_CROP_MIN_H = 180.0
_CROP_MAX_H = 900.0
_OVERLAY_NAME_RE = re.compile(
    r"(modal|dialog|drawer|popup|popover|overlay|dropdown|toast|alert|confirm)",
    re.I,
)


def _is_full_page(tree: dict[str, Any]) -> bool:
    """Desktop-width long pages should stay intact; crops are noise for them."""
    width = float(tree.get("w") or 0)
    height = float(tree.get("h") or 0)
    return width >= 1280 and height >= 2000


def _is_crop_frame(node: dict[str, Any]) -> bool:
    """
    Mid-size nested frames that often match standalone design exports.

    Heuristic (kit-agnostic): wide enough to be a UI crop, short enough not to
    be a full desktop page, richly named (or clearly an overlay), and dense
    enough to be worth a screenshot.
    """
    if node.get("type") not in _FRAME_TYPES:
        return False
    width = float(node.get("w") or 0)
    height = float(node.get("h") or 0)
    if not (_CROP_MIN_W <= width <= _CROP_MAX_W and _CROP_MIN_H <= height <= _CROP_MAX_H):
        return False
    # Skip near-square icon sheets and full-bleed heroes that already split.
    if height > 0 and width / height > 4.5:
        return False
    name = str(node.get("name") or "").strip()
    if not _meaningful_name(name):
        return False
    if re.match(r"^screen-\d+$", name, re.I):
        return False
    # Prefer explicitly named overlays; allow other meaningful mid-size frames
    # only when dense (cards / panels that match kit exports).
    nodes = _count_nodes(node, cap=32)
    if _OVERLAY_NAME_RE.search(name):
        return nodes >= 8
    return nodes >= 28


def _promote_crops(
    screen: dict[str, Any],
    tree: dict[str, Any],
    *,
    seen_ids: set[str],
    max_crops: int = 8,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """
    Lift mid-size nested frames into their own screens.

    Design kits often nest overlays / cards inside tall boards. Promoting them
    produces one PNG per UI crop so local shots can be compared to original
    exports across arbitrary Figma files.

    Skip promotion on full marketing pages and on typical single-UI leaves —
    otherwise Metronic auth pages explode into thousands of card crops.
    """
    if _is_full_page(tree):
        return []
    parent_w = float(tree.get("w") or 0)
    parent_h = float(tree.get("h") or 0)
    # Single interface pages: keep one screenshot unless an overlay is named.
    single_ui = parent_w >= 1000 and 500 <= parent_h <= 2200

    promoted: list[tuple[dict[str, Any], dict[str, Any]]] = []
    # BFS so shallow overlays are preferred over deep nested cards.
    queue: deque[dict[str, Any]] = deque(tree.get("children") or [])
    while queue and len(promoted) < max_crops:
        child = queue.popleft()
        queue.extend(child.get("children") or [])
        node_id = str(child.get("id") or "")
        if not _is_crop_frame(child):
            continue
        name = str(child.get("name") or "")
        if single_ui and not _OVERLAY_NAME_RE.search(name):
            continue
        if node_id and node_id in seen_ids:
            continue
        if node_id:
            seen_ids.add(node_id)
        label = _child_label(child, len(promoted))
        crop_tree = dict(child)
        _inherit_background(crop_tree, tree)
        crop_tree["x"] = 0
        crop_tree["y"] = 0
        crop_tree.pop("absolute", None)
        board_name = str(screen.get("name") or tree.get("name") or "board")
        board_chain = list(screen.get("boards") or [])
        if board_name not in board_chain:
            board_chain = board_chain + [board_name]
        promoted.append(
            (
                {
                    "page": screen.get("page"),
                    "pageId": screen.get("pageId"),
                    "id": child.get("id") or f"{screen.get('id')}:crop:{len(promoted)}",
                    "type": child.get("type") or "FRAME",
                    "name": label,
                    "width": child.get("w"),
                    "height": child.get("h"),
                    "board": board_name,
                    "boardId": screen.get("id"),
                    "boards": board_chain,
                    "sourceBoard": screen.get("sourceBoard") or board_name,
                    "crop": True,
                },
                crop_tree,
            )
        )
    return promoted


def split_screen_boards(out: Path) -> dict[str, Any]:
    """
    Replace multi-UI board screens with one screen entry per nested UI.

    Also promotes mid-size overlay crops so half-width Figma exports can be
    matched against local screenshots.

    Rewrites ``design/screens.json``, replaces ``design/trees/*.json`` with the
    leaf trees, and updates ``trees/index.json``.
    """
    design = design_dir(out)
    screens_path = design / "screens.json"
    trees_dir = design / "trees"
    if not screens_path.is_file() or not trees_dir.is_dir():
        raise FileNotFoundError("screens.json / trees/ required before board split")

    screens: list[dict[str, Any]] = orjson.loads(screens_path.read_bytes())
    expanded: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    boards_split = 0
    crops_promoted = 0
    seen_ids: set[str] = set()
    for screen in screens:
        tree_rel = screen.get("tree")
        if not tree_rel:
            # Keep structure-only screens so they are not dropped from screens.json.
            expanded.append((screen, None))
            continue
        tree_path = design / str(tree_rel)
        if not tree_path.is_file():
            expanded.append((screen, None))
            continue
        tree = orjson.loads(tree_path.read_bytes())
        pieces = _expand_screen(screen, tree, depth=0)
        if len(pieces) > 1:
            boards_split += 1
        for piece_screen, piece_tree in pieces:
            node_id = str(piece_screen.get("id") or "")
            if node_id:
                seen_ids.add(node_id)
            expanded.append((piece_screen, piece_tree))
            crops = _promote_crops(piece_screen, piece_tree, seen_ids=seen_ids)
            crops_promoted += len(crops)
            expanded.extend(crops)

    # Drop old tree files, then write leaf trees with unique slugs.
    for path in trees_dir.glob("*.json"):
        path.unlink()

    used_names: set[str] = set()
    final_screens: list[dict[str, Any]] = []
    for screen, tree in expanded:
        if tree is None:
            screen.pop("localScreenshot", None)
            screen.pop("localScreenshotError", None)
            screen.pop("preview", None)
            final_screens.append(screen)
            continue
        page_slug = slug(ascii_name(str(screen.get("page") or "page")))
        board_parts = [slug(str(part)) for part in (screen.get("boards") or []) if part]
        # Keep the immediate board in the slug so Auth Branded/Classic Sign In
        # stay distinct: authentication__auth-branded__sign-in
        if board_parts:
            name_slug = "__".join(board_parts[-1:] + [slug(str(screen.get("name") or "screen"))])
        else:
            name_slug = slug(str(screen.get("name") or screen.get("id") or "screen"))
        if screen.get("crop"):
            name_slug = f"{name_slug}__crop"
        candidate = unique_slug(f"{page_slug}__{name_slug}", used_names)
        write_json(trees_dir / f"{candidate}.json", tree)
        screen["tree"] = f"trees/{candidate}.json"
        screen["slug"] = candidate
        screen["renderNodes"] = _count_nodes(tree)
        screen.pop("localScreenshot", None)
        screen.pop("localScreenshotError", None)
        screen.pop("preview", None)
        screen.pop("screenshot", None)
        screen.pop("screenshotError", None)
        final_screens.append(screen)

    summary = {
        "boardsSplit": boards_split,
        "cropsPromoted": crops_promoted,
        "screensBefore": len(screens),
        "screensAfter": len(final_screens),
        "trees": len(final_screens),
    }
    write_json(screens_path, final_screens)
    write_json(trees_dir / "index.json", {"screens": final_screens, "summary": summary})
    console.print(
        f"[green]Split[/] {boards_split} boards + {crops_promoted} crops → "
        f"{len(final_screens)} UI screens (from {len(screens)}) → {trees_dir}"
    )
    return summary
