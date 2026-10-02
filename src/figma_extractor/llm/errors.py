"""Errors for the optional LLM layer.

Messages name the provider and the install command. They do not include
credential values.
"""

from __future__ import annotations


class LlmError(RuntimeError):
    """Base error for configuration and provider failures."""


class MissingProviderPackage(LlmError):
    """The selected provider extra is not installed."""

    def __init__(self, provider: str, package: str, extra: str) -> None:
        self.provider = provider
        self.package = package
        self.extra = extra
        super().__init__(
            f"Provider '{provider}' is enabled but {package} is not installed.\n\n"
            "Install:\n"
            f"pip install 'figma-extractor[{extra}]'"
        )


class MissingLlmRuntime(LlmError):
    """LangGraph is required only when LLM mode is turned on."""

    def __init__(self) -> None:
        super().__init__(
            "LLM mode is enabled but langgraph is not installed.\n\n"
            "Install:\n"
            "pip install 'figma-extractor[llm]'"
        )


class MissingCredential(LlmError):
    """A required environment variable is unset. The value is never stored."""


class ProviderCapabilityError(LlmError):
    """The selected provider does not offer a capability the task needs."""


class UnknownProvider(LlmError):
    """The provider id is not in the registry."""


class LlmConfigError(LlmError):
    """Configuration is inconsistent or contains a secret field."""


class ProviderCallError(LlmError):
    """The provider failed after the shared retry policy was exhausted."""
