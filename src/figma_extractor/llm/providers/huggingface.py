"""Hugging Face endpoint or a local transformers pipeline.

``provider_options['backend']`` is ``endpoint`` (default) or ``local``.
Local inference imports transformers and torch when the session is built.
It is not imported for an endpoint session, and never during extract.
"""

from __future__ import annotations

from figma_extractor.llm.chat import LangChainSession
from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.errors import LlmConfigError, MissingProviderPackage
from figma_extractor.llm.factory import load_class
from figma_extractor.llm.registry import ProviderSpec, get_provider


def build(config: LlmConfig) -> LangChainSession:
    spec = get_provider("huggingface")
    backend = config.provider_options.get("backend", "endpoint")
    chat_cls = load_class("langchain_huggingface", "ChatHuggingFace", spec)
    if backend == "local":
        llm = local_pipeline(config, spec)
    elif backend == "endpoint":
        llm = hosted_endpoint(config, spec)
    else:
        raise LlmConfigError("huggingface backend must be 'endpoint' or 'local'.")
    return LangChainSession(chat_cls(llm=llm), config)


def hosted_endpoint(config: LlmConfig, spec: ProviderSpec) -> object:
    endpoint_cls = load_class("langchain_huggingface", "HuggingFaceEndpoint", spec)
    return endpoint_cls(
        repo_id=config.resolved_model(),
        task="text-generation",
        max_new_tokens=config.max_tokens or 512,
        temperature=config.temperature,
    )


def local_pipeline(config: LlmConfig, spec: ProviderSpec) -> object:
    try:
        pipeline_cls = load_class("langchain_huggingface", "HuggingFacePipeline", spec)
    except MissingProviderPackage:
        raise
    try:
        return pipeline_cls.from_model_id(
            model_id=config.resolved_model(),
            task="text-generation",
            pipeline_kwargs={"max_new_tokens": config.max_tokens or 512},
        )
    except ImportError as exc:
        raise MissingProviderPackage(
            "huggingface",
            "transformers (and a torch build from requirements/torch/)",
            "huggingface",
        ) from exc
