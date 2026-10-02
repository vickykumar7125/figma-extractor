# Usage

The usual path is extract, then inspect, then optionally annotate.

```bash
figma-extractor extract --file ./design.fig --output ./out
figma-extractor info --dir ./out
figma-extractor annotate --dir ./out --llm-disabled
```

The same three commands exist as `python -m figma_extractor …`. Every flag is listed on the [CLI](cli.md) page.

## Local `.fig`

```bash
figma-extractor extract --file ./design.fig --output ./out
figma-extractor extract -f ./design.fig -o ./out --no-clean
figma-extractor extract -f ./design.fig -o ./out --keep-intermediates
```

`--no-clean` keeps files already in the output directory. `--keep-intermediates` leaves `source/` and `extracted/` in place after a successful run. The default removes both the previous deliverables and those temporary folders.

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
