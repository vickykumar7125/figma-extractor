# 05 — Component extraction

## Objective

Tell an LLM what is reusable, what varies, and what an instance overrides, using fields Figma already stored.

## Context

`docs/redesign/AUDIT.md` section B. Vuexy: 6,055 symbols, 88 state-group sets. Rocket: hundreds of symbols, zero `isStateGroup`, empty `component-sets.json` (correct). Tree instances inline the master. `componentPropRefs` and `componentPropAssignments` are in the Vuexy ndjson and absent from trees. `components.json` variant props are parsed from `Key=Value` names only.

## Existing implementation to inspect

`extract/structure.py` `slim`, `parse_variant`, component and set builders. Instance override merge in `extract/trees.py` `override_map` and the `INSTANCE` branch of `walk`.

## Files and folders to inspect

`out/vuexy-.../component-sets.json`, `out/vuexy-.../components.json`, `out/Rocket – Admin Dashboard [Light]/component-sets.json` (empty array), Icon Button crop instances (`instanceOf` `5636:463`).

## Constraints

Do not invent variant axes for Rocket’s kiwi v1 symbols. Do not stop inlining instance children until prompt 06 has a `vectorRef` (inlining remains the fallback). An empty `component-sets.json` stays valid.

## Required analysis

Take one Vuexy symbol with `componentPropDefs` and one instance with `componentPropAssignments`. List which values the tree currently shows only as flattened paints or text.

## Required implementation

- Keep `components.json` and `component-sets.json` keys.
- Include full prop def metadata that is already on the node (`id`, `name`, `type`, default, variant options) when present.
- On `INSTANCE` nodes, add `overrides`: a list of `{targetId, keys}` for fields applied from symbol overrides, not a second copy of the subtree.
- Add `componentPropAssignments` when the raw instance has them.
- Leave Rocket sets empty. Optionally add `derivedFromName: false` on name-parsed props so they are not confused with `isStateGroup` axes.

## Required tests

- Vuexy set count stays 88 and each set still has `axes` and `variants`.
- Rocket `component-sets.json` is `[]`.
- Icon Button instance still has `instanceOf` and children.
- An instance with assignments exposes them without dropping `children`.

## Required outputs

Richer component records and instance override indexes.

## Acceptance criteria

An LLM can answer which component an instance uses and which props were assigned, without parsing the symbol name only.

## Do-not-break rules

Do not synthesize Rocket variant sets. Preserve `variantOf`, `variantOfId`, `instanceOf`. Deterministic prop order. Inspect structure builder before adding fields.
