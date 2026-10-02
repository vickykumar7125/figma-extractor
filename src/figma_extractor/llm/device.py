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
