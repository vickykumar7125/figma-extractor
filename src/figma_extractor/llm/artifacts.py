"""Disk cache and reproducible prompt/TOON artifacts. Secrets are never written."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from figma_extractor.util import write_json


def digest(value: Any) -> str:
    packed = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(packed.encode("utf-8")).hexdigest()


def cache_key(
    *,
    task: str,
    payload: Any,
    feedback: Any,
    provider: str,
    model: str,
) -> str:
    return digest(
        {
            "task": task,
            "payload": payload,
            "feedback": feedback,
            "provider": provider,
            "model": model,
        }
    )


class DiskCache:
    """JSON files under ``directory/.cache/llm``. One file per request digest."""

    def __init__(self, directory: Path) -> None:
        self.root = Path(directory) / ".cache" / "llm"
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> Any | None:
        path = self.root / f"{key}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def put(self, key: str, value: Any) -> None:
        path = self.root / f"{key}.json"
        path.write_text(json.dumps(value, default=str) + "\n", encoding="utf-8")


def write_prompt_artifact(
    directory: Path,
    *,
    task: str,
    messages: list[dict[str, str]],
    provider: str,
    model: str,
    context_hash: str,
    prompt_hash: str,
    token_estimate: int,
    validation: dict[str, Any] | None = None,
    retries: int = 0,
) -> Path:
    """Store enough metadata to reproduce a request. No credentials."""
    root = Path(directory) / "prompts" / "tasks"
    path = root / f"{task}.json"
    write_json(
        path,
        {
            "task": task,
            "provider": provider,
            "model": model,
            "promptVersion": 1,
            "toonSchemaVersion": 1,
            "contextHash": context_hash,
            "promptHash": prompt_hash,
            "tokenEstimate": token_estimate,
            "retries": retries,
            "validation": validation,
            "messages": messages,
        },
    )
    return path


def update_prompt_validation(directory: Path, reports: list[dict[str, Any]]) -> None:
    """Attach the latest validation outcome to stored prompt task artifacts."""
    root = Path(directory) / "prompts" / "tasks"
    for report in reports:
        if not isinstance(report, dict):
            continue
        task = report.get("task")
        if not isinstance(task, str):
            continue
        path = root / f"{task}.json"
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        payload["validation"] = {
            "ok": bool(report.get("ok")),
            "problems": list(report.get("problems") or []),
        }
        write_json(path, payload)


def write_prompt_manifest(directory: Path, tasks: list[str]) -> Path:
    return write_json(
        Path(directory) / "prompts" / "manifest.json",
        {"version": 1, "tasks": tasks},
    )


def merge_proposals(directory: Path, results: dict[str, Any]) -> dict[str, str]:
    """Write AI proposals beside the Figma catalogs. Source files stay untouched."""
    root = Path(directory)
    written: dict[str, str] = {}
    components = results.get("component_synthesis")
    if isinstance(components, dict) and isinstance(components.get("items"), list):
        path = root / "components" / "proposed.json"
        write_json(
            path,
            {
                "version": 1,
                "origin": "llm_proposed",
                "kind": "proposed",
                "items": components["items"],
            },
        )
        written["components"] = str(path)
    patterns = results.get("pattern_synthesis")
    if isinstance(patterns, dict) and isinstance(patterns.get("items"), list):
        path = root / "patterns" / "proposed.json"
        write_json(
            path,
            {
                "version": 1,
                "origin": "llm_proposed",
                "kind": "proposed",
                "items": patterns["items"],
            },
        )
        written["patterns"] = str(path)
    return written
