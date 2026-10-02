"""Patch-style model replies normalize to items."""

from __future__ import annotations

from figma_extractor.llm.patches import canonicalize_response
from figma_extractor.llm.schemas import validate_task_payload


def test_ops_normalize_to_items() -> None:
    raw = {
        "ops": [
            {
                "op": "annotate",
                "target": {"screen_id": "1:1"},
                "changes": {"slug": "home", "role": "page"},
                "confidence": 0.8,
                "evidence": ["title"],
                "inferred": True,
            }
        ]
    }
    problems = validate_task_payload("screen_classification", raw)
    assert problems == []
    normalized = canonicalize_response("screen_classification", raw)
    assert len(normalized["items"]) == 1
    assert normalized["items"][0]["screen_id"] == "1:1"
    assert normalized["items"][0]["slug"] == "home"


def test_hint_ops_default_kind() -> None:
    raw = {
        "ops": [
            {
                "op": "annotate",
                "target": {"screen_id": "2:2"},
                "changes": {"hint": "use grid"},
                "confidence": 0.5,
                "evidence": ["layout"],
            }
        ]
    }
    problems = validate_task_payload("reconstruction_hints", raw)
    assert problems == []
    item = canonicalize_response("reconstruction_hints", raw)["items"][0]
    assert item["kind"] == "recommended"
