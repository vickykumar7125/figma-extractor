"""Configuration loading, secret rejection, and override order."""

from __future__ import annotations

import json

import pytest

from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.errors import LlmConfigError


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    config = LlmConfig.from_env()
    assert config.enabled is False
    assert config.tasks.enabled_names() == []


def test_env_then_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_TASKS", "screen_classification")
    config = LlmConfig.load(overrides={"temperature": 0.2, "model": "llama3.2"})
    assert config.enabled is True
    assert config.provider == "ollama"
    assert config.model == "llama3.2"
    assert config.temperature == 0.2
    assert config.tasks.screen_classification is True


def test_file_cannot_hold_a_key(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    path = tmp_path / "llm.json"
    path.write_text(json.dumps({"api_key": "should-not-be-here"}), encoding="utf-8")
    with pytest.raises(LlmConfigError, match="environment variable"):
        LlmConfig.load(path=path)


def test_enabled_requires_a_task(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    with pytest.raises(LlmConfigError, match="no task"):
        LlmConfig.from_env()


def test_max_context_tokens_must_be_large_enough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_TASKS", "screen_classification")
    with pytest.raises(LlmConfigError, match="max_context_tokens"):
        LlmConfig.load(overrides={"max_context_tokens": 10})


def test_unknown_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "not-a-provider")
    monkeypatch.setenv("LLM_TASKS", "screen_classification")
    with pytest.raises(LlmConfigError):
        LlmConfig.from_env()
