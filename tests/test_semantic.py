"""Deterministic semantic kinds and role keyword narrowing."""

from __future__ import annotations

from figma_extractor.extract.flow import infer_role
from figma_extractor.extract.semantic import attach_semantic, classify_semantic
from figma_extractor.extract.trees import shadows, text


def test_icon_button_crop_is_specimens() -> None:
    node = {
        "id": "1:1",
        "type": "FRAME",
        "name": "Icon Button / crop",
        "w": 800,
        "h": 400,
        "children": [
            {"id": f"2:{i}", "type": "INSTANCE", "name": f"State={i},Size=md", "instanceOf": "9:9"}
            for i in range(6)
        ],
    }
    semantic = classify_semantic(node)
    assert semantic is not None
    assert semantic["kind"] == "specimens"
    assert semantic["confidence"] >= 0.65
    assert node["type"] == "FRAME"


def test_icon_button_crop_unwraps_wrapper_frame() -> None:
    """Vuexy nests specimen symbols under a single IconButton container."""
    from figma_extractor.extract.semantic import screen_semantic

    node = {
        "id": "1:1",
        "type": "FRAME",
        "name": "Icon Button",
        "w": 800,
        "h": 400,
        "children": [
            {
                "id": "2:0",
                "type": "FRAME",
                "name": "IconButton",
                "children": [
                    {
                        "id": f"3:{i}",
                        "type": "SYMBOL",
                        "name": f"Size=Medium, Color={'Primary' if i % 2 else 'Secondary'}",
                    }
                    for i in range(8)
                ],
            }
        ],
    }
    semantic = classify_semantic(node)
    assert semantic is not None
    assert semantic["kind"] == "specimens"
    screen = {"id": "1:1", "name": "Icon Button", "origin": "crop", "width": 800, "height": 400}
    assert screen_semantic(screen, node)["kind"] == "specimens"


def test_unmatched_frame_has_no_semantic() -> None:
    node = {"id": "1:1", "type": "FRAME", "name": "Untitled 12", "w": 40, "h": 40, "children": []}
    assert classify_semantic(node) is None


def test_attach_semantic_is_deterministic() -> None:
    tree = {
        "id": "1:1",
        "type": "FRAME",
        "name": "Header",
        "w": 100,
        "h": 40,
        "children": [],
    }
    attach_semantic(tree)
    first = dict(tree["semantic"])
    attach_semantic(tree)
    assert tree["semantic"] == first


def test_home_icon_is_not_dashboard_role() -> None:
    assert infer_role("Home icon crop", page="Buttons") != "dashboard"
    assert infer_role("Home", page="App") == "dashboard"
    # Kit page titles containing "Dashboard" must not force every screen role.
    assert infer_role("Current Values", page="Modernize Admin Dashboard by AdminMart") == "page"
    assert infer_role("Sales overview", page="Modernize Admin Dashboard by AdminMart") == "dashboard"


def test_blur_clamp_records_original() -> None:
    effects = shadows([{"type": "LAYER_BLUR", "radius": 48, "visible": True}])
    assert effects[0]["blur"] == 24
    assert effects[0]["clamped"] is True
    assert effects[0]["originalRadius"] == 48


def test_text_weight_source_from_style_name() -> None:
    payload = text(
        {
            "textData": {"characters": "Hello"},
            "fontName": {"family": "Inter", "style": "SemiBold"},
            "fontSize": 16,
        }
    )
    assert payload is not None
    assert payload["weightSource"] == "font-style-name"
    assert payload["weight"] == 600
