"""Task-sized context built from an extract. Full trees are not sent to a model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson

from figma_extractor.llm.prompt_format import context_size


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return orjson.loads(path.read_bytes())


def build_raw_task_context(directory: Path, tasks: list[str]) -> dict[str, Any]:
    """Return one JSON-serializable payload per enabled task, before budget packing."""
    screens = load_json(directory / "screens.json", [])
    if not isinstance(screens, list):
        screens = []
    from figma_extractor.catalog import changed_screen_ids

    changed = changed_screen_ids(directory)
    if changed is not None:
        screens = [row for row in screens if str(row.get("id")) in changed]
    sets = load_json(directory / "component-sets.json", [])
    if not isinstance(sets, list):
        sets = []
    context: dict[str, Any] = {}
    screen_tasks = {
        "semantic_classification",
        "screen_classification",
        "svg_analysis",
        "reconstruction_hints",
        "interaction_analysis",
        "responsive_analysis",
        "pattern_synthesis",
    }
    for task in tasks:
        if changed is not None and not screens and task in screen_tasks:
            continue
        if task == "screen_classification":
            context[task] = screen_payload(screens)
        elif task == "component_analysis":
            context[task] = component_payload(sets)
        elif task == "svg_analysis":
            context[task] = svg_payload(directory, screens)
        elif task == "semantic_classification":
            context[task] = semantic_payload(directory, screens)
        elif task == "reconstruction_hints":
            context[task] = reconstruction_payload(directory, screens)
        elif task == "asset_analysis":
            context[task] = asset_payload(directory)
        elif task == "interaction_analysis":
            context[task] = interaction_payload(directory, screens)
        elif task == "responsive_analysis":
            context[task] = responsive_payload(screens)
        elif task == "component_synthesis":
            context[task] = synthesis_payload(sets, note="Propose a component only when several rows repeat.")
        elif task == "pattern_synthesis":
            context[task] = pattern_payload(screens)
        elif task == "prompt_optimization":
            context[task] = {"tasks": [name for name in tasks if name != "prompt_optimization"]}
    return context


def build_task_context(
    directory: Path,
    tasks: list[str],
    max_chars: int,
    *,
    compact: bool = False,
    max_tokens: int | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Build per-task payloads and pack them to the character budget."""
    raw = build_raw_task_context(directory, tasks)
    return fit_context(raw, max_chars, compact=compact, max_tokens=max_tokens, model=model)


def screen_rows(screens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for screen in screens[:40]:
        rows.append(
            {
                "id": screen.get("id"),
                "name": screen.get("name"),
                "slug": screen.get("slug"),
                "width": screen.get("width"),
                "height": screen.get("height"),
                "role": screen.get("role"),
                "regions": screen.get("regions") or [],
                "tree": screen.get("tree"),
            }
        )
    return rows


def screen_payload(screens: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "note": "Roles already on these screens came from name keywords. Correct only with evidence.",
        "screens": screen_rows(screens),
    }


def component_payload(sets: list[dict[str, Any]]) -> dict[str, Any]:
    slim = []
    for entry in sets[:30]:
        axes = entry.get("axes") or {}
        slim.append(
            {
                "id": entry.get("id"),
                "name": entry.get("name"),
                "page": entry.get("page"),
                "variantCount": entry.get("variantCount"),
                "axisNames": sorted(axes) if isinstance(axes, dict) else [],
            }
        )
    return {"componentSets": slim}


def semantic_payload(directory: Path, screens: list[dict[str, Any]]) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    for screen in screens[:3]:
        tree_rel = screen.get("tree")
        if not tree_rel:
            continue
        tree = load_json(directory / str(tree_rel), None)
        if isinstance(tree, dict):
            walk_nodes(tree, samples, budget=40)
    return {"nodes": samples[:40]}


def svg_payload(directory: Path, screens: list[dict[str, Any]]) -> dict[str, Any]:
    found: list[dict[str, Any]] = []
    for screen in screens[:4]:
        tree_rel = screen.get("tree")
        if not tree_rel:
            continue
        tree = load_json(directory / str(tree_rel), None)
        if isinstance(tree, dict):
            collect_vectors(tree, found, budget=12)
    return {
        "note": "Path commands were omitted. Use these records only as structure.",
        "vectors": found[:12],
    }


def reconstruction_payload(directory: Path, screens: list[dict[str, Any]]) -> dict[str, Any]:
    chosen = next((screen for screen in screens if screen.get("tree")), None)
    if chosen is None:
        return {"screen": None, "layout": None}
    tree = load_json(directory / str(chosen["tree"]), None)
    layout = layout_skeleton(tree, depth=0) if isinstance(tree, dict) else None
    return {
        "screen": {
            "id": chosen.get("id"),
            "name": chosen.get("name"),
            "slug": chosen.get("slug"),
            "role": chosen.get("role"),
        },
        "layout": layout,
    }


def asset_payload(directory: Path) -> dict[str, Any]:
    manifest = load_json(directory / "assets" / "manifest.json", [])
    rows = manifest if isinstance(manifest, list) else []
    if isinstance(manifest, dict):
        images = manifest.get("images")
        rows = images if isinstance(images, list) else []
    slim = []
    for entry in rows[:30]:
        if not isinstance(entry, dict):
            continue
        slim.append(
            {
                "assetId": entry.get("hash"),
                "mime": entry.get("mime"),
                "w": entry.get("width"),
                "h": entry.get("height"),
                "usageCount": entry.get("usageCount"),
            }
        )
    return {
        "note": "Proposals annotate asset ids. They do not replace the file path.",
        "assets": slim,
    }


def interaction_payload(directory: Path, screens: list[dict[str, Any]]) -> dict[str, Any]:
    flow = load_json(directory / "ui-flow.json", {})
    routes = flow.get("suggestedRoutes") if isinstance(flow, dict) else None
    return {
        "screens": [{"id": row.get("id"), "name": row.get("name"), "slug": row.get("slug")} for row in screens[:20]],
        "routes": routes if isinstance(routes, list) else [],
    }


def responsive_payload(screens: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "screens": [
            {"id": row.get("id"), "name": row.get("name"), "w": row.get("width"), "h": row.get("height")}
            for row in screens[:20]
        ]
    }


def synthesis_payload(sets: list[dict[str, Any]], *, note: str) -> dict[str, Any]:
    rows = []
    for entry in sets[:20]:
        if not isinstance(entry, dict):
            continue
        rows.append({"id": entry.get("id"), "name": entry.get("name"), "variantCount": entry.get("variantCount")})
    return {"note": note + " origin must be llm_proposed.", "componentSets": rows}


def pattern_payload(screens: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "note": "A pattern is a proposal. origin must be llm_proposed.",
        "screens": [
            {"id": row.get("id"), "name": row.get("name"), "role": row.get("role")}
            for row in screens[:20]
        ],
    }


def layout_skeleton(node: dict[str, Any], depth: int) -> dict[str, Any]:
    layout = node.get("layout") if isinstance(node.get("layout"), dict) else {}
    skeleton: dict[str, Any] = {
        "id": node.get("id"),
        "type": node.get("type"),
        "name": node.get("name"),
        "w": node.get("w"),
        "h": node.get("h"),
    }
    if layout.get("dir"):
        skeleton["dir"] = layout.get("dir")
        skeleton["gap"] = layout.get("gap")
    if depth >= 3:
        return skeleton
    children = node.get("children") or []
    skeleton["children"] = [
        layout_skeleton(child, depth + 1)
        for child in children[:8]
        if isinstance(child, dict)
    ]
    return skeleton


def walk_nodes(node: dict[str, Any], samples: list[dict[str, Any]], budget: int) -> None:
    if len(samples) >= budget or not isinstance(node, dict):
        return
    samples.append(
        {"id": node.get("id"), "type": node.get("type"), "name": node.get("name")}
    )
    for child in node.get("children") or []:
        if len(samples) >= budget:
            return
        if isinstance(child, dict):
            walk_nodes(child, samples, budget)


def collect_vectors(node: dict[str, Any], found: list[dict[str, Any]], budget: int) -> None:
    if len(found) >= budget or not isinstance(node, dict):
        return
    if node.get("type") == "VECTOR" or node.get("paths"):
        found.append(
            {
                "id": node.get("id"),
                "name": node.get("name"),
                "w": node.get("w"),
                "h": node.get("h"),
                "hasPath": bool(node.get("paths")),
            }
        )
    for child in node.get("children") or []:
        if len(found) >= budget:
            return
        if isinstance(child, dict):
            collect_vectors(child, found, budget)


def fit_context(
    context: dict[str, Any],
    max_chars: int,
    *,
    compact: bool = False,
    max_tokens: int | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Drop the lowest-value rows until the TOON user text fits the budget."""
    from figma_extractor.llm.prompt_format import context_token_size
    from figma_extractor.toon.optimize import pack_context

    char_measure = lambda ctx: context_size(ctx, compact=compact)
    token_measure = lambda ctx: context_token_size(ctx, compact=compact, model=model)
    return pack_context(
        context,
        max_chars,
        char_measure,
        max_tokens=max_tokens,
        token_measure=token_measure if max_tokens is not None else None,
    )
