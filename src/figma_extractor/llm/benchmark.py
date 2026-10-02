"""Compare JSON and TOON prompt sizes for task context in an extract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from figma_extractor.llm.context import build_task_context
from figma_extractor.toon.optimize import compare_context_formats


def benchmark_context(
    directory: Path,
    *,
    max_chars: int = 12_000,
    compact: bool = False,
) -> list[dict[str, Any]]:
    """Return one stats row per task payload that would be sent to a model."""
    root = Path(directory)
    from figma_extractor.llm.config import LlmConfig

    config = LlmConfig.from_env()
    tasks = config.tasks.enabled_names() or [
        "screen_classification",
        "semantic_classification",
        "component_analysis",
        "svg_analysis",
        "asset_analysis",
    ]
    context = build_task_context(root, tasks, max_chars, compact=compact)
    rows: list[dict[str, Any]] = []
    for task, payload in context.items():
        if not isinstance(payload, dict):
            continue
        stats = compare_context_formats(payload)
        rows.append({"task": task, **stats})
    return rows
