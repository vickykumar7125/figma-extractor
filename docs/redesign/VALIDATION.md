# Validation note (prompt 17)

Fresh re-extracts used for this pass (not overwriting checked-in `out/`):

| Kit | Output |
| --- | --- |
| CreBiz | `/tmp/fe-validate-crebiz` |
| Modernize | `/tmp/fe-validate-modernize` |
| Vuexy | `/tmp/fe-validate-vuexy` (reuse decode + fresh pipeline) |
| Rocket Light | `/tmp/fe-validate-rocket-light` |
| readmin | `/tmp/fe-validate-readmin4` |

| Question | File / field | Result |
| --- | --- | --- |
| Screens and origin | `screens.json` `origin`, `sourceScreenId`, `trees/boards/` | Pass — CreBiz 12×`top-level`; Modernize 160/10/10; Vuexy 416/112/168; Rocket 103/204/101; boards archived when split |
| Role and confidence | `role`, `semantic` | Pass — Modernize **1** dashboard (was ~170); Vuexy Icon Button crop `semantic.kind=specimens` |
| Route and inferred | `suggestedRoutes[].inferred` | Pass — all `inferred: true`; Icon Button crop **absent** from primary routes |
| Regions | `ui-flow` regions + evidence | Pass when name regex matches |
| Components / axes | `components.json`, `component-sets.json` | Pass — Vuexy **88** sets; Rocket Light **`[]`** (no fabricated axes) |
| Instance → component | tree `instanceOf`, `overrides`, `componentPropAssignments` | Pass |
| Explicit tokens / refs | `styleRefs`, `variableRefs` | Pass — CreBiz 747 styleRef nodes; Vuexy variableRefs present (3100+ in sample) |
| SVG asset and usage | `vectorRef`, `vectorScale`, unified manifest | Pass — Icon Button crop **24×`vectorRef`**, 0 inline paths; ~14.7 MB path bytes saved on Vuexy |
| Raster assets | `assets/manifest.json` `kind:raster` | Pass — readmin rasters restored via sibling `images/` copy; Rocket blob materialize 29 |
| Hierarchy / constraints | tree + `diagnostics/layout.json` | Pass — value distributions; `breakpoints: null` |
| Text | `text.weightSource` | Pass when text exists |
| Prototype interactions | `ui-flow.interactions` | Pass — Vuexy 1680; CreBiz `[]`; readmin 15 |
| Truncation / unsupported | diagnostics | Pass — budget=5 fixture; outline-compile-failed recorded for missing stroke blobs |
| Per-file LLM guide | `LLM.md`, `screens/<slug>/screen.json` | Pass — headers differ; reconstruction hints include `flex` / `svg-reference` when evidenced |

## Gaps that stay gaps

- Checked-in `out/*` remains stale until re-extracted.
- A few stroke geometries reference missing command blobs → listed in `diagnostics/unsupported.json` (`outline-compile-failed`), not invented.

## Determinism

Two CreBiz extracts into different directories (`/tmp/fe-det-crebiz-a` / `-b`) produced identical screen rows, routes, interactions, tree SHA-256 hashes, and `vectors.json`. `LLM.md` headers differ only by the output folder name used as `source`.

## Schema migration (prompt 16)

Extracts write `schemaVersion: 2`, unified `assets/index.json`, `diagnostics/performance.json`, and always-present diagnostics. Schema 1 trees remain readable.
