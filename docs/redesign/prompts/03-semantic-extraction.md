# 03 — Semantic extraction

## Objective

Add an optional `semantic` object beside `type`, with confidence and evidence, for a closed set of kinds that the corpus can test.

## Context

`docs/redesign/AUDIT.md` section I. `type` stays the Figma enum. Current roles live in `extract/flow.py` and are name keywords. The Icon Button crop (`buttons__material-icon-button__icon-button__crop.json`) is a frame of `SYMBOL` specimens and must not be labeled a product screen at high confidence.

## Existing implementation to inspect

`infer_role`, `infer_region_role`, `DEMO_PAGE_NAMES` in `extract/flow.py`. Screen `role` written in `build_ui_flow`. Tree node construction in `extract/trees.py`.

## Files and folders to inspect

`out/CreBiz/screens.json` (roles look plausible). `out/Modernize-Dashboard-Admin-Figma-Latest` (170 of 180 screens are `dashboard` because keywords include `home`). `out/vuexy-.../trees/buttons__material-icon-button__icon-button__crop.json`.

## Constraints

Closed vocabulary only: `screen`, `section`, `header`, `nav`, `sidebar`, `footer`, `card`, `button`, `icon-button`, `input`, `image`, `icon`, `component-gallery`, `specimens`. No match means omit `semantic`. Name-only matches use confidence at or below 0.6 and list the keyword in `evidence`. Never delete `type` or the existing `role` string in this phase.

## Required analysis

List the rule for each kind before coding. Mark which rules use only the node name and which use children (for example child `SYMBOL` nodes plus `Key=Value` names).

## Required implementation

Pure function of a node plus parent and immediate children. Attach `semantic` on tree nodes and on screen records. Keep the existing `role` string. Narrow the `home` and `index` keyword hits so a split crop is not a dashboard unless the name actually denotes one, or lower the confidence and record the evidence.

The Icon Button crop’s semantic kind is `specimens` or `component-gallery`, with evidence that children are symbols whose names contain variant axes.

## Required tests

- Icon Button crop kind is specimens/gallery, confidence stated, `type` still `FRAME`.
- CreBiz screen count and existing `role` strings still present.
- A frame with no rule has no `semantic` key.
- Two extracts of the same fixture produce the same `semantic` object.

## Required outputs

`semantic` on trees and screen records. Short rule table in `README.md` or `docs/redesign/AUDIT.md` appendix only if the code’s docstring is not enough.

## Acceptance criteria

A reader can see why a node was classified. Unclassified nodes stay clean. Modernize no longer reports ~170 dashboards without evidence.

## Do-not-break rules

Do not replace `type`. Do not fabricate kinds outside the closed set. Inspect `flow.py` and reuse its keyword lists only where confidence stays low. Deterministic ordering of `evidence`. Schema stays additive.
