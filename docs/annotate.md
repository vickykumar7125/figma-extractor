# Annotation

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

## Environment variables

These apply when the matching CLI flag is omitted.

| Variable | Meaning |
| --- | --- |
| `LLM_ENABLED` | `true` or `false` (default false) |
| `LLM_PROVIDER` | provider id from the [install table](install.md#install-one-feature-yourself) |
| `LLM_MODEL` | model id; each provider has a default |
| `LLM_TEMPERATURE` | 0 to 2 |
| `LLM_MAX_TOKENS` | response token cap |
| `LLM_TIMEOUT` | seconds |
| `LLM_MAX_RETRIES` | transport retries |
| `LLM_STREAMING` | `true` or `false` |
| `LLM_TASKS` | comma-separated task names |

## JSON config

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
