"""LangGraph annotation workflow.

The graph runs only when LLM mode is enabled. Disabled annotation never
imports this module. The compiled graph does not store clients or files
in its state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from figma_extractor.llm.artifacts import (
    DiskCache,
    cache_key,
    digest,
    merge_proposals,
    update_prompt_validation,
    write_prompt_artifact,
    write_prompt_manifest,
)
from figma_extractor.llm.chat import ChatSession
from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.context import (
    build_raw_task_context,
    fit_context,
    load_json,
    screen_rows,
)
from figma_extractor.llm.prompt_format import render_user
from figma_extractor.llm.errors import MissingLlmRuntime
from figma_extractor.llm.observe import log_event
from figma_extractor.llm.policy import CircuitBreaker, call_with_policy
from figma_extractor.llm.prompt_format import (
    apply_prompt_proposals,
    encode_context,
    prompt_messages,
    proposals_from_result,
)
from figma_extractor.llm.merge import apply_llm_overlays, load_json as merge_load_json, stitch_incremental_annotations
from figma_extractor.llm.patches import canonicalize_response
from figma_extractor.llm.schemas import validate_task_payload
from figma_extractor.toon.optimize import estimate_tokens


def run_annotation_graph(
    directory: Path,
    config: LlmConfig,
    session: ChatSession | None = None,
) -> dict[str, Any]:
    """Execute prepare → optimize_toon → build_prompt → invoke → validate → repair → finalize."""
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
    memory_cache: dict[str, Any] = {}
    disk_cache = DiskCache(directory) if config.cache_results else None
    root = directory
    model_name = config.resolved_model()

    def prepare(state: dict[str, Any]) -> dict[str, Any]:
        screens = load_json(root / "screens.json", [])
        if not isinstance(screens, list):
            screens = []
        task_names = [name for name, enabled in state["tasks"].items() if enabled]
        context_raw = build_raw_task_context(root, task_names) if task_names else {}
        warnings = list(state["warnings"])
        if task_names and not context_raw:
            warnings.append("No LLM task context could be built from this extract.")
        log_event(
            "prepare",
            tasks=",".join(task_names),
            screens=len(screens),
            concurrency=policy.max_concurrency,
        )
        return {
            "screens": screen_rows(screens),
            "context_raw": context_raw,
            "context": {},
            "warnings": warnings,
            "nodes": context_raw.get("semantic_classification", {}).get("nodes", []),
            "assets": asset_rows(root),
        }

    def optimize_toon(state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("context_raw") or {}
        if not raw:
            return {"context": {}, "context_stats": {}}
        context = fit_context(
            raw,
            config.max_context_chars,
            compact=config.toon_compact,
            max_tokens=config.max_context_tokens,
            model=model_name,
        )
        stats: dict[str, Any] = {}
        for task, payload in context.items():
            if not isinstance(payload, dict):
                continue
            user_text = render_user(str(task), payload, [], compact=config.toon_compact)
            stats[str(task)] = {
                "chars": len(user_text),
                "tokens": estimate_tokens(user_text, model=model_name),
                "compact": config.toon_compact,
            }
        log_event(
            "optimize_toon",
            tasks=len(stats),
            chars=sum(item["chars"] for item in stats.values()),
            tokens=sum(item["tokens"] for item in stats.values()),
            node="optimize_toon",
        )
        warnings = list(state["warnings"])
        if context.get("truncated"):
            warnings.append("Task context was truncated to fit the character or token budget.")
        return {"context": context, "context_stats": stats, "warnings": warnings}

    def build_prompt(state: dict[str, Any]) -> dict[str, Any]:
        feedback = state.get("validation_results") or []
        results = state.get("llm_results") or {}
        proposals = proposals_from_result(results.get("prompt_optimization"))
        prompts: dict[str, list[dict[str, str]]] = {}
        for task in state.get("context") or {}:
            payload = state["context"][task]
            messages = prompt_messages(task, payload, feedback, compact=config.toon_compact)
            if task != "prompt_optimization":
                messages = apply_prompt_proposals(task, messages, proposals)
            prompts[task] = messages
        log_event("build_prompt", tasks=len(prompts), node="build_prompt")
        return {"prompts": prompts}

    def invoke(state: dict[str, Any]) -> dict[str, Any]:
        assert session is not None
        attempts = int(state.get("attempts", 0)) + 1
        results: dict[str, Any] = dict(state.get("llm_results") or {})
        errors = list(state.get("errors") or [])
        feedback = state.get("validation_results") or []
        proposals: dict[str, str] = proposals_from_result(results.get("prompt_optimization"))
        failed = {
            item["task"]
            for item in feedback
            if isinstance(item, dict) and not item.get("ok") and item.get("task")
        }
        ordered = list(state["context"])
        if "prompt_optimization" in ordered:
            ordered = ["prompt_optimization", *[name for name in ordered if name != "prompt_optimization"]]
        if attempts > 1 and failed:
            ordered = [name for name in ordered if name in failed]
        built = state.get("prompts") or {}
        for task in ordered:
            payload = state["context"][task]
            messages = built.get(task)
            if not messages:
                messages = prompt_messages(task, payload, feedback, compact=config.toon_compact)
                if task != "prompt_optimization":
                    messages = apply_prompt_proposals(task, messages, proposals)
            task_name = task
            key = cache_key(
                task=task_name,
                payload=payload,
                feedback=feedback,
                provider=config.provider,
                model=model_name,
            )
            started_retry = 0
            cached = memory_cache.get(key)
            if cached is None and disk_cache is not None:
                cached = disk_cache.get(key)
                if cached is not None:
                    memory_cache[key] = cached
            if cached is not None:
                cached = canonicalize_response(task, cached)
                results[task] = cached
                if task == "prompt_optimization":
                    proposals.update(proposals_from_result(cached))
                log_event(
                    "invoke",
                    provider=config.provider,
                    model=model_name,
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
                    model=model_name,
                    task=task,
                    cache_hit=False,
                    failure=type(exc).__name__,
                    retries=started_retry,
                    node="invoke",
                )
                continue
            parsed = canonicalize_response(task, parsed)
            memory_cache[key] = parsed
            if disk_cache is not None:
                disk_cache.put(key, parsed)
            results[task] = parsed
            if task == "prompt_optimization":
                proposals.update(proposals_from_result(parsed))
            if config.write_artifacts:
                write_prompt_artifact(
                    root,
                    task=task,
                    messages=messages,
                    provider=config.provider,
                    model=model_name,
                    context_hash=digest(payload),
                    prompt_hash=digest(messages),
                    token_estimate=estimate_tokens(encode_context({"task": task, "context": payload})),
                    retries=started_retry,
                )
            log_event(
                "invoke",
                provider=config.provider,
                model=model_name,
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
        if config.write_artifacts:
            update_prompt_validation(root, reports)
        return {"validation_results": reports}

    def repair(state: dict[str, Any]) -> dict[str, Any]:
        log_event("repair", attempts=state.get("attempts", 0), node="repair")
        warnings = list(state["warnings"])
        failed = [
            item["task"]
            for item in state.get("validation_results") or []
            if isinstance(item, dict) and not item.get("ok")
        ]
        warnings.append(
            "Model output failed validation and will be requested again for: "
            + ", ".join(failed)
        )
        return {"warnings": warnings}

    def finalize(state: dict[str, Any]) -> dict[str, Any]:
        results = dict(state.get("llm_results") or {})
        validation = list(state.get("validation_results") or [])
        prior = merge_load_json(root / "llm-annotations.json", {})
        if isinstance(prior, dict) and isinstance(prior.get("llmResults"), dict):
            from figma_extractor.llm.merge import merge_llm_results

            results = merge_llm_results(prior["llmResults"], results)
        if not validation and isinstance(prior, dict) and isinstance(prior.get("validation"), list):
            validation = prior["validation"]
        screens, nodes, assets = apply_llm_overlays(
            state["screens"],
            state.get("nodes") or [],
            state.get("assets") or [],
            results,
            validation,
        )
        screens, nodes, results = stitch_incremental_annotations(root, screens, nodes, results)
        proposals = merge_proposals(root, results) if config.write_artifacts else {}
        if config.write_artifacts:
            write_prompt_manifest(root, sorted(state.get("context") or {}))
        final = {
            "llmEnabled": True,
            "provider": config.provider,
            "model": model_name,
            "screens": screens,
            "nodes": nodes,
            "assets": assets,
            "llmResults": results,
            "validation": validation,
            "errors": state.get("errors") or [],
            "warnings": state.get("warnings") or [],
            "metadata": {
                "maxAttempts": config.validation_attempts,
                "attempts": state.get("attempts", 0),
                "streaming": config.streaming,
                "cacheResults": config.cache_results,
                "writeArtifacts": config.write_artifacts,
                "toonCompact": config.toon_compact,
                "contextStats": state.get("context_stats") or {},
                "maxContextTokens": config.max_context_tokens,
                "proposals": proposals,
            },
        }
        log_event("finalize", attempts=final["metadata"]["attempts"], node="finalize")
        return {"final": final}

    def route_after_prepare(state: dict[str, Any]) -> str:
        if state.get("context_raw"):
            return "optimize_toon"
        return "finalize"

    def route_after_optimize(state: dict[str, Any]) -> str:
        if state.get("context"):
            return "build_prompt"
        return "finalize"

    def route_after_build_prompt(state: dict[str, Any]) -> str:
        if state.get("prompts"):
            return "invoke"
        return "finalize"

    def route_after_validate(state: dict[str, Any]) -> str:
        failed = [item for item in state.get("validation_results") or [] if not item.get("ok")]
        if failed and int(state.get("attempts", 0)) < config.validation_attempts:
            return "repair"
        return "finalize"

    graph = StateGraph(GraphState)
    graph.add_node("prepare", prepare)
    graph.add_node("optimize_toon", optimize_toon)
    graph.add_node("build_prompt", build_prompt)
    graph.add_node("invoke", invoke)
    graph.add_node("validate", validate)
    graph.add_node("repair", repair)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "prepare")
    graph.add_conditional_edges(
        "prepare",
        route_after_prepare,
        {"optimize_toon": "optimize_toon", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "optimize_toon",
        route_after_optimize,
        {"build_prompt": "build_prompt", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "build_prompt",
        route_after_build_prompt,
        {"invoke": "invoke", "finalize": "finalize"},
    )
    graph.add_edge("invoke", "validate")
    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {"repair": "repair", "finalize": "finalize"},
    )
    graph.add_edge("repair", "build_prompt")
    graph.add_edge("finalize", END)
    result = graph.compile().invoke(initial_state(directory, config))
    return result["final"]


class GraphState(TypedDict, total=False):
    document: str
    tasks: dict[str, bool]
    screens: list[dict[str, Any]]
    nodes: list[dict[str, Any]]
    assets: list[dict[str, Any]]
    context_raw: dict[str, Any]
    context: dict[str, Any]
    context_stats: dict[str, Any]
    prompts: dict[str, list[dict[str, str]]]
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
        "context_raw": {},
        "context": {},
        "context_stats": {},
        "prompts": {},
        "llm_results": {},
        "validation_results": [],
        "errors": [],
        "warnings": [],
        "metadata": {},
        "attempts": 0,
        "final": {},
    }


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
