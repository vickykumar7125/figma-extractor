"""Screen origin, boards archive, dynamic LLM.md, and route exclusion."""

from __future__ import annotations

import json
from pathlib import Path

from figma_extractor.extract.flow import build_ui_flow, llm_guide
from figma_extractor.extract.split import split_screen_boards


def _write_tree(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_split_sets_origin_and_archives_board(tmp_path: Path) -> None:
    trees = tmp_path / "trees"
    trees.mkdir()
    board = {
        "id": "board:1",
        "type": "FRAME",
        "name": "Auth Board",
        "w": 1440,
        "h": 2400,
        "children": [
            {
                "id": "ui:1",
                "type": "FRAME",
                "name": "Sign In",
                "x": 0,
                "y": 0,
                "w": 1440,
                "h": 900,
                "children": [{"id": "t:1", "type": "TEXT", "name": "Title", "text": {"content": "Hi"}}],
            },
            {
                "id": "ui:2",
                "type": "FRAME",
                "name": "Sign Up",
                "x": 0,
                "y": 1000,
                "w": 1440,
                "h": 900,
                "children": [],
            },
        ],
    }
    _write_tree(trees / "page__auth-board.json", board)
    (tmp_path / "screens.json").write_text(
        json.dumps(
            [
                {
                    "id": "board:1",
                    "name": "Auth Board",
                    "page": "Auth",
                    "tree": "trees/page__auth-board.json",
                    "width": 1440,
                    "height": 2400,
                }
            ]
        ),
        encoding="utf-8",
    )

    summary = split_screen_boards(tmp_path)
    assert summary["boardsSplit"] == 1
    assert summary["boardsArchived"] == 1
    screens = json.loads((tmp_path / "screens.json").read_text(encoding="utf-8"))
    assert len(screens) == 2
    assert all(screen.get("origin") == "board-child" for screen in screens)
    assert all(screen.get("sourceScreenId") == "board:1" for screen in screens)
    assert all(screen.get("boardTree", "").startswith("trees/boards/") for screen in screens)
    board_files = list((trees / "boards").glob("*.json"))
    assert len(board_files) == 1
    archived = json.loads(board_files[0].read_text(encoding="utf-8"))
    assert archived["id"] == "board:1"
    assert len(archived["children"]) == 2


def test_crop_origin_and_route_exclusion(tmp_path: Path) -> None:
    trees = tmp_path / "trees"
    trees.mkdir()
    # Dense mid-size frame that promote_crops will lift.
    symbols = [
        {
            "id": f"s:{i}",
            "type": "INSTANCE",
            "name": f"State={i},Size=md",
            "instanceOf": "9:9",
            "w": 40,
            "h": 40,
            "children": [],
        }
        for i in range(8)
    ]
    crop = {
        "id": "crop:1",
        "type": "FRAME",
        "name": "Icon Button",
        "w": 640,
        "h": 360,
        "children": symbols,
    }
    # Pad with enough nodes so count_nodes >= 28 for non-overlay crops,
    # or rely on overlay name — use Modal in name for promotion.
    crop["name"] = "Icon Button modal"
    parent = {
        "id": "leaf:1",
        "type": "FRAME",
        "name": "Kit Page",
        "w": 1200,
        "h": 800,
        "children": [crop],
    }
    _write_tree(trees / "kit__page.json", parent)
    (tmp_path / "screens.json").write_text(
        json.dumps(
            [
                {
                    "id": "leaf:1",
                    "name": "Kit Page",
                    "page": "Components",
                    "tree": "trees/kit__page.json",
                    "width": 1200,
                    "height": 800,
                    "origin": "top-level",
                }
            ]
        ),
        encoding="utf-8",
    )
    summary = split_screen_boards(tmp_path)
    assert summary["cropsPromoted"] >= 1
    screens = json.loads((tmp_path / "screens.json").read_text(encoding="utf-8"))
    crops = [screen for screen in screens if screen.get("origin") == "crop"]
    assert crops
    assert crops[0].get("sourceScreenId") == "leaf:1"
    semantic = crops[0].get("semantic") or {}
    assert semantic.get("kind") in {"specimens", "component-gallery"}

    build_ui_flow(tmp_path)
    flow = json.loads((tmp_path / "ui-flow.json").read_text(encoding="utf-8"))
    crop_slugs = {screen["slug"] for screen in crops}
    assert all(route["screen"] not in crop_slugs for route in flow["suggestedRoutes"])


def test_llm_guide_is_file_specific(tmp_path: Path) -> None:
    a = llm_guide({"source": "CreBiz", "screens": 12, "primaryScreens": 12, "components": 3,
                   "colorStyles": 10, "variables": 0, "rasters": 18, "vectors": 2, "schemaVersion": 2})
    b = llm_guide({"source": "Vuexy", "screens": 400, "primaryScreens": 200, "components": 90,
                   "colorStyles": 40, "variables": 265, "rasters": 5, "vectors": 12, "schemaVersion": 2})
    assert a != b
    assert "CreBiz" in a
    assert "Vuexy" in b
    assert "Read order" in a

    trees = tmp_path / "trees"
    trees.mkdir()
    _write_tree(
        trees / "app__home.json",
        {"id": "1:1", "type": "FRAME", "name": "Home", "w": 1200, "h": 800, "children": []},
    )
    (tmp_path / "screens.json").write_text(
        json.dumps(
            [
                {
                    "id": "1:1",
                    "name": "Home",
                    "page": "App",
                    "slug": "app__home",
                    "tree": "trees/app__home.json",
                    "width": 1200,
                    "height": 800,
                    "origin": "top-level",
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "components.json").write_text("[]", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "manifest.json").write_text("[]", encoding="utf-8")
    (tmp_path / "assets" / "vectors.json").write_text("[]", encoding="utf-8")
    (tmp_path / "tokens").mkdir()
    (tmp_path / "tokens" / "color-styles.flat.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tokens" / "variables.json").write_text('{"variables":[]}', encoding="utf-8")

    build_ui_flow(tmp_path)
    guide = (tmp_path / "LLM.md").read_text(encoding="utf-8")
    assert "Extraction summary" in guide
    assert str(tmp_path.name) in guide or "Screens:" in guide
    bundle = tmp_path / "screens" / "app__home" / "screen.json"
    assert bundle.is_file()
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["tree"] == "trees/app__home.json"
    assert "children" not in payload
