"""Optional LLM annotation layer.

Importing this package does not import LangChain, LangGraph, or torch.
``annotate`` loads those only when ``LlmConfig.enabled`` is true.
"""

from figma_extractor.llm.annotate import annotate
from figma_extractor.llm.config import LlmConfig

__all__ = ["LlmConfig", "annotate"]
