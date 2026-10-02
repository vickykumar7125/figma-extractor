# Output

Deliverables land at the output root. There is no nested `design/` folder. `source/` and `extracted/` are deleted after a successful extract unless you pass `--keep-intermediates`.

```
out/
├── LLM.md                     read order for an agent
├── ui-flow.json               pages, roles, regions, suggested routes
├── llm-annotations.json       written by annotate, not by extract
├── trees/
│   ├── index.json
│   └── <page>__<screen>.json  layout, fills, text, instances
├── tokens/
│   ├── tokens.css
│   └── …
├── components/
│   └── index.json             variant-set axes
├── assets/
│   ├── images/
│   └── manifest.json
├── structure/<page>.md
├── pages.json
├── screens.json               tree path, role, regions
├── components.json
├── component-sets.json
├── text-content.json
├── STRUCTURE.md
└── COMPONENTS.md
```

`suggestedRoutes` in `ui-flow.json` are slug guesses. A screen role is a keyword match on the name.
