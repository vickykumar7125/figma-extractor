"""Local Hugging Face Transformers, with optional hosted inference.

``HF_BACKEND=local`` is the default. It loads ``HuggingFacePipeline`` from a
directory and wraps it in ``ChatHuggingFace``. ``HF_BACKEND=remote`` (also
accepted as ``endpoint``) uses ``HuggingFaceEndpoint`` and a Hub token.

Extract never imports this module.
"""

from __future__ import annotations

from figma_extractor.llm.chat import LangChainSession
from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.errors import MissingProviderPackage
from figma_extractor.llm.factory import load_class
from figma_extractor.llm.huggingface_local import load_pipeline, settings_for
from figma_extractor.llm.huggingface_settings import HuggingFaceSettings
from figma_extractor.llm.registry import ProviderSpec, get_provider


def build(config: LlmConfig) -> LangChainSession:
    spec = get_provider("huggingface")
    settings = settings_for(config)
    chat_cls = load_class("langchain_huggingface", "ChatHuggingFace", spec)
    if settings.backend == "local":
        pipeline_cls = load_class("langchain_huggingface", "HuggingFacePipeline", spec)
        llm = load_pipeline(config, pipeline_cls)
    else:
        llm = hosted_endpoint(config, settings, spec)
    return LangChainSession(chat_cls(llm=llm), config)


def hosted_endpoint(config: LlmConfig, settings: HuggingFaceSettings, spec: ProviderSpec) -> object:
    endpoint_cls = load_class("langchain_huggingface", "HuggingFaceEndpoint", spec)
    kwargs = {
        "repo_id": config.resolved_model(),
        "task": settings.task,
        "max_new_tokens": settings.max_new_tokens or config.max_tokens or 512,
        "temperature": config.temperature,
        "do_sample": bool(settings.do_sample),
        "repetition_penalty": settings.repetition_penalty,
    }
    try:
        return endpoint_cls(**kwargs)
    except ImportError as exc:
        raise MissingProviderPackage("huggingface", "langchain-huggingface", "huggingface") from exc
