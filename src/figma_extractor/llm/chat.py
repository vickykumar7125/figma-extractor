"""LangChain chat adapter. The SDK is imported when a provider module builds it."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from typing import Any, Protocol

from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.schemas import JSON_SCHEMA_HINT


class ChatSession(Protocol):
    def complete_json(self, messages: list[dict[str, str]], *, task: str) -> Any: ...

    def stream_text(self, messages: list[dict[str, str]]) -> Iterator[str]: ...

    async def acomplete_json(self, messages: list[dict[str, str]], *, task: str) -> Any: ...

    async def astream_text(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...


class LangChainSession:
    """Wraps one LangChain chat model. The model object is not stored in graph state."""

    def __init__(self, model: Any, config: LlmConfig) -> None:
        self.model = model
        self.config = config

    def complete_json(self, messages: list[dict[str, str]], *, task: str) -> Any:
        lc_messages = to_langchain_messages(messages)
        structured = getattr(self.model, "with_structured_output", None)
        if structured is not None:
            try:
                schema = task_model(task)
                result = structured(schema).invoke(lc_messages)
                return coerce_payload(result)
            except Exception:
                pass
        instructed = [
            *messages,
            {
                "role": "user",
                "content": "Reply with JSON only, matching " + JSON_SCHEMA_HINT[task],
            },
        ]
        message = self.model.invoke(to_langchain_messages(instructed))
        content = getattr(message, "content", message)
        if not isinstance(content, str):
            content = str(content)
        return json.loads(extract_json(content))

    def stream_text(self, messages: list[dict[str, str]]) -> Iterator[str]:
        if not self.config.streaming:
            payload = self.model.invoke(to_langchain_messages(messages))
            yield text_of(payload)
            return
        for chunk in self.model.stream(to_langchain_messages(messages)):
            yield text_of(chunk)

    async def acomplete_json(self, messages: list[dict[str, str]], *, task: str) -> Any:
        return await asyncio.to_thread(self.complete_json, messages, task=task)

    async def astream_text(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        for chunk in self.stream_text(messages):
            yield chunk


def to_langchain_messages(messages: list[dict[str, str]]) -> list[Any]:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    converted: list[Any] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "assistant":
            converted.append(AIMessage(content=content))
        else:
            converted.append(HumanMessage(content=content))
    return converted


def task_model(task: str) -> type:
    from pydantic import BaseModel, Field

    class Item(BaseModel):
        model_config = {"extra": "allow"}

    class Payload(BaseModel):
        items: list[Item] = Field(default_factory=list)

    Payload.__name__ = task
    return Payload


def coerce_payload(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        return json.loads(extract_json(result))
    return {"items": []}


def text_of(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    return str(content)


def extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text
