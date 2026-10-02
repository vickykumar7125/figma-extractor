"""Build the system and user messages for one annotation task.

The user message is one TOON document from ``figma_extractor.toon``. Uniform
rows share a header. The model still replies with one JSON object, and
annotation files stay JSON.
"""

from __future__ import annotations

from typing import Any

from figma_extractor.llm.schemas import JSON_SCHEMA_HINT
from figma_extractor.toon import encode

# Comma columns and a length marker, so a table header is [#3]{id,name}.
PROMPT_OPTIONS = {"delimiter": ",", "indent": 2, "lengthMarker": "#"}


def encode_context(value: Any) -> str:
    """Encode one JSON-like value with the prompt options."""
    return encode(value, PROMPT_OPTIONS)


def render_user(
    task: str,
    payload: dict[str, Any],
    problems: list[Any],
    *,
    compact: bool = False,
) -> str:
    """One document: the task, its context, and validation problems on a retry."""
    context = payload
    if compact:
        from figma_extractor.toon.optimize import apply_compact_aliases

        context = apply_compact_aliases(payload)
    document: dict[str, Any] = {"task": task, "context": context}
    if problems:
        document["invalid"] = problems
    return encode_context(document)


def render_system(task: str) -> str:
    """Rules for reading the TOON context and the JSON object to return."""
    return (
        "You annotate a Figma extract that was already decoded deterministically. "
        "Do not invent colors, spacing, typography, or copy. "
        "The user message is one TOON document. "
        "A header such as [#3]{id,name} names the columns, and each following line is one row. "
        "Use only that context. Mark guesses as inferred. "
        "Reconstruction hints must use kind \"recommended\". "
        "You may reply with either an items array or a compact ops array (op, target, changes). "
        "Reply with one JSON object and no prose: " + JSON_SCHEMA_HINT[task]
    )


def apply_prompt_proposals(
    task: str,
    messages: list[dict[str, str]],
    proposals: dict[str, str],
) -> list[dict[str, str]]:
    """Append a validated proposal for this task. The JSON schema line stays."""
    text = proposals.get(task)
    if not text or not messages:
        return messages
    updated = [dict(message) for message in messages]
    updated[0]["content"] = updated[0]["content"] + "\nPrompt proposal: " + text
    return updated


def proposals_from_result(payload: Any) -> dict[str, str]:
    """Accepted prompt proposals only. Other tasks are not rewritten from guesses."""
    if not isinstance(payload, dict):
        return {}
    found: dict[str, str] = {}
    items = payload.get("items")
    if not isinstance(items, list):
        return {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("task")
        proposal = item.get("proposal")
        if isinstance(name, str) and isinstance(proposal, str) and proposal.strip():
            found[name] = proposal.strip()
    return found


def prompt_messages(
    task: str,
    payload: dict[str, Any],
    feedback: list[dict[str, Any]],
    *,
    compact: bool = False,
) -> list[dict[str, str]]:
    """System rules, then one encoded user document."""
    problems = [
        item["problems"]
        for item in feedback
        if item.get("task") == task and not item.get("ok")
    ]
    return [
        {"role": "system", "content": render_system(task)},
        {"role": "user", "content": render_user(task, payload, problems, compact=compact)},
    ]


def context_size(context: dict[str, Any], *, compact: bool = False) -> int:
    """Characters of the user documents these task payloads will produce."""
    total = 0
    for task, payload in context.items():
        if isinstance(payload, dict):
            total += len(render_user(str(task), payload, [], compact=compact))
        else:
            total += len(encode_context(payload))
    return total


def context_token_size(context: dict[str, Any], *, compact: bool = False, model: str | None = None) -> int:
    """Estimated tokens for all task user documents in this context."""
    from figma_extractor.toon.optimize import estimate_tokens

    total = 0
    for task, payload in context.items():
        if isinstance(payload, dict):
            total += estimate_tokens(render_user(str(task), payload, [], compact=compact), model=model)
        else:
            total += estimate_tokens(encode_context(payload), model=model)
    return total
