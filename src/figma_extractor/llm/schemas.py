"""Validation for model JSON. No Pydantic import, so disabled mode stays light."""

from __future__ import annotations

from typing import Any

from figma_extractor.llm.patches import PATCH_TASKS, canonicalize_response, validate_ops

TASK_ITEM_FIELDS: dict[str, tuple[str, ...]] = {
    "semantic_classification": ("node_id", "semantic_type", "confidence", "reasoning"),
    "screen_classification": ("screen_id", "slug", "role", "confidence", "evidence", "inferred"),
    "component_analysis": ("component_id", "name", "suggested_element", "confidence", "evidence"),
    "svg_analysis": ("node_id", "kind", "reusable", "confidence", "evidence"),
    "reconstruction_hints": ("screen_id", "hint", "kind"),
    "asset_analysis": ("asset_id", "role", "confidence", "evidence"),
    "interaction_analysis": ("screen_id", "hint", "kind", "confidence", "evidence"),
    "responsive_analysis": ("screen_id", "hint", "kind", "confidence", "evidence"),
    "component_synthesis": ("name", "origin", "targets", "confidence", "evidence"),
    "pattern_synthesis": ("name", "origin", "confidence", "evidence"),
    "prompt_optimization": ("task", "proposal", "reason"),
}

PATCH_REPLY = (
    ' Alternate ops form: {"ops":[{"op":"annotate","target":{ID},"changes":{FIELDS},'
    '"confidence":0.0,"evidence":["..."]}]}'
)


JSON_SCHEMA_HINT: dict[str, str] = {
    "semantic_classification": (
        '{"items":[{"node_id":"...","semantic_type":"button","confidence":0.0,"reasoning":["..."]}]} '
        'or {"ops":[{"op":"annotate","target":{"node_id":"..."},"changes":{"semantic_type":"button"},'
        '"confidence":0.0,"reasoning":["..."]}]}'
    ),
    "screen_classification": (
        '{"items":[{"screen_id":"...","slug":"...","role":"page","confidence":0.0,'
        '"evidence":["..."],"inferred":true}]}' + PATCH_REPLY.replace("{ID}", '"screen_id":"..."').replace("{FIELDS}", '"slug":"..."')
    ),
    "component_analysis": (
        '{"items":[{"component_id":"...","name":"...","suggested_element":"button",'
        '"confidence":0.0,"evidence":["..."]}]}' + PATCH_REPLY.replace("{ID}", '"component_id":"..."').replace("{FIELDS}", '"suggested_element":"button"')
    ),
    "svg_analysis": (
        '{"items":[{"node_id":"...","kind":"icon","reusable":true,"confidence":0.0,"evidence":["..."]}]}'
        + PATCH_REPLY.replace("{ID}", '"node_id":"..."').replace("{FIELDS}", '"kind":"icon"')
    ),
    "reconstruction_hints": (
        '{"items":[{"screen_id":"...","hint":"...","kind":"recommended"}]}'
        + PATCH_REPLY.replace("{ID}", '"screen_id":"..."').replace("{FIELDS}", '"hint":"..."')
    ),
    "asset_analysis": (
        '{"items":[{"asset_id":"...","role":"icon","confidence":0.0,"evidence":["..."]}]}'
        + PATCH_REPLY.replace("{ID}", '"asset_id":"..."').replace("{FIELDS}", '"role":"icon"')
    ),
    "interaction_analysis": (
        '{"items":[{"screen_id":"...","hint":"...","kind":"recommended","confidence":0.0,"evidence":["..."]}]}'
        + PATCH_REPLY.replace("{ID}", '"screen_id":"..."').replace("{FIELDS}", '"hint":"..."')
    ),
    "responsive_analysis": (
        '{"items":[{"screen_id":"...","hint":"...","kind":"recommended","confidence":0.0,"evidence":["..."]}]}'
        + PATCH_REPLY.replace("{ID}", '"screen_id":"..."').replace("{FIELDS}", '"hint":"..."')
    ),
    "component_synthesis": (
        '{"items":[{"name":"ProductCard","origin":"llm_proposed","targets":["..."],'
        '"confidence":0.0,"evidence":["..."]}]}'
        + ' Alternate ops form: {"ops":[{"op":"propose","target":{"name":"ProductCard"},'
        '"changes":{"targets":["..."]},"confidence":0.0,"evidence":["..."]}]}'
    ),
    "pattern_synthesis": (
        '{"items":[{"name":"dashboard","origin":"llm_proposed","confidence":0.0,"evidence":["..."]}]}'
        + ' Alternate ops form: {"ops":[{"op":"propose","target":{"name":"dashboard"},'
        '"changes":{},"confidence":0.0,"evidence":["..."]}]}'
    ),
    "prompt_optimization": (
        '{"items":[{"task":"screen_classification","proposal":"...","reason":"..."}]}'
    ),
}


def validate_task_payload(task: str, payload: Any) -> list[str]:
    """Return a list of problems. An empty list means the payload is usable."""
    if task not in TASK_ITEM_FIELDS:
        return [f"unknown task {task}"]
    if not isinstance(payload, dict):
        return ["response must be a JSON object"]
    if task in PATCH_TASKS and isinstance(payload.get("ops"), list):
        problems = validate_ops(task, payload["ops"])
        if problems:
            return problems
        payload = canonicalize_response(task, payload)
    items = payload.get("items")
    if not isinstance(items, list):
        return ["response must contain an items array or ops array"]
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
    if task in {"reconstruction_hints", "interaction_analysis", "responsive_analysis"}:
        if "kind" in item and item.get("kind") != "recommended":
            problems.append(f"items[{index}].kind must be 'recommended'")
    if task in {"component_synthesis", "pattern_synthesis"} and "origin" in item:
        if item.get("origin") != "llm_proposed":
            problems.append(f"items[{index}].origin must be 'llm_proposed'")
    if task == "component_synthesis" and "targets" in item and not string_list(item.get("targets")):
        problems.append(f"items[{index}].targets must be an array of strings")
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
