# Output

Deliverables land at the output root. There is no nested `design/` folder. `source/` and `extracted/` are deleted after a successful extract unless you pass `--keep-intermediates`.

```
out/
├── LLM.md
├── ui-flow.json
├── llm-annotations.json          # written by annotate, not by extract
├── pages.json
├── screens.json
├── components.json
├── component-sets.json
├── text-content.json
├── STRUCTURE.md
├── COMPONENTS.md
├── trees/
│   ├── index.json
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
│   ├── manifest.json
│   └── missing-hashes.json
└── structure/
    └── <page>.md
```

`--clean` (the default) deletes those deliverable files and directories, plus a legacy `design/` folder, before writing. `llm-annotations.json` is in that list, so a later `extract` removes a previous annotation file.

## What each file is for

| Path | Produced by | Contents |
| --- | --- | --- |
| `pages.json` | extract | Page records |
| `screens.json` | extract | Screen records: tree path, role, regions |
| `components.json` | extract | Component records |
| `component-sets.json` | extract | Variant sets |
| `text-content.json` | extract | Unique strings grouped by page |
| `STRUCTURE.md` | extract | Structure outline |
| `COMPONENTS.md` | extract | Component outline |
| `LLM.md` | extract | Read order for an agent. The text is a static guide |
| `ui-flow.json` | extract | Pages, roles, regions, `suggestedRoutes` |
| `trees/index.json` | extract | Screen list and tree summary |
| `trees/<page>__<screen>.json` | extract | Layout, fills, text, expanded instances |
| `tokens/tokens.css` | extract | CSS custom properties |
| `tokens/*.json` | extract | Colour styles, variables, typography, effects, font families |
| `components/index.json` | extract | Variant-set axes |
| `assets/manifest.json` | extract | Exported images |
| `assets/missing-hashes.json` | extract | Image refs that were not materialized |
| `structure/<page>.md` | extract | Per-page outline |
| `llm-annotations.json` | annotate | Model suggestions, or the deterministic screen rows |

`suggestedRoutes` in `ui-flow.json` are slug guesses. A screen role is a keyword match on the name.

`info()` loads `pages.json`, `screens.json`, `components.json`, `component-sets.json`, `text-content.json`, `tokens/variables.json`, `tokens/typography.json`, `tokens/effects.json`, `assets/manifest.json`, and `ui-flow.json`. It does not load `llm-annotations.json`.
