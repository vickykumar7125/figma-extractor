"""Fit a task context to a character budget without cutting every list in half.

Notes are dropped first. List rows are removed from the end, so earlier
rows stay. At least one row is kept when a list is the remaining evidence.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from figma_extractor.toon import encode

OPTIONAL_KEYS = frozenset({"note"})

# Short keys for TOON tables. Values are expanded only inside the LLM prompt path.
COMPACT_ALIASES: dict[str, str] = {
    "id": "i",
    "name": "nm",
    "screen_id": "sid",
    "node_id": "nid",
    "component_id": "cid",
    "asset_id": "aid",
    "semantic_type": "st",
    "suggested_element": "el",
    "confidence": "cf",
    "evidence": "ev",
    "reasoning": "rs",
    "slug": "sl",
    "role": "rl",
    "width": "w",
    "height": "h",
    "hasPath": "hp",
    "kind": "k",
    "hint": "ht",
    "reusable": "ru",
    "inferred": "inf",
    "targets": "tg",
    "origin": "or",
    "proposal": "pr",
    "task": "tk",
    "screens": "sc",
    "nodes": "nd",
    "vectors": "vc",
    "assets": "as",
    "components": "cp",
    "note": "nt",
}

PROMPT_TOON_OPTIONS = {"delimiter": ",", "indent": 2, "lengthMarker": "#"}


def within_budget(
    context: dict[str, Any],
    max_chars: int,
    char_measure: Callable[[dict[str, Any]], int],
    *,
    max_tokens: int | None = None,
    token_measure: Callable[[dict[str, Any]], int] | None = None,
) -> bool:
    if char_measure(context) > max_chars:
        return False
    if max_tokens is not None and token_measure is not None and token_measure(context) > max_tokens:
        return False
    return True


def pack_context(
    context: dict[str, Any],
    max_chars: int,
    measure: Callable[[dict[str, Any]], int],
    *,
    max_tokens: int | None = None,
    token_measure: Callable[[dict[str, Any]], int] | None = None,
) -> dict[str, Any]:
    """Return a copy within the char (and optional token) budget, or a truncation marker."""
    char_measure = measure
    if within_budget(context, max_chars, char_measure, max_tokens=max_tokens, token_measure=token_measure):
        return context
    fitted = json.loads(json.dumps(context, default=str))
    drop_optional_keys(fitted)
    steps = 0
    while (
        not within_budget(fitted, max_chars, char_measure, max_tokens=max_tokens, token_measure=token_measure)
        and steps < 500
    ):
        steps += 1
        if not drop_lowest_row(fitted):
            break
    if not within_budget(fitted, max_chars, char_measure, max_tokens=max_tokens, token_measure=token_measure):
        return {"truncated": True, "tasks": sorted(context)}
    return fitted


def drop_optional_keys(context: dict[str, Any]) -> None:
    for payload in context.values():
        if not isinstance(payload, dict):
            continue
        for key in list(payload):
            if key in OPTIONAL_KEYS:
                payload.pop(key, None)


def drop_lowest_row(context: dict[str, Any]) -> bool:
    """Remove the last item of the longest list that still has more than one row."""
    chosen: list[Any] | None = None
    longest = 1
    for payload in context.values():
        if not isinstance(payload, dict):
            continue
        for value in payload.values():
            if isinstance(value, list) and len(value) > longest:
                chosen = value
                longest = len(value)
    if chosen is None:
        return False
    chosen.pop()
    return True


def apply_compact_aliases(value: Any, aliases: dict[str, str] | None = None) -> Any:
    """Return a copy with known dict keys shortened for TOON transport."""
    mapping = aliases or COMPACT_ALIASES
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            short = mapping.get(key, key)
            out[short] = apply_compact_aliases(item, mapping)
        return out
    if isinstance(value, list):
        return [apply_compact_aliases(item, mapping) for item in value]
    return value


def estimate_tokens(text: str, *, model: str | None = None) -> int:
    """Token count via tiktoken when installed, otherwise chars/4."""
    if not text:
        return 0
    try:
        import tiktoken

        if model:
            try:
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                encoding = tiktoken.get_encoding("cl100k_base")
        else:
            encoding = tiktoken.get_encoding("cl100k_base")
        return max(1, len(encoding.encode(text)))
    except ImportError:
        return max(1, len(text) // 4)


def compare_context_formats(payload: dict[str, Any]) -> dict[str, int]:
    """Character and token estimates for JSON vs TOON vs compact TOON."""
    document = {"task": "sample", "context": payload}
    as_json = json.dumps(document, default=str)
    as_toon = encode(document, PROMPT_TOON_OPTIONS)
    compact = {"task": "sample", "context": apply_compact_aliases(payload)}
    as_compact = encode(compact, PROMPT_TOON_OPTIONS)
    return {
        "json_chars": len(as_json),
        "toon_chars": len(as_toon),
        "compact_toon_chars": len(as_compact),
        "json_tokens": estimate_tokens(as_json),
        "toon_tokens": estimate_tokens(as_toon),
        "compact_toon_tokens": estimate_tokens(as_compact),
    }
