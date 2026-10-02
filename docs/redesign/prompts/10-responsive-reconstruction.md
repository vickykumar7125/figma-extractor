# 10 — Responsive reconstruction

## Objective

Represent responsive behavior only where the file states it: constraints, sizing, wrap, grow, absolute children.

## Context

`docs/redesign/AUDIT.md` sections B and D. The corpus has no stored breakpoint set. Constraints are on the raw nodes and were dropped. Auto-layout `wrap`, `grow`, `hugMain`, `hugCross`, and `absolute` are already on trees when Figma set them. Inventing 768 or 1024 widths would be false precision.

## Existing implementation to inspect

`extract/trees.py` `layout` and the sizing flags in `node`. Prompt 02 constraint fields.

## Files and folders to inspect

A Vuexy frame with `horizontalConstraint` not equal to a fixed default, and a CreBiz auto-layout frame that wraps or hugs. `out/CreBiz/trees` for a screen with `layout.wrap` or `grow` if any exist.

## Constraints

No breakpoint table unless a raw field contains explicit layout dimensions for more than one size (not observed in this audit). If you find one, quote the field. Otherwise do not add `breakpoints`.

## Required analysis

Distribution of `horizontalConstraint` and `verticalConstraint` values on one Vuexy page. Count `stackWrap`, `stackChildPrimaryGrow`, and `stackPositioning=ABSOLUTE`. Publish that count in the diagnostics or README note so the reconstruction hint is grounded.

## Required implementation

Ensure prompt 02 fields survive. Add `layout.sizing` only as a normalized view of hug/grow/fixed already implied by `hugMain`, `hugCross`, and `grow`. Recommendations such as `stack-on-small-screen` belong in prompt 11 and must be marked recommended, not stored as facts here.

## Required tests

- A constrained node round-trips its enum values.
- CreBiz output gains no `breakpoints` key.
- A node with `absolute: true` still has it.

## Required outputs

Constraint and sizing facts on nodes. A written statement of what was not inferred.

## Acceptance criteria

An LLM can say which children are fixed, hugging, wrapping, or edge-constrained, and cannot cite a breakpoint the file never had.

## Do-not-break rules

Do not invent viewport widths. Do not rewrite `layout.dir`. Inspect raw enums before mapping them to CSS. Missing constraints stay omitted.
