"""Claude on Vertex AI. Not the Anthropic API provider."""

from __future__ import annotations

import os

from figma_extractor.llm.chat import LangChainSession
from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.factory import load_class
from figma_extractor.llm.providers.common import runtime_kwargs
from figma_extractor.llm.registry import get_provider


def build(config: LlmConfig) -> LangChainSession:
    spec = get_provider("anthropic-vertex")
    cls = load_class(
        "langchain_google_vertexai.model_garden",
        "ChatAnthropicVertex",
        spec,
    )
    location = config.provider_options.get("location") or os.environ.get(
        "GOOGLE_CLOUD_LOCATION", "us-east5"
    )
    kwargs = runtime_kwargs(config)
    kwargs.update(
        {
            "model_name": config.resolved_model(),
            "project": os.environ.get("GOOGLE_CLOUD_PROJECT"),
            "location": location,
        }
    )
    kwargs.pop("model", None)
    return LangChainSession(cls(**kwargs), config)
