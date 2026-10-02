"""Anthropic API chat via langchain-anthropic.

This is the direct Anthropic API. Claude on Vertex AI is ``anthropic-vertex``.
"""

from __future__ import annotations

from figma_extractor.llm.chat import LangChainSession
from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.providers.common import instantiate
from figma_extractor.llm.registry import get_provider


def build(config: LlmConfig) -> LangChainSession:
    spec = get_provider("anthropic")
    model = instantiate("langchain_anthropic", "ChatAnthropic", spec, config)
    return LangChainSession(model, config)
