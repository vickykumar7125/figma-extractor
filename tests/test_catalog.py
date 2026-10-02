"""Reference catalog and TOON tables from an extract, with no LLM import."""

from __future__ import annotations

import json
import sys

from figma_extractor.catalog import build_catalog, publish_transport
from figma_extractor.toon import decode


def write_extract(tmp_path) -> None:
    (tmp_path / "screens.json").write_text(
        json.dumps(
            [
                {
                    "id": "1:1",
                    "name": "Home",
                    "slug": "home",
                    "tree": "trees/home.json",
                    "role": "page",
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "components.json").write_text(
        json.dumps([{"id": "2:2", "name": "Logo", "page": "Style"}]),
        encoding="utf-8",
    )
    (tmp_path / "component-sets.json").write_text("[]", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "manifest.json").write_text(
        json.dumps(
            [
                {
                    "hash": "abc",
                    "file": "images/abc.png",
                    "mime": "image/png",
                    "width": 10,
                    "height": 12,
                    "usageCount": 2,
                    "usedBy": [{"node": "9:9", "name": "img"}],
                }
            ]
        ),
        encoding="utf-8",
    )


def test_catalog_keeps_refs_and_figma_origin(tmp_path) -> None:
    write_extract(tmp_path)
    catalog = build_catalog(tmp_path)
    screen = catalog["screens"][0]
    assert screen["tree"] == "trees/home.json"
    assert screen["componentRefs"] == []
    assert screen["role"]["kind"] == "derived"
    assert catalog["components"][0]["origin"] == "figma"
    assert catalog["assets"][0]["nodeRefs"] == ["9:9"]
    assert catalog["assets"][0]["localPath"] == "images/abc.png"


def test_toon_bundle_round_trips_without_langchain(tmp_path) -> None:
    write_extract(tmp_path)
    before = set(sys.modules)
    written = publish_transport(tmp_path)
    loaded = set(sys.modules) - before
    assert not any(name.startswith("langchain") or name.startswith("langgraph") for name in loaded)
    screens = decode((tmp_path / "toon" / "screens.toon").read_text(encoding="utf-8"))
    assert screens[0]["id"] == "1:1"
    assert written["components"].endswith("components.toon")
    screen_file = tmp_path / "screens" / "home" / "screen.json"
    assert screen_file.is_file()
    assert (tmp_path / "document" / "document.json").is_file()
    assert (tmp_path / "patterns" / "screens.json").is_file()
    assert (tmp_path / "diagnostics" / "extraction-report.json").is_file()
    assert (tmp_path / "toon" / "tokens.toon").is_file()


def test_component_refs_come_from_instance_of(tmp_path) -> None:
    write_extract(tmp_path)
    trees = tmp_path / "trees"
    trees.mkdir()
    (trees / "home.json").write_text(
        json.dumps(
            {
                "id": "1:1",
                "children": [
                    {"id": "3:3", "type": "INSTANCE", "instanceOf": "2:2", "children": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    catalog = build_catalog(tmp_path)
    assert catalog["screens"][0]["componentRefs"] == ["2:2"]


def test_asset_refs_come_from_the_screen_tree(tmp_path) -> None:
    write_extract(tmp_path)
    trees = tmp_path / "trees"
    trees.mkdir()
    (trees / "home.json").write_text(
        json.dumps(
            {
                "id": "1:1",
                "fills": [{"type": "image", "hash": "abc"}],
                "children": [],
            }
        ),
        encoding="utf-8",
    )
    catalog = build_catalog(tmp_path)
    assert catalog["screens"][0]["assetRefs"] == ["abc"]


def test_component_refs_include_component_nodes(tmp_path) -> None:
    write_extract(tmp_path)
    trees = tmp_path / "trees"
    trees.mkdir()
    (trees / "home.json").write_text(
        json.dumps(
            {
                "id": "1:1",
                "children": [{"id": "2:2", "type": "COMPONENT", "children": []}],
            }
        ),
        encoding="utf-8",
    )
    catalog = build_catalog(tmp_path)
    assert catalog["screens"][0]["componentRefs"] == ["2:2"]


def test_update_prompt_validation_merges_into_artifact(tmp_path) -> None:
    from figma_extractor.llm.artifacts import update_prompt_validation, write_prompt_artifact

    write_prompt_artifact(
        tmp_path,
        task="screen_classification",
        messages=[{"role": "user", "content": "task"}],
        provider="ollama",
        model="test",
        context_hash="abc",
        prompt_hash="def",
        token_estimate=10,
    )
    update_prompt_validation(
        tmp_path,
        [{"task": "screen_classification", "ok": False, "problems": ["missing slug"]}],
    )
    payload = json.loads((tmp_path / "prompts" / "tasks" / "screen_classification.json").read_text())
    assert payload["validation"]["ok"] is False
    assert "missing slug" in payload["validation"]["problems"]


def test_sync_annotation_writes_llm_into_screen_bundle(tmp_path) -> None:
    write_extract(tmp_path)
    publish_transport(tmp_path)
    annotation = {
        "llmEnabled": True,
        "provider": "ollama",
        "model": "test",
        "screens": [{"id": "1:1", "llm": {"role": "dashboard", "task": "screen_classification"}}],
        "llmResults": {},
        "validation": [{"task": "screen_classification", "ok": True, "problems": []}],
    }
    from figma_extractor.catalog import sync_annotation_transport

    sync_annotation_transport(tmp_path, annotation)
    screen = json.loads((tmp_path / "screens" / "home" / "screen.json").read_text(encoding="utf-8"))
    catalog = json.loads((tmp_path / "catalog" / "index.json").read_text(encoding="utf-8"))
    assert screen["llm"]["role"] == "dashboard"
    assert catalog["screens"][0]["llm"]["role"] == "dashboard"
    assert (tmp_path / "document" / "llm-summary.json").is_file()


def test_disk_cache_round_trips(tmp_path) -> None:
    from figma_extractor.llm.artifacts import DiskCache

    cache = DiskCache(tmp_path)
    cache.put("abc", {"items": [1]})
    assert cache.get("abc") == {"items": [1]}
    assert cache.get("missing") is None


def test_merge_proposals_keeps_figma_files(tmp_path) -> None:
    from figma_extractor.llm.artifacts import merge_proposals

    (tmp_path / "components").mkdir()
    (tmp_path / "components" / "index.json").write_text("[]", encoding="utf-8")
    written = merge_proposals(
        tmp_path,
        {
            "component_synthesis": {
                "items": [
                    {
                        "name": "Card",
                        "origin": "llm_proposed",
                        "targets": ["1:1"],
                        "confidence": 0.9,
                        "evidence": ["repeat"],
                    }
                ]
            }
        },
    )
    assert "components" in written
    assert (tmp_path / "components" / "proposed.json").is_file()
    assert (tmp_path / "components" / "index.json").read_text(encoding="utf-8") == "[]"
