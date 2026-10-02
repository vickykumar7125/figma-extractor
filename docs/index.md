# figma-extractor

Extract design tokens, screens, components, and image assets from Figma.

| Surface | Name |
| --- | --- |
| CLI | `figma-extractor` and `python -m figma_extractor` |
| Python import | `figma_extractor.extract`, `info`, `annotate` |
| Max-feature installer | `python setup.py` |
| Docs | this site |

Commands: `extract`, `info`, `annotate`, `devices`, `model validate`, `model download`. Flag tables are on the [CLI](cli.md) page. Local Hugging Face models are on the [Hugging Face local](huggingface.md) page. Function signatures and return values are on the [Python API](python-api.md) page.

The default install extracts design data and does not install an LLM provider or PyTorch. `setup.py` detects this machine and installs the richest compatible profile on top of that core.

## What it supports today

- Local `.fig` archives (offline kiwi decode, no Figma account needed)
- Remote Figma files via the REST API
- Design tokens: colour styles, variables, typography, effects, plus a `tokens.css` bundle
- Per-screen layout trees (`trees/`) with auto-layout, fills, text, and expanded component instances
- UI flow index (`ui-flow.json` and `LLM.md`): roles, regions, sample copy, suggested routes
- Structure: pages, screens, components, variant sets, and unique text content
- Image assets exported with a manifest
- Optional annotation (`llm-annotations.json`) when an LLM extra is installed and explicitly enabled
- Optional local Hugging Face models (`HF_BACKEND=local`, the default for that provider), with remote Hub inference only when `HF_BACKEND=remote`
- Fresh rebuilds: each `extract` wipes previous deliverables under the output directory (disable with `--no-clean`)
- Temporary `source/` and `extracted/` removed after extract (`--keep-intermediates` to retain them)

This package does not render screenshots. HTML generation from an extract is an upcoming feature.

## Upcoming: HTML from an extract

HTML output is not implemented yet.

A later release will build HTML from the strings and structure this package already writes: `trees/*.json`, `tokens/tokens.css`, `components.json`, `assets/manifest.json`, and `ui-flow.json`. The builder will follow the deterministic tree first. When LLM mode is enabled, it may ask the selected provider for recommendations, and those recommendations will stay marked as recommendations. The command will be added beside `extract` and `annotate`. `python setup.py` already installs the provider and torch profile that builder will use.

## Notes

- A `.fig` archive is decoded locally through the embedded kiwi schema, so local extraction works offline.
- Remote files are normalized into the same node stream as local `.fig` files, so token, structure, and image builders are shared.
- Fonts are not embedded in a `.fig`. Typography tokens record family, style, size, line height, and letter spacing.
