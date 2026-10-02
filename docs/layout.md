# Project layout

```
figma-extractor/
├── pyproject.toml
├── setup.py                 # detects OS and accelerator, installs the max profile
├── requirements.txt         # extraction only, no version pins
├── requirements/
│   ├── common.txt
│   ├── cuda132.txt
│   ├── cuda130.txt
│   ├── cuda129.txt
│   ├── cpu.txt
│   ├── xpu.txt
│   ├── gpu.txt              # AMD ROCm
│   └── macos.txt
├── mkdocs.yml               # this documentation site
├── README.md
├── .github/workflows/docs.yml
└── src/figma_extractor/
    ├── __main__.py          # python -m figma_extractor
    ├── api.py               # extract(), info()
    ├── cli.py               # extract, info, annotate, devices
    ├── paths.py
    ├── remote.py            # Figma REST client
    ├── util.py
    ├── fig/                 # .fig unzip and canvas decode
    ├── kiwi/                # kiwi schema and decoder
    ├── extract/             # tokens, structure, images, trees, split, flow, vectors, semantic
    ├── catalog.py           # reference catalog + TOON publish (no LLM)
    ├── llm/                 # optional; not imported by extract
    │   ├── annotate.py
    │   ├── config.py
    │   ├── factory.py
    │   ├── graph.py         # LangGraph: prepare, invoke, validate, repair, finalize
    │   ├── device.py        # detect_device and local execution placement
    │   ├── huggingface_local.py
    │   ├── huggingface_settings.py
    │   ├── prompt_format.py # one TOON document per annotation task
    │   ├── patches.py
    │   ├── merge.py
    │   └── providers/       # one module per provider, imported only when selected
    └── toon/                # included encoder and decoder for that document
```

`docs/redesign/` holds internal redesign notes. It is excluded from this site.

Raster `assets/manifest.json` rows include `id` and `kind: raster`. Image paints gain a matching `file` path after trees are written. Vector assets use `kind: vector` in `assets/vectors.json` and are also appended to the unified manifest via `assets/index.json`. Style and variable token records carry `kind: explicit`. Instance nodes may expose `overrides`, `componentPropAssignments`, and richer `propDefs`. Screen records carry `origin` and optional `semantic`. Shared icons use `vectorRef` (and `vectorScale` when sized differently from the master SVG).
