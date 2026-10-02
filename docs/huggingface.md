# Hugging Face local models

Local execution is the Hugging Face path. `annotate` builds `ChatHuggingFace` around `HuggingFacePipeline.from_model_id` pointed at a directory on disk. Transformers reads that directory (a single `model.safetensors` or sharded `model-00001-of-0000N.safetensors` plus `model.safetensors.index.json`). The rest of the app still talks to the same chat session the other providers use.

`HF_BACKEND=remote` keeps `HuggingFaceEndpoint` for hosted inference. `endpoint` is an older name for the same mode. Remote mode needs `HF_TOKEN` or `HUGGINGFACEHUB_API_TOKEN`. Local mode does not.

## Install

Core extraction does not install Transformers, Accelerate, bitsandbytes, or PyTorch.

```bash
pip install -e ".[huggingface-local]"
pip install -r requirements/cuda132.txt
```

Use `cuda130.txt` or `cuda129.txt` when the driver reports CUDA 13.0/13.1 or 12.9. Otherwise use `cpu.txt`, `macos.txt`, `gpu.txt`, or `xpu.txt`. `python setup.py` reads `nvidia-smi` and installs the matching file. The three CUDA files include `bitsandbytes`. The others do not.

## Configure

Copy the keys you need from `.env.example`.

```bash
export LLM_ENABLED=true
export LLM_PROVIDER=huggingface
export LLM_TASKS=screen_classification
export HF_BACKEND=local
export HF_LOCAL_MODEL_PATH=/models/Qwen3-0.6B
export HF_QUANTIZATION=none
export HF_OFFLINE=true

figma-extractor annotate --dir ./out
```

`HF_LOCAL_MODEL_PATH` is the directory. `LLM_MODEL` is not a Hub repo id in local mode. If `LLM_MODEL` itself is an existing directory, it is accepted when the path variable is unset.

| Choice | Effect |
| --- | --- |
| `HF_QUANTIZATION=none` | Full precision. Default |
| `HF_QUANTIZATION=4bit` | BitsAndBytes NF4. Lower memory, more numeric error |
| `HF_QUANTIZATION=8bit` | BitsAndBytes 8-bit. More memory than 4-bit, closer to full precision |
| `HF_DTYPE=auto` | float32 on CPU. On CUDA, bfloat16 only when the GPU implements it in hardware, otherwise float16. Emulated bfloat16 is not selected. Local chat turns off template reasoning (`enable_thinking=false`) so the generation budget is the answer rather than a `<think>` block. |
| `HF_DEVICE=cpu` | Force CPU. `device_map=auto` is not applied |
| `HF_DEVICE=cuda` | Require CUDA. Fails when CUDA is absent |
| `HF_OFFLINE=true` | Sets `HF_HUB_OFFLINE` and `TRANSFORMERS_OFFLINE` while loading, and `model download` refuses to run |

`HF_BNB_4BIT_QUANT_TYPE`, `HF_BNB_4BIT_COMPUTE_DTYPE`, and `HF_BNB_4BIT_USE_DOUBLE_QUANT` apply when 4-bit is actually active. Local loads always pass `local_files_only=True`. A missing weight file is an error, not a download. On some Turing GPUs, cuBLAS rejects an 8-bit matrix shape. Prompts are left-padded to a multiple of 16, with those positions masked, so the fast kernel is used. A remaining rejected shape uses the same full-precision multiplication BitsAndBytes already uses for unaligned dimensions. The loaded layers stay 8-bit. Quantized loads keep the runtime dtype, so a card without hardware bfloat16 does not cast bfloat16 weights on every layer.

The pipeline is cached in the process. A second `annotate` with the same path, dtype, and quantization reuses it.

## Commands

```bash
figma-extractor model download Qwen/Qwen3-0.6B --dest /models/Qwen3-0.6B
figma-extractor model validate --path /models/Qwen3-0.6B
figma-extractor model validate --path /models/Qwen3-0.6B --load
```

`validate` without `--load` reads `config.json` and `tokenizer_config.json`. It reports the architecture, device, dtype, requested quantization, active quantization, and package versions. `--load` constructs the pipeline and, when the model exposes it, prints `get_memory_footprint()`.

Weights belong under a `models/` directory. That directory, plus `*.safetensors`, `*.bin`, `*.pt`, and `*.pth`, is gitignored.

## Offline

Download once, then set `HF_OFFLINE=true` before `annotate` and `model validate`. Startup will not call the Hub. `HF_HOME`, `TRANSFORMERS_CACHE`, and `HUGGINGFACE_HUB_CACHE` still matter if a tool downloads into the default cache. This provider prefers `HF_LOCAL_MODEL_PATH` over that cache.

## Deploy

1. Install Python 3.11+.
2. Create a virtual environment.
3. `pip install -e ".[huggingface-local]"`.
4. Install `requirements/cuda132.txt`, `cuda130.txt`, or `cuda129.txt` for NVIDIA, or `cpu.txt`, `xpu.txt`, `gpu.txt`, or `macos.txt`.
5. The CUDA files already include bitsandbytes for 4-bit and 8-bit.
6. `figma-extractor model download … --dest …` on a machine that may reach the Hub.
7. Copy the directory to the host that will run, or mount it.
8. Export `HF_LOCAL_MODEL_PATH`, `HF_BACKEND=local`, and `HF_OFFLINE=true`.
9. `figma-extractor devices`.
10. `figma-extractor model validate --path …`.
11. `figma-extractor annotate --dir ./out --llm --llm-provider huggingface --llm-task screen_classification`.

Linux and Windows NVIDIA hosts use `cuda132.txt` (torch `2.14.1+cu132`), `cuda130.txt` (torch `2.14.1+cu130`), or `cuda129.txt` (Linux torch `2.13.0+cu129`, Windows torch `2.8.0+cu129`). macOS Apple Silicon uses `macos.txt` and does not install bitsandbytes. There is no Dockerfile in this repository. Mount a host directory at the path you set in `HF_LOCAL_MODEL_PATH` if you add a container later. Do not copy weights into an image unless you mean to.

## Hardware

| Backend | Local full precision | 4-bit / 8-bit |
| --- | --- | --- |
| NVIDIA CUDA 13.2, 13.0, or 12.9 | Yes, when the matching CUDA file is installed | Yes, when bitsandbytes imports and `HF_DEVICE` resolves to CUDA |
| CPU torch wheel | Yes, dtype float32 when `HF_DTYPE=auto` | No. The run fails, or stays full precision when `HF_QUANTIZATION_ON_UNSUPPORTED=fallback` |
| macOS MPS, ROCm, XPU | The matching torch file loads the model without bitsandbytes | Not claimed. The same failure or fallback rule applies |

The quantization decision is unit-tested with stand-in CPU and CUDA status objects. A real weight file was not loaded in that suite. Set `HF_RUN_INTEGRATION=1` and `HF_LOCAL_MODEL_PATH` to run `tests/llm/test_huggingface_integration.py`.

Active quantization in `figma-extractor model validate` is `none` unless 4-bit or 8-bit was actually selected. A fallback does not print an active 4-bit line.

## What changed

Hosted inference used to be the default (`backend=endpoint`). The default is now `local`. Remote inference remains behind `HF_BACKEND=remote`. Settings are parsed once. `build_local_plan` records path, device, dtype, and the quantization recipe. `load_pipeline` reuses that plan: prepare the runtime, construct the pipeline, then adapt 8-bit prompts. `model validate --load` passes the plan it already built. The graph still receives a `LangChainSession` and does not construct Transformers itself.
