# Usage

The usual path is extract, then inspect, then optionally annotate.

```bash
figma-extractor extract --file ./design.fig --output ./out
figma-extractor info --dir ./out
figma-extractor annotate --dir ./out --llm-disabled
```

The same three commands exist as `python -m figma_extractor …`. Every flag is listed on the [CLI](cli.md) page. Deliverable layout is on the [Output](output.md) page.

## Local `.fig`

```bash
figma-extractor extract --file ./design.fig --output ./out
figma-extractor extract -f ./design.fig -o ./out --no-clean
figma-extractor extract -f ./design.fig -o ./out --keep-intermediates
figma-extractor extract -f ./design.fig -o ./out --toon
```

`--no-clean` keeps files already in the output directory. `--keep-intermediates` leaves `source/` and `extracted/` in place after a successful run. `--toon` also writes `catalog/`, `toon/`, and related transport files. Vectors, diagnostics, and schema markers are always written. The default removes both the previous deliverables and the temporary folders.

When you pass a bare `canvas.fig` that sits next to an `images/` folder, those rasters are copied into the extract automatically.

## What you get

- `screens.json` rows include `origin` (`top-level`, `board-child`, or `crop`) and optional `sourceScreenId` / `semantic`
- Trees expose `layout.padding`, `constraints`, `styleRefs`, `variableRefs`, and shared icons as `vectorRef`
- `ui-flow.json` keeps guessed routes as `inferred: true` and lists real prototype edges under `interactions`
- `LLM.md` starts with counts for this extract, then the static read-order guide
- `screens/<slug>/screen.json` is a reference bundle (tree path, role, route, optional reconstruction hints) without embedding the tree

Schema 1 extracts without those keys remain readable. See [Output](output.md) for the full tree.

## Remote file

`--remote` accepts a Figma design URL or a bare file key. The token comes from `--api-key` or from `FIGMA_API_KEY` when that flag is omitted.

```bash
export FIGMA_API_KEY=figd_xxx

figma-extractor extract --remote https://www.figma.com/design/ABC123/My-Kit \
  --output ./out

figma-extractor extract -r ABC123 -o ./out --api-key "$FIGMA_API_KEY"
```

The Python function requires `api_key` itself. Only the CLI reads `FIGMA_API_KEY`.

## Inspect

```bash
figma-extractor info --dir ./out
figma-extractor info --dir ./out --json
figma-extractor info
```

The last form reads `.` and prints JSON. The table form is only used when `--dir` is set and `--json` is not.

## Module invocation

```bash
python -m figma_extractor extract -f ./design.fig -o ./out
python -m figma_extractor info -d ./out --json
python -m figma_extractor annotate -d ./out --llm-disabled
python -m figma_extractor devices
python -m figma_extractor model validate --path /models/Qwen3-0.6B
python -m figma_extractor --version
```

## Local Hugging Face model

Download once, validate the directory, then annotate. The annotation does not download weights.

```bash
figma-extractor model download Qwen/Qwen3-0.6B --dest /models/Qwen3-0.6B
figma-extractor model validate --path /models/Qwen3-0.6B

export HF_BACKEND=local
export HF_LOCAL_MODEL_PATH=/models/Qwen3-0.6B
export HF_QUANTIZATION=none

figma-extractor annotate --dir ./out \
  --llm \
  --llm-provider huggingface \
  --llm-task screen_classification
```

Settings, quantization, and the CUDA-only 4-bit and 8-bit install are on the [Hugging Face local](huggingface.md) page.
