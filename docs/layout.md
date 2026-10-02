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
    ├── extract/             # tokens, structure, images, trees, flow
    ├── llm/                 # optional; not imported by extract
    │   ├── annotate.py
    │   ├── config.py
    │   ├── factory.py
    │   ├── graph.py         # LangGraph: prepare, invoke, validate, repair, finalize
    │   ├── device.py        # detect_device and local execution placement
    │   ├── huggingface_local.py
    │   ├── huggingface_settings.py
    │   ├── prompt_format.py # one TOON document per annotation task
    │   └── providers/       # one module per provider, imported only when selected
    └── toon/                # included encoder and decoder for that document
```

`docs/redesign/` holds internal redesign notes. It is excluded from this site.
