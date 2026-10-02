# Install

Python 3.11+ is required.

## Default: extraction only

```bash
pip install .
# or published package:
pip install figma-extractor
conda install -c vickykumar7125 figma-extractor
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

## Maximum features for this machine

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
| *(none)* | Editable package, then `cuda132.txt`, `cuda130.txt`, `cuda129.txt`, `cpu.txt`, `xpu.txt`, `gpu.txt`, or `macos.txt` |
| `--core` | Extraction only, same result as `pip install -e .` |
| `--no-llm` | Skip LangChain and provider packages |
| `--no-torch` | Skip PyTorch and torchvision |
| `--dry-run` | Print the plan and commands |

Detection order:

| Environment | Profile | Requirements file |
| --- | --- | --- |
| macOS Apple Silicon | MPS via the PyPI wheel | `requirements/macos.txt` |
| Linux or Windows, driver CUDA 13.2 or newer | torch `2.14.1+cu132`, torchvision `0.29.1+cu132` | `requirements/cuda132.txt` |
| Linux or Windows, driver CUDA 13.0 or 13.1 | torch `2.14.1+cu130`, torchvision `0.29.1+cu130` | `requirements/cuda130.txt` |
| Linux or Windows, driver CUDA 12.9 | Linux: torch `2.13.0+cu129` / torchvision `0.28.0+cu129`. Windows: torch `2.8.0+cu129` / torchvision `0.23.0+cu129` | `requirements/cuda129.txt` |
| Linux with ROCm and no NVIDIA GPU | ROCm index `rocm7.1` | `requirements/gpu.txt` |
| Linux or Windows with `xpu-smi` or `sycl-ls` | Intel XPU index | `requirements/xpu.txt` |
| Linux or Windows otherwise | CPU index | `requirements/cpu.txt` |

`python setup.py` reads the CUDA version from `nvidia-smi` and chooses one of the three CUDA files. A driver newer than 13.2 uses `cuda132.txt`. Those three files pin torch and torchvision to the pair published on that index, checked on 2026-10-02. CPU, XPU, GPU, and macOS files have no version pins. macOS Intel is reported and the profile is skipped. The editable package is installed first, then the selected file.

## Install one feature yourself

```bash
pip install -e ".[openai]"          # also: anthropic, google, vertex, ollama,
                                    # huggingface, groq, xai, nvidia, cohere,
                                    # together, deepseek
pip install -e ".[llm]"             # LangGraph runtime, no chat provider
pip install -e ".[all-llm]"         # every chat provider, no Transformers or torch
pip install -e ".[huggingface-local]"
pip install -e ".[huggingface-quant]"   # NVIDIA CUDA bitsandbytes
pip install -r requirements/cuda132.txt
pip install -r requirements/cuda130.txt
pip install -r requirements/cuda129.txt
pip install -r requirements/cpu.txt
pip install -r requirements/xpu.txt
pip install -r requirements/gpu.txt
```

`requirements/common.txt` is the shared chat-provider list. The accelerator files include it.

Credentials stay in the environment. They are not accepted in JSON config files.

| Provider id | Extra | Environment variable |
| --- | --- | --- |
| `openai` | `openai` | `OPENAI_API_KEY` |
| `anthropic` | `anthropic` | `ANTHROPIC_API_KEY` |
| `google` | `google` | `GOOGLE_API_KEY` |
| `vertex` | `vertex` | `GOOGLE_CLOUD_PROJECT` and Application Default Credentials |
| `anthropic-vertex` | `vertex` | `GOOGLE_CLOUD_PROJECT` and Application Default Credentials |
| `ollama` | `ollama` | none (`OLLAMA_BASE_URL` optional) |
| `huggingface` | `huggingface` | `HF_TOKEN` or `HUGGINGFACEHUB_API_TOKEN` only for `HF_BACKEND=remote` |
| `groq` | `groq` | `GROQ_API_KEY` |
| `xai` | `xai` | `XAI_API_KEY` |
| `nvidia` | `nvidia` | `NVIDIA_API_KEY` |
| `cohere` | `cohere` | `COHERE_API_KEY` |
| `together` | `together` | `TOGETHER_API_KEY` |
| `deepseek` | `deepseek` | `DEEPSEEK_API_KEY` |

`anthropic` calls the Anthropic API. `anthropic-vertex` calls Claude on Vertex AI. Local Hugging Face execution is the default for that provider. `cuda132.txt`, `cuda130.txt`, and `cuda129.txt` include `bitsandbytes`. The other profiles do not. See [Hugging Face local](huggingface.md).

Default model when `--llm-model` and `LLM_MODEL` are omitted:

| Provider id | Default model |
| --- | --- |
| `openai` | `gpt-4.1-mini` |
| `anthropic` | `claude-sonnet-4-5` |
| `google` | `gemini-2.5-flash` |
| `vertex` | `gemini-2.5-flash` |
| `anthropic-vertex` | `claude-haiku-4-5@20251001` |
| `ollama` | `llama3.2` |
| `huggingface` | local: `HF_LOCAL_MODEL_PATH`. Remote: `microsoft/Phi-3-mini-4k-instruct` |
| `groq` | `llama-3.3-70b-versatile` |
| `xai` | `grok-3` |
| `nvidia` | `meta/llama-3.1-70b-instruct` |
| `cohere` | `command-r-plus` |
| `together` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| `deepseek` | `deepseek-chat` |

After torch is installed:

```bash
figma-extractor devices
```

That reports `cpu`, `cuda`, `rocm`, `mps`, `xpu`, or `unavailable`.
