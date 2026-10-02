# Compatibility

`figma-extractor` is pure Python. The published artifact is one wheel, `py3-none-any`, plus an sdist. Operating system, CPU architecture, and accelerator do not change which wheel pip selects.

The unit suite in CI runs on Linux, Windows, and macOS for Python 3.11 and 3.12. The table below marks that suite. It does not mark a GPU extraction as tested.

| Python | Wheel | Linux | Windows | macOS | Notes |
| --- | --- | --- | --- | --- | --- |
| 3.11 | `py3-none-any` | CI | CI | CI | `requires-python >=3.11` |
| 3.12 | `py3-none-any` | CI | CI | CI | same wheel |
| 3.13+ | same tag | not in the CI matrix | not in the CI matrix | not in the CI matrix | allowed by the metadata when the dependencies install |

## Accelerators

These are PyTorch install profiles. They are not extra wheels.

| Profile | Where it applies | Tested as a wheel |
| --- | --- | --- |
| CPU | `requirements/cpu.txt` | The package imports without torch. A CPU torch install is optional. |
| CUDA 13.2 | `requirements/cuda132.txt`, torch `2.14.1+cu132`, torchvision `0.29.1+cu132` | Index checked 2026-10-02. Not a separate package wheel. |
| CUDA 13.0 | `requirements/cuda130.txt`, torch `2.14.1+cu130`, torchvision `0.29.1+cu130` | Same. |
| CUDA 12.9 | `requirements/cuda129.txt`. Linux torch `2.13.0+cu129`. Windows torch `2.8.0+cu129` | Same. The 12.9 index does not publish the Linux pair for Windows. |
| Intel XPU | `requirements/xpu.txt` | Runtime detection exists. CI does not run an XPU device. |
| AMD ROCm | `requirements/gpu.txt` | Linux x86_64 profile. CI does not run ROCm. |
| macOS MPS | `requirements/macos.txt` | Apple Silicon PyPI wheel. Intel macOS is not given that file. MPS is not CUDA. |

The corpus extraction tests need a local directory of `.fig` files and are not part of CI.
