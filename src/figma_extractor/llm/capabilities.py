"""Provider capabilities checked before a task is sent to a model."""

from __future__ import annotations

from enum import StrEnum


class Capability(StrEnum):
    CHAT = "chat"
    STREAMING = "streaming"
    STRUCTURED_OUTPUT = "structured_output"
    TOOL_CALLING = "tool_calling"
    VISION = "vision"
    EMBEDDINGS = "embeddings"
    REASONING = "reasoning"
    JSON_MODE = "json_mode"
    ASYNC = "async"
    BATCH = "batch"
    LOCAL_INFERENCE = "local_inference"


# Annotation tasks ask for a JSON object. They do not send images.
TASK_CAPABILITIES: dict[str, frozenset[Capability]] = {
    "semantic_classification": frozenset({Capability.CHAT, Capability.STRUCTURED_OUTPUT}),
    "screen_classification": frozenset({Capability.CHAT, Capability.STRUCTURED_OUTPUT}),
    "component_analysis": frozenset({Capability.CHAT, Capability.STRUCTURED_OUTPUT}),
    "svg_analysis": frozenset({Capability.CHAT, Capability.STRUCTURED_OUTPUT}),
    "reconstruction_hints": frozenset({Capability.CHAT, Capability.STRUCTURED_OUTPUT}),
}


def required_for_tasks(task_names: list[str]) -> frozenset[Capability]:
    required: set[Capability] = set()
    for name in task_names:
        required.update(TASK_CAPABILITIES[name])
    return frozenset(required)
