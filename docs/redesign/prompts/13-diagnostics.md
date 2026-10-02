# 13 — Diagnostics

## Objective

Unsupported or truncated structure is written down. One bad asset does not erase the screen.

## Context

`docs/redesign/AUDIT.md` sections G and B. The tree walk stops at 60,000 nodes and depth 60 and returns a partial node with no flag. Remote image failures are already skipped and logged to stderr (`remote.py`). Local vector outlines that fail to compile disappear. Empty canvases still produce a tiny `structure/*.md`.

## Existing implementation to inspect

`TreeBuilder.walk` budget and depth. `download_remote_images`. `PathStore.outlines`. `extract/images.py` missing hashes (`missingHashes` is already in the images summary).

## Files and folders to inspect

`out/*/extracted` only as evidence. Stderr text is not a contract. `tests/test_fig_corpus.py` “intermediates removed” check fails when `--keep` is set; do not treat that as a product defect.

## Constraints

Diagnostics are JSON files, not a reason to fail the extract. Unknown node types stay in the tree with their `type` string. Do not drop a screen because one child failed.

## Required analysis

Identify each `continue` or `return None` in the tree walk and image loop that discards information. Classify it as skip-invisible (acceptable), truncate, or unsupported.

## Required implementation

- `diagnostics/truncated.json`: screen id, nodes written, budget or depth.
- `diagnostics/unsupported.json`: node id, type or field, reason.
- `diagnostics/assets.json`: image refs with no bytes, SVG outlines that could not be built.
- Set `truncated: true` on the tree root when the budget or depth stops the walk.
- Empty arrays when the extract was clean, so the file always exists.

## Required tests

- CreBiz diagnostics exist and `truncated.json` is empty unless a screen actually hit the cap.
- A unit fixture with a node budget of 5 writes a partial tree and one truncation record.
- A remote-style bad image name is skipped and listed, and the rest of the images remain (existing remote behavior).

## Required outputs

`diagnostics/*.json` and a `truncated` flag on partial trees.

## Acceptance criteria

After an extract, a missing icon or a cut-off frame is visible in diagnostics and the rest of the file is still there.

## Do-not-break rules

Do not turn diagnostics into a non-zero exit. Preserve invisible-node skipping. Do not swallow exceptions that mean the decode itself failed (`canvas.fig` missing still raises). Inspect before adding new try/except blocks.
