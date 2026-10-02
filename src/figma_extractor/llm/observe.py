"""Structured logs for provider calls. Prompt text and secrets are dropped."""

from __future__ import annotations

import logging

from figma_extractor.llm.policy import redact

logger = logging.getLogger("figma_extractor.llm")

DROPPED_FIELDS = frozenset(
    {
        "prompt",
        "messages",
        "content",
        "api_key",
        "apikey",
        "token",
        "secret",
        "authorization",
        "password",
    }
)


def log_event(event: str, **fields: object) -> None:
    parts = [f"event={event}"]
    for key in sorted(fields):
        if key.lower() in DROPPED_FIELDS:
            continue
        value = redact(str(fields[key]))
        parts.append(f"{key}={value}")
    logger.info(" ".join(parts))
