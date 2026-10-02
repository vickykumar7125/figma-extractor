"""Factory errors stay specific to the selected provider."""

from __future__ import annotations

import importlib.util

import pytest

from figma_extractor.llm.config import LlmConfig, LlmTasks
from figma_extractor.llm.errors import (
    MissingCredential,
    MissingProviderPackage,
    ProviderCapabilityError,
    UnknownProvider,
)
from figma_extractor.llm.factory import build_session, load_class, require_credentials
from figma_extractor.llm.registry import PROVIDERS, get_provider


def enabled(provider: str, **options: str) -> LlmConfig:
    return LlmConfig(
        enabled=True,
        provider=provider,
        tasks=LlmTasks(screen_classification=True),
        provider_options=dict(options),
        max_retries=0,
        backoff_seconds=0,
    )


def test_unknown_provider() -> None:
    with pytest.raises(UnknownProvider, match="ollama"):
        get_provider("missing-provider")


def test_registry_covers_optional_extras() -> None:
    extras = {spec.extra for spec in PROVIDERS.values()}
    assert extras == {
        "openai",
        "anthropic",
        "google",
        "vertex",
        "ollama",
        "huggingface",
        "groq",
        "xai",
        "nvidia",
        "cohere",
        "together",
        "deepseek",
    }


def test_missing_credential_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(MissingCredential, match="OPENAI_API_KEY") as exc:
        require_credentials(get_provider("openai"), enabled("openai"))
    assert "sk-" not in str(exc.value)


def test_ollama_does_not_require_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    require_credentials(get_provider("ollama"), enabled("ollama"))


def test_local_huggingface_skips_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACEHUB_API_TOKEN", raising=False)
    require_credentials(get_provider("huggingface"), enabled("huggingface", backend="local"))


def test_streaming_rejected_for_huggingface() -> None:
    config = enabled("huggingface")
    config.streaming = True
    with pytest.raises(ProviderCapabilityError, match="streaming"):
        from figma_extractor.llm.factory import require_ready

        require_ready(get_provider("huggingface"), config)


def test_missing_package_message(monkeypatch: pytest.MonkeyPatch) -> None:
    if importlib.util.find_spec("langchain_openai") is not None:
        pytest.skip("langchain-openai is installed in this interpreter")
    monkeypatch.setenv("OPENAI_API_KEY", "present-but-not-logged")
    with pytest.raises(MissingProviderPackage, match="figma-extractor\\[openai\\]") as exc:
        build_session(enabled("openai"))
    assert "present-but-not-logged" not in str(exc.value)


def test_load_class_unknown_module() -> None:
    spec = get_provider("openai")
    with pytest.raises(MissingProviderPackage):
        load_class("figma_extractor_missing_provider_sdk", "ChatOpenAI", spec)


def test_importing_one_provider_does_not_import_another() -> None:
    import sys

    import figma_extractor.llm.providers.openai as openai_provider

    assert openai_provider.build
    assert "langchain_openai" not in sys.modules
    assert "langchain_anthropic" not in sys.modules
