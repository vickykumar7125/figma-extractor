# figma-extractor

Extract design tokens, screens, components, and image assets from Figma.

Documentation: <https://vickykumar7125.github.io/figma-extractor/>

| Surface | Name |
| --- | --- |
| CLI / PyPI package | `figma-extractor` |
| Python import | `figma_extractor` |
| Max-feature installer | `python setup.py` |

The default install extracts design data and does not install an LLM provider or PyTorch. `setup.py` detects this machine and installs the richest compatible profile on top of that core.

Supports today:

- local `.fig` archives (offline kiwi decode — no Figma account needed)
- remote Figma files via the REST API
- design tokens: colour styles, variables, typography, effects, plus a `tokens.css` bundle
- per-screen layout trees (`trees/`) with auto-layout, fills, text, and expanded component instances
- UI flow index (`ui-flow.json` + `LLM.md`): roles, regions, sample copy, suggested routes
- structure: pages, screens, components, variant sets, and unique text content
- image assets exported with a manifest
- optional annotation (`llm-annotations.json`) when an LLM extra is installed and explicitly enabled
- fresh rebuilds: each `extract` wipes previous deliverables under the output directory (disable with `--no-clean`)
- temporary `source/` and `extracted/` removed after extract (`--keep-intermediates` to retain them)

This package does not render screenshots. HTML generation from an extract is an upcoming feature, described at the end of this file.

## Install

Python 3.11+ is required.

### Default: extraction only

```bash
pip install .
```

From a requirements file:

```bash
pip install -r requirements.txt
```

That file includes `requirements/base.txt` only. Development tests:

```bash
pip install -e ".[dev]"
```

`extract` and `info` work after this install. They do not import LangChain or PyTorch.

### Maximum features for this machine

From the repository root:

```bash
python setup.py
```

The installer prints the detected OS, CPU architecture, accelerator, and the pip commands it will run. See the plan without installing:

```bash
python setup.py --dry-run
```

| Flag | Effect |
| --- | --- |
| *(none)* | Core package, every LLM provider extra (`all-llm`), and the matching torch profile |
| `--core` | Extraction only, same result as `pip install -e .` |
| `--no-llm` | Skip LangChain and provider packages |
| `--no-torch` | Skip PyTorch and torchvision |
| `--dry-run` | Print the plan and commands |

Detection order:

| Environment | Profile | Requirements file |
| --- | --- | --- |
| macOS Apple Silicon | MPS via the default PyPI wheel | `requirements/torch/macos.txt` |
| Linux or Windows with `nvidia-smi` | CUDA 13.2 | `requirements/torch/cuda.txt` |
| Linux with ROCm and no NVIDIA GPU | ROCm 7.1 | `requirements/torch/rocm.txt` |
| Linux or Windows with `xpu-smi` or `sycl-ls` | Intel XPU | `requirements/torch/xpu.txt` |
| Linux or Windows otherwise | CPU | `requirements/torch/cpu.txt` |

macOS does not receive a CUDA, ROCm, or XPU wheel. macOS Intel is reported and torch is skipped, because the pinned macOS wheels are `macosx_14_0_arm64`. ROCm stays on torch `2.13.0` / torchvision `0.28.0` because that index does not publish torch `2.14.1`. CUDA, CPU, and XPU use torch `2.14.1` and torchvision `0.29.1`, checked on 2026-10-02.

Torch is a second `pip` command. Its index URL would hide PyPI if it were mixed into the package install.

### Install one feature yourself

```bash
pip install -e ".[openai]"          # also: anthropic, google, vertex, ollama,
                                    # huggingface, groq, xai, nvidia, cohere,
                                    # together, deepseek
pip install -e ".[llm]"             # LangGraph runtime, no chat provider
pip install -e ".[all-llm]"         # every provider extra
pip install -r requirements/torch/cuda.txt
```

The same provider lists are under `requirements/providers/`.

Credentials stay in the environment. They are not accepted in JSON config files.

| Provider id | Extra | Environment variable |
| --- | --- | --- |
| `openai` | `openai` | `OPENAI_API_KEY` |
| `anthropic` | `anthropic` | `ANTHROPIC_API_KEY` |
| `google` | `google` | `GOOGLE_API_KEY` |
| `vertex` | `vertex` | `GOOGLE_CLOUD_PROJECT` and Application Default Credentials |
| `anthropic-vertex` | `vertex` | `GOOGLE_CLOUD_PROJECT` and Application Default Credentials |
| `ollama` | `ollama` | none (`OLLAMA_BASE_URL` optional) |
| `huggingface` | `huggingface` | `HF_TOKEN` or `HUGGINGFACEHUB_API_TOKEN` (not required when `backend=local`) |
| `groq` | `groq` | `GROQ_API_KEY` |
| `xai` | `xai` | `XAI_API_KEY` |
| `nvidia` | `nvidia` | `NVIDIA_API_KEY` |
| `cohere` | `cohere` | `COHERE_API_KEY` |
| `together` | `together` | `TOGETHER_API_KEY` |
| `deepseek` | `deepseek` | `DEEPSEEK_API_KEY` |

`anthropic` calls the Anthropic API. `anthropic-vertex` calls Claude on Vertex AI. Local Hugging Face inference (`backend=local`) also needs the torch profile `setup.py` selected, plus `transformers`.

After torch is installed:

```bash
figma-extractor devices
```

That reports `cpu`, `cuda`, `rocm`, `mps`, `xpu`, or `unavailable`.

## Usage

### Extract a file

```bash
# local .fig, offline
figma-extractor extract --file ./design.fig --output ./out

# remote file key or URL
figma-extractor extract --remote https://www.figma.com/design/ABC123/My-Kit \
  --output ./out --api-key figd_xxx
```

`FIGMA_API_KEY` is used when `--api-key` is omitted. `--no-clean` keeps previous deliverables. `--keep-intermediates` keeps `source/` and `extracted/`.

### Inspect an extract

```bash
figma-extractor info --dir ./out
figma-extractor info --dir ./out --json
```

Without `--dir`, `info` reads the current directory and prints JSON.

### Annotate (optional)

Annotation is off by default. A disabled run writes the roles and regions already on disk and does not call a model.

```bash
figma-extractor annotate --dir ./out --llm-disabled

figma-extractor annotate --dir ./out \
  --llm \
  --llm-provider ollama \
  --llm-model llama3.2 \
  --llm-task screen_classification \
  --llm-task reconstruction_hints
```

`--llm-task` repeats. Allowed tasks: `semantic_classification`, `screen_classification`, `component_analysis`, `svg_analysis`, `reconstruction_hints`. `--llm-config ./llm.json` reads a JSON object. `--llm` and `--llm-disabled` override `LLM_ENABLED`.

Environment variables, applied when the matching CLI flag is omitted:

| Variable | Meaning |
| --- | --- |
| `LLM_ENABLED` | `true` or `false` (default false) |
| `LLM_PROVIDER` | provider id from the table above |
| `LLM_MODEL` | model id; each provider has a default |
| `LLM_TEMPERATURE` | 0 to 2 |
| `LLM_MAX_TOKENS` | response token cap |
| `LLM_TIMEOUT` | seconds |
| `LLM_MAX_RETRIES` | transport retries |
| `LLM_STREAMING` | `true` or `false` |
| `LLM_TASKS` | comma-separated task names |

JSON config example:

```json
{
  "enabled": true,
  "provider": "ollama",
  "model": "llama3.2",
  "temperature": 0,
  "tasks": {
    "screen_classification": true,
    "reconstruction_hints": true
  }
}
```

Model suggestions are written to `llm-annotations.json`. They do not replace `screens.json`. Reconstruction hints are recommendations (`kind` is `recommended`), not file facts.

## Python API

```python
from figma_extractor import extract, info, annotate
from figma_extractor.llm.config import LlmConfig, LlmTasks

extract(file="./design.fig", output="./out")
extract(remote="ABC123", output="./out", api_key="figd_xxx")

print(info("./out")["summary"])

# Deterministic. Does not import a provider SDK.
annotate("./out", LlmConfig(enabled=False))

# Calls the selected provider. Requires that extra to be installed.
annotate(
    "./out",
    LlmConfig(
        enabled=True,
        provider="ollama",
        model="llama3.2",
        tasks=LlmTasks(screen_classification=True),
    ),
)
```

`from figma_extractor import extract, info` does not import LangChain, LangGraph, or torch. `annotate` imports them only when `enabled=True`.

## Output

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

## Project layout

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
├── README.md
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

## Upcoming: HTML from an extract

HTML output is not implemented yet.

A later release will build HTML from the strings and structure this package already writes: `trees/*.json`, `tokens/tokens.css`, `components.json`, `assets/manifest.json`, and `ui-flow.json`. The builder will follow the deterministic tree first. When LLM mode is enabled, it may ask the selected provider for recommendations, and those recommendations will stay marked as recommendations. The command will be added beside `extract` and `annotate`. `python setup.py` already installs the provider and torch profile that builder will use.

## Notes

- A `.fig` archive is decoded locally through the embedded kiwi schema, so local extraction works offline.
- Remote files are normalized into the same node stream as local `.fig` files, so token, structure, and image builders are shared.
- Fonts are not embedded in a `.fig`. Typography tokens record family, style, size, line height, and letter spacing.
