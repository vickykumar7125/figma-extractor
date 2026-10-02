"""info() reports annotation status without importing LLM providers."""

from __future__ import annotations

import json

from figma_extractor.api import info, llm_info_summary


def write_minimal_extract(tmp_path) -> None:
    (tmp_path / "screens.json").write_text(
        json.dumps([{"id": "1:1", "name": "Home", "tree": "trees/home.json"}]),
        encoding="utf-8",
    )
    (tmp_path / "pages.json").write_text("[]", encoding="utf-8")
    (tmp_path / "components.json").write_text("[]", encoding="utf-8")
    (tmp_path / "component-sets.json").write_text("[]", encoding="utf-8")
    (tmp_path / "text-content.json").write_text("{}", encoding="utf-8")
    tokens = tmp_path / "tokens"
    tokens.mkdir()
    (tokens / "variables.json").write_text('{"variables":[]}', encoding="utf-8")
    (tokens / "typography.json").write_text("{}", encoding="utf-8")
    (tokens / "effects.json").write_text("[]", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "manifest.json").write_text("[]", encoding="utf-8")


def test_info_without_annotations_has_null_llm(tmp_path) -> None:
    write_minimal_extract(tmp_path)
    details = info(tmp_path)
    assert details["llm"] is None
    assert "llmEnabled" not in details["summary"]


def test_info_reads_llm_summary_file(tmp_path) -> None:
    write_minimal_extract(tmp_path)
    document = tmp_path / "document"
    document.mkdir()
    (document / "llm-summary.json").write_text(
        json.dumps(
            {
                "version": 1,
                "llmEnabled": True,
                "provider": "ollama",
                "model": "llama3.2",
                "tasks": ["screen_classification"],
                "validationOk": 1,
                "validationFailed": 0,
            }
        ),
        encoding="utf-8",
    )
    details = info(tmp_path)
    assert details["llm"]["provider"] == "ollama"
    assert details["summary"]["llmEnabled"] is True
    assert details["summary"]["llmTasks"] == 1


def test_llm_info_summary_falls_back_to_annotations(tmp_path) -> None:
    write_minimal_extract(tmp_path)
    (tmp_path / "llm-annotations.json").write_text(
        json.dumps(
            {
                "llmEnabled": False,
                "provider": None,
                "model": None,
                "llmResults": {},
                "validation": [],
            }
        ),
        encoding="utf-8",
    )
    summary = llm_info_summary(tmp_path)
    assert summary is not None
    assert summary["llmEnabled"] is False
    assert summary["source"] == "llm-annotations.json"
