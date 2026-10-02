"""Cohere chat via langchain-cohere."""

from __future__ import annotations

from figma_extractor.llm.chat import LangChainSession
from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.providers.common import instantiate
from figma_extractor.llm.registry import get_provider


def build(config: LlmConfig) -> LangChainSession:
    spec = get_provider("cohere")
    model = instantiate("langchain_cohere", "ChatCohere", spec, config)
    return LangChainSession(model, config)
