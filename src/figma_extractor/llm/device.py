"""Runtime device detection. Torch is imported only when this function runs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceStatus:
    kind: str
    available: bool
    detail: str
    torch_version: str | None = None

    def summary(self) -> str:
        version = self.torch_version or "not installed"
        return f"{self.kind}: {self.detail} (torch {version})"


def detect_device() -> DeviceStatus:
    """Report CPU, CUDA, ROCm, MPS, or XPU without being called from core extract."""
    try:
        import torch
    except ImportError:
        return DeviceStatus(
            kind="unavailable",
            available=False,
            detail=(
                "torch is not installed. Install one hardware profile from "
                "requirements/torch/."
            ),
        )
    version = getattr(torch, "__version__", None)
    hip = getattr(getattr(torch, "version", None), "hip", None)
    cuda = getattr(torch, "cuda", None)
    if hip and cuda is not None and cuda.is_available():
        return DeviceStatus("rocm", True, f"hip {hip}", version)
    if cuda is not None and cuda.is_available():
        name = "cuda"
        try:
            name = str(cuda.get_device_name(0))
        except Exception:
            name = "cuda device"
        return DeviceStatus("cuda", True, name, version)
    mps = getattr(getattr(torch, "backends", None), "mps", None)
    if mps is not None and mps.is_available():
        return DeviceStatus("mps", True, "Apple Metal Performance Shaders", version)
    xpu = getattr(torch, "xpu", None)
    if xpu is not None and bool(getattr(xpu, "is_available", lambda: False)()):
        return DeviceStatus("xpu", True, "Intel XPU", version)
    return DeviceStatus("cpu", True, "CPU", version)


@dataclass(frozen=True)
class ExecutionPlacement:
    """Where a local Hugging Face model will run. Quantization is decided separately."""

    kind: str
    device_map: str | None
    pipeline_device: int | None
    dtype_name: str
    detail: str


def execution_placement(
    status: DeviceStatus,
    *,
    device: str,
    device_map: str,
    dtype: str,
    quantized: bool,
) -> ExecutionPlacement:
    """Pick device, device_map, and dtype from one status object.

    ``device_map='auto'`` is used for CUDA when the caller asked for auto or for
    a quantized load. It is not combined with a forced CPU device.
    """
    requested = device or "auto"
    available = status.kind if status.available else "unavailable"
    if requested == "auto":
        kind = available if available not in {"unavailable"} else "cpu"
    else:
        kind = requested
    if kind not in {"cpu", "cuda", "rocm", "mps", "xpu"}:
        raise ValueError("HF_DEVICE must be auto, cpu, cuda, rocm, mps, or xpu.")
    if requested != "auto" and kind != "cpu" and available != kind:
        raise ValueError(
            f"HF_DEVICE={requested} but the runtime reports {available}. "
            "Install the matching requirements/torch profile or set HF_DEVICE=cpu."
        )
    if device_map not in {"auto", "none", ""}:
        chosen_map: str | None = device_map
    else:
        chosen_map = None
    if kind == "cpu" and (device_map == "auto" or quantized):
        if device_map == "auto":
            chosen_map = None
        if quantized:
            chosen_map = None
    if kind == "cuda" and quantized and chosen_map is None:
        chosen_map = "auto"
    if kind == "cuda" and device_map == "auto" and not quantized:
        chosen_map = "auto"
    pipeline_device: int | None = None
    if chosen_map is None and kind == "cpu":
        pipeline_device = -1
    elif chosen_map is None and kind == "cuda":
        pipeline_device = 0
    dtype_name = resolved_dtype(kind, dtype)
    detail = status.detail if kind == available else kind
    return ExecutionPlacement(kind, chosen_map, pipeline_device, dtype_name, detail)


def cuda_supports_bfloat16() -> bool:
    try:
        import torch
    except ImportError:
        return False
    checker = getattr(getattr(torch, "cuda", None), "is_bf16_supported", None)
    if checker is None:
        return False
    try:
        return bool(checker())
    except Exception:
        return False


def resolved_dtype(kind: str, dtype: str) -> str:
    if dtype == "auto":
        if kind == "cpu":
            return "float32"
        if kind == "cuda" and cuda_supports_bfloat16():
            return "bfloat16"
        return "float16"
    if dtype == "float16" and kind == "cpu":
        raise ValueError(
            "HF_DTYPE=float16 is not selected for CPU. Use HF_DTYPE=auto or HF_DTYPE=float32."
        )
    if dtype == "bfloat16" and kind == "cpu":
        raise ValueError(
            "HF_DTYPE=bfloat16 is not selected for CPU. Use HF_DTYPE=auto or HF_DTYPE=float32."
        )
    return dtype
