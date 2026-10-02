"""Shared SVG vector assets and vectorRef wiring."""

from __future__ import annotations

import json

from figma_extractor.extract.vectors import publish_vector_assets


def test_repeated_paths_share_one_vector_asset(tmp_path) -> None:
    trees = tmp_path / "trees"
    trees.mkdir()
    star = {
        "id": "v1",
        "name": "star",
        "w": 16,
        "h": 16,
        "paths": [{"d": "M0 0 L8 16 L16 0 Z", "rule": "nonzero"}],
        "fills": [{"type": "solid", "color": "#111111"}],
    }
    tree = {
        "id": "1:1",
        "type": "FRAME",
        "children": [
            {**star, "id": "v1"},
            {**star, "id": "v2"},
            {**star, "id": "v3", "w": 32, "h": 32},
        ],
    }
    (trees / "home.json").write_text(json.dumps(tree), encoding="utf-8")
    (tmp_path / "screens.json").write_text(
        json.dumps([{"id": "1:1", "tree": "trees/home.json"}]),
        encoding="utf-8",
    )
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "manifest.json").write_text("[]", encoding="utf-8")

    records = publish_vector_assets(tmp_path)
    assert len(records) == 1
    assert records[0]["usageCount"] == 3
    updated = json.loads((trees / "home.json").read_text(encoding="utf-8"))
    refs = {child["vectorRef"] for child in updated["children"]}
    assert refs == {records[0]["id"]}
    assert all("paths" not in child for child in updated["children"])
    scaled = next(child for child in updated["children"] if child["id"] == "v3")
    assert scaled.get("vectorScale") == [2.0, 2.0]
    assert (tmp_path / "assets" / "vectors.json").is_file()
    assert (tmp_path / "assets" / "svg" / f"{records[0]['id']}.svg").is_file()
    svg = (tmp_path / "assets" / "svg" / f"{records[0]['id']}.svg").read_text(encoding="utf-8")
    assert "M0 0 L8 16 L16 0 Z" in svg
    manifest = json.loads((tmp_path / "assets" / "manifest.json").read_text(encoding="utf-8"))
    assert any(row.get("kind") == "vector" for row in manifest)


def test_svg_stroke_includes_weight_cap_join() -> None:
    from figma_extractor.extract.svg import svg_markup

    markup = svg_markup(
        {
            "w": 24,
            "h": 24,
            "strokePaths": [{"d": "M0 0 L24 24"}],
            "stroke": {
                "paints": [{"type": "solid", "color": "#ff0000"}],
                "weight": 2,
                "cap": "ROUND",
                "join": "MITER",
                "dash": [4, 2],
            },
        }
    )
    assert 'stroke="#ff0000"' in markup
    assert 'stroke-width="2.0"' in markup or 'stroke-width="2"' in markup
    assert 'stroke-linecap="round"' in markup
    assert 'stroke-linejoin="miter"' in markup
    assert 'stroke-dasharray="4.0 2.0"' in markup or 'stroke-dasharray="4 2"' in markup
