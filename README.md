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
- design tokens: colour styles, variables, typography, effects (`kind: explicit` when authored), plus a `tokens.css` bundle
- per-screen layout trees (`trees/`) with auto-layout, constraints, `layout.padding`, fills, text, `styleRefs` / `variableRefs`, and expanded component instances
- screen lineage: `origin` (`top-level` / `board-child` / `crop`), optional `sourceScreenId`, pre-split boards under `trees/boards/`
- shared SVG vectors (`vectorRef` / `vectorScale`) and a unified `assets/` index
- UI flow index (`ui-flow.json` + per-file `LLM.md`): roles, optional `semantic`, regions, inferred routes, prototype interactions
- per-screen reference bundles at `screens/<slug>/screen.json` (paths and hints, no embedded tree)
- structure: pages, screens, components, variant sets, and unique text content
- image assets with a manifest (sibling `images/` is copied when extracting a bare `canvas.fig`)
- optional TOON / catalog transport (`--toon` or `figma-extractor toon`)
- optional annotation (`llm-annotations.json`) when an LLM extra is installed and explicitly enabled
- fresh rebuilds: each `extract` wipes previous deliverables under the output directory (disable with `--no-clean`)
- temporary `source/` and `extracted/` removed after extract (`--keep-intermediates` to retain them)

This package does not render screenshots. HTML generation from an extract is an upcoming feature, described at the end of this file.

Commands: `extract`, `info`, `annotate`, `toon`, `context-benchmark`, `devices`, `model validate`, `model download`. `--version` / `-V` prints the package version.

## Install

Python 3.11+ is required. The published package is one universal wheel. Pip selects it on Linux, Windows, and macOS. PyTorch and CUDA are not inside that wheel.

### From PyPI

```bash
pip install figma-extractor
```

### From Anaconda.org (conda)

```bash
conda install -c vickykumar7125 figma-extractor
```

Optional extras use the same wheel plus extra packages, for example `pip install "figma-extractor[huggingface]"`. Accelerator-specific PyTorch installs are listed in the [installation guide](https://vickykumar7125.github.io/figma-extractor/installation/).

### From a checkout

```bash
pip install .
```

From a requirements file:

```bash
pip install -r requirements.txt
```

That file is the extraction list, with no version pins. Development tests:

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
| *(none)* | Editable package, then the detected file: `cuda132.txt`, `cuda130.txt`, `cuda129.txt`, `cpu.txt`, `xpu.txt`, `gpu.txt`, or `macos.txt` |
| `--core` | Extraction only, same result as `pip install -e .` |
| `--no-llm` | Skip LangChain and provider packages |
| `--no-torch` | Skip PyTorch and torchvision |
| `--dry-run` | Print the plan and commands |

Detection order:

| Environment | Profile | Requirements file |
| --- | --- | --- |
| macOS Apple Silicon | MPS via the PyPI wheel | `requirements/macos.txt` |
| Linux or Windows, driver CUDA 13.2 or newer | CUDA 13.2, torch `2.14.1+cu132`, torchvision `0.29.1+cu132` | `requirements/cuda132.txt` |
| Linux or Windows, driver CUDA 13.0 or 13.1 | CUDA 13.0, torch `2.14.1+cu130`, torchvision `0.29.1+cu130` | `requirements/cuda130.txt` |
| Linux or Windows, driver CUDA 12.9 | CUDA 12.9. Linux: torch `2.13.0+cu129` / torchvision `0.28.0+cu129`. Windows: torch `2.8.0+cu129` / torchvision `0.23.0+cu129` | `requirements/cuda129.txt` |
| Linux with ROCm and no NVIDIA GPU | ROCm index `rocm7.1` | `requirements/gpu.txt` |
| Linux or Windows with `xpu-smi` or `sycl-ls` | Intel XPU index | `requirements/xpu.txt` |
| Linux or Windows otherwise | CPU index | `requirements/cpu.txt` |

`python setup.py` reads the CUDA version from `nvidia-smi` and installs `cuda132.txt`, `cuda130.txt`, or `cuda129.txt`. A driver newer than 13.2 still uses `cuda132.txt`. CPU, XPU, GPU, and macOS files have no version pins. The three CUDA files pin torch and torchvision to the pair published on that index, checked on 2026-10-02. `cuda129.txt` uses a different pin on Windows because that index does not publish torch `2.13.0+cu129` for Windows. macOS Intel is reported and the profile is skipped. The editable package is installed from PyPI first, then the selected file.

### Install one feature yourself

```bash
pip install -e ".[openai]"          # also: anthropic, google, vertex, ollama,
                                    # huggingface, groq, xai, nvidia, cohere,
                                    # together, deepseek
pip install -e ".[llm]"             # LangGraph runtime, no chat provider
pip install -e ".[all-llm]"         # every chat provider, no Transformers or torch
pip install -e ".[huggingface-local]"   # ChatHuggingFace plus transformers and accelerate
pip install -e ".[huggingface-quant]"   # local extra plus bitsandbytes (NVIDIA CUDA)
pip install -r requirements/cuda132.txt
pip install -r requirements/cuda130.txt
pip install -r requirements/cuda129.txt
pip install -r requirements/cpu.txt
pip install -r requirements/xpu.txt
pip install -r requirements/gpu.txt
```

`requirements/common.txt` is the shared chat-provider list. The accelerator files include it.

Credentials stay in the environment. They are not accepted in JSON config files.

| Provider id | Extra | Environment variable | Default model |
| --- | --- | --- | --- |
| `openai` | `openai` | `OPENAI_API_KEY` | `gpt-4.1-mini` |
| `anthropic` | `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-5` |
| `google` | `google` | `GOOGLE_API_KEY` | `gemini-2.5-flash` |
| `vertex` | `vertex` | `GOOGLE_CLOUD_PROJECT` and Application Default Credentials | `gemini-2.5-flash` |
| `anthropic-vertex` | `vertex` | `GOOGLE_CLOUD_PROJECT` and Application Default Credentials | `claude-haiku-4-5@20251001` |
| `ollama` | `ollama` | none (`OLLAMA_BASE_URL` optional) | `llama3.2` |
| `huggingface` | `huggingface` for remote; `huggingface-local` for files on disk; `huggingface-quant` for 4-bit and 8-bit on CUDA | `HF_TOKEN` or `HUGGINGFACEHUB_API_TOKEN` only when `HF_BACKEND=remote` | `HF_LOCAL_MODEL_PATH` locally. Remote default is `microsoft/Phi-3-mini-4k-instruct` |
| `groq` | `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| `xai` | `xai` | `XAI_API_KEY` | `grok-3` |
| `nvidia` | `nvidia` | `NVIDIA_API_KEY` | `meta/llama-3.1-70b-instruct` |
| `cohere` | `cohere` | `COHERE_API_KEY` | `command-r-plus` |
| `together` | `together` | `TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| `deepseek` | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` |

`anthropic` calls the Anthropic API. `anthropic-vertex` calls Claude on Vertex AI.

Provider options: `ollama` takes `base_url`; `vertex` and `anthropic-vertex` take `location`. Gemini on Vertex defaults to `us-central1`. Claude on Vertex defaults to `us-east5`. Both honour `GOOGLE_CLOUD_LOCATION`.

### Hugging Face local models

The default Hugging Face backend is local. `annotate` loads `ChatHuggingFace` from `HuggingFacePipeline` and a directory you already have on disk. It does not download weights. `HF_BACKEND=remote` (the old name `endpoint` still works) is the optional Hub path and needs a token.

```bash
pip install -e ".[huggingface-local]"
pip install -r requirements/cuda132.txt    # or cuda130.txt, cuda129.txt, cpu.txt, macos.txt, gpu.txt, xpu.txt

figma-extractor model download Qwen/Qwen3-0.6B --dest /models/Qwen3-0.6B
figma-extractor model validate --path /models/Qwen3-0.6B
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `HF_BACKEND` | `local` | `local` or `remote` (`endpoint` means `remote`) |
| `HF_LOCAL_MODEL_PATH` | unset | Directory with `config.json` and weight files |
| `HF_TASK` | `text-generation` | Causal LM task. Other tasks are rejected |
| `HF_DEVICE` | `auto` | `auto`, `cpu`, `cuda`, `rocm`, `mps`, or `xpu` |
| `HF_DEVICE_MAP` | `auto` | Applied on CUDA. A forced CPU device does not use it |
| `HF_DTYPE` | `auto` | CPU uses float32. CUDA uses bfloat16 only when the GPU implements it in hardware, otherwise float16 |
| `HF_QUANTIZATION` | `none` | `none`, `4bit`, or `8bit` |
| `HF_BNB_4BIT_QUANT_TYPE` | `nf4` | Used only while 4-bit is active |
| `HF_BNB_4BIT_COMPUTE_DTYPE` | `float16` | 4-bit compute dtype |
| `HF_BNB_4BIT_USE_DOUBLE_QUANT` | `true` | Nested 4-bit quantization |
| `HF_QUANTIZATION_ON_UNSUPPORTED` | `error` | `error` stops. `fallback` keeps full precision and reports quantization `none` |
| `HF_OFFLINE` | `false` | Blocks `model download` and sets `HF_HUB_OFFLINE` plus `TRANSFORMERS_OFFLINE` while loading |
| `HF_MAX_NEW_TOKENS` | 512, or `LLM_MAX_TOKENS` | Generation cap |
| `HF_TOP_P` | `1.0` | Used when sampling is on |
| `HF_TOP_K` | unset | Optional sampler cutoff |
| `HF_REPETITION_PENALTY` | `1.0` | Generation penalty |

4-bit and 8-bit use BitsAndBytes on NVIDIA CUDA (`cuda132.txt`, `cuda130.txt`, and `cuda129.txt` include `bitsandbytes`, or `pip install -e ".[huggingface-quant]"`). CPU, MPS, ROCm, and XPU stay full precision. Setting `HF_QUANTIZATION_ON_UNSUPPORTED=fallback` runs full precision and the report says quantization is not active. A local run passes `local_files_only`, so a missing file fails instead of downloading. Copy `.env.example` for the full list. The longer guide is in the docs under Hugging Face local.

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
figma-extractor extract -f ./design.fig -o ./out --toon

figma-extractor extract --remote https://www.figma.com/design/ABC123/My-Kit \
  --output ./out
figma-extractor extract -r ABC123 -o ./out --api-key "$FIGMA_API_KEY"
```

Pass exactly one of `--file` / `-f` or `--remote` / `-r`. `--output` / `-o` is required. `--api-key` reads `FIGMA_API_KEY` when the flag is omitted. A remote extract needs that token. `--clean` is the default; `--no-clean` keeps previous files. `--keep-intermediates` retains `source/` and `extracted/`. `--toon` also writes `catalog/`, `toon/`, and related transport files (vectors and schema artifacts are always written).

When the path is a bare `canvas.fig` next to an `images/` folder (common after a prior decode), those rasters are copied into the extract automatically.

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

figma-extractor annotate --dir ./out \
  --llm \
  --llm-provider huggingface \
  --llm-task screen_classification
```

The Hugging Face example above uses `HF_LOCAL_MODEL_PATH`. It does not pass a Hub id.

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

### Devices and local model files

```bash
figma-extractor devices
figma-extractor model download Qwen/Qwen3-0.6B --dest /models/Qwen3-0.6B
figma-extractor model validate --path /models/Qwen3-0.6B
figma-extractor model validate --path /models/Qwen3-0.6B --load
```

`model validate` reads the directory and prints architecture, device, dtype, requested quantization, and active quantization. `--load` loads weights. `model download` is the only command that fetches the Hub, and it refuses to run when `HF_OFFLINE` is true.

## Python API

`extract` is keyword-only. Pass exactly one of `file` or `remote`. `api_key` is required for a remote call and is not read from `FIGMA_API_KEY` (that variable is CLI-only).

```python
from figma_extractor import extract, info, annotate, __version__
from figma_extractor.llm.config import LlmConfig, LlmTasks
from figma_extractor.llm.device import detect_device

extract(file="./design.fig", output="./out")
extract(file="./design.fig", output="./out", clean=False, keep_intermediates=True)
extract(file="./design.fig", output="./out", write_toon=True)
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
annotate(
    "./out",
    LlmConfig(
        enabled=True,
        provider="huggingface",
        tasks=LlmTasks(screen_classification=True),
        provider_options={
            "backend": "local",
            "model_path": "/models/Qwen3-0.6B",
            "quantization": "none",
        },
    ),
)

print(detect_device().summary())
```

`from figma_extractor import extract, info` does not import LangChain, LangGraph, or torch. `annotate` imports them only when `enabled=True`.

`extract()` returns `source`, `output`, `design` (same path as `output`), `decode`, `tokens`, `structure`, `images`, `trees`, `vectors`, `flow`, `intermediatesKept`, `transport` (when `write_toon=True`), and `schemaVersion` (2). It runs tokens → structure → images → trees → vector assets → UI flow → schema markers. Those stage functions are importable from `figma_extractor.extract` when you already have a decoded `extracted/` tree.

`info()` returns `directory`, `summary`, `pages`, `screens`, `components`, `componentSets`, `tokens`, `assets`, `text`, and `uiFlow`. Summary keys are `pages`, `screens`, `trees`, `components`, `componentSets`, `variables`, `textStyles`, `effects`, `assets`, `uniqueTextStrings`, and `suggestedRoutes`.

`annotate(directory, config=None, *, write=True)` requires `screens.json`. `write=False` returns the dict and skips `llm-annotations.json`. `LlmConfig.load(path=..., overrides=...)` applies defaults, then the file, then the environment, then overrides. `LlmConfig.from_env()` is `load()` with no file. Useful fields and defaults: `enabled=False`, `provider="openai"`, `model=None`, `temperature=0.0`, `max_tokens=None`, `timeout=60`, `max_retries=2`, `streaming=False`, `max_context_chars=12000`, `tasks=LlmTasks()`. Enabled config with no task raises before LangGraph is imported.

`detect_device()` returns `kind`, `available`, `detail`, and `torch_version`. Torch is imported inside that function.

## Output

Deliverables land at the output root. There is no nested `design/` folder. `source/` and `extracted/` are deleted after a successful extract unless you pass `--keep-intermediates`.

```
out/
├── manifest.json              # schemaVersion: 2, counts, index paths
├── LLM.md                     # per-extract summary + static read order
├── ui-flow.json
├── llm-annotations.json       # annotate, not extract
├── pages.json
├── screens.json               # origin, role, optional semantic, tree
├── components.json
├── component-sets.json
├── text-content.json
├── STRUCTURE.md
├── COMPONENTS.md
├── trees/
│   ├── index.json             # schemaVersion: 2
│   ├── boards/                # pre-split boards when a board was split
│   └── <page>__<screen>.json
├── screens/<slug>/screen.json # reference bundle (no embedded tree)
├── tokens/
│   ├── tokens.css
│   └── …
├── components/
│   └── index.json
├── assets/
│   ├── index.json             # rasters + vectors
│   ├── images/
│   ├── svg/
│   ├── manifest.json          # unified raster + vector rows
│   ├── vectors.json
│   └── missing-hashes.json
├── diagnostics/
│   ├── truncated.json
│   ├── unsupported.json
│   ├── assets.json
│   ├── layout.json            # constraint counts; no invented breakpoints
│   ├── interactions.json
│   └── performance.json       # vectorRef path-byte savings
└── structure/
    └── <page>.md
```

`suggestedRoutes` in `ui-flow.json` are slug guesses marked `inferred: true`. Specimen/gallery crops are omitted from that list. Prototype edges live under `interactions` (empty when the file has none). Screen `role` matches the **screen name** (kit page titles like “Admin Dashboard” do not force every crop to `dashboard`). `--clean` also removes `llm-annotations.json`.

### Schema versions

| | Schema 1 (older extracts) | Schema 2 (current) |
| --- | --- | --- |
| Marker | no `schemaVersion` | `manifest.json` and `trees/index.json` set `schemaVersion: 2` |
| Layout padding | `layout.pad` = `[top, right, bottom, left]` | same `pad` **plus** `layout.padding` `{top,right,bottom,left}` |
| Constraints | omitted | `constraints.horizontal` / `.vertical` when present in the file |
| Style / variable refs | omitted | `styleRefs` / `variableRefs` from `inherit*StyleID` and `variableConsumptionMap` |
| Screen lineage | omitted | `origin` (`top-level` / `board-child` / `crop`), `sourceScreenId`, `trees/boards/` |
| Routes | `suggestedRoutes[].path` | same, plus `inferred: true`; separate `interactions`; specimen crops excluded |
| Assets | raster `manifest.json` | + `id`/`kind`, `vectors.json`, unified index, image paint `file`, `vectorRef` |
| LLM guide | static identical text | per-extract header + `screens/<slug>/screen.json` bundles |
| Diagnostics | absent | always written (often empty arrays) |

Schema 1 files remain readable: readers should treat missing schema-2 keys as absent, not errors. Do not invent breakpoints; `diagnostics/layout.json` states that explicitly.


## Project layout

```
figma-extractor/
├── pyproject.toml
├── setup.py                 # detects OS and accelerator, installs the max profile
├── mkdocs.yml
├── requirements.txt         # extraction only, no version pins
├── requirements/
│   ├── common.txt           # chat providers, Transformers, Accelerate
│   ├── cuda132.txt          # NVIDIA CUDA 13.2
│   ├── cuda130.txt          # NVIDIA CUDA 13.0
│   ├── cuda129.txt          # NVIDIA CUDA 12.9
│   ├── cpu.txt
│   ├── xpu.txt              # Intel
│   ├── gpu.txt              # AMD ROCm
│   └── macos.txt
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
    ├── extract/             # tokens, structure, images, trees, split, flow, vectors, semantic
    ├── catalog.py           # reference catalog + TOON publish (no LLM)
    ├── llm/                 # optional; not imported by extract
    │   ├── annotate.py
    │   ├── config.py
    │   ├── factory.py
    │   ├── graph.py         # LangGraph: prepare, invoke, validate, repair, finalize
    │   ├── device.py
    │   ├── huggingface_local.py
    │   ├── huggingface_settings.py
    │   ├── prompt_format.py # turns task context into compact text
    │   ├── patches.py
    │   ├── merge.py
    │   └── providers/       # one module per provider, imported only when selected
    └── toon/                # included encoder and decoder for that text
```

## Upcoming: HTML from an extract

HTML output is not implemented yet.

A later release will build HTML from the strings and structure this package already writes: `trees/*.json`, `tokens/tokens.css`, `components.json`, `assets/manifest.json`, and `ui-flow.json`. The builder will follow the deterministic tree first. When LLM mode is enabled, it may ask the selected provider for recommendations, and those recommendations will stay marked as recommendations. The command will be added beside `extract` and `annotate`. `python setup.py` already installs the provider and torch profile that builder will use.

## Notes

- A `.fig` archive is decoded locally through the embedded kiwi schema, so local extraction works offline.
- Remote files are normalized into the same node stream as local `.fig` files, so token, structure, and image builders are shared.
- Fonts are not embedded in a `.fig`. Typography tokens record family, style, size, line height, and letter spacing.
