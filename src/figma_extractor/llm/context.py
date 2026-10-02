"""Task-sized context built from an extract. Full trees are not sent to a model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import orjson

from figma_extractor.llm.prompt_format import context_size


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return orjson.loads(path.read_bytes())


def build_task_context(directory: Path, tasks: list[str], max_chars: int) -> dict[str, Any]:
    """Return one JSON-serializable payload per enabled task."""
    screens = load_json(directory / "screens.json", [])
    if not isinstance(screens, list):
        screens = []
    sets = load_json(directory / "component-sets.json", [])
    if not isinstance(sets, list):
        sets = []
    manifest = load_json(directory / "assets" / "manifest.json", {})
    context: dict[str, Any] = {}
    for task in tasks:
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
    return fit_context(context, max_chars)


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


def fit_context(context: dict[str, Any], max_chars: int) -> dict[str, Any]:
    """Drop trailing list entries until the TOON text fits the configured budget."""
    if context_size(context) <= max_chars:
        return context
    fitted = json.loads(json.dumps(context, default=str))
    for payload in fitted.values():
        if not isinstance(payload, dict):
            continue
        for value in payload.values():
            if isinstance(value, list) and len(value) > 1:
                value[:] = value[: max(1, len(value) // 2)]
    if context_size(fitted) > max_chars:
        return {"truncated": True, "tasks": sorted(context)}
    return fitted
