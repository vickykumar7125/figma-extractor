"""Build one chat session. Only the selected provider module is imported."""

from __future__ import annotations

import importlib
import os

from figma_extractor.llm.capabilities import Capability, required_for_tasks
from figma_extractor.llm.chat import ChatSession
from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.errors import MissingCredential, MissingProviderPackage, ProviderCapabilityError
from figma_extractor.llm.registry import ProviderSpec, get_provider

ALLOWED_OPTIONS: dict[str, frozenset[str]] = {
    "ollama": frozenset({"base_url"}),
    "huggingface": frozenset({"backend"}),
    "vertex": frozenset({"location"}),
    "anthropic-vertex": frozenset({"location"}),
}


def build_session(config: LlmConfig) -> ChatSession:
    config.check()
    spec = get_provider(config.provider)
    require_credentials(spec, config)
    require_ready(spec, config)
    reject_unknown_options(spec, config)
    module = importlib.import_module(spec.module)
    return module.build(config)


def require_ready(spec: ProviderSpec, config: LlmConfig) -> None:
    have = set(spec.capabilities)
    if spec.id == "huggingface" and config.provider_options.get("backend") == "local":
        have.add(Capability.LOCAL_INFERENCE)
    if spec.id == "ollama":
        have.add(Capability.LOCAL_INFERENCE)
    required = set(required_for_tasks(config.tasks.enabled_names()))
    if config.streaming:
        required.add(Capability.STREAMING)
    missing = required - have
    if missing:
        names = ", ".join(sorted(item.value for item in missing))
        raise ProviderCapabilityError(
            f"Provider '{spec.id}' does not provide {names}, which this run requires."
        )


def require_credentials(spec: ProviderSpec, config: LlmConfig) -> None:
    if spec.id == "huggingface" and config.provider_options.get("backend") == "local":
        return
    if not spec.credential_env:
        return
    if any(os.environ.get(name) for name in spec.credential_env):
        return
    names = " or ".join(spec.credential_env)
    extra = ""
    if spec.id in {"vertex", "anthropic-vertex"}:
        extra = (
            " Vertex also expects Application Default Credentials "
            "(GOOGLE_APPLICATION_CREDENTIALS or gcloud auth)."
        )
    raise MissingCredential(
        f"Provider '{spec.id}' requires {names} to be set.{extra} "
        "The value is read from the environment and is not stored in config."
    )


def reject_unknown_options(spec: ProviderSpec, config: LlmConfig) -> None:
    allowed = ALLOWED_OPTIONS.get(spec.id, frozenset())
    unknown = sorted(set(config.provider_options) - allowed)
    if unknown:
        names = ", ".join(unknown)
        raise ProviderCapabilityError(
            f"Provider '{spec.id}' does not accept options: {names}."
        )


def load_class(module: str, class_name: str, spec: ProviderSpec) -> type:
    try:
        imported = importlib.import_module(module)
    except ImportError as exc:
        raise MissingProviderPackage(spec.id, spec.package, spec.extra) from exc
    try:
        return getattr(imported, class_name)
    except AttributeError as exc:
        raise MissingProviderPackage(spec.id, spec.package, spec.extra) from exc
