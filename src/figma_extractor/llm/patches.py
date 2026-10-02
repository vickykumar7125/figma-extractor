"""Normalize compact patch-style model replies into the usual ``items`` arrays."""

from __future__ import annotations

from typing import Any

PATCH_TASKS = frozenset(
    {
        "semantic_classification",
        "screen_classification",
        "component_analysis",
        "svg_analysis",
        "reconstruction_hints",
        "asset_analysis",
        "interaction_analysis",
        "responsive_analysis",
        "component_synthesis",
        "pattern_synthesis",
    }
)
ALLOWED_OPS = frozenset({"annotate", "propose"})


def canonicalize_response(task: str, payload: Any) -> Any:
    """Ensure ``items`` is present when the model returned ``ops`` instead."""
    if task not in PATCH_TASKS or not isinstance(payload, dict):
        return payload
    if isinstance(payload.get("items"), list):
        return payload
    ops = payload.get("ops")
    if not isinstance(ops, list):
        return payload
    items = ops_to_items(task, ops)
    merged = dict(payload)
    merged["items"] = items
    return merged


def validate_ops(task: str, ops: Any) -> list[str]:
    if task not in PATCH_TASKS:
        return [f"task {task} does not accept ops"]
    if not isinstance(ops, list):
        return ["ops must be an array"]
    problems: list[str] = []
    for index, op in enumerate(ops):
        problems.extend(validate_op(task, op, index))
    return problems


def validate_op(task: str, op: Any, index: int) -> list[str]:
    if not isinstance(op, dict):
        return [f"ops[{index}] must be an object"]
    problems: list[str] = []
    name = op.get("op")
    if name not in ALLOWED_OPS:
        problems.append(f"ops[{index}].op must be annotate or propose")
    target = op.get("target")
    if not isinstance(target, dict):
        problems.append(f"ops[{index}].target must be an object")
    changes = op.get("changes")
    if changes is not None and not isinstance(changes, dict):
        problems.append(f"ops[{index}].changes must be an object")
    return problems


def ops_to_items(task: str, ops: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for op in ops:
        if isinstance(op, dict):
            items.append(op_to_item(task, op))
    return items


def op_to_item(task: str, op: dict[str, Any]) -> dict[str, Any]:
    target = dict(op.get("target") or {})
    changes = dict(op.get("changes") or {})
    item = {**target, **changes}
    for field in ("confidence", "evidence", "reasoning", "inferred", "reusable", "origin", "targets"):
        if field in op and field not in item:
            item[field] = op[field]
    if task in {"component_synthesis", "pattern_synthesis"} and "origin" not in item:
        item["origin"] = "llm_proposed"
    if task in {"reconstruction_hints", "interaction_analysis", "responsive_analysis"} and "kind" not in item:
        item["kind"] = "recommended"
    return item
