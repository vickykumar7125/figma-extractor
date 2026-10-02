# 11 — LLM output

## Objective

Make one screen discoverable without a static guide that is identical for every file.

## Context

`docs/redesign/AUDIT.md` sections F and H. `LLM.md` is `flow.llm_guide()` and hashes the same for all 12 extracts. A screen is scattered across `screens.json`, `trees/<slug>.json`, `ui-flow.json`, `components.json`, `tokens.css`, and `assets/manifest.json`. The largest Vuexy trees are tens of megabytes because instances inline vectors.

## Existing implementation to inspect

`extract/flow.py` `llm_guide`, `build_ui_flow`. `trees/index.json`.

## Files and folders to inspect

`out/CreBiz/LLM.md`, `out/vuexy-.../LLM.md` (same text), `out/CreBiz/screens.json`, `out/CreBiz/trees/index.json`.

## Constraints

Keep the current read-order instructions in `LLM.md` under the generated section. Do not copy full tree bodies into a second directory. Bundles are references.

## Required analysis

List the joins required to answer, for one CreBiz screen: size, role, regions, tree path, component ids, image hashes, text samples. That list is the bundle schema.

## Required implementation

- Generate the top of `LLM.md` from this extract: source name, screen count, component count, token counts, asset counts, schema version, and the paths of the indexes. Keep the static instructions below.
- Write `manifest.json` at the output root with those counts and paths.
- Write `screens/<slug>/screen.json` containing references only: screen record, `tree` path, asset ids, component ids, text samples already collected by flow, semantic evidence, route with `inferred`. No embedded tree.
- Reconstruction hints, if any, live under `reconstruction` and use `kind: "recommended"`. Allowed hints must be derived from fields that exist (`layout.dir` → flex, `vectorRef` → svg reference, button semantic → `button`). If the evidence is missing, omit the hint.

## Required tests

- Two files no longer share identical `LLM.md`.
- CreBiz `screens.json` tree paths still open.
- A bundle’s `tree` path exists and its JSON has `type` and `w`.
- Bundle file does not contain a nested `children` array of the full tree.

## Required outputs

Per-file `LLM.md`, root `manifest.json`, `screens/<slug>/screen.json`.

## Acceptance criteria

An agent can open one bundle and know which files to read, what is inferred, and what is recommended.

## Do-not-break rules

Do not remove `trees/*.json`. Do not duplicate path data into the bundle. Recommendations are not facts. Inspect `scan_tree` and reuse its text and component caps instead of a second walk with different limits.
