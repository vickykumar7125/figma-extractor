"""Local models served by Ollama (langchain-ollama)."""

from __future__ import annotations

import os

from figma_extractor.llm.chat import LangChainSession
from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.providers.common import instantiate
from figma_extractor.llm.registry import get_provider


def build(config: LlmConfig) -> LangChainSession:
    spec = get_provider("ollama")
    base_url = config.provider_options.get("base_url") or os.environ.get("OLLAMA_BASE_URL")
    extra = {"base_url": base_url} if base_url else {}
    model = instantiate("langchain_ollama", "ChatOllama", spec, config, **extra)
    return LangChainSession(model, config)
