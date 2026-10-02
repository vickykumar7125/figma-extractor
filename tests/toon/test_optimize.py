"""Budget packing keeps the earliest rows and drops notes first."""

from __future__ import annotations

from figma_extractor.llm.context import context_size
from figma_extractor.llm.schemas import validate_task_payload
from figma_extractor.toon.optimize import pack_context


def test_pack_respects_token_budget() -> None:
    from figma_extractor.llm.context import fit_context

    screens = [{"id": str(index), "name": f"Screen {index}", "role": "page"} for index in range(30)]
    context = {"screen_classification": {"screens": screens}}
    packed = fit_context(context, 50_000, max_tokens=80)
    rows = packed["screen_classification"]["screens"]
    assert len(rows) < 30


def test_pack_keeps_the_front_of_a_list() -> None:
    screens = [{"id": str(index), "name": "Screen"} for index in range(12)]
    context = {
        "screen_classification": {
            "note": "x" * 400,
            "screens": screens,
        }
    }
    packed = pack_context(context, 180, context_size)
    rows = packed["screen_classification"]["screens"]
    assert "note" not in packed["screen_classification"]
    assert rows[0]["id"] == "0"
    assert len(rows) < 12
    assert context_size(packed) <= 180


def test_svg_markup_keeps_the_path() -> None:
    from figma_extractor.extract.svg import svg_markup

    markup = svg_markup(
        {
            "w": 16,
            "h": 16,
            "paths": [{"d": "M 0 0", "rule": "nonzero"}],
            "fills": [{"type": "solid", "color": "#111111"}],
        }
    )
    assert 'd="M 0 0"' in markup
    assert 'fill="#111111"' in markup


def test_unchanged_screens_are_skipped_after_annotation(tmp_path) -> None:
    from figma_extractor.catalog import changed_screen_ids, screen_hashes
    from figma_extractor.util import write_json

    trees = tmp_path / "trees"
    trees.mkdir()
    (trees / "home.json").write_text('{"id":"1:1"}', encoding="utf-8")
    (tmp_path / "screens.json").write_text(
        '[{"id":"1:1","tree":"trees/home.json"}]',
        encoding="utf-8",
    )
    assert changed_screen_ids(tmp_path) is None
    write_json(tmp_path / "catalog" / "screen-hashes.json", screen_hashes(tmp_path))
    (tmp_path / "llm-annotations.json").write_text("{}", encoding="utf-8")
    assert changed_screen_ids(tmp_path) == set()
    (trees / "home.json").write_text('{"id":"1:1","w":2}', encoding="utf-8")
    assert changed_screen_ids(tmp_path) == {"1:1"}


def test_prompt_proposal_is_applied_only_when_present() -> None:
    from figma_extractor.llm.prompt_format import apply_prompt_proposals

    messages = apply_prompt_proposals(
        "screen_classification",
        [{"role": "system", "content": "Reply with one JSON object"}, {"role": "user", "content": "task: x"}],
        {"screen_classification": "Keep ids."},
    )
    assert "Prompt proposal: Keep ids." in messages[0]["content"]
    assert "JSON object" in messages[0]["content"]
    assert messages[1]["content"] == "task: x"


def test_compact_aliases_shorten_keys() -> None:
    from figma_extractor.toon.optimize import apply_compact_aliases, compare_context_formats

    payload = {"screens": [{"id": "1", "name": "Home", "width": 100}]}
    compact = apply_compact_aliases(payload)
    assert compact["sc"][0]["i"] == "1"
    stats = compare_context_formats(payload)
    assert stats["compact_toon_chars"] <= stats["toon_chars"]


def test_svg_image_fill_uses_manifest_path(tmp_path) -> None:
    from figma_extractor.extract.svg import svg_markup

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "manifest.json").write_text(
        '[{"hash":"abc","file":"images/abc.png"}]',
        encoding="utf-8",
    )
    markup = svg_markup(
        {
            "w": 20,
            "h": 20,
            "paths": [{"d": "M0 0", "rule": "nonzero"}],
            "fills": [{"type": "image", "hash": "abc"}],
        },
        image_files={"abc": "images/abc.png"},
    )
    assert "<pattern" in markup
    assert "images/abc.png" in markup


def test_svg_clip_uses_bounds_and_radius() -> None:
    from figma_extractor.extract.svg import svg_markup

    markup = svg_markup(
        {
            "w": 40,
            "h": 20,
            "clip": True,
            "radius": 4,
            "paths": [{"d": "M0 0", "rule": "nonzero"}],
            "fills": [{"type": "solid", "color": "#111111"}],
        }
    )
    assert 'clipPath id="c0"' in markup
    assert 'rx="4' in markup
    assert 'clip-path="url(#c0)"' in markup


def test_svg_opacity_and_blend_wrap_paths() -> None:
    from figma_extractor.extract.svg import svg_markup

    markup = svg_markup(
        {
            "w": 10,
            "h": 10,
            "opacity": 0.5,
            "blend": "multiply",
            "paths": [{"d": "M0 0", "rule": "nonzero"}],
            "fills": [{"type": "solid", "color": "#111111"}],
        }
    )
    assert 'opacity="0.5"' in markup
    assert "mix-blend-mode:multiply" in markup


def test_svg_linear_gradient_is_referenced() -> None:
    from figma_extractor.extract.svg import svg_markup

    markup = svg_markup(
        {
            "w": 100,
            "h": 40,
            "paths": [{"d": "M0 0", "rule": "nonzero"}],
            "fills": [
                {
                    "type": "gradient",
                    "kind": "GRADIENT_LINEAR",
                    "angle": 90,
                    "stops": [{"at": 0, "color": "#000"}, {"at": 1, "color": "#fff"}],
                }
            ],
        }
    )
    assert "linearGradient" in markup
    assert 'fill="url(#g0)"' in markup


def test_proposed_component_must_not_claim_figma_origin() -> None:
    problems = validate_task_payload(
        "component_synthesis",
        {
            "items": [
                {
                    "name": "ProductCard",
                    "origin": "figma",
                    "targets": ["1:1"],
                    "confidence": 0.9,
                    "evidence": ["repeated row"],
                }
            ]
        },
    )
    assert any("llm_proposed" in item for item in problems)
