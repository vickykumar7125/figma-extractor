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


def render_user(task: str, payload: dict[str, Any], problems: list[Any]) -> str:
    """One document: the task, its context, and validation problems on a retry."""
    document: dict[str, Any] = {"task": task, "context": payload}
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
        "Reply with one JSON object and no prose: " + JSON_SCHEMA_HINT[task]
    )


def prompt_messages(
    task: str,
    payload: dict[str, Any],
    feedback: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """System rules, then one encoded user document."""
    problems = [
        item["problems"]
        for item in feedback
        if item.get("task") == task and not item.get("ok")
    ]
    return [
        {"role": "system", "content": render_system(task)},
        {"role": "user", "content": render_user(task, payload, problems)},
    ]


def context_size(context: dict[str, Any]) -> int:
    """Characters of the user documents these task payloads will produce."""
    total = 0
    for task, payload in context.items():
        if isinstance(payload, dict):
            total += len(render_user(str(task), payload, []))
        else:
            total += len(encode_context(payload))
    return total
