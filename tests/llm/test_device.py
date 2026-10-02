"""Device detection must not require torch for the core package."""

from __future__ import annotations

import importlib.util

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
