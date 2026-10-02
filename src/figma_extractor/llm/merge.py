"""Apply validated model output onto annotation rows without editing extract JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return orjson.loads(path.read_bytes())


def merge_llm_results(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Later tasks in ``current`` replace the same keys in ``previous``."""
    merged = dict(previous)
    merged.update(current)
    return merged


def task_validated(validation: list[dict[str, Any]], task: str) -> bool:
    return any(
        isinstance(item, dict) and item.get("task") == task and item.get("ok") for item in validation
    )


def apply_llm_overlays(
    screens: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    results: dict[str, Any],
    validation: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Attach ``llm`` overlays from validated task payloads."""
    screen_rows = [dict(row) for row in screens]
    node_rows = [dict(row) for row in nodes]
    asset_rows = [dict(row) for row in assets]

    if task_validated(validation, "screen_classification"):
        by_screen = {str(row.get("id")): row for row in screen_rows if row.get("id") is not None}
        for item in _items(results, "screen_classification"):
            screen_id = str(item.get("screen_id"))
            if screen_id in by_screen:
                by_screen[screen_id]["llm"] = _screen_overlay(item)

    if task_validated(validation, "semantic_classification"):
        by_node = {str(row.get("id")): row for row in node_rows if row.get("id") is not None}
        for item in _items(results, "semantic_classification"):
            node_id = str(item.get("node_id"))
            overlay = _semantic_overlay(item)
            if node_id in by_node:
                by_node[node_id]["llm"] = overlay
            else:
                node_rows.append({"id": node_id, "llm": overlay})

    if task_validated(validation, "asset_analysis"):
        by_hash = {str(row.get("hash")): row for row in asset_rows if row.get("hash") is not None}
        for item in _items(results, "asset_analysis"):
            asset_id = str(item.get("asset_id"))
            overlay = _asset_overlay(item)
            if asset_id in by_hash:
                by_hash[asset_id]["llm"] = overlay
            else:
                asset_rows.append({"hash": asset_id, "llm": overlay})

    return screen_rows, node_rows, asset_rows


def stitch_incremental_annotations(
    directory: Path,
    screens: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    results: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Keep prior overlays for screens whose trees did not change."""
    from figma_extractor.catalog import changed_screen_ids

    changed = changed_screen_ids(directory)
    if changed is None:
        return screens, nodes, results
    prior = load_json(directory / "llm-annotations.json", {})
    if not isinstance(prior, dict):
        return screens, nodes, results
    prior_results = prior.get("llmResults")
    if not isinstance(prior_results, dict):
        prior_results = {}
    merged_results = merge_llm_results(prior_results, results)

    prior_screens = prior.get("screens")
    if not isinstance(prior_screens, list):
        return screens, nodes, merged_results

    prior_by_id = {
        str(row.get("id")): row for row in prior_screens if isinstance(row, dict) and row.get("id")
    }
    out_screens = []
    for row in screens:
        screen_id = str(row.get("id"))
        if screen_id not in changed and screen_id in prior_by_id:
            prior_row = prior_by_id[screen_id]
            merged = dict(row)
            if prior_row.get("llm"):
                merged["llm"] = prior_row["llm"]
            out_screens.append(merged)
        else:
            out_screens.append(row)

    prior_nodes = prior.get("nodes")
    if isinstance(prior_nodes, list) and not changed:
        return out_screens, prior_nodes, merged_results
    return out_screens, nodes, merged_results


def _items(results: dict[str, Any], task: str) -> list[dict[str, Any]]:
    payload = results.get(task)
    if not isinstance(payload, dict):
        return []
    raw = payload.get("items")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _screen_overlay(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": "screen_classification",
        "role": item.get("role"),
        "slug": item.get("slug"),
        "confidence": item.get("confidence"),
        "evidence": item.get("evidence"),
        "inferred": item.get("inferred"),
    }


def _semantic_overlay(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": "semantic_classification",
        "semanticType": item.get("semantic_type"),
        "confidence": item.get("confidence"),
        "reasoning": item.get("reasoning"),
    }


def _asset_overlay(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": "asset_analysis",
        "role": item.get("role"),
        "confidence": item.get("confidence"),
        "evidence": item.get("evidence"),
    }
