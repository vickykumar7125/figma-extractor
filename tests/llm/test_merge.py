"""Merge validated LLM output onto annotation rows."""

from __future__ import annotations

import json

from figma_extractor.llm.merge import apply_llm_overlays, stitch_incremental_annotations


def test_screen_overlay_requires_validation_ok() -> None:
    screens = [{"id": "1:1", "name": "Home", "role": "page"}]
    results = {
        "screen_classification": {
            "items": [
                {
                    "screen_id": "1:1",
                    "slug": "home",
                    "role": "dashboard",
                    "confidence": 0.9,
                    "evidence": ["widgets"],
                    "inferred": True,
                }
            ]
        }
    }
    merged, _, _ = apply_llm_overlays(screens, [], [], results, [{"task": "screen_classification", "ok": True}])
    assert merged[0]["role"] == "page"
    assert merged[0]["llm"]["role"] == "dashboard"


def test_incremental_keeps_prior_llm_for_unchanged_screen(tmp_path) -> None:
    from figma_extractor.catalog import screen_hashes
    from figma_extractor.util import write_json

    trees = tmp_path / "trees"
    trees.mkdir()
    (trees / "home.json").write_text('{"id":"1:1"}', encoding="utf-8")
    (tmp_path / "screens.json").write_text(
        json.dumps([{"id": "1:1", "name": "Home", "tree": "trees/home.json"}]),
        encoding="utf-8",
    )
    write_json(tmp_path / "catalog" / "screen-hashes.json", screen_hashes(tmp_path))
    (tmp_path / "llm-annotations.json").write_text(
        json.dumps(
            {
                "screens": [{"id": "1:1", "llm": {"role": "dashboard", "task": "screen_classification"}}],
                "nodes": [],
                "llmResults": {"screen_classification": {"items": []}},
                "validation": [],
            }
        ),
        encoding="utf-8",
    )
    screens, _, results = stitch_incremental_annotations(
        tmp_path,
        [{"id": "1:1", "name": "Home"}],
        [],
        {},
    )
    assert screens[0]["llm"]["role"] == "dashboard"
    assert "screen_classification" in results
