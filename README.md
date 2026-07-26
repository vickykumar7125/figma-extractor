# figma-extractor

Extract design tokens, screens, components, and image assets from Figma.

| Surface | Name |
| --- | --- |
| CLI / PyPI package | `figma-extractor` |
| Python import | `figma_extractor` |

Supports:

- local `.fig` archives (offline kiwi decode)
- remote Figma files via the REST API

## Install

```bash
# dependencies only
pip install -r requirements.txt

# install the package
pip install .

# development install
pip install -e .

# from git
pip install git+https://github.com/vickykumar7125/figma-extractor.git
```

Python 3.11+ required.

## CLI

```bash
# local
figma-extractor extract --file ./design.fig --output ./out

# remote (URL or file key)
figma-extractor extract \
  --remote https://www.figma.com/design/<FILE_KEY>/Name \
  --output ./out \
  --api-key "$FIGMA_API_KEY"

# inspect previous extraction
figma-extractor info --dir ./out
figma-extractor info --dir ./out --json
```

`FIGMA_API_KEY` can replace `--api-key`.

## Python API

```python
from figma_extractor import extract, info

# local
result = extract(file="./design.fig", output="./out")
print(result["design"])

# remote
result = extract(
    remote="https://www.figma.com/design/<FILE_KEY>/Name",
    output="./out",
    api_key="figd_...",
)

# full report
details = info("./out")
print(details["summary"])
print(details["screens"][0])
print(details["components"][:5])
```

## Output

```
out/
└── design/
    ├── tokens/                 CSS variables, colours, type, effects
    ├── structure/              page outlines
    ├── assets/images/          bitmaps with real extensions
    ├── pages.json
    ├── screens.json
    ├── components.json
    ├── component-sets.json
    └── text-content.json
```

Temporary `source/` and `extracted/` folders are removed after a successful run.
Pass `--keep-intermediates` to retain them.

## Project layout

```
figma-extractor/
├── pyproject.toml
├── requirements.txt
├── README.md
└── src/figma_extractor/
    ├── api.py          # extract(), info()
    ├── cli.py          # figma-extractor CLI
    ├── remote.py       # Figma REST client
    ├── util.py         # JSON / colour helpers
    ├── paths.py        # output paths
    ├── fig/            # .fig unzip + canvas decode
    ├── kiwi/           # kiwi binary schema + decoder
    └── extract/        # tokens, structure, images
```

## Notes

- Local decode reads the schema embedded in each `.fig` file.
- Remote extract normalizes the REST document into the same `design/` shape.
- Duplicate colour-style names across libraries are recorded in
  `design/tokens/color-styles.conflicts.json`.
