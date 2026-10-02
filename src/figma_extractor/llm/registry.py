"""Provider catalog.

Importing this module does not import LangChain or any provider SDK.
"""

from __future__ import annotations

from dataclasses import dataclass

from figma_extractor.llm.capabilities import Capability
from figma_extractor.llm.errors import UnknownProvider

CHAT = frozenset(
    {
        Capability.CHAT,
        Capability.STREAMING,
        Capability.STRUCTURED_OUTPUT,
        Capability.TOOL_CALLING,
        Capability.ASYNC,
        Capability.JSON_MODE,
    }
)


def chat_capabilities(*extra: Capability) -> frozenset[Capability]:
    return CHAT | frozenset(extra)


@dataclass(frozen=True)
class ProviderSpec:
    """One installable chat integration.

    ``credential_env`` lists environment variable names. Any one of them
    satisfies the check. An empty tuple means the provider does not use a key
    (local Ollama, or a local Hugging Face pipeline).
    """

    id: str
    extra: str
    package: str
    module: str
    default_model: str
    capabilities: frozenset[Capability]
    credential_env: tuple[str, ...] = ()
    local: bool = False
    note: str = ""


PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        id="openai",
        extra="openai",
        package="langchain-openai",
        module="figma_extractor.llm.providers.openai",
        default_model="gpt-4.1-mini",
        capabilities=chat_capabilities(Capability.VISION),
        credential_env=("OPENAI_API_KEY",),
    ),
    "anthropic": ProviderSpec(
        id="anthropic",
        extra="anthropic",
        package="langchain-anthropic",
        module="figma_extractor.llm.providers.anthropic",
        default_model="claude-sonnet-4-5",
        capabilities=chat_capabilities(Capability.VISION),
        credential_env=("ANTHROPIC_API_KEY",),
        note="Anthropic API. This is not Anthropic on Vertex AI.",
    ),
    "google": ProviderSpec(
        id="google",
        extra="google",
        package="langchain-google-genai",
        module="figma_extractor.llm.providers.google",
        default_model="gemini-2.5-flash",
        capabilities=chat_capabilities(Capability.VISION),
        credential_env=("GOOGLE_API_KEY",),
        note="Gemini via the Google AI API.",
    ),
    "vertex": ProviderSpec(
        id="vertex",
        extra="vertex",
        package="langchain-google-vertexai",
        module="figma_extractor.llm.providers.vertex",
        default_model="gemini-2.5-flash",
        capabilities=chat_capabilities(Capability.VISION),
        credential_env=("GOOGLE_CLOUD_PROJECT",),
        note="Gemini on Vertex AI. Uses Application Default Credentials.",
    ),
    "anthropic-vertex": ProviderSpec(
        id="anthropic-vertex",
        extra="vertex",
        package="langchain-google-vertexai",
        module="figma_extractor.llm.providers.anthropic_vertex",
        default_model="claude-haiku-4-5@20251001",
        capabilities=chat_capabilities(Capability.VISION),
        credential_env=("GOOGLE_CLOUD_PROJECT",),
        note="Claude on Vertex AI. Separate from the Anthropic API provider.",
    ),
    "ollama": ProviderSpec(
        id="ollama",
        extra="ollama",
        package="langchain-ollama",
        module="figma_extractor.llm.providers.ollama",
        default_model="llama3.2",
        capabilities=chat_capabilities(Capability.VISION, Capability.LOCAL_INFERENCE),
        local=True,
        note="Local Ollama server. Optional OLLAMA_BASE_URL.",
    ),
    "huggingface": ProviderSpec(
        id="huggingface",
        extra="huggingface",
        package="langchain-huggingface",
        module="figma_extractor.llm.providers.huggingface",
        default_model="microsoft/Phi-3-mini-4k-instruct",
        capabilities=frozenset(
            {
                Capability.CHAT,
                Capability.STRUCTURED_OUTPUT,
                Capability.TOOL_CALLING,
                Capability.VISION,
                Capability.ASYNC,
            }
        ),
        credential_env=("HUGGINGFACEHUB_API_TOKEN", "HF_TOKEN"),
        note="Hosted inference by default. Set backend=local for a local pipeline.",
    ),
    "groq": ProviderSpec(
        id="groq",
        extra="groq",
        package="langchain-groq",
        module="figma_extractor.llm.providers.groq",
        default_model="llama-3.3-70b-versatile",
        capabilities=chat_capabilities(Capability.VISION),
        credential_env=("GROQ_API_KEY",),
    ),
    "xai": ProviderSpec(
        id="xai",
        extra="xai",
        package="langchain-xai",
        module="figma_extractor.llm.providers.xai",
        default_model="grok-3",
        capabilities=chat_capabilities(),
        credential_env=("XAI_API_KEY",),
    ),
    "nvidia": ProviderSpec(
        id="nvidia",
        extra="nvidia",
        package="langchain-nvidia-ai-endpoints",
        module="figma_extractor.llm.providers.nvidia",
        default_model="meta/llama-3.1-70b-instruct",
        capabilities=chat_capabilities(Capability.VISION),
        credential_env=("NVIDIA_API_KEY",),
    ),
    "cohere": ProviderSpec(
        id="cohere",
        extra="cohere",
        package="langchain-cohere",
        module="figma_extractor.llm.providers.cohere",
        default_model="command-r-plus",
        capabilities=chat_capabilities(),
        credential_env=("COHERE_API_KEY",),
    ),
    "together": ProviderSpec(
        id="together",
        extra="together",
        package="langchain-together",
        module="figma_extractor.llm.providers.together",
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        capabilities=chat_capabilities(Capability.VISION),
        credential_env=("TOGETHER_API_KEY",),
    ),
    "deepseek": ProviderSpec(
        id="deepseek",
        extra="deepseek",
        package="langchain-deepseek",
        module="figma_extractor.llm.providers.deepseek",
        default_model="deepseek-chat",
        capabilities=chat_capabilities(),
        credential_env=("DEEPSEEK_API_KEY",),
        note="Package verified on PyPI as langchain-deepseek.",
    ),
}


def get_provider(provider_id: str) -> ProviderSpec:
    try:
        return PROVIDERS[provider_id]
    except KeyError as exc:
        known = ", ".join(sorted(PROVIDERS))
        raise UnknownProvider(
            f"Unknown LLM provider '{provider_id}'. Known providers: {known}."
        ) from exc
