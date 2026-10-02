"""Split multi-UI board frames into one screen tree per UI.

Metronic-style kits stack many full pages inside one tall board, e.g.
``Auth - Branded`` contains ``Sign In``, ``Sign Up``, ``2FA``, … This module
detects those boards from the render trees and replaces each board entry with
its individual UI children so downstream consumers get one screen per UI.

Example::

    from figma_extractor.extract.split import split_screen_boards

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

FRAME_TYPES = {"FRAME", "INSTANCE", "SYMBOL", "COMPONENT", "SECTION"}
GENERIC_NAMES = {
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
GENERIC_RE = re.compile(r"^(frame|group|rectangle|vector|ellipse)\s*\d*$", re.I)
SECTION_NAMES = {
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
MIN_UI_W = 280.0
MIN_UI_H = 400.0
MAX_DEPTH = 3


def meaningful_name(name: str | None) -> bool:
    text = (name or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered in GENERIC_NAMES:
        return False
    return GENERIC_RE.match(text) is None


def title_from_tree(node: dict[str, Any]) -> str | None:
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


def child_label(node: dict[str, Any], index: int) -> str:
    name = str(node.get("name") or "").strip()
    if meaningful_name(name):
        return name
    titled = title_from_tree(node)
    if titled:
        return titled
    return f"screen-{index + 1}"


def ui_children(tree: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for child in tree.get("children") or []:
        if child.get("type") not in FRAME_TYPES:
            continue
        width = float(child.get("w") or 0)
        height = float(child.get("h") or 0)
        if width >= MIN_UI_W and height >= MIN_UI_H:
            result.append(child)
    return result


def is_section_name(name: str | None) -> bool:
    text = re.sub(r"[\W_]+", " ", (name or "").strip().lower()).strip()
    if not text:
        return False
    if text in SECTION_NAMES:
        return True
    # "01 Home" / "Home Section" style landing blocks still count as sections
    # when the meaningful token is a known section word.
    tokens = [token for token in text.split() if token and not token.isdigit()]
    return bool(tokens) and all(token in SECTION_NAMES for token in tokens)


def height_cv(heights: list[float]) -> float:
    if not heights:
        return 0.0
    mean = sum(heights) / len(heights)
    if mean <= 0:
        return 0.0
    var = sum((height - mean) ** 2 for height in heights) / len(heights)
    return (var**0.5) / mean


def looks_like_landing_sections(parent: dict[str, Any], kids: list[dict[str, Any]]) -> bool:
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
        sectionish = sum(1 for child in kids if is_section_name(str(child.get("name") or "")))
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
        1 for child in stacked if is_section_name(str(child.get("name") or ""))
    )
    if sectionish_stacked >= max(2, int(len(stacked) * 0.5)):
        return True

    heights = [float(child.get("h") or 0) for child in stacked]
    total_h = sum(heights)
    # Contiguous sections usually cover most of the parent height.
    if parent_h > 0 and total_h >= parent_h * 0.7:
        # Peer UI boards also sum high — require heterogeneous heights.
        if height_cv(heights) >= 0.28:
            return True
    # Wide + very tall with a few full-bleed chrome sections.
    if parent_w >= 1280 and parent_h >= 3000 and len(stacked) <= 8 and sectionish_stacked >= 1:
        return True
    return False


def is_grid_of_peers(parent: dict[str, Any], candidates: list[dict[str, Any]]) -> bool:
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


def split_targets(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return child trees that should become their own screens.

    Prefers meaningfully named peer UIs (``Sign In``, ``Dashboard - Widgets``).
    Falls back to similarly sized full-width peers so light/dark ``item`` stacks
    still split. Never splits stacked landing-page sections into fake screens.
    """
    kids = ui_children(tree)
    if len(kids) < 2:
        return []

    if looks_like_landing_sections(tree, kids):
        return []

    named = [child for child in kids if meaningful_name(str(child.get("name") or ""))]
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
        if median < MIN_UI_H:
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
        if not is_grid_of_peers(tree, candidates):
            return []

    if looks_like_landing_sections(tree, candidates):
        return []

    # Prefer similarly sized peer pages (admin boards) over mixed sections.
    # Named peers may still vary in height (short auth + tall dashboard).
    heights = [float(child.get("h") or 0) for child in candidates]
    cv = height_cv(heights)
    if cv > 0.75:
        return []
    if cv > 0.55 and not all(
        meaningful_name(str(child.get("name") or "")) for child in candidates
    ):
        return []

    return candidates


def solid_fill(node: dict[str, Any]) -> str | None:
    return first_solid_fill(node.get("fills"))


def inherit_background(child: dict[str, Any], parent: dict[str, Any]) -> None:
    """
    Carry the board's backdrop onto a split child.

    A nested UI frame often has no fill of its own because the surrounding board
    supplies it; without this the child would render on white.
    """
    if parent.get("pageBackground") and not child.get("pageBackground"):
        child["pageBackground"] = parent["pageBackground"]
    inherited = solid_fill(parent) or parent.get("inheritedBackground")
    if inherited and not solid_fill(child):
        child["inheritedBackground"] = inherited


def count_nodes(tree: dict[str, Any], *, cap: int | None = None) -> int:
    total = 0
    stack = [tree]
    while stack:
        node = stack.pop()
        total += 1
        if cap is not None and total >= cap:
            return total
        stack.extend(node.get("children") or [])
    return total


def expand_screen(
    screen: dict[str, Any],
    tree: dict[str, Any],
    *,
    depth: int,
    board_archives: list[tuple[dict[str, Any], dict[str, Any]]] | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Recursively expand one board into leaf UI screens + their trees."""
    if depth >= MAX_DEPTH:
        return [(screen, tree)]

    targets = split_targets(tree)
    if not targets:
        return [(screen, tree)]

    if board_archives is not None:
        board_archives.append((dict(screen), tree))

    board_name = str(screen.get("name") or tree.get("name") or "board")
    board_id = screen.get("id")
    board_chain = list(screen.get("boards") or [])
    board_chain.append(board_name)

    expanded: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for index, child_tree in enumerate(targets):
        inherit_background(child_tree, tree)
        label = child_label(child_tree, index)
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
            "origin": "board-child",
            "sourceScreenId": board_id,
        }
        expanded.extend(
            expand_screen(
                child_screen,
                child_tree,
                depth=depth + 1,
                board_archives=board_archives,
            )
        )
    return expanded


CROP_MIN_W = 480.0
CROP_MAX_W = 1400.0
CROP_MIN_H = 180.0
CROP_MAX_H = 900.0
OVERLAY_NAME_RE = re.compile(
    r"(modal|dialog|drawer|popup|popover|overlay|dropdown|toast|alert|confirm)",
    re.I,
)


def is_full_page(tree: dict[str, Any]) -> bool:
    """Desktop-width long pages should stay intact; crops are noise for them."""
    width = float(tree.get("w") or 0)
    height = float(tree.get("h") or 0)
    return width >= 1280 and height >= 2000


def is_crop_frame(node: dict[str, Any]) -> bool:
    """
    Mid-size nested frames that often match standalone design exports.

    Heuristic (kit-agnostic): wide enough to be a UI crop, short enough not to
    be a full desktop page, richly named (or clearly an overlay), and dense
    enough to be worth its own tree.
    """
    if node.get("type") not in FRAME_TYPES:
        return False
    width = float(node.get("w") or 0)
    height = float(node.get("h") or 0)
    if not (CROP_MIN_W <= width <= CROP_MAX_W and CROP_MIN_H <= height <= CROP_MAX_H):
        return False
    # Skip near-square icon sheets and full-bleed heroes that already split.
    if height > 0 and width / height > 4.5:
        return False
    name = str(node.get("name") or "").strip()
    if not meaningful_name(name):
        return False
    if re.match(r"^screen-\d+$", name, re.I):
        return False
    # Prefer explicitly named overlays; allow other meaningful mid-size frames
    # only when dense (cards / panels that match kit exports).
    nodes = count_nodes(node, cap=32)
    if OVERLAY_NAME_RE.search(name):
        return nodes >= 8
    return nodes >= 28


def promote_crops(
    screen: dict[str, Any],
    tree: dict[str, Any],
    *,
    seen_ids: set[str],
    max_crops: int = 8,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """
    Lift mid-size nested frames into their own screens.

    Design kits often nest overlays / cards inside tall boards. Promoting them
    produces one tree per UI crop so a consumer sees each interface in
    isolation across arbitrary Figma files.

    Skip promotion on full marketing pages and on typical single-UI leaves —
    otherwise Metronic auth pages explode into thousands of card crops.
    """
    if is_full_page(tree):
        return []
    parent_w = float(tree.get("w") or 0)
    parent_h = float(tree.get("h") or 0)
    # Single interface pages: keep one screen unless an overlay is named.
    single_ui = parent_w >= 1000 and 500 <= parent_h <= 2200

    promoted: list[tuple[dict[str, Any], dict[str, Any]]] = []
    # BFS so shallow overlays are preferred over deep nested cards.
    queue: deque[dict[str, Any]] = deque(tree.get("children") or [])
    while queue and len(promoted) < max_crops:
        child = queue.popleft()
        queue.extend(child.get("children") or [])
        node_id = str(child.get("id") or "")
        if not is_crop_frame(child):
            continue
        name = str(child.get("name") or "")
        if single_ui and not OVERLAY_NAME_RE.search(name):
            continue
        if node_id and node_id in seen_ids:
            continue
        if node_id:
            seen_ids.add(node_id)
        label = child_label(child, len(promoted))
        crop_tree = dict(child)
        inherit_background(crop_tree, tree)
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
                    "origin": "crop",
                    "sourceScreenId": screen.get("id"),
                },
                crop_tree,
            )
        )
    return promoted


def split_screen_boards(out: Path) -> dict[str, Any]:
    """
    Replace multi-UI board screens with one screen entry per nested UI.

    Also promotes mid-size overlay crops so nested half-width UI regions become
    addressable as standalone screens.

    Rewrites ``design/screens.json``, replaces ``design/trees/*.json`` with the
    leaf trees, archives pre-split boards under ``trees/boards/``, and updates
    ``trees/index.json``.
    """
    from figma_extractor.extract.semantic import attach_semantic, screen_semantic

    design = design_dir(out)
    screens_path = design / "screens.json"
    trees_dir = design / "trees"
    if not screens_path.is_file() or not trees_dir.is_dir():
        raise FileNotFoundError("screens.json / trees/ required before board split")

    screens: list[dict[str, Any]] = orjson.loads(screens_path.read_bytes())
    expanded: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    board_archives: list[tuple[dict[str, Any], dict[str, Any]]] = []
    boards_split = 0
    crops_promoted = 0
    seen_ids: set[str] = set()
    for screen in screens:
        tree_rel = screen.get("tree")
        if not tree_rel:
            # Keep structure-only screens so they are not dropped from screens.json.
            screen.setdefault("origin", "top-level")
            expanded.append((screen, None))
            continue
        tree_path = design / str(tree_rel)
        if not tree_path.is_file():
            screen.setdefault("origin", "top-level")
            expanded.append((screen, None))
            continue
        tree = orjson.loads(tree_path.read_bytes())
        pieces = expand_screen(screen, tree, depth=0, board_archives=board_archives)
        if len(pieces) > 1:
            boards_split += 1
        for piece_screen, piece_tree in pieces:
            if "origin" not in piece_screen:
                piece_screen["origin"] = "top-level"
            node_id = str(piece_screen.get("id") or "")
            if node_id:
                seen_ids.add(node_id)
            expanded.append((piece_screen, piece_tree))
            crops = promote_crops(piece_screen, piece_tree, seen_ids=seen_ids)
            crops_promoted += len(crops)
            expanded.extend(crops)

    # Drop old leaf tree files, then write leaf trees with unique slugs.
    for path in trees_dir.glob("*.json"):
        path.unlink()

    boards_dir = trees_dir / "boards"
    if boards_dir.is_dir():
        for path in boards_dir.glob("*.json"):
            path.unlink()
    board_tree_by_id: dict[str, str] = {}
    used_board_names: set[str] = set()
    if board_archives:
        boards_dir.mkdir(parents=True, exist_ok=True)
        for board_screen, board_tree in board_archives:
            board_id = str(board_screen.get("id") or "")
            page_slug = slug(ascii_name(str(board_screen.get("page") or "page")))
            name_slug = slug(str(board_screen.get("name") or board_id or "board"))
            candidate = unique_slug(f"{page_slug}__{name_slug}", used_board_names)
            write_json(boards_dir / f"{candidate}.json", board_tree)
            rel = f"trees/boards/{candidate}.json"
            if board_id:
                board_tree_by_id[board_id] = rel
            board_screen["boardTree"] = rel

    used_names: set[str] = set()
    final_screens: list[dict[str, Any]] = []
    for screen, tree in expanded:
        if tree is None:
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
        attach_semantic(tree)
        semantic = screen_semantic(screen, tree)
        if semantic:
            screen["semantic"] = semantic
        elif "semantic" in screen:
            screen.pop("semantic", None)
        source_id = str(screen.get("sourceScreenId") or screen.get("boardId") or "")
        if source_id and source_id in board_tree_by_id:
            screen["boardTree"] = board_tree_by_id[source_id]
        write_json(trees_dir / f"{candidate}.json", tree)
        screen["tree"] = f"trees/{candidate}.json"
        screen["slug"] = candidate
        screen["renderNodes"] = count_nodes(tree)
        final_screens.append(screen)

    summary = {
        "boardsSplit": boards_split,
        "cropsPromoted": crops_promoted,
        "boardsArchived": len(board_tree_by_id),
        "screensBefore": len(screens),
        "screensAfter": len(final_screens),
        "trees": len(final_screens),
    }
    write_json(screens_path, final_screens)
    write_json(
        trees_dir / "index.json",
        {"schemaVersion": 2, "screens": final_screens, "summary": summary},
    )
    console.print(
        f"[green]Split[/] {boards_split} boards + {crops_promoted} crops → "
        f"{len(final_screens)} UI screens (from {len(screens)}) → {trees_dir}"
    )
    return summary
