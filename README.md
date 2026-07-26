# figma-extractor

Extract design tokens, screens, components, and image assets from Figma.

| Surface | Name |
| --- | --- |
| CLI / PyPI package | `figma-extractor` |
| Python import | `figma_extractor` |

Supports:

- local `.fig` archives (offline kiwi decode)
- remote Figma files via the REST API
- local screen PNG rebuild from extracted `design/` trees (no Figma API / no AI)
- component instance expansion and decoded vector outlines, so rebuilt screens
  contain real buttons, inputs, cards, and icons
- automatic split of multi-UI boards (e.g. Auth - Branded → Sign In / Sign Up / …)
  so each PNG is one interface
- fresh rebuilds: each `extract` wipes previous `design/` + `screenshot/` under the
  output directory (disable with `--no-clean`)

## Install

Python 3.11+ required. Local screen rebuild needs a Chromium binary via Playwright.

```bash
# from the package directory (contains pyproject.toml)
pip install .
playwright install chromium
```

Editable install for development:

```bash
pip install -e .
playwright install chromium
```

The `figma-extractor` console script is registered on install. Runtime
dependencies are declared in `pyproject.toml`; `requirements.txt` mirrors them
for pinned environments (`pip install -r requirements.txt`).

## CLI

```bash
# local .fig → extract design/ and rebuild one PNG per UI screen into out/screenshot/
figma-extractor extract --file ./design.fig --output ./out --render

# remote file (URL or file key) — needs a Figma token
figma-extractor extract --remote https://www.figma.com/design/ABC123/My-Kit \
  --output ./out --api-key figd_xxx        # or set FIGMA_API_KEY

# useful extract flags
#   --render-scale 2       high-DPI PNGs
#   --render-limit 5       only first N screens (quick test)
#   --render-page Auth     only screens from one Figma page
#   --no-clean             keep previous design/ + screenshot/ instead of wiping

# rebuild screenshots later from an existing extract (no Figma API)
figma-extractor render --dir ./out
figma-extractor render --dir ./out --page Dashboards --limit 5 --scale 2

# optional: pull exact cloud PNGs via the Figma Images API
figma-extractor screenshots --dir ./out --file-key ABC123 --api-key figd_xxx

# inspect a previous run
figma-extractor info --dir ./out          # summary table
figma-extractor info --dir ./out --json   # full JSON
```

## Python API

```python
from figma_extractor import extract, info, render, export_screenshots

# local extract + local PNG rebuild
extract(file="./design.fig", output="./out", render=True)

# remote extract
extract(remote="ABC123", output="./out", api_key="figd_xxx", render=True)

# rebuild screenshots from an existing extract
render("./out", scale=2, page="Dashboards")

# optional cloud renders (Figma Images API)
export_screenshots("./out", file_key="ABC123", api_key="figd_xxx")

print(info("./out")["summary"])
```

## Output

```
out/
├── design/
│   ├── tokens/
│   ├── trees/                 per-screen layout trees used for local render
│   ├── preview/               HTML previews
│   ├── assets/images/
│   ├── pages.json
│   ├── screens.json           includes tree + localScreenshot paths
│   └── ...
└── screenshot/                rebuilt screen PNGs (local, from design/)
```

## Screen trees

`design/trees/<page>__<screen>.json` is the renderable description of one screen:

| Field | Meaning |
| --- | --- |
| `w` / `h` / `x` / `y` | size and parent-relative offset |
| `layout` | `dir`, `gap`, `pad`, `justify`, `align`, `wrap` |
| `fills` | solid / image / gradient paints |
| `stroke` | paints, `weight`, `align` |
| `shadows` | drop, inner, and blur effects |
| `radius` | single value or four corners |
| `text` | content, family, size, weight, line height, alignment |
| `paths` | decoded SVG outlines for vectors and icons |
| `instanceOf` | master symbol id when the node is an expanded instance |

## Project layout

```
figma-extractor/
├── pyproject.toml
├── requirements.txt
├── README.md
└── src/figma_extractor/
    ├── api.py          # extract(), info(), render(), export_screenshots()
    ├── cli.py          # figma-extractor CLI
    ├── remote.py       # Figma REST client
    ├── util.py         # JSON / colour helpers
    ├── paths.py        # output paths
    ├── fig/            # .fig unzip, canvas decode, vector path decode
    ├── kiwi/           # kiwi binary schema + decoder
    └── extract/        # tokens, structure, images, trees, render, screenshots
```

## Notes

- Local screenshots are rebuilt from `design/trees` + tokens + bitmaps via Playwright.
- Vector outlines come from the `.fig` path blobs, so icons render as real shapes.
- Component instances are expanded from their master symbol, including per-instance
  geometry overrides.
- Fonts are not embedded in a `.fig`; install the design's families locally for exact
  typography, otherwise a metric-compatible fallback is used.
- Optional cloud screenshots (`--screenshots`) still exist but require a Figma API key.
