# 14 — Performance

## Objective

Decode and index once, and stop repeating vector geometry in every instance.

## Context

`docs/redesign/AUDIT.md` sections A and H. `extract()` already decodes once to ndjson, then structure, tokens, and images each scan that file. `TreeBuilder` loads every node into memory, then expands instances per screen. Vuexy is 80,875 nodes and a 290 MB ndjson; the 8 largest trees alone are about 27 MB, dominated by repeated vectors. Flow BFS-walks every tree again with an 800-node cap.

## Existing implementation to inspect

`api.py` `extract` order. `TreeBuilder.__init__` and `walk` instance branch. `build_ui_flow`. Prompt 06 `vectorRef` is the size win. Do not start this prompt by rewriting the kiwi decoder.

## Files and folders to inspect

`out/vuexy-.../extracted/nodes.ndjson` size, `out/vuexy-.../trees` file sizes, CreBiz timing from corpus reports (about 2 seconds).

## Constraints

Correctness before speed. Do not drop overrides to save memory. A shared asset must still show instance-level position, size, and override paints.

## Required analysis

Measure, on Vuexy or a fixture with repeated instances: peak time in tree build versus flow, and bytes of `paths` that a `vectorRef` would remove. Record numbers in the PR or the diagnostics report. Do not optimize a stage you have not measured.

## Required implementation

Only changes justified by those numbers. Expected direction: emit `vectorRef` and stop copying identical path strings; avoid a second full parse of ndjson inside flow if the tree walk already knows component ids. Keep the node index as one pass.

## Required tests

- Icon Button crop file is smaller after dedupe and still has 24 instances positioned apart.
- CreBiz tree JSON remains valid and visually the same node count.
- Corpus harness memory cap still isolates one file.

## Required outputs

Smaller repeated trees and a note of what was measured.

## Acceptance criteria

Repeated icons are referenced, not recopied. CreBiz node counts stay stable. No decoder rewrite.

## Do-not-break rules

Measure first. Do not change kiwi decoding to chase tree size. Deterministic output. Override paints on an instance still win over the master.
