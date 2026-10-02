"""Timeouts, retries, and the circuit breaker shared by every provider."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from figma_extractor.llm.errors import ProviderCallError

T = TypeVar("T")

SECRET_PATTERN = re.compile(
    r"(?i)\b(sk-|key-|bearer\s+|api[_-]?key['\"]?\s*[:=]\s*)([A-Za-z0-9_\-]{6,})"
)


def redact(text: str) -> str:
    """Mask credential-like fragments before they reach logs or errors."""
    return SECRET_PATTERN.sub(r"\1***", text)


@dataclass(frozen=True)
class ExecutionPolicy:
    timeout: float = 60.0
    max_retries: int = 2
    backoff_seconds: float = 0.5
    max_concurrency: int = 1
    failure_limit: int = 4

    def client_kwargs(self) -> dict[str, float | int]:
        """Kwargs applied once, inside the provider factory, not in graph nodes."""
        return {
            "timeout": self.timeout,
            "max_retries": 0,
        }


class CircuitBreaker:
    """Stops calling a provider after consecutive failures in one run."""

    def __init__(self, failure_limit: int) -> None:
        self.failure_limit = failure_limit
        self.failures = 0

    @property
    def open(self) -> bool:
        return self.failures >= self.failure_limit

    def before(self) -> None:
        if self.open:
            raise ProviderCallError(
                f"Stopped calling the provider after {self.failures} consecutive failures."
            )

    def success(self) -> None:
        self.failures = 0

    def failure(self) -> None:
        self.failures += 1


def call_with_policy(
    operation: Callable[[], T],
    policy: ExecutionPolicy,
    breaker: CircuitBreaker,
) -> tuple[T, int]:
    """Run ``operation`` with shared backoff. Returns the value and retry count."""
    last_error: Exception | None = None
    for attempt in range(policy.max_retries + 1):
        breaker.before()
        try:
            value = operation()
        except ProviderCallError:
            raise
        except Exception as exc:
            breaker.failure()
            last_error = exc
            if attempt >= policy.max_retries or breaker.open:
                break
            delay = min(policy.backoff_seconds * (2**attempt), policy.timeout)
            if delay > 0:
                time.sleep(delay)
            continue
        breaker.success()
        return value, attempt
    detail = redact(str(last_error))[:300] if last_error else "unknown error"
    name = type(last_error).__name__ if last_error else "Error"
    raise ProviderCallError(f"{name}: {detail}") from last_error
