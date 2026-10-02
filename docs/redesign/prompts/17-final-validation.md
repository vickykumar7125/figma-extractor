# 17 — Final validation

## Objective

Re-extract representative files and answer the audit’s reconstruction questions from the output alone.

## Context

`docs/redesign/AUDIT.md`, especially the closing table and section M. Phases 1–4 are the bar for this validation. Semantic kinds beyond the closed set, inferred spacing, and invented breakpoints are out of scope.

## Existing implementation to inspect

The extractor after prompts 02–16. Compare against `out/CreBiz`, the Vuexy Icon Button crop, `out/Rocket – Admin Dashboard [Light]`, and `out/readmin` as the pre-change evidence. Re-extract into a new directory, not over `out/`, until the diff is understood.

## Files and folders to inspect

New extract of CreBiz, Rocket Light, readmin, and Vuexy (or the Icon Button page if a full Vuexy run is too heavy, plus one real dashboard screen). `tests/test_fig_corpus.py` if the drive is mounted.

## Constraints

Do not edit a fixture so it matches a regression. Do not delete `out/` until the comparison is written down.

## Required analysis

For each question below, cite the file and field in the new extract, or cite the diagnostic that says the information is absent:

- screens and their origin
- role and confidence
- route and whether it is inferred
- regions
- reusable components and variant axes
- instance to component id
- explicit tokens and refs
- SVG asset and usage
- hierarchy and layout, including constraints when the source had them
- text
- prototype interactions when present, empty list when not
- truncation or unsupported nodes

## Required implementation

Bugfixes only for failures this pass finds. No new subsystem.

## Required tests

Fixture suite green. If the corpus drive is present, the 12-file harness green except checks you have explicitly retired in prompt 16.

## Required outputs

A validation note in `docs/redesign/VALIDATION.md`: question, file, field, pass or gap. Gaps stay gaps. Do not mark a slug guess as a real route.

## Acceptance criteria

CreBiz can be rebuilt from structure without a screenshot for flex, text, fills, and images. The Icon Button star is a referenced SVG, and that frame is not a primary product route. Rocket still has no fabricated variant sets. readmin still has its rasters. Anything missing is named in diagnostics.

## Do-not-break rules

Validate against the corpus, not only happy-path fixtures. Preserve determinism on a second CreBiz extract. Do not start a new architecture if a question fails; record the gap and fix the specific field.
