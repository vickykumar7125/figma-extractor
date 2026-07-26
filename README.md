# figma-extractor

Extract design tokens, screens, components, and image assets from Figma.

| Surface | Name |
| --- | --- |
| CLI / PyPI package | `figma-extractor` |
| Python import | `figma_extractor` |

Supports:

- local `.fig` archives (offline kiwi decode — no Figma account needed)
- remote Figma files via the REST API
- design tokens: colour styles, variables, typography, effects, plus a `tokens.css` bundle
- **per-screen layout trees** (`trees/`) with auto-layout, fills, text, and expanded
  component instances — enough for an LLM to rebuild HTML without screenshots
- **UI flow index** (`ui-flow.json` + `LLM.md`): roles, regions, sample copy, suggested routes
- structure: pages, screens, components, variant sets, and unique text content
- image assets exported with a manifest
- fresh rebuilds: each `extract` wipes previous deliverables under the output
  directory (disable with `--no-clean`)
- after extract, temporary `source/` and `extracted/` are removed by default
  (`--keep-intermediates` to retain them)

This package extracts design *data* for LLM / tooling consumption. It does not
render or generate screen images.

## Install

Python 3.11+ required.

```bash
# from the package directory (contains pyproject.toml)
pip install .
```

Editable install for development:

```bash
pip install -e .
```

The `figma-extractor` console script is registered on install. Runtime
dependencies are declared in `pyproject.toml`; `requirements.txt` mirrors them
for pinned environments (`pip install -r requirements.txt`).

## CLI

```bash
# local .fig → extract flat into ./out/
figma-extractor extract --file ./design.fig --output ./out

# remote file (URL or file key) — needs a Figma token
figma-extractor extract --remote https://www.figma.com/design/ABC123/My-Kit \
  --output ./out --api-key figd_xxx        # or set FIGMA_API_KEY

# extract flags
#   --no-clean             keep previous tokens/assets/JSON instead of wiping
#   --keep-intermediates   keep temporary source/ and extracted/ folders

# inspect a previous run
figma-extractor info --dir ./out          # summary table
figma-extractor info --dir ./out --json   # full JSON
```

## Python API

```python
from figma_extractor import extract, info

# local extract
extract(file="./design.fig", output="./out")

# remote extract
extract(remote="ABC123", output="./out", api_key="figd_xxx")

print(info("./out")["summary"])
```

## Output

Deliverables land at the output root (no nested `design/` folder). Temporary
`source/` and `extracted/` are deleted after a successful extract unless you
pass `--keep-intermediates`.

```
out/
├── LLM.md                     how an LLM should use this extract
├── ui-flow.json               pages → screens, roles, regions, routes
├── trees/
│   ├── index.json
│   └── <page>__<screen>.json  full layout tree (layout/fills/text/instances)
├── tokens/
│   ├── tokens.css
│   └── …
├── components/
│   └── index.json             variant-set axes for LLM lookup
├── assets/
│   ├── images/
│   └── manifest.json
├── structure/<page>.md
├── pages.json
├── screens.json               includes tree path, role, regions
├── components.json
├── component-sets.json
├── text-content.json
├── STRUCTURE.md
└── COMPONENTS.md
```

## Project layout

```
figma-extractor/
├── pyproject.toml
├── requirements.txt
├── README.md
└── src/figma_extractor/
    ├── api.py          # extract(), info()
    ├── cli.py          # figma-extractor CLI
    ├── remote.py       # Figma REST client + document normalizer
    ├── util.py         # JSON / colour helpers
    ├── paths.py        # output paths
    ├── fig/            # .fig unzip and canvas decode
    ├── kiwi/           # kiwi binary schema + decoder
    └── extract/        # tokens, structure, images
```

## Notes

- A `.fig` archive is decoded locally through the embedded kiwi schema, so local
  extraction works fully offline.
- Remote files are normalized into the same node stream as local `.fig` files, so
  the token / structure / image builders are shared across both sources.
- Fonts are not embedded in a `.fig`; typography tokens record family, style, size,
  line height, and letter spacing rather than font binaries.
