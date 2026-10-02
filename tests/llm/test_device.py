"""Device detection must not require torch for the core package."""

from __future__ import annotations

import importlib.util

from figma_extractor.llm import device
from figma_extractor.llm.device import detect_device


def test_detect_device_reports_a_known_kind() -> None:
    status = detect_device()
    if importlib.util.find_spec("torch") is None:
        assert status.kind == "unavailable"
        assert status.available is False
        assert "requirements/" in status.detail
    else:
        assert status.kind in {"cpu", "cuda", "rocm", "mps", "xpu"}
        assert status.torch_version


def test_cuda_auto_dtype_uses_hardware_bfloat16(monkeypatch) -> None:
    monkeypatch.setattr(device, "cuda_supports_bfloat16", lambda: True)
    assert device.resolved_dtype("cuda", "auto") == "bfloat16"
    monkeypatch.setattr(device, "cuda_supports_bfloat16", lambda: False)
    assert device.resolved_dtype("cuda", "auto") == "float16"
