"""NVIDIA AI Endpoints via langchain-nvidia-ai-endpoints."""

from __future__ import annotations

from figma_extractor.llm.chat import LangChainSession
from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.providers.common import instantiate
from figma_extractor.llm.registry import get_provider


def build(config: LlmConfig) -> LangChainSession:
    spec = get_provider("nvidia")
    model = instantiate("langchain_nvidia_ai_endpoints", "ChatNVIDIA", spec, config)
    return LangChainSession(model, config)
