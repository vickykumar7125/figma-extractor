"""Validation for model JSON. No Pydantic import, so disabled mode stays light."""

from __future__ import annotations

from typing import Any

TASK_ITEM_FIELDS: dict[str, tuple[str, ...]] = {
    "semantic_classification": ("node_id", "semantic_type", "confidence", "reasoning"),
    "screen_classification": ("screen_id", "slug", "role", "confidence", "evidence", "inferred"),
    "component_analysis": ("component_id", "name", "suggested_element", "confidence", "evidence"),
    "svg_analysis": ("node_id", "kind", "reusable", "confidence", "evidence"),
    "reconstruction_hints": ("screen_id", "hint", "kind"),
}

JSON_SCHEMA_HINT: dict[str, str] = {
    "semantic_classification": (
        '{"items":[{"node_id":"...","semantic_type":"button","confidence":0.0,"reasoning":["..."]}]}'
    ),
    "screen_classification": (
        '{"items":[{"screen_id":"...","slug":"...","role":"page","confidence":0.0,'
        '"evidence":["..."],"inferred":true}]}'
    ),
    "component_analysis": (
        '{"items":[{"component_id":"...","name":"...","suggested_element":"button",'
        '"confidence":0.0,"evidence":["..."]}]}'
    ),
    "svg_analysis": (
        '{"items":[{"node_id":"...","kind":"icon","reusable":true,"confidence":0.0,"evidence":["..."]}]}'
    ),
    "reconstruction_hints": (
        '{"items":[{"screen_id":"...","hint":"...","kind":"recommended"}]}'
    ),
}


def validate_task_payload(task: str, payload: Any) -> list[str]:
    """Return a list of problems. An empty list means the payload is usable."""
    if task not in TASK_ITEM_FIELDS:
        return [f"unknown task {task}"]
    if not isinstance(payload, dict):
        return ["response must be a JSON object"]
    items = payload.get("items")
    if not isinstance(items, list):
        return ["response must contain an items array"]
    problems: list[str] = []
    for index, item in enumerate(items):
        problems.extend(validate_item(task, item, index))
    return problems


def validate_item(task: str, item: Any, index: int) -> list[str]:
    if not isinstance(item, dict):
        return [f"items[{index}] must be an object"]
    problems: list[str] = []
    for name in TASK_ITEM_FIELDS[task]:
        if name not in item:
            problems.append(f"items[{index}] missing {name}")
    if "confidence" in item and not confidence_in_range(item.get("confidence")):
        problems.append(f"items[{index}].confidence must be a number from 0 to 1")
    if task == "reconstruction_hints" and item.get("kind") != "recommended":
        problems.append(f"items[{index}].kind must be 'recommended'")
    if task == "screen_classification" and "inferred" in item and not isinstance(item["inferred"], bool):
        problems.append(f"items[{index}].inferred must be a boolean")
    if task == "svg_analysis" and "reusable" in item and not isinstance(item["reusable"], bool):
        problems.append(f"items[{index}].reusable must be a boolean")
    for list_field in ("evidence", "reasoning"):
        if list_field in item and not string_list(item[list_field]):
            problems.append(f"items[{index}].{list_field} must be an array of strings")
    return problems


def confidence_in_range(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= float(value) <= 1


def string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(entry, str) for entry in value)
