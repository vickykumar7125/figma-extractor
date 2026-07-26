"""Build LLM-oriented UI flow artifacts from per-screen layout trees."""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path
from typing import Any

import orjson
from rich.console import Console

from figma_extractor.paths import design_dir
from figma_extractor.util import ascii_name, slug, write_json, write_text

console = Console(stderr=True)

ScreenRole = str

_ROLE_KEYWORDS: dict[ScreenRole, tuple[str, ...]] = {
    "auth": (
        "login",
        "log in",
        "sign in",
        "sign-in",
        "sign up",
        "signup",
        "register",
        "forgot password",
        "reset password",
        "verify email",
        "two factor",
        "2fa",
        "otp",
        "auth",
    ),
    "dashboard": ("dashboard", "analytics", "overview", "home", "summary"),
    "list": ("list", "listing", "table", "grid", "catalog", "browse", "all ", "index"),
    "detail": ("detail", "details", "view", "profile", "single", "show", "read"),
    "form": ("form", "edit", "create", "add ", "new ", "wizard", "checkout", "submit"),
    "settings": ("settings", "preferences", "config", "configuration", "account settings"),
    "dialog": ("dialog", "modal", "popup", "confirm", "alert dialog"),
    "empty": ("empty", "no data", "no results", "placeholder", "404", "not found", "zero state"),
    "marketing": ("landing", "hero", "pricing", "about us", "marketing", "welcome", "promo"),
    "component-gallery": (
        "accordion",
        "alert",
        "avatar",
        "badge",
        "button",
        "card",
        "chip",
        "components",
        "ui kit",
        "style guide",
        "foundation",
        "atoms",
        "molecules",
    ),
}

_DEMO_PAGE_NAMES = frozenset(
    {
        "accordion",
        "alert",
        "avatar",
        "badge",
        "button",
        "card",
        "chip",
        "checkbox",
        "dialog",
        "dropdown",
        "input",
        "modal",
        "pagination",
        "progress",
        "radio",
        "select",
        "slider",
        "switch",
        "table",
        "tabs",
        "tooltip",
        "typography",
    }
)

_REGION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("nav", re.compile(r"\b(nav|navigation|navbar|topbar|appbar|app-bar|breadcrumb)\b", re.I)),
    ("sidebar", re.compile(r"\b(sidebar|side-bar|side nav|sidenav|rail)\b", re.I)),
    ("menu", re.compile(r"\b(menu|menubar|context menu|dropdown menu)\b", re.I)),
    ("header", re.compile(r"\b(header|page header|top bar)\b", re.I)),
    ("footer", re.compile(r"\b(footer|page footer)\b", re.I)),
    ("content", re.compile(r"\b(content|main|body|container|page content|scroll area)\b", re.I)),
    ("toolbar", re.compile(r"\b(toolbar|action bar|actions|controls)\b", re.I)),
    ("modal", re.compile(r"\b(modal|dialog|popup|overlay)\b", re.I)),
    ("drawer", re.compile(r"\b(drawer|sheet|slide.?over|off.?canvas)\b", re.I)),
)

_FORM_HINTS = re.compile(
    r"\b(input|textfield|text field|textarea|select|checkbox|radio|form|field|datepicker|"
    r"combobox|switch|slider)\b",
    re.I,
)

_ROUTE_PREFIX_RE = re.compile(
    r"^(?:ecommerce|e-commerce|user|users|admin|app|page|screen|view|application|"
    r"dashboard|account|settings|auth|login|academy|invoice|calendar|chat|email|"
    r"kanban|logistics|crm|analytics)\s*[-–—:/]\s*",
    re.I,
)

_BFS_NODE_CAP = 800
_TEXT_CAP = 15
_TEXT_MAX_LEN = 80
_COMPONENT_CAP = 40


def infer_role(name: str, page: str = "") -> ScreenRole:
    """Infer a coarse screen role from page and screen names."""
    page_lower = page.lower().strip()
    name_lower = name.lower().strip()
    combined = f"{page_lower} {name_lower}"

    if page_lower in _DEMO_PAGE_NAMES or (
        page_lower and (name_lower == page_lower or name_lower.startswith(page_lower))
    ):
        return "component-gallery"

    for role, keywords in _ROLE_KEYWORDS.items():
        if role == "component-gallery":
            continue
        if any(keyword in combined for keyword in keywords):
            return role

    if any(keyword in combined for keyword in _ROLE_KEYWORDS["component-gallery"]):
        return "component-gallery"

    return "page" if page_lower else "other"


def infer_region_role(name: str) -> str | None:
    for role, pattern in _REGION_PATTERNS:
        if pattern.search(name):
            return role
    return None


def _truncate_text(text: str, max_len: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def scan_tree(tree: dict[str, Any]) -> dict[str, Any]:
    """Light BFS over a layout tree to collect LLM-oriented hints."""
    components_used: list[str] = []
    seen_components: set[str] = set()
    texts: list[str] = []
    seen_texts: set[str] = set()
    has_nav = False
    has_sidebar = False
    has_form = False
    regions: list[dict[str, Any]] = []
    seen_region_keys: set[str] = set()

    def _add_region(node: dict[str, Any]) -> None:
        nonlocal has_nav, has_sidebar
        child_name = str(node.get("name") or "")
        region_role = infer_region_role(child_name)
        if not region_role:
            return
        key = f"{region_role}:{child_name}"
        if key in seen_region_keys:
            return
        seen_region_keys.add(key)
        regions.append(
            {
                "role": region_role,
                "name": child_name,
                "w": node.get("w"),
                "h": node.get("h"),
            }
        )
        if region_role in ("nav", "menu"):
            has_nav = True
        if region_role == "sidebar":
            has_sidebar = True

    # Regions: root children + one level deeper (Menu/Nav often nest under Wrapper).
    for child in tree.get("children") or []:
        _add_region(child)
        for grand in child.get("children") or []:
            _add_region(grand)

    queue: deque[dict[str, Any]] = deque([tree])
    visited = 0
    while queue and visited < _BFS_NODE_CAP:
        node = queue.popleft()
        visited += 1

        node_name = str(node.get("name") or "")
        node_type = str(node.get("type") or "")

        region_role = infer_region_role(node_name)
        if region_role in ("nav", "menu"):
            has_nav = True
        if region_role == "sidebar":
            has_sidebar = True

        if _FORM_HINTS.search(node_name):
            has_form = True

        instance_of = node.get("instanceOf")
        if instance_of:
            component_key = str(instance_of)
            if component_key not in seen_components and len(components_used) < _COMPONENT_CAP:
                seen_components.add(component_key)
                components_used.append(component_key)
            if _FORM_HINTS.search(node_name):
                has_form = True
        elif node_type in ("INSTANCE", "SYMBOL", "COMPONENT"):
            component_key = node_name or str(node.get("id") or "")
            if (
                component_key
                and component_key not in seen_components
                and len(components_used) < _COMPONENT_CAP
            ):
                seen_components.add(component_key)
                components_used.append(component_key)

        text_obj = node.get("text")
        if isinstance(text_obj, dict):
            content = str(text_obj.get("content") or text_obj.get("characters") or "").strip()
        elif isinstance(text_obj, str):
            content = text_obj.strip()
        else:
            content = ""

        if content and content not in seen_texts and len(texts) < _TEXT_CAP:
            seen_texts.add(content)
            texts.append(_truncate_text(content, _TEXT_MAX_LEN))

        for child in node.get("children") or []:
            queue.append(child)

    return {
        "regions": regions,
        "componentsUsed": components_used,
        "texts": texts,
        "hasNav": has_nav,
        "hasSidebar": has_sidebar,
        "hasForm": has_form,
    }


def suggest_route_path(screen_name: str, page_name: str, role: ScreenRole) -> str:
    """Suggest a slug-based route from a screen name."""
    stripped = _ROUTE_PREFIX_RE.sub("", screen_name.strip())
    parts = [part.strip() for part in re.split(r"[-–—/|:]", stripped) if part.strip()]
    if not parts:
        parts = [screen_name.strip() or "screen"]

    segments = [slug(part) for part in parts if slug(part)]
    if not segments:
        segments = [slug(screen_name) or "screen"]

    page_slug = slug(ascii_name(page_name))
    if role in ("dashboard", "list", "detail", "form", "settings") and page_slug:
        skip_pages = {"applications-new", "pages", "screens", "applications", "misc"}
        if segments[0] != page_slug and page_slug not in skip_pages:
            segments = [page_slug, *segments]

    return "/" + "/".join(segments)


def _load_tree(design: Path, tree_rel: str) -> dict[str, Any] | None:
    path = design / tree_rel
    if not path.is_file():
        return None
    return orjson.loads(path.read_bytes())


def _discover_tree_files(trees_dir: Path) -> dict[str, str]:
    discovered: dict[str, str] = {}
    if not trees_dir.is_dir():
        return discovered
    for path in sorted(trees_dir.glob("*.json")):
        if path.name == "index.json":
            continue
        discovered[path.stem] = f"trees/{path.name}"
    return discovered


def _llm_guide() -> str:
    return "\n".join(
        [
            "# Using this extraction to build HTML",
            "",
            "This folder contains machine-readable design data. Treat these artifacts as the",
            "source of truth — do not guess colors, spacing, typography, or copy.",
            "",
            "## Read order",
            "",
            "1. **`tokens/tokens.css`** — CSS custom properties for colors, typography, shadows,",
            "   and spacing. Import or copy into your stylesheet.",
            "2. **`ui-flow.json`** — Screen inventory, inferred roles, layout regions, sample text,",
            "   and suggested routes. Start here for site map and page priorities.",
            "3. **`trees/<page>__<screen>.json`** — Per-screen layout trees: flex direction, padding,",
            "   fills, text styles, and component instances. Use one tree per HTML page/view.",
            "4. **`components.json`** + **`components/index.json`** — Component symbols and variant",
            "   axes. Resolve `instanceOf` ids in trees against these entries.",
            "5. **`COMPONENTS.md`** — Human-readable variant catalog when you need prop/axis names.",
            "",
            "## Building a page",
            "",
            "1. Pick a screen from `ui-flow.json` and open its `tree` file.",
            "2. Walk the tree root → children recursively. Map `layout.dir` to `flex-direction`,",
            "   `layout.gap` to `gap`, and `layout.pad` to padding.",
            "3. Apply `fills`, `stroke`, `radius`, and `shadows` from tree nodes; prefer token",
            "   variables from `tokens.css` when values match.",
            "4. For `INSTANCE` nodes, look up `instanceOf` in `components.json` and reuse a shared",
            "   HTML partial; pick the variant that matches visible props when needed.",
            "5. Map `text` nodes to semantic HTML (`h1`–`h6`, `p`, `button`, `label`) using content",
            "   and weight/size.",
            "6. Use `regions` in `ui-flow.json` to structure `<header>`, `<nav>`, `<aside>`,",
            "   `<main>`, and `<footer>` wrappers.",
            "",
            "## Routes",
            "",
            "`suggestedRoutes` in `ui-flow.json` are slug guesses (e.g. `/user/overview`). Adjust to",
            "your router; use `role` to group auth shells vs app pages.",
            "",
            "## Assets",
            "",
            "Reference images by hash under `assets/` when tree nodes specify `\"type\": \"image\"`.",
            "",
            "## What not to use",
            "",
            "- Raw `extracted/nodes.ndjson` unless you need fields missing from trees.",
            "- Screens without a `tree` field were skipped or too large — infer lightly from",
            "  `screens.json` only.",
            "",
        ]
    )


def _build_components_index(design: Path) -> dict[str, Any] | None:
    sets_path = design / "component-sets.json"
    if not sets_path.is_file():
        return None

    raw_sets: list[dict[str, Any]] = orjson.loads(sets_path.read_bytes())
    slim_sets = [
        {
            "id": entry.get("id"),
            "name": entry.get("name"),
            "page": entry.get("page"),
            "variantCount": entry.get("variantCount"),
            "axes": entry.get("axes") or {},
        }
        for entry in raw_sets
    ]

    count = 0
    components_path = design / "components.json"
    if components_path.is_file():
        count = len(orjson.loads(components_path.read_bytes()))

    return {"count": count, "sets": slim_sets}


def build_ui_flow(out: Path) -> dict[str, Any]:
    """
    Produce LLM-oriented UI flow artifacts after screen trees are built.

    Writes ``ui-flow.json``, ``LLM.md``, updates ``screens.json`` with role/region
    summaries, and optionally ``components/index.json``.
    """
    design = design_dir(out)
    screens_path = design / "screens.json"
    if not screens_path.is_file():
        raise FileNotFoundError(f"Missing {screens_path}; run structure extract first.")

    screens: list[dict[str, Any]] = orjson.loads(screens_path.read_bytes())
    trees_dir = design / "trees"
    discovered_trees = _discover_tree_files(trees_dir)

    if (trees_dir / "index.json").is_file():
        index_data = orjson.loads((trees_dir / "index.json").read_bytes())
        for indexed in index_data.get("screens") or []:
            tree_rel = indexed.get("tree")
            slug_key = indexed.get("slug")
            if tree_rel and slug_key:
                discovered_trees.setdefault(slug_key, tree_rel)

    pages_map: dict[str, dict[str, Any]] = {}
    suggested_routes: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    roles_count: dict[str, int] = {}
    screens_with_trees = 0

    for screen in screens:
        page_name = str(screen.get("page") or "unknown")
        page_entry = pages_map.setdefault(
            page_name,
            {
                "name": page_name,
                "slug": slug(ascii_name(page_name)),
                "screenCount": 0,
                "screens": [],
            },
        )
        page_entry["screenCount"] += 1

        screen_slug = screen.get("slug") or slug(str(screen.get("name") or screen.get("id") or "screen"))
        tree_rel = screen.get("tree")
        if not tree_rel and screen_slug in discovered_trees:
            tree_rel = discovered_trees[screen_slug]
            screen["tree"] = tree_rel

        flow_screen: dict[str, Any] = {
            "id": screen.get("id"),
            "name": screen.get("name"),
            "slug": screen_slug,
            "width": screen.get("width"),
            "height": screen.get("height"),
        }

        role = infer_role(str(screen.get("name") or ""), page_name)
        flow_screen["role"] = role

        if tree_rel:
            flow_screen["tree"] = tree_rel
            tree = _load_tree(design, tree_rel)
            if tree:
                screens_with_trees += 1
                scan = scan_tree(tree)
                flow_screen.update(scan)

                screen["role"] = role
                screen["regions"] = [{"role": r["role"], "name": r["name"]} for r in scan["regions"]]

                roles_count[role] = roles_count.get(role, 0) + 1

                route_path = suggest_route_path(str(screen.get("name") or ""), page_name, role)
                if route_path not in seen_paths:
                    seen_paths.add(route_path)
                    suggested_routes.append(
                        {
                            "path": route_path,
                            "screen": screen_slug,
                            "page": page_name,
                            "role": role,
                        }
                    )

        page_entry["screens"].append(flow_screen)

    pages = sorted(pages_map.values(), key=lambda item: item["name"])
    summary = {
        "pages": len(pages),
        "screens": len(screens),
        "screensWithTrees": screens_with_trees,
        "roles": dict(sorted(roles_count.items())),
        "suggestedRouteCount": len(suggested_routes),
    }

    write_json(
        design / "ui-flow.json",
        {
            "summary": summary,
            "pages": pages,
            "suggestedRoutes": sorted(suggested_routes, key=lambda item: item["path"]),
        },
    )
    write_json(screens_path, screens)
    write_text(design / "LLM.md", _llm_guide())

    components_index = _build_components_index(design)
    if components_index is not None:
        write_json(design / "components" / "index.json", components_index)

    console.print(
        f"[green]UI flow[/] {screens_with_trees} trees · "
        f"{len(suggested_routes)} routes · {len(pages)} pages → {design}"
    )
    return summary
