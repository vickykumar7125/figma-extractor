# 16 — Schema migration

## Objective

Ship additive schema 2 while schema 1 files remain readable.

## Context

`docs/redesign/AUDIT.md` section K. Current artifacts have no `schema_version`. Keys consumers already use: `screens.json` `id`, `slug`, `tree`, `role`, `width`, `height`; tree `type`, `layout.dir`, `layout.pad`, `instanceOf`, `paths`, `fills`, `text`; `suggestedRoutes[].path`; token css; asset `file` and `bytes`.

## Existing implementation to inspect

`README.md` output tree. `tests/test_fig_corpus.py` `REQUIRED_FILES`. `extract/__init__.py` exports. `paths.py` deliverable names in `api.py`.

## Files and folders to inspect

`README.md`, `src/figma_extractor/api.py` `DELIVERABLE_FILES`, `out/CreBiz` listing.

## Constraints

No renames of existing files in this phase. New files are allowed (`manifest.json`, `diagnostics/`, `screens/<slug>/screen.json`, `assets/svg/`, `assets/vectors.json`, `trees/boards/`). `layout.pad` stays until `layout.padding` is tested against it. `component-sets.json` may be `[]`. `role` remains a string.

## Required analysis

List every new key and file from prompts 02–13 and the schema 1 key it must not replace.

## Required implementation

- Write `schemaVersion: 2` on root `manifest.json` and `trees/index.json` when the additive fields exist.
- Document schema 1 versus 2 in `README.md`, including `pad` order and `layout.padding` names.
- Update `REQUIRED_FILES` only for files that every extract writes, including empty diagnostics. Do not require `assets/svg` on files with no shared vectors; require `assets/vectors.json` only if the prompt 06 contract says it always exists (empty list is fine).

## Required tests

A schema 1 fixture (current CreBiz tree fragment) still loads with the reader the README describes. A schema 2 extract contains the new files and the old paths.

## Required outputs

README schema section, version fields, corpus required-file list aligned with the contract.

## Acceptance criteria

An old agent that only opens `trees/*.json` and `screens.json` still works. A new agent can see `schemaVersion`.

## Do-not-break rules

Do not move `trees/` or `tokens/` in this phase. Do not remove `LLM.md`. Inspect `DELIVERABLE_FILES` before adding required outputs. Empty collections are valid.
