# Annotation

Annotation is a second step. `extract` never calls a model. `annotate` reads `screens.json` and writes `llm-annotations.json`.

```bash
figma-extractor annotate --dir ./out --llm-disabled
```

A disabled run writes roles and regions already on disk and does not call a model. The file records `llmEnabled: false` and a warning that the annotations are the deterministic extract. Those suggestions do not replace `screens.json`. Reconstruction hints, when a model produces them, use `kind: "recommended"`.

## Turn a model on

```bash
figma-extractor annotate --dir ./out \
  --llm \
  --llm-provider ollama \
  --llm-model llama3.2 \
  --llm-task screen_classification \
  --llm-task reconstruction_hints
```

`--llm-task` repeats. Allowed names:

| Task | What it asks for |
| --- | --- |
| `semantic_classification` | Role labels for nodes in the bounded context |
| `screen_classification` | Screen role for each listed screen |
| `component_analysis` | Notes on components in the bounded context |
| `svg_analysis` | Notes on vector assets. Path `d` commands are omitted from the prompt |
| `reconstruction_hints` | Layout recommendations, marked `recommended` |

Enabled mode with an empty task list exits with an error. Hugging Face chat has no streaming capability, so `LLM_STREAMING=true` is rejected for that provider. The default Hugging Face backend is local: set `HF_LOCAL_MODEL_PATH` and do not pass a Hub id. `HF_BACKEND=remote` is the hosted path. The local install, quantization, and `model validate` command are on the [Hugging Face local](huggingface.md) page.

```bash
figma-extractor annotate --dir ./out \
  --llm \
  --llm-provider huggingface \
  --llm-task screen_classification
```

## Configuration order

Later values replace earlier ones:

1. Built-in defaults (`enabled` false, provider `openai`, temperature `0`)
2. JSON from `--llm-config`
3. Environment variables
4. CLI flags that you actually pass (`--llm`, `--llm-provider`, `--llm-model`, `--llm-temperature`, `--llm-task`)

```bash
figma-extractor annotate --dir ./out --llm --llm-config ./llm.json
```

```json
{
  "enabled": true,
  "provider": "ollama",
  "model": "llama3.2",
  "temperature": 0,
  "max_tokens": 1024,
  "timeout": 60,
  "max_retries": 2,
  "streaming": false,
  "max_context_chars": 12000,
  "tasks": {
    "screen_classification": true,
    "reconstruction_hints": true
  },
  "provider_options": {
    "base_url": "http://127.0.0.1:11434"
  }
}
```

The same object may sit under an `"llm"` key. Credentials are environment variables. A JSON file that contains `api_key`, `token`, `secret`, `password`, `authorization`, or `credentials` is rejected.

## Environment variables

Applied when the matching CLI flag is omitted.

| Variable | Meaning |
| --- | --- |
| `LLM_ENABLED` | `true` or `false` (default false). Also `1`/`yes`/`on` and `0`/`no`/`off` |
| `LLM_PROVIDER` | Provider id. Default `openai` |
| `LLM_MODEL` | Model id. Empty means the provider default |
| `LLM_TEMPERATURE` | `0` to `2` |
| `LLM_MAX_TOKENS` | Response token cap |
| `LLM_TIMEOUT` | Seconds |
| `LLM_MAX_RETRIES` | Transport retries |
| `LLM_STREAMING` | `true` or `false` |
| `LLM_TASKS` | Comma-separated task names |
| `LLM_TASK_SEMANTIC_CLASSIFICATION` | `true` or `false` for that task |
| `LLM_TASK_SCREEN_CLASSIFICATION` | same pattern |
| `LLM_TASK_COMPONENT_ANALYSIS` | same pattern |
| `LLM_TASK_SVG_ANALYSIS` | same pattern |
| `LLM_TASK_RECONSTRUCTION_HINTS` | same pattern |

`LLM_TASK_<NAME>` overrides the same name from `LLM_TASKS`.

```bash
export LLM_ENABLED=true
export LLM_PROVIDER=ollama
export LLM_MODEL=llama3.2
export LLM_TASKS=screen_classification,reconstruction_hints
figma-extractor annotate --dir ./out
```

Provider credential variables and per-provider options (`OLLAMA_BASE_URL`, `backend`, Vertex `location`) are on the [Python API](python-api.md#llmconfig) page. Default model ids are on the [Install](install.md#install-one-feature-yourself) page.

## From Python

```python
from figma_extractor import annotate
from figma_extractor.llm.config import LlmConfig, LlmTasks

annotate("./out", LlmConfig(enabled=False))

annotate(
    "./out",
    LlmConfig(
        enabled=True,
        provider="ollama",
        model="llama3.2",
        tasks=LlmTasks(
            screen_classification=True,
            reconstruction_hints=True,
        ),
    ),
)
```

`annotate(directory)` with no config object uses `LlmConfig.from_env()`. Pass `write=False` to get the dict and skip the file. The code-level field list, return shape, and graph steps are on the [Python API](python-api.md#annotate) page.
