# 08 — Design token pipeline

## Objective

Mark every token as explicit, derived, or inferred, and point tree paints at explicit styles and variables when the file has them.

## Context

`docs/redesign/AUDIT.md` sections B and D. Styles and variables are already exported for files that contain them. CreBiz and readmin have no variables. Vuexy has 265 variables and thousands of `variableConsumptionMap` / `inheritFillStyleID` entries that never reach the tree. Spacing scales are not inferred, and must not be invented. `LLM.md` currently tells the agent to match hex strings against `tokens.css`.

## Existing implementation to inspect

`extract/tokens.py` `build_tokens`, `paint_to_css`, `resolve_variable_value`, `style_group`, `build_css`. Prompt 02 `styleRefs` and `variableRefs`.

## Files and folders to inspect

`out/vuexy-.../tokens/`, `out/CreBiz/tokens/tokens.css` (small, few styles), `out/Rocket – Admin Dashboard [Light]/tokens` (styles, no variables).

## Constraints

Do not add a spacing scale unless a value occurs at a documented frequency and is marked `kind: inferred`. Do not rename CSS variables already emitted. Color groups stay first-slash unless you add a separate semantic group that does not replace the file.

## Required analysis

Count how often a tree solid color equals an explicit style value in CreBiz versus how often it is only a raw paint. Report the match rate. Matching by string is a fallback, not the link.

## Required implementation

- Add `kind: "explicit"` on style and variable records.
- Keep `tokens.css` output stable for existing custom properties.
- When prompt 02 refs exist, prefer those over color equality.
- If an inferred scale is added, write it to `tokens/spacing.inferred.json` and do not merge it into `tokens.css` in this phase.

## Required tests

- CreBiz still writes `tokens/tokens.css` with balanced braces and a `:root` block when styles exist; empty-style files stay valid.
- A node with `inheritFillStyleID` exposes that id and the style’s explicit value resolves.
- Rocket text styles still produce typography tokens and font weights.
- No inferred file is created when the threshold is not met (CreBiz is the check).

## Required outputs

Labeled token records and tree-to-token refs.

## Acceptance criteria

An LLM can tell a named color style from a one-off paint. It is not instructed to guess by hex when a ref exists.

## Do-not-break rules

Corpus token checks in `tests/test_fig_corpus.py` stay. Do not emit empty groups that change “file declares no FILL styles” behavior. Facts (explicit) stay separate from inferred tokens.
