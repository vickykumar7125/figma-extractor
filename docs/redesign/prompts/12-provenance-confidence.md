# 12 — Provenance and confidence

## Objective

Every derived value states what it was derived from. Source facts stay unmarked or marked explicit.

## Context

`docs/redesign/AUDIT.md` sections I and J. Today a CSS color, a role, and a route look equally authoritative. `semantic.confidence` and route `inferred` come from prompts 03 and 09. This prompt applies the same discipline to the remaining derived fields.

## Existing implementation to inspect

Role assignment, route suggestion, font weight fallback (`font_weight_from_name` used when `derivedTextData` is absent), blur radius clamp at 24 in `shadows`, boolean child omission.

## Files and folders to inspect

`extract/trees.py` `shadows` and `text`. `extract/tokens.py` font weight comment. `extract/flow.py` `infer_role`.

## Constraints

Do not wrap every raw field in a provenance envelope. Attach provenance only to values the code computed. Confidence is a number only when a heuristic ran. Explicit copies of raw fields do not get a confidence.

## Required analysis

Make a table: field, raw or derived, where the decision lives. Include font weight, role, route, blur clamp, semantic kind, inferred spacing if it exists.

## Required implementation

- Font weight that came from the style name gets `text.weightSource: "font-style-name"`. Weight from `derivedTextData` gets `"font-metadata"`.
- Blur values that were clamped get `clamped: true` and the original radius.
- Boolean nodes that omitted children get `childrenOmitted: "resolved-outline"`.
- Roles and routes use the evidence and `inferred` flags from earlier prompts. Do not add a second role field.

## Required tests

- A local text style without `derivedTextData` (Rocket or the token tests) records `weightSource`.
- An effect with radius above 24 records the clamp.
- A CreBiz solid fill that was copied from a paint has no confidence wrapper.

## Required outputs

Source tags on derived text, effects, and booleans.

## Acceptance criteria

An LLM can tell a clamped blur and a guessed route from a fill that was in the file.

## Do-not-break rules

Do not change numeric weight or CSS color values. Inspect the existing fallback before renaming it. Deterministic evidence strings. No confidence on raw copies.
