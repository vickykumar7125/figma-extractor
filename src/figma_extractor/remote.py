"""
Figma REST API client and document normalizer.

Maps remote file JSON into the same NDJSON node stream used by local `.fig`
extraction so token / structure / image builders stay shared.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from rich.console import Console

from figma_extractor.util import to_ndjson_line, write_json

console = Console(stderr=True)
FIGMA_API = "https://api.figma.com/v1"
_FILE_KEY_RE = re.compile(r"/(?:design|file|board|slides)/([^/]+)")


def parse_file_key(value: str) -> str:
    """
    Accept a bare file key or a figma.com URL.

    >>> parse_file_key("ABC123")
    'ABC123'
    >>> parse_file_key("https://www.figma.com/design/ABC123/Name")
    'ABC123'
    """
    value = value.strip()
    if not value:
        raise ValueError("Remote Figma file key/URL cannot be empty")
    if "figma.com" not in value:
        return value
    match = _FILE_KEY_RE.search(urlparse(value).path)
    if not match:
        raise ValueError(f"Could not find a Figma file key in URL: {value}")
    return match.group(1)


class FigmaClient:
    """Authenticated client for the Figma REST API."""

    def __init__(self, api_key: str, *, timeout: float = 120.0) -> None:
        if not api_key.strip():
            raise ValueError("A Figma API key is required for remote extraction")
        self._client = httpx.Client(
            base_url=FIGMA_API,
            headers={"X-Figma-Token": api_key.strip()},
            timeout=timeout,
            follow_redirects=True,
        )

    def __enter__(self) -> FigmaClient:
        return self

    def __exit__(self, *args: object) -> None:
        self._client.close()

    def get_file(self, file_key: str) -> dict[str, Any]:
        response = self._client.get(f"/files/{file_key}")
        self._raise(response)
        return response.json()

    def get_images(self, file_key: str) -> dict[str, str]:
        """Fill-image asset map (hash → download URL)."""
        response = self._client.get(f"/files/{file_key}/images")
        self._raise(response)
        return (response.json().get("meta") or {}).get("images") or {}

    @staticmethod
    def _raise(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Figma API returned HTTP {response.status_code}: {response.text[:500]}"
            ) from exc


def normalize_remote_document(payload: dict[str, Any], out_dir: Path) -> int:
    """Write a REST document as ``nodes.ndjson`` + ``document-meta.json``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    components = payload.get("components") or {}
    count = 0
    # (node, parent_id, position, parent_abs_xy)
    stack: list[tuple[dict[str, Any], str | None, int, tuple[float, float] | None]] = [
        (payload["document"], None, 0, None)
    ]

    with (out_dir / "nodes.ndjson").open("w", encoding="utf-8", buffering=8 << 20) as handle:
        while stack:
            node, parent_id, position, parent_abs = stack.pop()
            handle.write(
                to_ndjson_line(
                    _normalize_node(
                        node, parent_id, position, components, parent_abs=parent_abs
                    )
                )
                + "\n"
            )
            count += 1
            bounds = node.get("absoluteBoundingBox") or {}
            abs_xy = (float(bounds.get("x") or 0), float(bounds.get("y") or 0))
            children = node.get("children") or []
            for index in range(len(children) - 1, -1, -1):
                stack.append((children[index], str(node.get("id")), index, abs_xy))

    write_json(
        out_dir / "document-meta.json",
        {
            "name": payload.get("name"),
            "lastModified": payload.get("lastModified"),
            "version": payload.get("version"),
            "source": "figma-rest-api",
            "_counts": {"nodeChanges": count, "blobs": 0},
        },
    )
    console.print(f"[green]Remote document[/] {count:,} nodes → {out_dir}")
    return count


def download_remote_images(image_urls: dict[str, str], destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        for image_ref, url in image_urls.items():
            response = client.get(url)
            response.raise_for_status()
            (destination / image_ref).write_bytes(response.content)
            count += 1
    console.print(f"[green]Remote images[/] {count} → {destination}")
    return count


def _guid(node_id: str) -> dict[str, int]:
    parts = node_id.replace(";", ":").split(":")
    try:
        if len(parts) >= 2:
            return {"sessionID": int(parts[-2]), "localID": int(parts[-1])}
    except ValueError:
        pass
    digest = hashlib.blake2s(node_id.encode(), digest_size=8).digest()
    return {
        "sessionID": int.from_bytes(digest[:4], "little"),
        "localID": int.from_bytes(digest[4:], "little"),
    }


def _paint(paint: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": paint.get("type"),
        "visible": paint.get("visible", True),
        "opacity": paint.get("opacity", 1),
        "blendMode": paint.get("blendMode", "NORMAL"),
    }
    if paint.get("color"):
        # Keep colour-channel alpha separate from paint opacity so
        # to_css_color(color, paint.opacity) does not double-multiply.
        result["color"] = dict(paint["color"])
    if paint.get("imageRef"):
        result["image"] = {"hash": paint["imageRef"]}
        result["imageScaleMode"] = paint.get("scaleMode")
    if paint.get("gradientStops"):
        result["stops"] = [
            {"position": stop.get("position"), "color": stop.get("color")}
            for stop in paint["gradientStops"]
        ]
    return result


def _normalize_node(
    node: dict[str, Any],
    parent_id: str | None,
    position: int,
    components: dict[str, Any],
    *,
    parent_abs: tuple[float, float] | None = None,
) -> dict[str, Any]:
    node_id = str(node.get("id", "0:0"))
    node_type = node.get("type")
    normalized_type = {
        "COMPONENT": "SYMBOL",
        "COMPONENT_SET": "FRAME",
        "RECTANGLE": "ROUNDED_RECTANGLE",
    }.get(node_type, node_type)
    bounds = node.get("absoluteBoundingBox") or node.get("size") or {}
    style = node.get("style") or {}
    component_meta = components.get(node_id) or {}
    abs_x = float(bounds.get("x") or 0)
    abs_y = float(bounds.get("y") or 0)
    if parent_abs is not None:
        local_x = abs_x - parent_abs[0]
        local_y = abs_y - parent_abs[1]
    else:
        local_x = 0.0
        local_y = 0.0

    result: dict[str, Any] = {
        "guid": _guid(node_id),
        "phase": "CREATED",
        "type": normalized_type,
        "name": node.get("name") or "",
        "visible": node.get("visible", True),
        "opacity": node.get("opacity", 1),
        "size": {"x": bounds.get("width", 0), "y": bounds.get("height", 0)},
        "transform": {
            "m00": 1,
            "m01": 0,
            "m02": local_x,
            "m10": 0,
            "m11": 1,
            "m12": local_y,
        },
    }
    if parent_id:
        result["parentIndex"] = {"guid": _guid(parent_id), "position": f"{position:08d}"}
    if node_type == "COMPONENT_SET":
        result["isStateGroup"] = True
    if node_type == "COMPONENT":
        result["componentKey"] = node.get("key") or component_meta.get("key")
    if node.get("layoutMode") in ("HORIZONTAL", "VERTICAL"):
        result["stackMode"] = node["layoutMode"]
    if node.get("itemSpacing") is not None:
        result["stackSpacing"] = node["itemSpacing"]
    for source, target in (
        ("paddingTop", "stackVerticalPadding"),
        ("paddingLeft", "stackHorizontalPadding"),
        ("paddingBottom", "stackPaddingBottom"),
        ("paddingRight", "stackPaddingRight"),
    ):
        if node.get(source) is not None:
            result[target] = node[source]
    if node.get("cornerRadius") is not None:
        result["cornerRadius"] = node["cornerRadius"]
    if node.get("fills"):
        result["fillPaints"] = [_paint(p) for p in node["fills"] if p.get("type")]
    if node.get("strokes"):
        result["strokePaints"] = [_paint(p) for p in node["strokes"] if p.get("type")]
    if node.get("effects"):
        result["effects"] = node["effects"]
    if node.get("strokeWeight") is not None:
        result["strokeWeight"] = node["strokeWeight"]
    if node_type == "TEXT":
        result.update(
            {
                "textData": {"characters": node.get("characters", "")},
                "fontName": {
                    "family": style.get("fontFamily"),
                    "style": style.get("fontPostScriptName") or "",
                    "postscript": style.get("fontPostScriptName") or "",
                },
                "fontSize": style.get("fontSize"),
                "lineHeight": {"value": style.get("lineHeightPx", 0), "units": "PIXELS"},
                "letterSpacing": {"value": style.get("letterSpacing", 0), "units": "PIXELS"},
                "derivedTextData": {
                    "fontMetaData": [
                        {
                            "fontWeight": style.get("fontWeight"),
                            "fontStyle": "ITALIC" if style.get("italic") else "NORMAL",
                        }
                    ]
                },
            }
        )
    return result
