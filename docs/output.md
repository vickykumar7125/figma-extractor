# Output

Deliverables land at the output root. There is no nested `design/` folder. `source/` and `extracted/` are deleted after a successful extract unless you pass `--keep-intermediates`.

```
out/
├── LLM.md                        # per-extract summary + static read order
├── ui-flow.json
├── llm-annotations.json          # written by annotate, not by extract
├── manifest.json                 # schemaVersion: 2, counts, index paths
├── pages.json
├── screens.json                  # origin, sourceScreenId, role, semantic, tree
├── components.json
├── component-sets.json
├── text-content.json
├── STRUCTURE.md
├── COMPONENTS.md
├── trees/
│   ├── index.json                # schemaVersion: 2
│   ├── boards/                   # pre-split board trees when a board was split
│   └── <page>__<screen>.json
├── tokens/
│   ├── tokens.css
│   ├── color-styles.json
│   ├── color-styles.flat.json
│   ├── color-styles.conflicts.json
│   ├── variables.json
│   ├── typography.json
│   ├── effects.json
│   └── fonts.json
├── components/
│   └── index.json
├── assets/
│   ├── images/
│   ├── svg/                      # shared vector assets
│   ├── manifest.json             # rasters + vector rows (unified index)
│   ├── vectors.json
│   ├── index.json                # points at rasters + vectors
│   └── missing-hashes.json
├── structure/
│   └── <page>.md
├── screens/<slug>/screen.json    # reference bundle (no embedded tree)
├── catalog/                      # with extract --toon or figma-extractor toon
│   ├── index.json
│   └── screen-hashes.json
├── toon/
│   ├── screens.toon
│   ├── components.toon
│   ├── assets.toon
│   └── tokens.toon
├── document/
│   ├── document.json
│   └── llm-summary.json          # after annotate when catalog exists
├── patterns/
├── diagnostics/
│   ├── truncated.json
│   ├── unsupported.json
│   ├── assets.json
│   ├── layout.json               # constraint counts; breakpoints never invented
│   ├── interactions.json
│   └── performance.json          # vectorRef path-byte savings
└── prompts/                      # after LLM annotate with artifacts enabled
```

`--clean` (the default) deletes those deliverable files and directories, plus a legacy `design/` folder, before writing. `llm-annotations.json` is in that list, so a later `extract` removes a previous annotation file.

## What each file is for

| Path | Produced by | Contents |
| --- | --- | --- |
| `pages.json` | extract | Page records |
| `screens.json` | extract | Screen records: `tree`, `origin` (`top-level` / `board-child` / `crop`), optional `sourceScreenId` / `boardTree`, `role`, optional `semantic`, regions |
| `components.json` | extract | Component records with prop defs when present |
| `component-sets.json` | extract | Variant sets (`[]` when the file has none) |
| `text-content.json` | extract | Unique strings grouped by page |
| `STRUCTURE.md` | extract | Structure outline |
| `COMPONENTS.md` | extract | Component outline |
| `LLM.md` | extract | Per-file counts/header plus static read-order instructions |
| `ui-flow.json` | extract | Pages, roles, regions, `suggestedRoutes` (`inferred: true`), prototype `interactions` |
| `trees/index.json` | extract | Screen list and tree summary (`schemaVersion: 2`) |
| `trees/boards/*.json` | extract | Pre-split board trees when a multi-UI board was split |
| `trees/<page>__<screen>.json` | extract | Layout, fills, text, `styleRefs` / `variableRefs`, `vectorRef`, expanded instances |
| `tokens/tokens.css` | extract | CSS custom properties |
| `tokens/*.json` | extract | Colour styles, variables, typography, effects (`kind: explicit` when authored) |
| `components/index.json` | extract | Variant-set axes |
| `assets/manifest.json` | extract | Unified rasters (`kind: raster`) and vectors (`kind: vector`) |
| `assets/vectors.json` | extract | Shared SVG vector records |
| `assets/index.json` | extract | Pointers to raster + vector indexes |
| `assets/missing-hashes.json` | extract | Image refs that were not materialized |
| `screens/<slug>/screen.json` | extract | Reference bundle: paths, semantic, route, optional `reconstruction` hints |
| `structure/<page>.md` | extract | Per-page outline |
| `diagnostics/*` | extract | Truncation, unsupported outlines, layout facts, performance |
| `llm-annotations.json` | annotate | Model suggestions, or the deterministic screen rows |
| `catalog/index.json` | extract `--toon` or `toon` | Reference index with screen, component, and asset refs |
| `toon/*.toon` | extract `--toon` or `toon` | TOON tables for transport |
| `document/llm-summary.json` | annotate | Summary when `catalog/index.json` already exists |
| `prompts/` | annotate (LLM) | Prompt artifacts when `LLM_WRITE_ARTIFACTS` is true |

`suggestedRoutes` in `ui-flow.json` are slug guesses marked `inferred: true`. Specimen/gallery crops are omitted from that list. Prototype edges live under `interactions` and are empty when the file has none. Screen `role` is a keyword match on the **screen name** (not the kit page title).

Tree nodes may include `layout.padding` beside `layout.pad`, `constraints`, `layout.sizing`, `styleRefs`, `variableRefs`, and `vectorRef` / `vectorScale` for shared icons. No breakpoint table is invented.

`info()` loads `pages.json`, `screens.json`, `components.json`, `component-sets.json`, `text-content.json`, `tokens/variables.json`, `tokens/typography.json`, `tokens/effects.json`, `assets/manifest.json`, and `ui-flow.json`. When present, it also reports a compact `llm` block from `document/llm-summary.json` or `llm-annotations.json`.
