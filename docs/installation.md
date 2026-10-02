# Installation

```bash
pip install figma-extractor
```

Or with conda / mamba from Anaconda.org:

```bash
conda install -c vickykumar7125 figma-extractor
# or
mamba install -c vickykumar7125 figma-extractor
```

That installs the core extractor and the `figma-extractor` command. It does not install LangChain, Transformers, PyTorch, or bitsandbytes. Pip selects one universal wheel, `figma_extractor-<version>-py3-none-any.whl`, on Linux, Windows, and macOS. The conda package is `noarch` Python and installs the same runtime dependencies. There is no CUDA-specific wheel, because this package does not contain compiled CUDA code.

Python 3.11 or newer is required.

## Optional extras

```bash
pip install "figma-extractor[openai]"
pip install "figma-extractor[huggingface]"
pip install "figma-extractor[huggingface-local]"
pip install "figma-extractor[all-llm]"
pip install "figma-extractor[dev]"
```

Extras: `llm`, `openai`, `anthropic`, `google`, `vertex`, `ollama`, `huggingface`, `huggingface-local`, `huggingface-quant`, `groq`, `xai`, `nvidia`, `cohere`, `together`, `deepseek`, `all-llm`, `dev`, `test`.

`huggingface-quant` adds bitsandbytes. It does not select a CUDA build of PyTorch. Conda installs the extraction core only; use pip extras in the same environment when you need LLM providers.

## PyTorch

Install PyTorch from the official index that matches the machine, as a separate command. Then install this package, or the other way around. Pip cannot choose between the CUDA 12.9, 13.0, and 13.2 indexes by itself.

| Machine | Command |
| --- | --- |
| NVIDIA driver CUDA 13.2 or newer | `pip install -r requirements/cuda132.txt` from a checkout, or the pins in that file |
| NVIDIA driver CUDA 13.0 or 13.1 | `requirements/cuda130.txt` |
| NVIDIA driver CUDA 12.9 | `requirements/cuda129.txt` |
| CPU | `requirements/cpu.txt` |
| Intel XPU | `requirements/xpu.txt` |
| AMD ROCm on Linux | `requirements/gpu.txt` |
| macOS Apple Silicon | `requirements/macos.txt` |

Those files also install the chat-provider stack. For extraction only, stop after `pip install figma-extractor` or `conda install -c vickykumar7125 figma-extractor`.

From a clone, `python setup.py` reads `nvidia-smi` and installs the matching file. `python setup.py --core` installs the editable package only.

## Source

```bash
pip install .
```

If a wheel is not available for the platform, pip builds the sdist. The sdist needs a normal Python toolchain. It does not need a CUDA compiler.

## Conda recipe (maintainers)

The repository recipe lives in `conda-recipe/`. From a checkout with `conda-build`:

```bash
conda build conda-recipe -c conda-forge --output-folder ./conda-bld
anaconda --site anaconda.org upload -u vickykumar7125 ./conda-bld/noarch/figma-extractor-*.conda
```

Do not commit Anaconda tokens. Store `ANACONDA_API_TOKEN` as a GitHub Actions secret for the Release workflow.
