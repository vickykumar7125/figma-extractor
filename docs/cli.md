# CLI

Two entry points run the same Typer app:

```bash
figma-extractor --help
python -m figma_extractor --help
```

`figma-extractor` is the console script from `pyproject.toml` (`figma_extractor.cli:app`). `python -m figma_extractor` loads `figma_extractor.__main__`, which calls that app.

```bash
figma-extractor --version
figma-extractor -V
```

`--version` / `-V` prints `figma-extractor` plus the package version and exits. The four commands are `extract`, `info`, `annotate`, and `devices`. Running the program with no command prints help.

Errors from these commands print to stderr and exit with status `1`.

## extract

Write one local or remote file into an output directory. Deliverables land at the output root.

```bash
figma-extractor extract --file ./design.fig --output ./out
figma-extractor extract -f ./design.fig -o ./out
figma-extractor extract --remote https://www.figma.com/design/ABC123/My-Kit \
  --output ./out --api-key "$FIGMA_API_KEY"
figma-extractor extract -r ABC123 -o ./out
figma-extractor extract -f ./design.fig -o ./out --no-clean --keep-intermediates
```

Pass exactly one of `--file` or `--remote`. A remote call needs a token from `--api-key` or `FIGMA_API_KEY`.

| Flag | Short | Default | Meaning |
| --- | --- | --- | --- |
| `--file` | `-f` | unset | Local `.fig` archive |
| `--remote` | `-r` | unset | Figma file URL or file key |
| `--output` | `-o` | required | Destination directory |
| `--api-key` |  | `FIGMA_API_KEY` | Figma personal access token |
| `--clean` / `--no-clean` |  | `--clean` | Wipe previous deliverables under the output directory before writing |
| `--keep-intermediates` |  | off | Keep `source/` and `extracted/` after a successful run |

On success the CLI prints a table with the output path and counts of pages, screens, trees, and components.

## info

Read a previous extract and print counts or full JSON.

```bash
figma-extractor info --dir ./out
figma-extractor info -d ./out
figma-extractor info -d ./out --json
figma-extractor info
```

| Flag | Short | Default | Meaning |
| --- | --- | --- | --- |
| `--dir` | `-d` | current directory | Extraction root |
| `--json` |  | off | Print the full report as indented JSON |

Without `--dir`, `info` reads the current directory and always prints JSON. With `--dir` and without `--json`, it prints a summary table of the `summary` block (pages, screens, trees, components, component sets, variables, text styles, effects, assets, unique text strings, suggested routes).

The directory must contain `pages.json` or `screens.json`. A legacy extract that nested those files under `design/` is still accepted.

## annotate

Write `llm-annotations.json` next to the extract. The default is deterministic: roles and regions already on disk, no model call.

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

| Flag | Short | Default | Meaning |
| --- | --- | --- | --- |
| `--dir` | `-d` | `.` | Extract directory (`screens.json` required) |
| `--llm` / `--llm-disabled` |  | omitted | Enable or skip the model. When omitted, `LLM_ENABLED` applies (default false) |
| `--llm-provider` |  | `LLM_PROVIDER`, else `openai` | Provider id |
| `--llm-model` |  | `LLM_MODEL` | Model id. Each provider has a default when this is unset |
| `--llm-temperature` |  | `LLM_TEMPERATURE`, else `0` | Sampling temperature, `0` to `2` |
| `--llm-config` |  | unset | JSON object. Loaded before environment variables |
| `--llm-task` |  | unset | Repeat to enable one task. Used only when LLM mode is on |

`--llm` and `--llm-disabled` override `LLM_ENABLED`. A flag that you omit does not clear the matching environment variable. Enabled mode requires at least one task (`--llm-task`, `LLM_TASKS`, or `tasks` in the JSON file).

Allowed task names: `semantic_classification`, `screen_classification`, `component_analysis`, `svg_analysis`, `reconstruction_hints`.

## model

Prepare a local Hugging Face directory. These commands do not run during `extract` or `annotate`.

```bash
figma-extractor model download Qwen/Qwen3-0.6B --dest /models/Qwen3-0.6B
figma-extractor model validate --path /models/Qwen3-0.6B
figma-extractor model validate --path /models/Qwen3-0.6B --load
```

`download` is refused when `HF_OFFLINE` is true. `validate` reads `config.json` and reports device, dtype, and quantization. It does not download and it does not load weights unless you pass `--load`.

## devices

```bash
figma-extractor devices
```

Prints one line from the device detector: `cpu`, `cuda`, `rocm`, `mps`, `xpu`, or `unavailable`, plus a short detail and the installed torch version. Torch is imported only by this command (and by local Hugging Face inference). `extract` and `info` do not import it.
