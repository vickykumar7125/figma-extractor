"""LLM configuration from a JSON file, the environment, and explicit overrides.

Load order, later wins: defaults, JSON file, environment, then ``overrides``.
API keys are not accepted in files or overrides.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from figma_extractor.llm.errors import LlmConfigError, UnknownProvider
from figma_extractor.llm.huggingface_settings import merge_into_config_data
from figma_extractor.llm.policy import ExecutionPolicy
from figma_extractor.llm.registry import get_provider

TASK_NAMES: tuple[str, ...] = (
    "semantic_classification",
    "screen_classification",
    "component_analysis",
    "svg_analysis",
    "reconstruction_hints",
)

SECRET_FIELDS = frozenset(
    {
        "api_key",
        "apikey",
        "token",
        "secret",
        "password",
        "authorization",
        "credentials",
    }
)


def parse_bool(value: str | bool | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise LlmConfigError(f"Expected a boolean, got {value!r}.")


@dataclass
class LlmTasks:
    semantic_classification: bool = False
    screen_classification: bool = False
    component_analysis: bool = False
    svg_analysis: bool = False
    reconstruction_hints: bool = False

    def enabled_names(self) -> list[str]:
        return [name for name in TASK_NAMES if getattr(self, name)]

    def as_dict(self) -> dict[str, bool]:
        return {name: bool(getattr(self, name)) for name in TASK_NAMES}

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> LlmTasks:
        if not data:
            return cls()
        unknown = set(data) - set(TASK_NAMES)
        if unknown:
            names = ", ".join(sorted(unknown))
            raise LlmConfigError(f"Unknown LLM task names: {names}.")
        values = {name: parse_bool(data.get(name), default=False) for name in TASK_NAMES}
        return cls(**values)


@dataclass
class LlmConfig:
    enabled: bool = False
    provider: str = "openai"
    model: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout: float = 60.0
    max_retries: int = 2
    streaming: bool = False
    max_context_chars: int = 12_000
    max_concurrency: int = 1
    failure_limit: int = 4
    validation_attempts: int = 2
    backoff_seconds: float = 0.5
    tasks: LlmTasks = field(default_factory=LlmTasks)
    provider_options: dict[str, str] = field(default_factory=dict)

    def resolved_model(self) -> str:
        if self.model:
            return self.model
        return get_provider(self.provider).default_model

    def policy(self) -> ExecutionPolicy:
        return ExecutionPolicy(
            timeout=self.timeout,
            max_retries=self.max_retries,
            backoff_seconds=self.backoff_seconds,
            max_concurrency=self.max_concurrency,
            failure_limit=self.failure_limit,
        )

    def check(self) -> None:
        """Raise when enabled configuration cannot run. Disabled config is valid."""
        reject_secret_fields(self.provider_options)
        if not self.enabled:
            return
        try:
            get_provider(self.provider)
        except UnknownProvider as exc:
            raise LlmConfigError(str(exc)) from exc
        if not self.tasks.enabled_names():
            raise LlmConfigError(
                "LLM mode is enabled but no task is selected. "
                "Set one of: " + ", ".join(TASK_NAMES) + "."
            )
        if self.temperature < 0 or self.temperature > 2:
            raise LlmConfigError("LLM_TEMPERATURE must be between 0 and 2.")
        if self.timeout <= 0:
            raise LlmConfigError("LLM_TIMEOUT must be greater than 0.")
        if self.max_retries < 0:
            raise LlmConfigError("LLM_MAX_RETRIES must be zero or greater.")
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise LlmConfigError("LLM_MAX_TOKENS must be greater than 0.")
        if self.max_context_chars < 500:
            raise LlmConfigError("max_context_chars must be at least 500.")
        if self.validation_attempts < 1:
            raise LlmConfigError("validation_attempts must be at least 1.")
        if self.max_concurrency < 1:
            raise LlmConfigError("max_concurrency must be at least 1.")

    @classmethod
    def load(
        cls,
        *,
        path: str | Path | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> LlmConfig:
        data: dict[str, Any] = {}
        if path is not None:
            data.update(read_config_file(Path(path)))
        data.update(environment_config())
        overrides = merge_into_config_data(data, overrides)
        if overrides:
            data.update({key: value for key, value in overrides.items() if value is not None})
        reject_secret_fields(data)
        tasks = task_mapping(data)
        options = data.get("provider_options") or data.get("options") or {}
        if not isinstance(options, dict):
            raise LlmConfigError("provider_options must be an object of strings.")
        cleaned_options = {str(key): str(value) for key, value in options.items()}
        reject_secret_fields(cleaned_options)
        config = cls(
            enabled=parse_bool(data.get("enabled"), default=False),
            provider=str(data.get("provider") or "openai"),
            model=data.get("model") or None,
            temperature=float(data.get("temperature", 0.0)),
            max_tokens=int(data["max_tokens"]) if data.get("max_tokens") not in (None, "") else None,
            timeout=float(data.get("timeout", 60.0)),
            max_retries=int(data.get("max_retries", 2)),
            streaming=parse_bool(data.get("streaming"), default=False),
            max_context_chars=int(data.get("max_context_chars", 12_000)),
            max_concurrency=int(data.get("max_concurrency", 1)),
            failure_limit=int(data.get("failure_limit", 4)),
            validation_attempts=int(data.get("validation_attempts", 2)),
            backoff_seconds=float(data.get("backoff_seconds", 0.5)),
            tasks=LlmTasks.from_mapping(tasks),
            provider_options=cleaned_options,
        )
        config.check()
        return config

    @classmethod
    def from_env(cls) -> LlmConfig:
        return cls.load()


def reject_secret_fields(data: Mapping[str, Any]) -> None:
    found = sorted(key for key in data if key.lower() in SECRET_FIELDS)
    if found:
        names = ", ".join(found)
        raise LlmConfigError(
            f"Do not put {names} in configuration. Set the provider credential "
            "in an environment variable."
        )


def read_config_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LlmConfigError(f"LLM config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LlmConfigError(f"LLM config file is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise LlmConfigError("LLM config file must contain a JSON object.")
    reject_secret_fields(payload)
    nested = payload.get("llm")
    if isinstance(nested, dict):
        reject_secret_fields(nested)
        merged = {**payload, **nested}
        merged.pop("llm", None)
        payload = merged
    return payload


def environment_config() -> dict[str, Any]:
    data: dict[str, Any] = {}
    mapping = {
        "LLM_ENABLED": "enabled",
        "LLM_PROVIDER": "provider",
        "LLM_MODEL": "model",
        "LLM_TEMPERATURE": "temperature",
        "LLM_MAX_TOKENS": "max_tokens",
        "LLM_TIMEOUT": "timeout",
        "LLM_MAX_RETRIES": "max_retries",
        "LLM_STREAMING": "streaming",
    }
    for env_name, field_name in mapping.items():
        if env_name in os.environ and os.environ[env_name] != "":
            data[field_name] = os.environ[env_name]
    task_list = os.environ.get("LLM_TASKS", "")
    tasks: dict[str, bool] = {}
    if task_list.strip():
        for name in task_list.split(","):
            key = name.strip()
            if key:
                tasks[key] = True
    for name in TASK_NAMES:
        env_name = "LLM_TASK_" + name.upper()
        if env_name in os.environ:
            tasks[name] = parse_bool(os.environ[env_name])
    if tasks:
        data["tasks"] = tasks
    return data


def task_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    raw = data.get("tasks")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise LlmConfigError("tasks must be an object.")
    return raw
