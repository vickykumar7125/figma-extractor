# 15 — Testing corpus

## Objective

Lock the audit’s corpus findings into tests that run without the external drive, and keep the full-drive harness.

## Context

`tests/test_fig_corpus.py` extracts every `.fig` under `FIGMA_CORPUS` or `/run/media/kumar/DRIVE256/DataBackup/FigmaFiles`. It checks deliverables, canvas counts, conditional tokens, symbols, state groups, text, asset sizes, and guid-shaped `usedBy`. `--keep` fails “intermediates removed” on purpose. The drive is not available in CI.

## Existing implementation to inspect

`tests/test_fig_corpus.py`. `out/CreBiz` as the shape fixture source. Icon Button crop as the specimen fixture source. Do not commit `out/` or `corpus-review/`.

## Files and folders to inspect

`tests/`, `out/CreBiz/screens.json`, `out/CreBiz/trees` (one small tree), the Icon Button crop JSON, `out/Rocket – Admin Dashboard [Light]/component-sets.json`.

## Constraints

Commit trimmed fixtures, not the 12-file corpus and not ndjson for Vuexy. A fixture may be a checked-in fragment of a tree plus the assertion inputs, or a tiny synthetic `.fig` if one can be produced offline. Do not copy personal absolute paths into new tests beyond the existing default corpus path.

## Required analysis

Decide which assertions need a real `.fig` and which can read a JSON fixture. Schema tests should not re-decode Vuexy.

## Required implementation

- Keep `test_fig_corpus.py` as the optional full run.
- Add tests that load fixtures for: schema 1 keys still present, specimen crop not a primary route, empty component sets for a no-state-group sample, token `kind` when implemented, diagnostics files present, `LLM.md` not constant across two fixtures, SVG dedupe usage count.
- Gate each assertion on the schema version or feature so schema 1 fixtures still pass until that prompt lands. Use pytest skip or a version check, and do not delete the assertion.

## Required tests

`pytest tests` with no `FIGMA_CORPUS` passes the fixture suite. With the drive mounted, `pytest tests/test_fig_corpus.py` still runs the 12 files.

## Required outputs

`tests/fixtures/` and new test modules. No corpus binaries.

## Acceptance criteria

CI can tell a schema regression without the external disk. The drive harness still works.

## Do-not-break rules

Do not weaken canvas-count or asset-byte checks. Do not commit `out/` or `corpus-review/`. Inspect the harness checks before duplicating them.
