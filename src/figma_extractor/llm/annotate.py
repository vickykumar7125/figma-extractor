"""Public annotation entry. LLM packages load only when the config enables them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.context import load_json, screen_rows
from figma_extractor.util import write_json


def annotate(
    directory: str | Path,
    config: LlmConfig | None = None,
    *,
    write: bool = True,
) -> dict[str, Any]:
    """Annotate an existing extract.

    When ``config.enabled`` is false, this reads screens already produced by
    ``extract`` and does not import LangChain, LangGraph, or a provider SDK.
    """
    root = Path(directory)
    screens_path = root / "screens.json"
    if not screens_path.is_file():
        raise FileNotFoundError(f"Missing {screens_path}. Run extract before annotate.")
    active = config if config is not None else LlmConfig.from_env()
    active.check()
    if active.enabled:
        from figma_extractor.llm.graph import run_annotation_graph

        result = run_annotation_graph(root, active)
        from figma_extractor.catalog import screen_hashes

        write_json(root / "catalog" / "screen-hashes.json", screen_hashes(root))
    else:
        result = deterministic_annotations(root)
    if write:
        write_json(root / "llm-annotations.json", result)
        if (root / "catalog" / "index.json").is_file():
            from figma_extractor.catalog import sync_annotation_transport

            sync_annotation_transport(root, result)
    return result


def deterministic_annotations(directory: Path) -> dict[str, Any]:
    screens = load_json(directory / "screens.json", [])
    if not isinstance(screens, list):
        screens = []
    return {
        "llmEnabled": False,
        "provider": None,
        "model": None,
        "screens": screen_rows(screens),
        "nodes": [],
        "assets": [],
        "llmResults": {},
        "validation": [],
        "errors": [],
        "warnings": ["LLM is disabled. Annotations are the deterministic extract."],
        "metadata": {"attempts": 0},
    }
