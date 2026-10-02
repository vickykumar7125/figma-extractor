"""Shared constructor kwargs. Provider modules add model-specific fields."""

from __future__ import annotations

from typing import Any

from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.factory import load_class
from figma_extractor.llm.registry import ProviderSpec


def runtime_kwargs(config: LlmConfig, *, include_max_tokens: bool = True) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "temperature": config.temperature,
        **config.policy().client_kwargs(),
    }
    if include_max_tokens and config.max_tokens is not None:
        kwargs["max_tokens"] = config.max_tokens
    return kwargs


def instantiate(
    module: str,
    class_name: str,
    spec: ProviderSpec,
    config: LlmConfig,
    **kwargs: Any,
) -> Any:
    cls = load_class(module, class_name, spec)
    merged = runtime_kwargs(config)
    merged.update(kwargs)
    model_name = config.resolved_model()
    merged.setdefault("model", model_name)
    return cls(**merged)
