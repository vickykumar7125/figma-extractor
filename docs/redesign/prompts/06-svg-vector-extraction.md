# 06 — SVG and vector extraction

## Objective

Turn vector outlines the trees already contain into deduplicated SVG assets, without rasterizing and without removing one-off inline paths.

## Context

`docs/redesign/AUDIT.md` section E. No `.svg` files exist under `out/`. `PathStore` already emits `{d, rule}` from `fillGeometry` and `strokeGeometry`. The Icon Button crop repeats two star paths across 24 vectors. The 8 largest Vuexy trees contain 13,074 `VECTOR` nodes and only 2,072 with fill paths; raw `strokeGeometry` is nearly universal. Stroke cap and join are not on the tree until prompt 02 lands.

## Existing implementation to inspect

`fig` path store (search `PathStore`, `outlines`). `extract/trees.py` geometry block and boolean-operation early return. `extract/images.py` manifest shape to mirror for vectors.

## Files and folders to inspect

`out/vuexy-.../trees/buttons__material-icon-button__icon-button__crop.json`, `out/CreBiz/trees` (91 of 103 vectors have paths, modest repetition), `out/readmin/trees` (many vectors, no instances).

## Constraints

Do not rasterize. Do not drop boolean `paths` or the rule that hides boolean operands once an outline exists. Do not inline-remove a path unless `vectorRef` resolves to the same `d`. Dedup key is the geometry and paint/stroke signature, not the instance id. One star at three scales may be one asset with a scale, or three assets; pick one rule and test it. Prefer one asset plus instance scale when the commands match after normalization.

## Required analysis

Count distinct path strings in the Icon Button crop versus vector nodes. Find one Vuexy vector with stroke geometry in ndjson and neither `paths` nor `strokePaths` in the tree. Fix that loss or record it in diagnostics. Do not claim every vector becomes an SVG if the outline is missing.

## Required implementation

- `assets/vectors.json` records: `id`, `sourceNodeId` of the master, `name`, `width`, `height`, `viewBox`, `usageCount`, `hash`.
- `assets/svg/<id>.svg` for records used more than once, or small icon-like vectors (both width and height at most 64, or name/path that is already classified `icon` / `icon-button`).
- Tree node gains `vectorRef` when it participates. Inline `paths` remain for nodes that do not meet the asset rule.
- SVG uses the stored fill, stroke, cap, join, and opacity. No extra wrapper chrome.

## Required tests

- Icon Button star `d` appears in one SVG and the tree nodes reference it. Usage count covers the repeated vectors.
- CreBiz still has inline paths for vectors that are not shared icons.
- Re-extract is deterministic: same ids and filenames.
- A boolean operation with `paths` still omits operand children.
- Zero new PNGs produced from vectors.

## Required outputs

`assets/svg/`, `assets/vectors.json`, `vectorRef` on shared geometry.

## Acceptance criteria

An LLM can reference the star icon instead of copying the path 24 times, and can still read a one-off illustration from the tree.

## Do-not-break rules

Inspect `PathStore` and reuse it. Do not introduce a second path compiler. Keep `paths` for non-deduped nodes. Report missing stroke outlines instead of emitting empty SVG. No rasterization.
