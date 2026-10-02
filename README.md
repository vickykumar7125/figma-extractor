# figma-extractor

Extract design tokens, screens, components, and image assets from Figma.

Documentation: <https://vickykumar7125.github.io/figma-extractor/>

| Surface | Name |
| --- | --- |
| CLI | `figma-extractor` and `python -m figma_extractor` |
| Python import | `figma_extractor` (`extract`, `info`, `annotate`) |
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

Commands: `extract`, `info`, `annotate`, `devices`. `--version` / `-V` prints the package version.

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
python setup.py --dry-run
python setup.py --core
python setup.py --no-llm
python setup.py --no-torch
```

The installer prints the detected OS, CPU architecture, accelerator, and the pip commands it will run. `--dry-run` prints that plan and does not install.

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

| Provider id | Extra | Environment variable | Default model |
| --- | --- | --- | --- |
| `openai` | `openai` | `OPENAI_API_KEY` | `gpt-4.1-mini` |
| `anthropic` | `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-5` |
| `google` | `google` | `GOOGLE_API_KEY` | `gemini-2.5-flash` |
| `vertex` | `vertex` | `GOOGLE_CLOUD_PROJECT` and Application Default Credentials | `gemini-2.5-flash` |
| `anthropic-vertex` | `vertex` | `GOOGLE_CLOUD_PROJECT` and Application Default Credentials | `claude-haiku-4-5@20251001` |
| `ollama` | `ollama` | none (`OLLAMA_BASE_URL` optional) | `llama3.2` |
| `huggingface` | `huggingface` | `HF_TOKEN` or `HUGGINGFACEHUB_API_TOKEN` (not required when `backend=local`) | `microsoft/Phi-3-mini-4k-instruct` |
| `groq` | `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| `xai` | `xai` | `XAI_API_KEY` | `grok-3` |
| `nvidia` | `nvidia` | `NVIDIA_API_KEY` | `meta/llama-3.1-70b-instruct` |
| `cohere` | `cohere` | `COHERE_API_KEY` | `command-r-plus` |
| `together` | `together` | `TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| `deepseek` | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |

`anthropic` calls the Anthropic API. `anthropic-vertex` calls Claude on Vertex AI. Local Hugging Face inference (`backend=local`) also needs the torch profile `setup.py` selected, plus `transformers`.

Provider options accepted in config (`provider_options`): `ollama` takes `base_url`; `huggingface` takes `backend` (`endpoint` or `local`); `vertex` and `anthropic-vertex` take `location`. Gemini on Vertex defaults to `us-central1`. Claude on Vertex defaults to `us-east5`. Both honour `GOOGLE_CLOUD_LOCATION`.

After torch is installed:

```bash
figma-extractor devices
```

That prints one line, `kind: detail (torch version)`, where kind is `cpu`, `cuda`, `rocm`, `mps`, `xpu`, or `unavailable`.

## Usage

`python -m figma_extractor` accepts the same commands and flags as `figma-extractor`.

### Extract a file

```bash
figma-extractor extract --file ./design.fig --output ./out
figma-extractor extract -f ./design.fig -o ./out --no-clean --keep-intermediates

figma-extractor extract --remote https://www.figma.com/design/ABC123/My-Kit \
  --output ./out
figma-extractor extract -r ABC123 -o ./out --api-key "$FIGMA_API_KEY"
```

Pass exactly one of `--file` / `-f` or `--remote` / `-r`. `--output` / `-o` is required. `--api-key` reads `FIGMA_API_KEY` when the flag is omitted. A remote extract needs that token. `--clean` is the default; `--no-clean` keeps previous files. `--keep-intermediates` retains `source/` and `extracted/`.

### Inspect an extract

```bash
figma-extractor info --dir ./out
figma-extractor info -d ./out --json
figma-extractor info
```

Without `--dir`, `info` reads the current directory and prints JSON. With `--dir` and without `--json`, it prints a count table. The directory must contain `pages.json` or `screens.json`. A legacy `design/` subfolder is still accepted.

### Annotate (optional)

Annotation is off by default. A disabled run writes the roles and regions already on disk and does not call a model.

```bash
figma-extractor annotate --dir ./out --llm-disabled
figma-extractor annotate -d ./out

figma-extractor annotate --dir ./out \
  --llm \
  --llm-provider ollama \
  --llm-model llama3.2 \
  --llm-temperature 0 \
  --llm-task screen_classification \
  --llm-task reconstruction_hints

figma-extractor annotate --dir ./out --llm --llm-config ./llm.json
```

`--dir` defaults to `.`. `--llm` / `--llm-disabled` override `LLM_ENABLED`. When that flag is omitted, the environment value applies (default false). `--llm-task` repeats and is used only when LLM mode is on. Allowed tasks: `semantic_classification`, `screen_classification`, `component_analysis`, `svg_analysis`, `reconstruction_hints`.

Load order, later wins: defaults, JSON file, environment, CLI flags you pass. Enabled mode requires at least one task.

| Variable | Meaning |
| --- | --- |
| `LLM_ENABLED` | `true` or `false` (also `1`/`yes`/`on` and `0`/`no`/`off`). Default false |
| `LLM_PROVIDER` | provider id (default `openai`) |
| `LLM_MODEL` | model id; omitted means the provider default in the table above |
| `LLM_TEMPERATURE` | 0 to 2 |
| `LLM_MAX_TOKENS` | response token cap |
| `LLM_TIMEOUT` | seconds (default 60) |
| `LLM_MAX_RETRIES` | transport retries (default 2) |
| `LLM_STREAMING` | `true` or `false` |
| `LLM_TASKS` | comma-separated task names |
| `LLM_TASK_SCREEN_CLASSIFICATION` | `true` or `false` for one task. Same pattern for the other four names, uppercased |

`LLM_TASK_<NAME>` overrides that name from `LLM_TASKS`. JSON keys `api_key`, `token`, `secret`, `password`, `authorization`, and `credentials` are rejected.

```json
{
  "enabled": true,
  "provider": "ollama",
  "model": "llama3.2",
  "temperature": 0,
  "tasks": {
    "screen_classification": true,
    "reconstruction_hints": true
  },
  "provider_options": {
    "base_url": "http://127.0.0.1:11434"
  }
}
```

A nested `"llm"` object is merged over the top-level keys. `options` is an alias of `provider_options`.

Model suggestions are written to `llm-annotations.json`. They do not replace `screens.json`. Reconstruction hints are recommendations (`kind` is `recommended`), not file facts.

### Devices

```bash
figma-extractor devices
```

## Python API

`extract` is keyword-only. Pass exactly one of `file` or `remote`. `api_key` is required for a remote call and is not read from `FIGMA_API_KEY` (that variable is CLI-only).

```python
from figma_extractor import extract, info, annotate, __version__
from figma_extractor.llm.config import LlmConfig, LlmTasks
from figma_extractor.llm.device import detect_device

extract(file="./design.fig", output="./out")
extract(file="./design.fig", output="./out", clean=False, keep_intermediates=True)
extract(remote="ABC123", output="./out", api_key="figd_xxx")

details = info("./out")          # or info() for the current directory
print(details["summary"])

annotate("./out")                          # LlmConfig.from_env()
annotate("./out", LlmConfig(enabled=False))
annotate(
    "./out",
    LlmConfig(
        enabled=True,
        provider="ollama",
        model="llama3.2",
        tasks=LlmTasks(screen_classification=True),
        provider_options={"base_url": "http://127.0.0.1:11434"},
    ),
    write=True,
)

print(detect_device().summary())
```

`from figma_extractor import extract, info` does not import LangChain, LangGraph, or torch. `annotate` imports them only when `enabled=True`.

`extract()` returns `source`, `output`, `design` (same path as `output`), `decode`, `tokens`, `structure`, `images`, `trees`, `flow`, and `intermediatesKept`. It runs `build_tokens`, `build_structure`, `build_images`, `build_screen_trees`, then `build_ui_flow`. Those functions are importable from `figma_extractor.extract` when you already have a decoded `extracted/` tree.

`info()` returns `directory`, `summary`, `pages`, `screens`, `components`, `componentSets`, `tokens`, `assets`, `text`, and `uiFlow`. Summary keys are `pages`, `screens`, `trees`, `components`, `componentSets`, `variables`, `textStyles`, `effects`, `assets`, `uniqueTextStrings`, and `suggestedRoutes`.

`annotate(directory, config=None, *, write=True)` requires `screens.json`. `write=False` returns the dict and skips `llm-annotations.json`. `LlmConfig.load(path=..., overrides=...)` applies defaults, then the file, then the environment, then overrides. `LlmConfig.from_env()` is `load()` with no file. Useful fields and defaults: `enabled=False`, `provider="openai"`, `model=None`, `temperature=0.0`, `max_tokens=None`, `timeout=60`, `max_retries=2`, `streaming=False`, `max_context_chars=12000`, `tasks=LlmTasks()`. Enabled config with no task raises before LangGraph is imported.

`detect_device()` returns `kind`, `available`, `detail`, and `torch_version`. Torch is imported inside that function.

## Output

Deliverables land at the output root. There is no nested `design/` folder. `source/` and `extracted/` are deleted after a successful extract unless you pass `--keep-intermediates`.

```
out/
├── LLM.md
├── ui-flow.json
├── llm-annotations.json       # annotate, not extract
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

`suggestedRoutes` in `ui-flow.json` are slug guesses. A screen role is a keyword match on the name. `--clean` also removes `llm-annotations.json`.

## Project layout

```
figma-extractor/
├── pyproject.toml
├── setup.py                 # detects OS and accelerator, installs the max profile
├── mkdocs.yml
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
