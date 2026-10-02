"""Capability flags are provider data, not a live API call."""

from __future__ import annotations

from figma_extractor.llm.capabilities import Capability, required_for_tasks
from figma_extractor.llm.registry import PROVIDERS


def test_annotation_tasks_require_structured_chat() -> None:
    required = required_for_tasks(["screen_classification", "reconstruction_hints"])
    assert required == frozenset({Capability.CHAT, Capability.STRUCTURED_OUTPUT})


def test_every_provider_can_chat() -> None:
    for spec in PROVIDERS.values():
        assert Capability.CHAT in spec.capabilities
        assert Capability.STRUCTURED_OUTPUT in spec.capabilities


def test_anthropic_api_is_not_the_vertex_provider() -> None:
    api = PROVIDERS["anthropic"]
    vertex = PROVIDERS["anthropic-vertex"]
    assert api.package != vertex.module
    assert api.credential_env == ("ANTHROPIC_API_KEY",)
    assert vertex.credential_env == ("GOOGLE_CLOUD_PROJECT",)
    assert api.extra == "anthropic"
    assert vertex.extra == "vertex"
