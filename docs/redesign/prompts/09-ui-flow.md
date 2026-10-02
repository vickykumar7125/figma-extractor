# 09 — UI flow

## Objective

Keep guessed routes, and add real prototype links only where the decoded file contains them.

## Context

`docs/redesign/AUDIT.md` section B. `suggestedRoutes` are slugs. CreBiz’s first route is `/02-cdesign/studio`, a canvas-and-frame slug, role `page`. `LLM.md` already says the routes are guesses. Vuexy ndjson contains `prototypeInteractions`. CreBiz ndjson does not. Regions are name regexes, two levels down, capped while scanning.

## Existing implementation to inspect

`extract/flow.py` `suggest_route_path`, `build_ui_flow`, `scan_tree`. Search ndjson for `prototypeInteractions` shape before mapping fields.

## Files and folders to inspect

`out/CreBiz/ui-flow.json`, `out/vuexy-.../extracted/nodes.ndjson` (prototype lines), `out/vuexy-.../ui-flow.json` summary counts (696 trees, 290 routes, 49 pages).

## Constraints

Do not delete `suggestedRoutes`. Do not invent a destination. If a prototype record is missing a target, keep the source node and set `target: null` with a diagnostic. Region detection may gain evidence strings but must not drop `role` and `name`.

## Required analysis

Paste one raw prototype record (trimmed) and the fields you will keep: source node id, trigger, destination id, transition type. If the schema varies by kiwi version, support the shapes you actually see in Vuexy and ignore unknown shapes via diagnostics.

## Required implementation

- Every `suggestedRoutes` item gains `"inferred": true`.
- New `interactions` array, empty when the file has no prototype records. Each item is a source fact: `fromId`, `trigger`, `toId`, `navigation` when present.
- Do not copy interactions into `suggestedRoutes`.
- Screen flow entries may reference interaction ids that start on that screen.
- Prompt 04’s specimen screens stay out of the primary route list.

## Required tests

- CreBiz `interactions` is `[]` and existing paths still start with `/`.
- Vuexy `interactions` is non-empty and every `toId` that is non-null exists as a node id in ndjson or is diagnosed.
- Route paths stay unique.
- Re-extract preserves interaction order (source order or a documented sort).

## Required outputs

`ui-flow.json` with labeled guesses and a separate interaction list.

## Acceptance criteria

An LLM can follow a prototype edge when one exists, and can see that `/02-cdesign/studio` was not a prototype.

## Do-not-break rules

Do not turn keywords into click targets. Preserve `pages`, `summary`, `hasNav`, `hasSidebar`, `hasForm`, `texts`, `componentsUsed`. Inspect raw records before naming JSON fields.
