"""Local Hugging Face Transformers, with optional hosted inference.

``HF_BACKEND=local`` is the default. It loads ``HuggingFacePipeline`` from a
directory and wraps it in ``ChatHuggingFace``. ``HF_BACKEND=remote`` (also
accepted as ``endpoint``) uses ``HuggingFaceEndpoint`` and a Hub token.

Extract never imports this module.
"""

from __future__ import annotations

from typing import Any

from figma_extractor.llm.chat import LangChainSession
from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.errors import MissingProviderPackage
from figma_extractor.llm.factory import load_class
from figma_extractor.llm.huggingface_local import load_pipeline, sampling_kwargs, settings_for
from figma_extractor.llm.huggingface_settings import HuggingFaceSettings
from figma_extractor.llm.registry import ProviderSpec, get_provider


def build(config: LlmConfig) -> LangChainSession:
    """One settings object, then either a local pipeline or a hosted endpoint."""
    spec = get_provider("huggingface")
    settings = settings_for(config)
    chat_cls = load_class("langchain_huggingface", "ChatHuggingFace", spec)
    if settings.backend == "local":
        pipeline_cls = load_class("langchain_huggingface", "HuggingFacePipeline", spec)
        model = load_pipeline(config, pipeline_cls, settings=settings)
        session_cls = local_chat_class(chat_cls)
    else:
        model = hosted_endpoint(config, settings, spec)
        session_cls = chat_cls
    return LangChainSession(session_cls(llm=model), config)


def render_local_prompt(tokenizer: Any, messages: list[dict[str, str]]) -> str:
    """Render a chat prompt without a reasoning preamble.

    Qwen3-style templates spend the generation budget inside ``<think>`` unless
    ``enable_thinking`` is false. Templates that ignore the flag stay unchanged.
    """
    try:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    except Exception:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )


_LOCAL_CHATS: dict[type, type] = {}


def local_chat_class(base: type) -> type:
    """Return one chat subclass per base class, so repeated builds reuse it."""
    cached = _LOCAL_CHATS.get(base)
    if cached is not None:
        return cached

    class LocalChat(base):
        def _to_chat_prompt(self, messages: list) -> str:
            if not messages:
                raise ValueError("At least one HumanMessage must be provided!")
            rendered = render_local_prompt(
                self.tokenizer,
                [self._to_chatml_format(message) for message in messages],
            )
            return rendered

    LocalChat.__name__ = "LocalChatHuggingFace"
    _LOCAL_CHATS[base] = LocalChat
    return LocalChat


def hosted_endpoint(config: LlmConfig, settings: HuggingFaceSettings, spec: ProviderSpec) -> object:
    endpoint_cls = load_class("langchain_huggingface", "HuggingFaceEndpoint", spec)
    kwargs = {
        "repo_id": config.resolved_model(),
        "task": settings.task,
        **sampling_kwargs(config, settings),
    }
    try:
        return endpoint_cls(**kwargs)
    except ImportError as exc:
        raise MissingProviderPackage("huggingface", "langchain-huggingface", "huggingface") from exc
