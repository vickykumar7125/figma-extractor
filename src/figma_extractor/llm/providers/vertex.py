"""Gemini on Vertex AI via langchain-google-vertexai."""

from __future__ import annotations

import os

from figma_extractor.llm.chat import LangChainSession
from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.providers.common import instantiate
from figma_extractor.llm.registry import get_provider


def build(config: LlmConfig) -> LangChainSession:
    spec = get_provider("vertex")
    location = config.provider_options.get("location") or os.environ.get(
        "GOOGLE_CLOUD_LOCATION", "us-central1"
    )
    model = instantiate(
        "langchain_google_vertexai",
        "ChatVertexAI",
        spec,
        config,
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=location,
    )
    return LangChainSession(model, config)
