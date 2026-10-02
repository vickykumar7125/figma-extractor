"""Schema normalization, responsive facts, and UI-flow interactions."""

from __future__ import annotations

import json
from pathlib import Path

from figma_extractor.extract.flow import (
    extract_prototype_interactions,
    infer_region_role,
    suggest_route_path,
)
from figma_extractor.extract.trees import (
    TreeBuilder,
    constraints,
    layout,
    layout_sizing,
    stroke_details,
    transform_extras,
)


def test_layout_padding_keeps_pad_array() -> None:
    box = layout(
        {
            "stackMode": "VERTICAL",
            "stackVerticalPadding": 8,
            "stackPaddingRight": 12,
            "stackPaddingBottom": 8,
            "stackHorizontalPadding": 12,
            "stackWrap": "WRAP",
        }
    )
    assert box is not None
    assert box["pad"] == [8, 12, 8, 12]
    assert box["padding"] == {"top": 8, "right": 12, "bottom": 8, "left": 12}
    assert box["wrap"] is True


def test_constraints_round_trip_enums() -> None:
    box = constraints({"horizontalConstraint": "LEFT_RIGHT", "verticalConstraint": "TOP"})
    assert box == {"horizontal": "LEFT_RIGHT", "vertical": "TOP"}
    assert constraints({}) is None


def test_layout_sizing_from_hug_and_grow() -> None:
    assert layout_sizing(hug_main=True, hug_cross=False, grow=None) == {"main": "hug"}
    assert layout_sizing(hug_main=False, hug_cross=True, grow=1) == {"main": "grow", "cross": "hug"}


def test_absolute_and_no_breakpoints_on_node() -> None:
    builder = TreeBuilder.__new__(TreeBuilder)
    builder.paths = None
    node = TreeBuilder.node(
        builder,
        "1:1",
        {
            "type": "FRAME",
            "name": "Panel",
            "size": {"x": 100, "y": 40},
            "transform": {"m00": 1, "m01": 0, "m10": 0, "m11": 1, "m02": 0, "m12": 0},
            "stackPositioning": "ABSOLUTE",
            "horizontalConstraint": "SCALE",
            "verticalConstraint": "TOP",
        },
    )
    assert node["absolute"] is True
    assert node["constraints"]["horizontal"] == "SCALE"
    assert "breakpoints" not in node


def test_stroke_cap_and_dash() -> None:
    stroke = stroke_details(
        {
            "strokeWeight": 2,
            "strokeAlign": "CENTER",
            "strokeCap": "ROUND",
            "strokeJoin": "MITER",
            "dashPattern": [4, 2],
        },
        [{"type": "solid", "color": "#000"}],
    )
    assert stroke["cap"] == "ROUND"
    assert stroke["join"] == "MITER"
    assert stroke["dash"] == [4, 2]


def test_transform_rotation_when_not_translation() -> None:
    extras = transform_extras({"m00": 0, "m01": -1, "m10": 1, "m11": 0, "m02": 10, "m12": 20})
    assert extras is not None
    assert "rotation" in extras
    assert transform_extras({"m00": 1, "m01": 0, "m10": 0, "m11": 1}) is None


def test_suggested_route_marked_inferred_and_gallery_excluded(tmp_path: Path) -> None:
    from figma_extractor.extract.flow import build_ui_flow

    (tmp_path / "screens.json").write_text(
        json.dumps(
            [
                {
                    "id": "1:1",
                    "name": "Dashboard",
                    "page": "App",
                    "slug": "app__dashboard",
                    "tree": "trees/app__dashboard.json",
                    "width": 1200,
                    "height": 800,
                },
                {
                    "id": "2:2",
                    "name": "Buttons",
                    "page": "button",
                    "slug": "button__buttons",
                    "tree": "trees/button__buttons.json",
                    "width": 800,
                    "height": 600,
                    "semantic": {"kind": "specimens", "confidence": 0.7, "evidence": ["crop"]},
                },
            ]
        ),
        encoding="utf-8",
    )
    trees = tmp_path / "trees"
    trees.mkdir()
    for name in ("app__dashboard.json", "button__buttons.json"):
        (trees / name).write_text(
            json.dumps({"id": "1:1", "type": "FRAME", "name": "Root", "children": []}),
            encoding="utf-8",
        )
    summary = build_ui_flow(tmp_path)
    flow = json.loads((tmp_path / "ui-flow.json").read_text(encoding="utf-8"))
    assert all(route.get("inferred") is True for route in flow["suggestedRoutes"])
    assert all(route["role"] != "component-gallery" for route in flow["suggestedRoutes"])
    assert flow["interactions"] == []
    assert summary["interactionCount"] == 0


def test_prototype_interactions_extract(tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    lines = [
        {
            "guid": {"sessionID": 1, "localID": 1},
            "name": "Button",
            "prototypeInteractions": [
                {
                    "id": {"sessionID": 9, "localID": 9},
                    "event": {"interactionType": "ON_CLICK"},
                    "actions": [
                        {
                            "transitionNodeID": {"sessionID": 1, "localID": 2},
                            "connectionType": "INTERNAL_NODE",
                            "navigationType": "NAVIGATE",
                        }
                    ],
                    "isDeleted": False,
                }
            ],
        },
        {"guid": {"sessionID": 1, "localID": 2}, "name": "Target"},
    ]
    (extracted / "nodes.ndjson").write_bytes(b"\n".join(json.dumps(row).encode() for row in lines) + b"\n")
    interactions, diagnostics = extract_prototype_interactions(tmp_path)
    assert len(interactions) == 1
    assert interactions[0]["fromId"] == "1:1"
    assert interactions[0]["toId"] == "1:2"
    assert interactions[0]["trigger"] == "ON_CLICK"
    assert diagnostics == []


def test_region_evidence() -> None:
    role, evidence = infer_region_role("Primary Sidebar")
    assert role == "sidebar"
    assert evidence == "sidebar"


def test_node_budget_five_writes_truncation_record() -> None:
    """Prompt 13: budget of 5 yields a partial tree and truncation events."""
    builder = TreeBuilder.__new__(TreeBuilder)
    builder.paths = None
    builder.raw = {}
    builder.children = {}
    # Root + 8 children → budget 5 stops mid-walk.
    builder.raw["0:0"] = {
        "type": "FRAME",
        "name": "Root",
        "size": {"x": 100, "y": 100},
        "transform": {"m00": 1, "m01": 0, "m10": 0, "m11": 1, "m02": 0, "m12": 0},
        "visible": True,
    }
    child_ids = []
    for index in range(8):
        node_id = f"1:{index}"
        child_ids.append(node_id)
        builder.raw[node_id] = {
            "type": "FRAME",
            "name": f"Child {index}",
            "size": {"x": 10, "y": 10},
            "transform": {"m00": 1, "m01": 0, "m10": 0, "m11": 1, "m02": 0, "m12": float(index)},
            "visible": True,
        }
    builder.children = {"0:0": child_ids}
    for node_id in child_ids:
        builder.children[node_id] = []

    tree, written = builder.build("0:0", budget=5)
    assert tree is not None
    assert tree.get("truncated") is True
    assert written == 5
    assert builder.truncated_events
    assert builder.truncated_events[0]["reason"] == "node-budget"
    assert builder.truncated_events[0]["budget"] == 5
    assert len(tree.get("children") or []) < 8


def test_style_refs_from_inherit_ids() -> None:
    from figma_extractor.extract.trees import TreeBuilder, collect_style_refs, collect_variable_refs

    refs = collect_style_refs(
        {
            "inheritFillStyleID": {"sessionID": 8, "localID": 1758},
            "inheritTextStyleID": {"sessionID": 8, "localID": 99},
            "styleIdForFill": {"guid": {"sessionID": 8, "localID": 1758}},
        }
    )
    assert refs == [
        {"field": "fill", "id": "8:1758"},
        {"field": "text", "id": "8:99"},
    ]
    asset_refs = collect_style_refs(
        {"styleIdForFill": {"assetRef": {"key": "abc123", "version": "1:0"}}}
    )
    assert asset_refs == [{"field": "fill", "id": "abc123"}]

    var_refs = collect_variable_refs(
        {
            "variableConsumptionMap": {
                "entries": [
                    {
                        "variableField": "STACK_PADDING_TOP",
                        "variableData": {
                            "value": {
                                "alias": {"guid": {"sessionID": 407, "localID": 101457}}
                            }
                        },
                    },
                    {
                        "variableField": "STACK_PADDING_BOTTOM",
                        "variableData": {
                            "value": {
                                "alias": {"guid": {"sessionID": 407, "localID": 101457}}
                            }
                        },
                    },
                ]
            }
        }
    )
    assert var_refs == [
        {"id": "407:101457", "field": "STACK_PADDING_BOTTOM"},
        {"id": "407:101457", "field": "STACK_PADDING_TOP"},
    ]

    builder = TreeBuilder.__new__(TreeBuilder)
    builder.paths = None
    node = TreeBuilder.node(
        builder,
        "1:1",
        {
            "type": "FRAME",
            "name": "Row",
            "size": {"x": 100, "y": 40},
            "transform": {"m00": 1, "m01": 0, "m10": 0, "m11": 1, "m02": 0, "m12": 0},
            "inheritFillStyleID": {"sessionID": 3, "localID": 9},
            "variableConsumptionMap": {
                "entries": [
                    {
                        "variableField": "STACK_SPACING",
                        "variableData": {
                            "value": {"alias": {"guid": {"sessionID": 1, "localID": 2}}}
                        },
                    }
                ]
            },
        },
    )
    assert node["styleRefs"] == [{"field": "fill", "id": "3:9"}]
    assert node["variableRefs"] == [{"id": "1:2", "field": "STACK_SPACING"}]
