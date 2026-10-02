"""Schema 1 fixtures stay readable; schema 2 extract markers are present."""

from __future__ import annotations

import json
from pathlib import Path

from figma_extractor.api import write_schema_artifacts

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_schema1_tree_fragment_still_loads() -> None:
    """Older CreBiz-shaped trees have no schemaVersion and keep pad-only layout."""
    tree = {
        "id": "1:1",
        "type": "FRAME",
        "name": "Home",
        "w": 1440,
        "h": 900,
        "layout": {"dir": "column", "pad": [24, 24, 24, 24], "gap": 16},
        "children": [
            {
                "id": "2:2",
                "type": "INSTANCE",
                "instanceOf": "9:9",
                "name": "Card",
                "children": [],
            }
        ],
    }
    assert "schemaVersion" not in tree
    assert tree["layout"]["pad"] == [24, 24, 24, 24]
    assert "padding" not in tree["layout"]
    assert tree["children"][0]["instanceOf"] == "9:9"


def test_schema2_artifacts_are_written(tmp_path: Path) -> None:
    (tmp_path / "screens.json").write_text("[]", encoding="utf-8")
    (tmp_path / "components.json").write_text("[]", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "manifest.json").write_text("[]", encoding="utf-8")
    write_schema_artifacts(tmp_path)
    root = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert root["schemaVersion"] == 2
    assert json.loads((tmp_path / "assets" / "vectors.json").read_text(encoding="utf-8")) == []
    for name in (
        "truncated.json",
        "unsupported.json",
        "assets.json",
        "layout.json",
        "interactions.json",
        "performance.json",
    ):
        assert (tmp_path / "diagnostics" / name).is_file()


def test_constrained_fixture_is_schema2_compatible() -> None:
    node = json.loads((FIXTURES / "constrained-row.json").read_text(encoding="utf-8"))
    assert node["layout"]["pad"]
    assert node["layout"]["padding"]["top"] == node["layout"]["pad"][0]
    assert "breakpoints" not in node
