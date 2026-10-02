# Python API

`extract` and `info` are imported from the package root. `annotate` is also available there, and the import stays lazy: LangChain, LangGraph, and torch load only when annotation is enabled.

```python
from figma_extractor import extract, info, annotate, __version__
from figma_extractor.llm.config import LlmConfig, LlmTasks
```

`figma_extractor.llm` exports `annotate` and `LlmConfig`. Importing that package does not import a provider SDK.

## extract

Keyword-only. Pass exactly one of `file` or `remote`.

```python
extract(file="./design.fig", output="./out")
extract(file="./design.fig", output="./out", clean=False, keep_intermediates=True)

extract(remote="ABC123", output="./out", api_key="figd_xxx")
extract(
    remote="https://www.figma.com/design/ABC123/My-Kit",
    output="./out",
    api_key="figd_xxx",
)
```

| Argument | Default | Meaning |
| --- | --- | --- |
| `file` | `None` | Local `.fig` path |
| `remote` | `None` | File key or Figma URL |
| `output` | required | Destination directory. Created if missing |
| `api_key` | `None` | Required when `remote` is set. The function does not read `FIGMA_API_KEY` |
| `keep_intermediates` | `False` | Keep `source/` and `extracted/` |
| `clean` | `True` | Remove previous deliverables under `output` first |

The return value is a dict:

| Key | Meaning |
| --- | --- |
| `source` | `{"type": "local"\|"remote", "value": path or file key}` |
| `output` | Resolved output directory |
| `design` | Same path as `output` (older name) |
| `decode` | Local canvas summary, or remote node and image counts |
| `tokens` | Token summary from `build_tokens` |
| `structure` | Counts including `pages`, `screens`, `components` |
| `images` | Image export summary |
| `trees` | Tree summary (`trees`, and `split.screensAfter` when a board was split) |
| `flow` | UI-flow summary |
| `intermediatesKept` | The `keep_intermediates` flag you passed |

Inside `extract`, the stages run in this order and can also be called on a directory that already has `extracted/nodes.ndjson`:

```python
from figma_extractor.extract import (
    build_tokens,
    build_structure,
    build_images,
    build_screen_trees,
    build_ui_flow,
)
```

Call `extract()` for a full run. The stage functions expect the decode cache and write the same files `extract` writes.

## info

```python
details = info("./out")
details = info()  # current working directory
print(details["summary"])
for screen in details["screens"]:
    print(screen["name"], screen.get("width"), screen.get("height"))
```

`directory` may be omitted. The resolver accepts the output root or a legacy `design/` subfolder when `pages.json` or `screens.json` is there. Otherwise it raises `FileNotFoundError`.

| Key | Contents |
| --- | --- |
| `directory` | Resolved extract path |
| `summary` | Counts listed below |
| `pages` | `pages.json` |
| `screens` | `screens.json` |
| `components` | `components.json` |
| `componentSets` | `component-sets.json` |
| `tokens` | `variables`, `typography`, `effects` |
| `assets` | `assets/manifest.json` |
| `text` | `text-content.json` |
| `uiFlow` | `ui-flow.json`, or `None` when that file is absent |

`summary` keys: `pages`, `screens`, `trees`, `components`, `componentSets`, `variables`, `textStyles`, `effects`, `assets`, `uniqueTextStrings`, `suggestedRoutes`.

`figma_extractor.api.resolve_output_dir` is the same directory check. `resolve_design_dir` is an alias.

## annotate

```python
from figma_extractor import annotate
from figma_extractor.llm.config import LlmConfig, LlmTasks

# Reads LLM_* from the environment when config is omitted.
result = annotate("./out")

# Deterministic. Does not import a provider SDK.
result = annotate("./out", LlmConfig(enabled=False))

# Calls the selected provider. Requires that extra to be installed.
result = annotate(
    "./out",
    LlmConfig(
        enabled=True,
        provider="ollama",
        model="llama3.2",
        tasks=LlmTasks(screen_classification=True),
    ),
)

# Build the object and skip the file write.
payload = annotate("./out", LlmConfig(enabled=False), write=False)
```

| Argument | Default | Meaning |
| --- | --- | --- |
| `directory` | required | Extract root. Must contain `screens.json` |
| `config` | `None` | `LlmConfig`. Omitted means `LlmConfig.from_env()` |
| `write` | `True` | Write `llm-annotations.json` |

A disabled result has `llmEnabled: false`, empty `llmResults`, and screen rows copied from the extract. An enabled result is produced by the LangGraph workflow (`prepare`, `invoke`, `validate`, `repair`, `finalize`).

## LlmConfig

```python
from figma_extractor.llm.config import LlmConfig, LlmTasks

config = LlmConfig.load(path="./llm.json", overrides={"enabled": True, "provider": "ollama"})
config = LlmConfig.from_env()
config.resolved_model()  # explicit model, or the provider default
config.check()           # raises LlmConfigError when an enabled config cannot run
```

Load order, later wins: built-in defaults, JSON file, environment, then `overrides`. `None` values in `overrides` are ignored. Keys named `api_key`, `token`, `secret`, `password`, `authorization`, or `credentials` are rejected in the file, in `provider_options`, and in overrides.

| Field | Default | Meaning |
| --- | --- | --- |
| `enabled` | `False` | Call a model |
| `provider` | `"openai"` | Provider id |
| `model` | `None` | Falls back to that provider's default model |
| `temperature` | `0.0` | `0` to `2` |
| `max_tokens` | `None` | Response token cap |
| `timeout` | `60.0` | Seconds, must be `> 0` |
| `max_retries` | `2` | Transport retries in the shared policy |
| `streaming` | `False` | Requires a provider with streaming |
| `max_context_chars` | `12000` | Context cap, at least `500` |
| `max_concurrency` | `1` | Recorded on the policy. Tasks still run sequentially |
| `failure_limit` | `4` | Consecutive failures before the run stops calling the provider |
| `validation_attempts` | `2` | One initial attempt plus one repair by default |
| `backoff_seconds` | `0.5` | Delay between retries |
| `tasks` | all false | `LlmTasks` |
| `provider_options` | `{}` | String map. See the table below |

Enabled mode with no selected task raises `LlmConfigError` before LangGraph is imported.

`LlmTasks` fields match the task names. `enabled_names()` returns the names that are true. `from_mapping` rejects unknown names. Boolean strings accepted by the loader are `1`, `true`, `yes`, `on` and `0`, `false`, `no`, `off`.

JSON may nest settings under an `llm` object. That object is merged over the top-level keys. `options` is accepted as an alias of `provider_options`.

```python
LlmConfig(
    enabled=True,
    provider="huggingface",
    tasks=LlmTasks(screen_classification=True),
    provider_options={"backend": "local"},
)

LlmConfig(
    enabled=True,
    provider="vertex",
    tasks=LlmTasks(semantic_classification=True),
    provider_options={"location": "us-central1"},
)
```

| Provider | Allowed `provider_options` | Also read from the environment |
| --- | --- | --- |
| `ollama` | `base_url` | `OLLAMA_BASE_URL` |
| `huggingface` | `backend` = `endpoint` (default) or `local` | `HF_TOKEN` or `HUGGINGFACEHUB_API_TOKEN` skipped when `backend` is `local` |
| `vertex` | `location` | `GOOGLE_CLOUD_LOCATION`, default `us-central1` |
| `anthropic-vertex` | `location` | `GOOGLE_CLOUD_LOCATION`, default `us-east5` |
| every other provider | none | credential variables only |

Unknown option keys raise `ProviderCapabilityError` when a session is built.

## Devices

```python
from figma_extractor.llm.device import detect_device

status = detect_device()
status.kind       # cpu, cuda, rocm, mps, xpu, or unavailable
status.available
status.detail
status.torch_version
status.summary()  # same line the devices command prints
```

Importing `detect_device` does not import torch. The import happens inside the function.
