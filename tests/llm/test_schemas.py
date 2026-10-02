"""Schema checks used by the validation graph node."""

from __future__ import annotations

from figma_extractor.llm.policy import redact
from figma_extractor.llm.schemas import validate_task_payload


def test_hint_must_be_recommended() -> None:
    problems = validate_task_payload(
        "reconstruction_hints",
        {"items": [{"screen_id": "1", "hint": "use flex", "kind": "fact"}]},
    )
    assert any("recommended" in problem for problem in problems)


def test_valid_screen_item() -> None:
    problems = validate_task_payload(
        "screen_classification",
        {
            "items": [
                {
                    "screen_id": "1",
                    "slug": "home",
                    "role": "page",
                    "confidence": 0.2,
                    "evidence": ["name"],
                    "inferred": True,
                }
            ]
        },
    )
    assert problems == []


def test_redact_masks_key_material() -> None:
    hidden = redact("request failed for sk-abcdef123456")
    assert "abcdef" not in hidden
    assert "***" in hidden
