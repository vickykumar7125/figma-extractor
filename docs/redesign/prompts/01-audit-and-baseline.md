# 01 — Audit and baseline

## Objective

Confirm the implementation you are about to change is the audit baseline, and record any drift before writing code.

## Context

Read `docs/redesign/AUDIT.md`. GitHub `main` at `d4e8886` is the baseline. Local source matched that commit when the audit was written. `out/` and `corpus-review/` are extracts of the same 12 `.fig` files.

## Existing implementation to inspect

`src/figma_extractor/api.py` pipeline order. `extract/structure.py`, `extract/tokens.py`, `extract/images.py`, `extract/trees.py`, `extract/split.py`, `extract/flow.py`.

## Files and folders to inspect

- `docs/redesign/AUDIT.md`
- `README.md`
- `tests/test_fig_corpus.py`
- `out/CreBiz` (small, high quality)
- `out/vuexy-figma-dashboard-ui-kit-and-builder-v4/trees/buttons__material-icon-button__icon-button__crop.json`
- `corpus-review/*/report.json` for the check list the harness already enforces

## Constraints

Do not change extraction behavior in this prompt. Drift notes only.

## Required analysis

Diff local `src/` against `d4e8886`. If they differ, list the commits or dirty files and say which audit sections are stale. Confirm `out/` still has 12 directories and that `LLM.md` is identical across them.

## Required implementation

None.

## Required tests

None.

## Required outputs

A short drift note: commit, clean or dirty, any audit section that no longer matches the code.

## Acceptance criteria

A later prompt can assume the audit or can point at the lines that moved.

## Do-not-break rules

Do not edit `out/` or `corpus-review/` extracts. Do not commit those directories. Inspect before coding. Treat GitHub `main` as the baseline. Reuse working code. No speculative rewrite.
