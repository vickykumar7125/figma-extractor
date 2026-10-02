# Project layout

```
figma-extractor/
├── pyproject.toml
├── setup.py                 # detects OS and accelerator, installs the max profile
├── requirements.txt         # core only
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   ├── test.txt
│   ├── llm.txt              # LangGraph runtime, no provider
│   ├── providers/           # one file per chat provider, plus all-llm.txt
│   └── torch/               # cpu, cuda, rocm, xpu, macos
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
    ├── extract/             # tokens, structure, images, trees, flow
    └── llm/                 # optional; not imported by extract
        ├── annotate.py
        ├── config.py
        ├── factory.py
        ├── graph.py         # LangGraph: prepare, invoke, validate, repair, finalize
        ├── device.py
        └── providers/       # one module per provider, imported only when selected
```

`docs/redesign/` holds internal redesign notes. It is excluded from this site.
