"""Export exact screen PNGs via Figma's Images API (Approach A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import orjson
from rich.console import Console

from figma_extractor.paths import design_dir
from figma_extractor.remote import FigmaClient
from figma_extractor.util import slug, unique_slug, write_json

console = Console(stderr=True)

# Keep batches small: long frames + many ids hit URL / render limits.
_DEFAULT_BATCH = 20
_EXTENSIONS = {"png": ".png", "jpg": ".jpg", "svg": ".svg", "pdf": ".pdf"}


def build_screenshots(
    out: Path,
    *,
    file_key: str,
    api_key: str,
    format: str = "png",
    scale: float = 1.0,
    batch_size: int = _DEFAULT_BATCH,
) -> dict[str, Any]:
    """
    Render each entry in ``design/screens.json`` and write files under
    ``design/screenshots/``.

    Updates ``screens.json`` in place with ``screenshot`` / ``screenshotError``.
    Writes ``design/screenshots/manifest.json``.
    """
    design = design_dir(out)
    screens_path = design / "screens.json"
    if not screens_path.is_file():
        raise FileNotFoundError(
            f"Missing {screens_path}. Run extract first so screens.json exists."
        )

    screens: list[dict[str, Any]] = orjson.loads(screens_path.read_bytes())
    if not screens:
        summary = {"requested": 0, "rendered": 0, "failed": 0, "format": format, "scale": scale}
        write_json(design / "screenshots" / "manifest.json", {"screens": [], "summary": summary})
        return summary

    fmt = format.lower().strip()
    ext = _EXTENSIONS.get(fmt)
    if ext is None:
        raise ValueError(f"Unsupported screenshot format: {format!r}")

    shot_dir = design / "screenshots"
    shot_dir.mkdir(parents=True, exist_ok=True)

    used_names: set[str] = set()
    plan: list[dict[str, Any]] = []
    for index, screen in enumerate(screens):
        node_id = str(screen.get("id") or "")
        if not node_id:
            continue
        page_slug = slug(str(screen.get("page") or "page"))
        name_slug = slug(str(screen.get("name") or node_id))
        candidate = unique_slug(f"{page_slug}__{name_slug}", used_names)
        relative = f"screenshots/{candidate}{ext}"
        plan.append(
            {
                "index": index,
                "id": node_id,
                "file": relative,
                "path": shot_dir / f"{candidate}{ext}",
            }
        )

    rendered = 0
    failed = 0
    manifest_rows: list[dict[str, Any]] = []

    with FigmaClient(api_key, timeout=180.0) as client:
        with httpx.Client(timeout=180.0, follow_redirects=True) as downloader:
            for start in range(0, len(plan), batch_size):
                batch = plan[start : start + batch_size]
                urls = client.render_nodes(
                    file_key,
                    [item["id"] for item in batch],
                    format=fmt,
                    scale=scale,
                )
                for item in batch:
                    url = urls.get(item["id"])
                    screen = screens[item["index"]]
                    row: dict[str, Any] = {
                        "id": item["id"],
                        "name": screen.get("name"),
                        "page": screen.get("page"),
                        "file": item["file"],
                        "width": screen.get("width"),
                        "height": screen.get("height"),
                    }
                    if not url:
                        failed += 1
                        screen.pop("screenshot", None)
                        screen["screenshotError"] = "Figma returned no render URL"
                        row["ok"] = False
                        row["error"] = screen["screenshotError"]
                        manifest_rows.append(row)
                        continue
                    try:
                        response = downloader.get(url)
                        response.raise_for_status()
                        item["path"].write_bytes(response.content)
                    except (httpx.HTTPError, OSError) as exc:
                        failed += 1
                        screen.pop("screenshot", None)
                        screen["screenshotError"] = str(exc)
                        row["ok"] = False
                        row["error"] = screen["screenshotError"]
                        manifest_rows.append(row)
                        continue

                    rendered += 1
                    screen["screenshot"] = item["file"]
                    screen.pop("screenshotError", None)
                    row["ok"] = True
                    row["bytes"] = item["path"].stat().st_size
                    manifest_rows.append(row)

                console.print(
                    f"Screenshots batch {start // batch_size + 1}: "
                    f"{min(start + batch_size, len(plan))}/{len(plan)}"
                )

    write_json(screens_path, screens)
    summary = {
        "requested": len(plan),
        "rendered": rendered,
        "failed": failed,
        "format": fmt,
        "scale": scale,
        "fileKey": file_key,
    }
    write_json(
        shot_dir / "manifest.json",
        {"screens": manifest_rows, "summary": summary},
    )
    console.print(
        f"[green]Screenshots[/] {rendered}/{len(plan)} rendered "
        f"({failed} failed) → {shot_dir}"
    )
    return summary
