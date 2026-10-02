# 02 — Schema normalization

## Objective

Expose layout and paint facts the decoder already has, without a new semantic layer.

## Context

`docs/redesign/AUDIT.md` sections C, G, and J. Tree nodes drop constraints, stroke cap/join, the rest of the transform, and style/variable ids. `layout.pad` is `[stackVerticalPadding, stackPaddingRight, stackPaddingBottom, stackHorizontalPadding]` and is unlabeled. Vuexy’s first 12,000 nodes include `horizontalConstraint` and `verticalConstraint` on 11,866 of them.

## Existing implementation to inspect

`extract/trees.py` `paint`, `layout`, `radius`, `node`, `TreeBuilder.node`. Raw samples in `out/vuexy-figma-dashboard-ui-kit-and-builder-v4/extracted/nodes.ndjson` and the matching tree.

## Files and folders to inspect

`src/figma_extractor/extract/trees.py`, `src/figma_extractor/util.py` (`write_json`), `out/CreBiz/trees`, one Vuexy tree that contains a constrained frame.

## Constraints

Additive schema only. Keep `pad`, `x`, `y`, `w`, `h`, `stroke.weight`, `stroke.align`. Do not invent breakpoints. Do not emit nulls.

## Required analysis

Pick one raw guid that has constraints, stroke cap, and an inherit-style id. Show the tree node before the change. Confirm which transform matrix fields exist besides `m02` and `m12`.

## Required implementation

On the tree node, when the raw field is present:

- `layout.padding` as `{top, right, bottom, left}` mapped explicitly from the four stack padding fields. Keep `pad` byte-for-byte identical.
- `constraints.horizontal` and `constraints.vertical`.
- `stroke.cap`, `stroke.join`, dash pattern, and per-side weights when they differ from the uniform weight.
- `styleRefs` and `variableRefs` as ids, not resolved colors. Resolved fills stay.
- Rotation or scale only if the matrix is not a pure translation. Store the matrix; do not bake a second coordinate system.

Set `schemaVersion: 2` on `trees/index.json` only after these fields exist. Write a one-line schema note in `README.md`.

## Required tests

Corpus check or fixture: a node with constraints in ndjson has the same values on the tree. CreBiz trees still contain `layout.dir` and `layout.pad`. A node without constraints does not gain an empty `constraints` object.

## Required outputs

Updated trees, `trees/index.json` schema version, README schema note.

## Acceptance criteria

An LLM can read padding as named sides and can read constraints without opening ndjson. Existing keys are unchanged.

## Do-not-break rules

Inspect existing code first. GitHub `main` is the baseline. Reuse `layout` and `paint`. Preserve CreBiz and Rocket output keys. Do not drop inline `paths`. No silent discard: if a stroke cap value is unrecognized, record it in diagnostics (prompt 13) or pass it through as a string. Keep facts separate from recommendations. Document the schema change.
