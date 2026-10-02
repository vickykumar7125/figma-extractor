"""LangGraph annotation with an in-process fake model. No network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson
import pytest

from figma_extractor.llm.config import LlmConfig, LlmTasks

langgraph = pytest.importorskip("langgraph")


class FakeChat:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = list(payloads)
        self.calls = 0

    def complete_json(self, messages: list[dict[str, str]], *, task: str) -> Any:
        self.calls += 1
        assert messages[0]["role"] == "system"
        assert "recommended" in messages[0]["content"]
        return self.payloads.pop(0)

    def stream_text(self, messages: list[dict[str, str]]):
        yield "unused"

    async def acomplete_json(self, messages: list[dict[str, str]], *, task: str) -> Any:
        return self.complete_json(messages, task=task)

    async def astream_text(self, messages: list[dict[str, str]]):
        yield "unused"


def valid_item() -> dict[str, Any]:
    return {
        "items": [
            {
                "screen_id": "1:1",
                "slug": "home",
                "role": "page",
                "confidence": 0.4,
                "evidence": ["screen name"],
                "inferred": True,
            }
        ]
    }


def write_extract(directory: Path) -> None:
    screens = [
        {
            "id": "1:1",
            "name": "Home",
            "slug": "home",
            "width": 800,
            "height": 600,
            "role": "page",
            "regions": [{"role": "header", "name": "Header"}],
            "tree": "trees/home.json",
        }
    ]
    tree = {
        "id": "1:1",
        "type": "FRAME",
        "name": "Home",
        "w": 800,
        "h": 600,
        "layout": {"dir": "column", "gap": 8},
        "children": [
            {
                "id": "2:2",
                "type": "VECTOR",
                "name": "star-fill",
                "w": 16,
                "h": 16,
                "paths": [{"d": "M 0 0 L 1 1", "rule": "nonzero"}],
            }
        ],
    }
    directory.joinpath("trees").mkdir()
    directory.joinpath("screens.json").write_bytes(orjson.dumps(screens))
    directory.joinpath("trees", "home.json").write_bytes(orjson.dumps(tree))


def test_graph_accepts_structured_output(tmp_path: Path) -> None:
    from figma_extractor.llm.graph import run_annotation_graph

    write_extract(tmp_path)
    chat = FakeChat([valid_item()])
    config = LlmConfig(
        enabled=True,
        provider="ollama",
        tasks=LlmTasks(screen_classification=True),
        max_retries=0,
        backoff_seconds=0,
    )
    result = run_annotation_graph(tmp_path, config, session=chat)
    assert result["llmEnabled"] is True
    assert result["llmResults"]["screen_classification"]["items"][0]["inferred"] is True
    assert result["screens"][0]["role"] == "page"
    assert chat.calls == 1
    assert all(item["ok"] for item in result["validation"])
    assert "M 0 0" not in orjson.dumps(result).decode()


def test_graph_repairs_invalid_output_once(tmp_path: Path) -> None:
    from figma_extractor.llm.graph import run_annotation_graph

    write_extract(tmp_path)
    invalid = {"items": [{"screen_id": "1:1", "confidence": 4}]}
    chat = FakeChat([invalid, valid_item()])
    config = LlmConfig(
        enabled=True,
        provider="ollama",
        tasks=LlmTasks(screen_classification=True),
        validation_attempts=2,
        max_retries=0,
        backoff_seconds=0,
    )
    result = run_annotation_graph(tmp_path, config, session=chat)
    assert chat.calls == 2
    assert result["metadata"]["attempts"] == 2
    assert result["validation"][-1]["ok"] is True


def test_context_omits_vector_commands(tmp_path: Path) -> None:
    from figma_extractor.llm.context import build_task_context

    write_extract(tmp_path)
    context = build_task_context(tmp_path, ["svg_analysis", "reconstruction_hints"], 4000)
    encoded = orjson.dumps(context).decode()
    assert "M 0 0" not in encoded
    assert context["svg_analysis"]["vectors"][0]["hasPath"] is True
    assert context["reconstruction_hints"]["layout"]["dir"] == "column"
