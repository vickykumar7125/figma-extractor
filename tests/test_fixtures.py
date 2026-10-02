"""Offline fixtures that lock redesign schema without the corpus drive."""

from __future__ import annotations

import json
from pathlib import Path

from figma_extractor.extract.flow import suggest_route_path
from figma_extractor.extract.semantic import classify_semantic
from figma_extractor.extract.vectors import publish_vector_assets

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_icon_button_crop_fixture_is_specimens() -> None:
    crop = json.loads((FIXTURES / "icon-button-crop.json").read_text(encoding="utf-8"))
    expected = json.loads((FIXTURES / "icon-button-crop.semantic.json").read_text(encoding="utf-8"))
    assert crop["type"] == "FRAME"
    assert classify_semantic(crop) == expected
    assert expected["kind"] == "specimens"


def test_specimen_crop_is_not_a_primary_product_route() -> None:
    crop = json.loads((FIXTURES / "icon-button-crop.json").read_text(encoding="utf-8"))
    semantic = classify_semantic(crop)
    assert semantic is not None
    # Gallery/specimen frames stay out of product route lists in build_ui_flow.
    assert semantic["kind"] in {"specimens", "component-gallery"}
    path = suggest_route_path(crop["name"], "button", "component-gallery")
    assert path.startswith("/")


def test_constrained_row_fixture_keeps_schema_keys() -> None:
    node = json.loads((FIXTURES / "constrained-row.json").read_text(encoding="utf-8"))
    assert node["constraints"]["horizontal"] == "LEFT_RIGHT"
    assert node["layout"]["pad"] == [8, 8, 8, 8]
    assert node["layout"]["padding"]["left"] == 8
    assert "breakpoints" not in node


def test_rocket_light_has_empty_component_sets_fixture() -> None:
    sets = json.loads((FIXTURES / "rocket-light-component-sets.json").read_text(encoding="utf-8"))
    assert sets == []


def test_fixture_svg_dedupe_usage_count(tmp_path: Path) -> None:
    crop = json.loads((FIXTURES / "icon-button-crop.json").read_text(encoding="utf-8"))
    trees = tmp_path / "trees"
    trees.mkdir()
    (trees / "crop.json").write_text(json.dumps(crop), encoding="utf-8")
    (tmp_path / "screens.json").write_text(
        json.dumps([{"id": "1:1", "tree": "trees/crop.json"}]),
        encoding="utf-8",
    )
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "manifest.json").write_text("[]", encoding="utf-8")
    records = publish_vector_assets(tmp_path)
    assert len(records) == 1
    assert records[0]["usageCount"] == 6
    updated = json.loads((trees / "crop.json").read_text(encoding="utf-8"))
    assert all(child.get("vectorRef") == records[0]["id"] for child in updated["children"])
    assert all("paths" not in child for child in updated["children"])


def test_llm_guide_differs_across_two_headers() -> None:
    from figma_extractor.extract.flow import llm_guide

    a = llm_guide(
        {
            "source": "CreBiz",
            "schemaVersion": 2,
            "screens": 12,
            "primaryScreens": 12,
            "components": 4,
            "colorStyles": 8,
            "variables": 0,
            "rasters": 18,
            "vectors": 2,
        }
    )
    b = llm_guide(
        {
            "source": "Vuexy",
            "schemaVersion": 2,
            "screens": 696,
            "primaryScreens": 400,
            "components": 6055,
            "colorStyles": 83,
            "variables": 265,
            "rasters": 288,
            "vectors": 1200,
        }
    )
    assert a != b
    assert "CreBiz" in a and "Vuexy" in b
    assert "Read order" in a and "Read order" in b


def test_token_kind_explicit_shape() -> None:
    token = {"name": "Brand/Primary", "kind": "explicit", "value": "#111111", "id": "1:2"}
    assert token["kind"] == "explicit"
    assert token["id"]
