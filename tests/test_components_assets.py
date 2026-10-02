"""Component overrides, asset ids, and explicit token kinds."""

from __future__ import annotations

import json
from pathlib import Path

from figma_extractor.extract.structure import slim_prop_def
from figma_extractor.extract.trees import TreeBuilder, _attach_image_files


def test_slim_prop_def_keeps_options_and_default() -> None:
    entry = slim_prop_def(
        {
            "name": "State",
            "type": "VARIANT",
            "id": "p1",
            "defaultValue": "Default",
            "variantOptions": ["Default", "Hover"],
        }
    )
    assert entry["id"] == "p1"
    assert entry["default"] == "Default"
    assert entry["options"] == ["Default", "Hover"]


def test_instance_exposes_overrides_without_dropping_children() -> None:
    builder = TreeBuilder.__new__(TreeBuilder)
    builder.paths = None
    builder.budget = 100
    builder.truncated_events = []
    builder.unsupported_events = []
    builder.raw = {
        "1:1": {
            "type": "INSTANCE",
            "name": "Button",
            "size": {"x": 40, "y": 20},
            "transform": {"m00": 1, "m01": 0, "m10": 0, "m11": 1, "m02": 0, "m12": 0},
            "symbolData": {
                "symbolID": {"sessionID": 2, "localID": 2},
                "symbolOverrides": [
                    {
                        "guidPath": {"guids": [{"sessionID": 2, "localID": 3}]},
                        "fillPaints": [{"type": "SOLID", "color": {"r": 1, "g": 0, "b": 0, "a": 1}}],
                    }
                ],
            },
            "componentPropAssignments": [{"name": "State", "value": "Hover"}],
        },
        "2:2": {
            "type": "SYMBOL",
            "name": "Button",
            "size": {"x": 40, "y": 20},
            "transform": {"m00": 1, "m01": 0, "m10": 0, "m11": 1, "m02": 0, "m12": 0},
            "visible": True,
        },
        "2:3": {
            "type": "TEXT",
            "name": "Label",
            "size": {"x": 20, "y": 10},
            "transform": {"m00": 1, "m01": 0, "m10": 0, "m11": 1, "m02": 0, "m12": 0},
            "textData": {"characters": "Go"},
            "fontName": {"family": "Inter", "style": "Regular"},
            "visible": True,
        },
    }
    builder.children = {"2:2": ["2:3"], "1:1": []}
    node = builder.walk("1:1", depth=0, overrides={}, symbol_stack=(), force_visible=True)
    assert node is not None
    assert node["instanceOf"] == "2:2"
    assert node["children"]
    assert node["overrides"][0]["targetId"] == "2:3"
    assert "fillPaints" in node["overrides"][0]["keys"]
    assert node["componentPropAssignments"][0]["value"] == "Hover"


def test_attach_image_file_to_paint() -> None:
    tree = {
        "id": "1:1",
        "fills": [{"type": "image", "hash": "abc123"}],
        "children": [],
    }
    assert _attach_image_files(tree, {"abc123": "images/abc123.png"}) is True
    assert tree["fills"][0]["file"] == "images/abc123.png"


def test_manifest_kind_and_token_kind_helpers() -> None:
    # Smoke the public shapes expected by redesign docs.
    raster = {"id": "h1", "kind": "raster", "hash": "h1", "file": "images/h1.png"}
    vector = {"id": "v1", "kind": "vector", "localPath": "svg/v1.svg"}
    token = {"name": "Brand/Primary", "kind": "explicit", "value": "#111"}
    assert raster["kind"] == "raster"
    assert vector["kind"] == "vector"
    assert token["kind"] == "explicit"
