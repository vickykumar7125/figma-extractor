"""LangGraph annotation workflow.

The graph runs only when LLM mode is enabled. Disabled annotation never
imports this module. The compiled graph does not store clients or files
in its state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from figma_extractor.llm.chat import ChatSession
from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.context import build_task_context, load_json, screen_rows
from figma_extractor.llm.errors import MissingLlmRuntime
from figma_extractor.llm.observe import log_event
from figma_extractor.llm.policy import CircuitBreaker, call_with_policy
from figma_extractor.llm.schemas import JSON_SCHEMA_HINT, validate_task_payload


def run_annotation_graph(
    directory: Path,
    config: LlmConfig,
    session: ChatSession | None = None,
) -> dict[str, Any]:
    """Execute prepare → invoke → validate → optional repair → finalize."""
    config.check()
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise MissingLlmRuntime() from exc

    if session is None:
        from figma_extractor.llm.factory import build_session

        session = build_session(config)

    policy = config.policy()
    breaker = CircuitBreaker(policy.failure_limit)
    cache: dict[str, Any] = {}
    root = directory

    def prepare(state: dict[str, Any]) -> dict[str, Any]:
        screens = load_json(root / "screens.json", [])
        if not isinstance(screens, list):
            screens = []
        task_names = [name for name, enabled in state["tasks"].items() if enabled]
        context = build_task_context(root, task_names, config.max_context_chars) if task_names else {}
        warnings = list(state["warnings"])
        if not context:
            warnings.append("No LLM tasks were selected, so the model was not called.")
        log_event(
            "prepare",
            tasks=",".join(task_names),
            screens=len(screens),
            concurrency=policy.max_concurrency,
        )
        return {
            "screens": screen_rows(screens),
            "context": context,
            "warnings": warnings,
            "nodes": context.get("semantic_classification", {}).get("nodes", []),
            "assets": asset_rows(root),
        }

    def invoke(state: dict[str, Any]) -> dict[str, Any]:
        assert session is not None
        attempts = int(state.get("attempts", 0)) + 1
        results: dict[str, Any] = {}
        errors = list(state.get("errors") or [])
        feedback = state.get("validation_results") or []
        for task, payload in state["context"].items():
            messages = prompt_messages(task, payload, feedback)
            task_name = task
            cache_key = json.dumps(
                {"task": task_name, "payload": payload, "feedback": feedback},
                default=str,
            )
            started_retry = 0
            if cache_key in cache:
                results[task] = cache[cache_key]
                log_event(
                    "invoke",
                    provider=config.provider,
                    model=config.resolved_model(),
                    task=task,
                    cache_hit=True,
                    retries=0,
                    node="invoke",
                )
                continue
            try:
                parsed, started_retry = call_with_policy(
                    lambda messages=messages, task_name=task_name: session.complete_json(
                        messages, task=task_name
                    ),
                    policy,
                    breaker,
                )
            except Exception as exc:
                errors.append(f"{task}: {exc}")
                log_event(
                    "invoke",
                    provider=config.provider,
                    model=config.resolved_model(),
                    task=task,
                    cache_hit=False,
                    failure=type(exc).__name__,
                    retries=started_retry,
                    node="invoke",
                )
                continue
            cache[cache_key] = parsed
            results[task] = parsed
            log_event(
                "invoke",
                provider=config.provider,
                model=config.resolved_model(),
                task=task,
                cache_hit=False,
                retries=started_retry,
                node="invoke",
            )
        return {"llm_results": results, "errors": errors, "attempts": attempts}

    def validate(state: dict[str, Any]) -> dict[str, Any]:
        reports: list[dict[str, Any]] = []
        for task in state["context"]:
            if task not in state["llm_results"]:
                reports.append({"task": task, "ok": False, "problems": ["no model result"]})
                continue
            problems = validate_task_payload(task, state["llm_results"][task])
            reports.append({"task": task, "ok": not problems, "problems": problems})
        log_event(
            "validate",
            ok=sum(1 for item in reports if item["ok"]),
            failed=sum(1 for item in reports if not item["ok"]),
            node="validate",
        )
        return {"validation_results": reports}

    def repair(state: dict[str, Any]) -> dict[str, Any]:
        log_event("repair", attempts=state.get("attempts", 0), node="repair")
        warnings = list(state["warnings"])
        warnings.append("Model output failed validation and will be requested again.")
        return {"warnings": warnings}

    def finalize(state: dict[str, Any]) -> dict[str, Any]:
        final = {
            "llmEnabled": True,
            "provider": config.provider,
            "model": config.resolved_model(),
            "screens": state["screens"],
            "nodes": state.get("nodes") or [],
            "assets": state.get("assets") or [],
            "llmResults": state.get("llm_results") or {},
            "validation": state.get("validation_results") or [],
            "errors": state.get("errors") or [],
            "warnings": state.get("warnings") or [],
            "metadata": {
                "maxAttempts": config.validation_attempts,
                "attempts": state.get("attempts", 0),
                "streaming": config.streaming,
            },
        }
        log_event("finalize", attempts=final["metadata"]["attempts"], node="finalize")
        return {"final": final}

    def route_after_prepare(state: dict[str, Any]) -> str:
        if state.get("context"):
            return "invoke"
        return "finalize"

    def route_after_validate(state: dict[str, Any]) -> str:
        failed = [item for item in state.get("validation_results") or [] if not item.get("ok")]
        if failed and int(state.get("attempts", 0)) < config.validation_attempts:
            return "repair"
        return "finalize"

    graph = StateGraph(GraphState)
    graph.add_node("prepare", prepare)
    graph.add_node("invoke", invoke)
    graph.add_node("validate", validate)
    graph.add_node("repair", repair)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "prepare")
    graph.add_conditional_edges(
        "prepare",
        route_after_prepare,
        {"invoke": "invoke", "finalize": "finalize"},
    )
    graph.add_edge("invoke", "validate")
    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {"repair": "repair", "finalize": "finalize"},
    )
    graph.add_edge("repair", "invoke")
    graph.add_edge("finalize", END)
    result = graph.compile().invoke(initial_state(directory, config))
    return result["final"]


class GraphState(TypedDict, total=False):
    document: str
    tasks: dict[str, bool]
    screens: list[dict[str, Any]]
    nodes: list[dict[str, Any]]
    assets: list[dict[str, Any]]
    context: dict[str, Any]
    llm_results: dict[str, Any]
    validation_results: list[dict[str, Any]]
    errors: list[str]
    warnings: list[str]
    metadata: dict[str, Any]
    attempts: int
    final: dict[str, Any]


def initial_state(directory: Path, config: LlmConfig) -> GraphState:
    return {
        "document": str(directory),
        "tasks": config.tasks.as_dict(),
        "screens": [],
        "nodes": [],
        "assets": [],
        "context": {},
        "llm_results": {},
        "validation_results": [],
        "errors": [],
        "warnings": [],
        "metadata": {},
        "attempts": 0,
        "final": {},
    }


def prompt_messages(
    task: str,
    payload: dict[str, Any],
    feedback: list[dict[str, Any]],
) -> list[dict[str, str]]:
    problems = [
        item["problems"]
        for item in feedback
        if item.get("task") == task and not item.get("ok")
    ]
    correction = ""
    if problems:
        correction = " Previous output was invalid: " + json.dumps(problems)
    return [
        {
            "role": "system",
            "content": (
                "You annotate a Figma extract that was already decoded deterministically. "
                "Do not invent colors, spacing, typography, or copy. "
                "Use only the JSON context. Mark guesses as inferred. "
                "Reconstruction hints must use kind \"recommended\". "
                "Reply with one JSON object and no prose: " + JSON_SCHEMA_HINT[task]
            ),
        },
        {
            "role": "user",
            "content": json.dumps({"task": task, "context": payload}) + correction,
        },
    ]


def asset_rows(directory: Path) -> list[dict[str, Any]]:
    manifest = load_json(directory / "assets" / "manifest.json", {})
    images = manifest.get("images") if isinstance(manifest, dict) else None
    if not isinstance(images, list):
        return []
    rows = []
    for image in images[:20]:
        if isinstance(image, dict):
            rows.append(
                {
                    "hash": image.get("hash"),
                    "file": image.get("file"),
                    "mime": image.get("mime"),
                }
            )
    return rows
