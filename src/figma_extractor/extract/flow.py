"""Build LLM-oriented UI flow artifacts from per-screen layout trees."""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path
from typing import Any

import orjson
from rich.console import Console

from figma_extractor.paths import design_dir, nodes_path
from figma_extractor.util import ascii_name, gid, iter_ndjson, slug, write_json, write_text

console = Console(stderr=True)

ScreenRole = str

ROLE_KEYWORDS: dict[ScreenRole, tuple[str, ...]] = {
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
    # "home" / "index" are matched with word boundaries in infer_role so kit
    # crops named "home icon" do not become dashboards.
    "dashboard": ("dashboard", "analytics", "overview", "summary", "home", "index"),
    "list": ("list", "listing", "table", "grid", "catalog", "browse", "all "),
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

DEMO_PAGE_NAMES = frozenset(
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

REGION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
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

FORM_HINTS = re.compile(
    r"\b(input|textfield|text field|textarea|select|checkbox|radio|form|field|datepicker|"
    r"combobox|switch|slider)\b",
    re.I,
)

ROUTE_PREFIX_RE = re.compile(
    r"^(?:ecommerce|e-commerce|user|users|admin|app|page|screen|view|application|"
    r"dashboard|account|settings|auth|login|academy|invoice|calendar|chat|email|"
    r"kanban|logistics|crm|analytics)\s*[-–—:/]\s*",
    re.I,
)

BFS_NODE_CAP = 800
TEXT_CAP = 15
TEXT_MAX_LEN = 80
COMPONENT_CAP = 40


def infer_role(name: str, page: str = "") -> ScreenRole:
    """Infer a coarse screen role from page and screen names.

    Product roles match the **screen name** first. Kit page titles often contain
    brand words like ``Dashboard`` / ``Admin`` and must not force every crop into
    that role. Demo/component pages still map to ``component-gallery``.
    """
    page_lower = page.lower().strip()
    name_lower = name.lower().strip()

    # Only a known demo/component page implies a gallery. Matching a screen name
    # against its own page name must not do this: pages named after their screen
    # ("Dashboard", "Settings", "Landing Page") are ordinary product pages.
    if page_lower in DEMO_PAGE_NAMES:
        return "component-gallery"

    for role, keywords in ROLE_KEYWORDS.items():
        if role == "component-gallery":
            continue
        if any(_role_keyword_hit(name_lower, keyword) for keyword in keywords):
            return role

    gallery_keywords = ROLE_KEYWORDS["component-gallery"]
    if any(_role_keyword_hit(name_lower, keyword) for keyword in gallery_keywords):
        return "component-gallery"
    if any(_role_keyword_hit(page_lower, keyword) for keyword in gallery_keywords):
        return "component-gallery"

    return "page" if page_lower else "other"


_AMBIGUOUS_ROLE_WORDS = frozenset({"home", "index"})
_GALLERY_CONTEXT = re.compile(r"\b(icon|button|crop|variant|symbol|specimen|component)\b", re.I)


def _role_keyword_hit(text: str, keyword: str) -> bool:
    if keyword in _AMBIGUOUS_ROLE_WORDS:
        if not re.search(rf"\b{re.escape(keyword)}\b", text):
            return False
        # Kit specimen names often contain "home" without being a product home.
        return not _GALLERY_CONTEXT.search(text)
    return keyword in text


def infer_region_role(name: str) -> tuple[str, str] | tuple[None, None]:
    for role, pattern in REGION_PATTERNS:
        match = pattern.search(name)
        if match:
            return role, match.group(0).lower()
    return None, None


def truncate_text(text: str, max_len: int) -> str:
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

    def add_region(node: dict[str, Any]) -> None:
        nonlocal has_nav, has_sidebar
        child_name = str(node.get("name") or "")
        region_role, evidence = infer_region_role(child_name)
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
                "evidence": [f"name:{evidence}"],
            }
        )
        if region_role in ("nav", "menu"):
            has_nav = True
        if region_role == "sidebar":
            has_sidebar = True

    # Regions: root children + one level deeper (Menu/Nav often nest under Wrapper).
    for child in tree.get("children") or []:
        add_region(child)
        for grand in child.get("children") or []:
            add_region(grand)

    queue: deque[dict[str, Any]] = deque([tree])
    visited = 0
    while queue and visited < BFS_NODE_CAP:
        node = queue.popleft()
        visited += 1

        node_name = str(node.get("name") or "")
        node_type = str(node.get("type") or "")

        region_role, _ = infer_region_role(node_name)
        if region_role in ("nav", "menu"):
            has_nav = True
        if region_role == "sidebar":
            has_sidebar = True

        if FORM_HINTS.search(node_name):
            has_form = True

        instance_of = node.get("instanceOf")
        if instance_of:
            component_key = str(instance_of)
            if component_key not in seen_components and len(components_used) < COMPONENT_CAP:
                seen_components.add(component_key)
                components_used.append(component_key)
            if FORM_HINTS.search(node_name):
                has_form = True
        elif node_type in ("INSTANCE", "SYMBOL", "COMPONENT"):
            component_key = node_name or str(node.get("id") or "")
            if (
                component_key
                and component_key not in seen_components
                and len(components_used) < COMPONENT_CAP
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

        if content and content not in seen_texts and len(texts) < TEXT_CAP:
            seen_texts.add(content)
            texts.append(truncate_text(content, TEXT_MAX_LEN))

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
    stripped = ROUTE_PREFIX_RE.sub("", screen_name.strip())
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


def load_tree(design: Path, tree_rel: str) -> dict[str, Any] | None:
    path = design / tree_rel
    if not path.is_file():
        return None
    return orjson.loads(path.read_bytes())


def discover_tree_files(trees_dir: Path) -> dict[str, str]:
    discovered: dict[str, str] = {}
    if not trees_dir.is_dir():
        return discovered
    for path in sorted(trees_dir.glob("*.json")):
        if path.name == "index.json":
            continue
        discovered[path.stem] = f"trees/{path.name}"
    return discovered


def llm_guide(extract_header: dict[str, Any] | None = None) -> str:
    """Static read-order instructions, optionally prefixed with per-extract facts."""
    static = [
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
        "   variables from `tokens.css` when values match via `styleRefs` / `variableRefs`.",
        "4. For `INSTANCE` nodes, look up `instanceOf` in `components.json` and reuse a shared",
        "   HTML partial; pick the variant that matches visible props when needed.",
        "5. Map `text` nodes to semantic HTML (`h1`–`h6`, `p`, `button`, `label`) using content",
        "   and weight/size.",
        "6. Use `regions` in `ui-flow.json` to structure `<header>`, `<nav>`, `<aside>`,",
        "   `<main>`, and `<footer>` wrappers.",
        "",
        "## Routes",
        "",
        "`suggestedRoutes` in `ui-flow.json` are slug guesses marked `inferred: true`. "
        "Follow `interactions` for prototype edges when the file defines them. "
        "Crop screens with specimen/gallery semantic are omitted from the primary route list.",
        "",
        "## Assets",
        "",
        "Reference images by hash under `assets/` when tree nodes specify `\"type\": \"image\"`. "
        "Shared vectors use `vectorRef` → `assets/svg/<id>.svg` (see `assets/vectors.json` "
        "and `assets/index.json`).",
        "",
        "## What not to use",
        "",
        "- Raw `extracted/nodes.ndjson` unless you need fields missing from trees.",
        "- Screens without a `tree` field were skipped or too large — infer lightly from",
        "  `screens.json` only.",
        "",
    ]
    if not extract_header:
        return "\n".join(static)
    header = [
        "# Extraction summary",
        "",
        f"- **Source:** {extract_header.get('source') or 'unknown'}",
        f"- **Schema version:** {extract_header.get('schemaVersion', 2)}",
        f"- **Screens:** {extract_header.get('screens', 0)} "
        f"({extract_header.get('primaryScreens', extract_header.get('screens', 0))} primary)",
        f"- **Components:** {extract_header.get('components', 0)}",
        f"- **Color styles:** {extract_header.get('colorStyles', 0)}",
        f"- **Variables:** {extract_header.get('variables', 0)}",
        f"- **Raster assets:** {extract_header.get('rasters', 0)}",
        f"- **Vector assets:** {extract_header.get('vectors', 0)}",
        "",
        "## Indexes",
        "",
        "- `manifest.json` — root counts and paths",
        "- `screens.json` / `ui-flow.json` — screen inventory",
        "- `trees/index.json` — tree paths",
        "- `assets/index.json` — rasters + vectors",
        "- `screens/<slug>/screen.json` — per-screen reference bundle",
        "",
        "---",
        "",
    ]
    return "\n".join(header + static)


def extract_llm_header(design: Path, screens: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-file counts for the generated top of ``LLM.md``."""
    components = _json_list(design / "components.json")
    color_flat = _json_obj(design / "tokens" / "color-styles.flat.json")
    variables = _json_obj(design / "tokens" / "variables.json")
    assets = _json_list(design / "assets" / "manifest.json")
    vectors = _json_list(design / "assets" / "vectors.json")
    rasters = [
        row
        for row in assets
        if isinstance(row, dict) and row.get("kind") not in {"vector", "svg"}
    ]
    source_name = design.name
    meta_path = design / "manifest.json"
    if meta_path.is_file():
        meta = orjson.loads(meta_path.read_bytes())
        if isinstance(meta, dict) and meta.get("source"):
            source_name = str(meta["source"])
    primary = [
        screen
        for screen in screens
        if not _is_specimen_crop(screen)
    ]
    return {
        "source": source_name,
        "schemaVersion": 2,
        "screens": len(screens),
        "primaryScreens": len(primary),
        "components": len(components),
        "colorStyles": len(color_flat) if isinstance(color_flat, dict) else 0,
        "variables": len((variables or {}).get("variables") or []) if isinstance(variables, dict) else 0,
        "rasters": len(rasters),
        "vectors": len(vectors),
    }


def _is_specimen_crop(screen: dict[str, Any]) -> bool:
    semantic = screen.get("semantic") if isinstance(screen.get("semantic"), dict) else {}
    kind = semantic.get("kind") if isinstance(semantic, dict) else None
    if screen.get("origin") == "crop" and kind in {"specimens", "component-gallery"}:
        return True
    if kind in {"specimens", "component-gallery"}:
        return True
    return screen.get("role") == "component-gallery"


def _json_list(path: Path) -> list[Any]:
    if not path.is_file():
        return []
    payload = orjson.loads(path.read_bytes())
    return payload if isinstance(payload, list) else []


def _json_obj(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = orjson.loads(path.read_bytes())
    return payload if isinstance(payload, dict) else {}


def write_screen_bundles(
    design: Path,
    screens: list[dict[str, Any]],
    flow_by_id: dict[str, dict[str, Any]],
    suggested_routes: list[dict[str, Any]],
) -> None:
    """Write ``screens/<slug>/screen.json`` reference bundles (no embedded trees)."""
    routes_by_slug = {
        str(route.get("screen")): route
        for route in suggested_routes
        if isinstance(route, dict) and route.get("screen")
    }
    for screen in screens:
        if not isinstance(screen, dict):
            continue
        slug_key = str(screen.get("slug") or screen.get("id") or "screen")
        flow = flow_by_id.get(str(screen.get("id") or ""), {})
        reconstruction = _reconstruction_hints(design, screen, flow)
        bundle: dict[str, Any] = {
            "id": screen.get("id"),
            "name": screen.get("name"),
            "slug": slug_key,
            "page": screen.get("page"),
            "width": screen.get("width"),
            "height": screen.get("height"),
            "tree": screen.get("tree"),
            "role": screen.get("role") or flow.get("role"),
            "origin": screen.get("origin"),
            "schemaVersion": 2,
        }
        if screen.get("sourceScreenId"):
            bundle["sourceScreenId"] = screen["sourceScreenId"]
        if screen.get("boardTree"):
            bundle["boardTree"] = screen["boardTree"]
        if screen.get("semantic"):
            bundle["semantic"] = screen["semantic"]
        if flow.get("regions"):
            bundle["regions"] = flow["regions"]
        if flow.get("sampleText"):
            bundle["sampleText"] = flow["sampleText"]
        elif flow.get("texts"):
            bundle["sampleText"] = flow["texts"]
        if flow.get("componentsUsed"):
            bundle["componentIds"] = flow["componentsUsed"]
        route = routes_by_slug.get(slug_key)
        if route:
            bundle["route"] = route
        if reconstruction:
            bundle["reconstruction"] = reconstruction
        write_json(design / "screens" / slug_key / "screen.json", bundle)


def _reconstruction_hints(
    design: Path,
    screen: dict[str, Any],
    flow: dict[str, Any],
) -> list[dict[str, str]]:
    """Deterministic recommended hints from fields that already exist."""
    hints: list[dict[str, str]] = []
    semantic = screen.get("semantic") if isinstance(screen.get("semantic"), dict) else {}
    kind = semantic.get("kind") if isinstance(semantic, dict) else None
    if kind in {"button", "icon-button"}:
        hints.append({"kind": "recommended", "hint": kind, "evidence": "semantic.kind"})
    if flow.get("hasForm"):
        hints.append({"kind": "recommended", "hint": "form", "evidence": "ui-flow.hasForm"})
    if flow.get("hasNav"):
        hints.append({"kind": "recommended", "hint": "nav", "evidence": "ui-flow.hasNav"})

    tree_rel = screen.get("tree")
    if not tree_rel:
        return hints
    tree = load_tree(design, str(tree_rel))
    if not isinstance(tree, dict):
        return hints
    layout = tree.get("layout") if isinstance(tree.get("layout"), dict) else {}
    if layout.get("dir"):
        hints.append(
            {
                "kind": "recommended",
                "hint": "flex",
                "evidence": f"layout.dir:{layout['dir']}",
            }
        )
    seen_ref = False
    stack: list[dict[str, Any]] = [tree]
    visited = 0
    while stack and visited < 200:
        node = stack.pop()
        visited += 1
        if node.get("vectorRef") and not seen_ref:
            hints.append(
                {
                    "kind": "recommended",
                    "hint": "svg-reference",
                    "evidence": f"vectorRef:{node['vectorRef']}",
                }
            )
            seen_ref = True
        for child in node.get("children") or []:
            if isinstance(child, dict):
                stack.append(child)

    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in hints:
        key = (item.get("hint") or "", item.get("evidence") or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def build_components_index(design: Path) -> dict[str, Any] | None:
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


def extract_prototype_interactions(out: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read prototype edges from the decoded node stream.

    Returns ``(interactions, diagnostics)``. Interactions are source facts.
    Missing destinations are kept with ``toId: null`` and a diagnostic row.
    """
    path = nodes_path(out)
    if not path.is_file():
        # Intermediates may already be cleaned; try nothing.
        return [], []
    known_ids = set()
    pending: list[tuple[str, dict[str, Any]]] = []
    for raw in iter_ndjson(path):
        node_id = gid(raw.get("guid"))
        if node_id:
            known_ids.add(node_id)
        interactions = raw.get("prototypeInteractions")
        if not isinstance(interactions, list) or not interactions:
            continue
        if not node_id:
            continue
        for entry in interactions:
            if not isinstance(entry, dict) or entry.get("isDeleted"):
                continue
            pending.append((node_id, entry))

    results: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for from_id, entry in pending:
        event = entry.get("event") or {}
        trigger = event.get("interactionType") if isinstance(event, dict) else None
        actions = entry.get("actions") if isinstance(entry.get("actions"), list) else []
        if not actions:
            results.append(
                {
                    "id": gid(entry.get("id")) or f"{from_id}:{len(results)}",
                    "fromId": from_id,
                    "trigger": trigger,
                    "toId": None,
                    "navigation": None,
                }
            )
            diagnostics.append({"fromId": from_id, "reason": "missing-action"})
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            to_id = gid(action.get("transitionNodeID"))
            item = {
                "id": gid(entry.get("id")) or f"{from_id}:{len(results)}",
                "fromId": from_id,
                "trigger": trigger,
                "toId": to_id,
                "navigation": action.get("navigationType"),
            }
            if action.get("connectionType"):
                item["connection"] = action.get("connectionType")
            if action.get("transitionType"):
                item["transition"] = action.get("transitionType")
            results.append(item)
            if to_id is None:
                diagnostics.append({"fromId": from_id, "reason": "missing-target"})
            elif to_id not in known_ids:
                diagnostics.append(
                    {"fromId": from_id, "toId": to_id, "reason": "unknown-target"}
                )
    return results, diagnostics


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
    discovered_trees = discover_tree_files(trees_dir)

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
    flow_by_id: dict[str, dict[str, Any]] = {}
    interactions, interaction_diagnostics = extract_prototype_interactions(out)
    interactions_by_from = {}
    for item in interactions:
        interactions_by_from.setdefault(str(item["fromId"]), []).append(item["id"])

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
        if screen.get("origin"):
            flow_screen["origin"] = screen["origin"]
        if screen.get("sourceScreenId"):
            flow_screen["sourceScreenId"] = screen["sourceScreenId"]

        role = infer_role(str(screen.get("name") or ""), page_name)
        flow_screen["role"] = role
        semantic = screen.get("semantic") if isinstance(screen.get("semantic"), dict) else None
        if not semantic and tree_rel:
            tree_for_semantic = load_tree(design, tree_rel)
            if tree_for_semantic:
                from figma_extractor.extract.semantic import screen_semantic

                semantic = screen_semantic(screen, tree_for_semantic)
                if semantic:
                    screen["semantic"] = semantic
        if semantic:
            flow_screen["semantic"] = semantic

        if tree_rel:
            flow_screen["tree"] = tree_rel
            tree = load_tree(design, tree_rel)
            if tree:
                screens_with_trees += 1
                scan = scan_tree(tree)
                flow_screen.update(scan)

                screen["role"] = role
                screen["regions"] = [
                    {
                        "role": r["role"],
                        "name": r["name"],
                        **({"evidence": r["evidence"]} if r.get("evidence") else {}),
                    }
                    for r in scan["regions"]
                ]

                roles_count[role] = roles_count.get(role, 0) + 1

                screen_ids = collect_node_ids(tree)
                linked = []
                for node_id in screen_ids:
                    linked.extend(interactions_by_from.get(node_id) or [])
                if linked:
                    flow_screen["interactionIds"] = sorted(set(linked))

                exclude_route = (
                    role == "component-gallery"
                    or _is_specimen_crop({**screen, "role": role, "semantic": semantic or {}})
                )
                if not exclude_route:
                    route_path = suggest_route_path(str(screen.get("name") or ""), page_name, role)
                    if route_path not in seen_paths:
                        seen_paths.add(route_path)
                        suggested_routes.append(
                            {
                                "path": route_path,
                                "screen": screen_slug,
                                "page": page_name,
                                "role": role,
                                "inferred": True,
                            }
                        )

        flow_by_id[str(screen.get("id") or "")] = flow_screen
        page_entry["screens"].append(flow_screen)

    pages = sorted(pages_map.values(), key=lambda item: item["name"])
    summary = {
        "pages": len(pages),
        "screens": len(screens),
        "screensWithTrees": screens_with_trees,
        "roles": dict(sorted(roles_count.items())),
        "suggestedRouteCount": len(suggested_routes),
        "interactionCount": len(interactions),
    }

    write_json(
        design / "ui-flow.json",
        {
            "summary": summary,
            "pages": pages,
            "suggestedRoutes": sorted(suggested_routes, key=lambda item: item["path"]),
            "interactions": interactions,
        },
    )
    if interaction_diagnostics:
        write_json(design / "diagnostics" / "interactions.json", interaction_diagnostics)
    else:
        write_json(design / "diagnostics" / "interactions.json", [])
    write_json(screens_path, screens)
    header = extract_llm_header(design, screens)
    write_text(design / "LLM.md", llm_guide(header))
    write_screen_bundles(design, screens, flow_by_id, suggested_routes)

    components_index = build_components_index(design)
    if components_index is not None:
        write_json(design / "components" / "index.json", components_index)

    console.print(
        f"[green]UI flow[/] {screens_with_trees} trees · "
        f"{len(suggested_routes)} routes · {len(interactions)} interactions · "
        f"{len(pages)} pages → {design}"
    )
    return summary


def collect_node_ids(node: dict[str, Any], *, budget: int = 4000) -> set[str]:
    found: set[str] = set()
    stack = [node]
    while stack and len(found) < budget:
        current = stack.pop()
        if not isinstance(current, dict):
            continue
        node_id = current.get("id")
        if node_id is not None:
            found.add(str(node_id))
        for child in current.get("children") or []:
            if isinstance(child, dict):
                stack.append(child)
    return found
