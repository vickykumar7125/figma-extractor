# Install

Python 3.11+ is required.

## Default: extraction only

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

## Install one feature yourself

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

| Provider id | Extra | Environment variable |
| --- | --- | --- |
| `openai` | `openai` | `OPENAI_API_KEY` |
| `anthropic` | `anthropic` | `ANTHROPIC_API_KEY` |
| `google` | `google` | `GOOGLE_API_KEY` |
| `vertex` | `vertex` | `GOOGLE_CLOUD_PROJECT` and Application Default Credentials |
| `anthropic-vertex` | `vertex` | `GOOGLE_CLOUD_PROJECT` and Application Default Credentials |
| `ollama` | `ollama` | none (`OLLAMA_BASE_URL` optional) |
| `huggingface` | `huggingface` | `HF_TOKEN` or `HUGGINGFACEHUB_API_TOKEN` (not required when `backend=local`) |
| `groq` | `groq` | `GROQ_API_KEY` |
| `xai` | `xai` | `XAI_API_KEY` |
| `nvidia` | `nvidia` | `NVIDIA_API_KEY` |
| `cohere` | `cohere` | `COHERE_API_KEY` |
| `together` | `together` | `TOGETHER_API_KEY` |
| `deepseek` | `deepseek` | `DEEPSEEK_API_KEY` |

`anthropic` calls the Anthropic API. `anthropic-vertex` calls Claude on Vertex AI. Local Hugging Face inference (`backend=local`) also needs the torch profile `setup.py` selected, plus `transformers`.

After torch is installed:

```bash
figma-extractor devices
```

That reports `cpu`, `cuda`, `rocm`, `mps`, `xpu`, or `unavailable`.
