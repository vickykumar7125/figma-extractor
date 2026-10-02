"""Reference catalog over a finished extract.

Screens, components, and assets stay as ids. This module does not copy
trees, tokens, or image bytes, and it does not import an LLM.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hashlib
import orjson

from figma_extractor.toon import encode
from figma_extractor.util import write_json

TOON_OPTIONS = {"delimiter": ",", "indent": 2, "lengthMarker": "#"}


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return orjson.loads(path.read_bytes())


def build_catalog(directory: Path) -> dict[str, Any]:
    """Build a reference index from files extract already wrote."""
    root = Path(directory)
    screens = _as_list(load_json(root / "screens.json", []))
    components = _as_list(load_json(root / "components.json", []))
    sets = _as_list(load_json(root / "component-sets.json", []))
    images = _image_rows(load_json(root / "assets" / "manifest.json", []))
    screen_rows = [_screen_ref(row) for row in screens if isinstance(row, dict)]
    asset_rows = [_asset_ref(row) for row in images if isinstance(row, dict)]
    component_ids = {
        str(row.get("id"))
        for row in components
        if isinstance(row, dict) and row.get("id") is not None
    }
    attach_screen_asset_refs(root, screen_rows, asset_rows)
    attach_screen_component_refs(root, screen_rows, component_ids)
    return {
        "version": 1,
        "screens": screen_rows,
        "components": [_component_ref(row) for row in components if isinstance(row, dict)],
        "componentSets": [_set_ref(row) for row in sets if isinstance(row, dict)],
        "assets": asset_rows,
        "diagnostics": {
            "assetScreenRefs": (
                "Image usage is stored as node ids on each asset. "
                "Screens list those asset ids under assetRefs."
            ),
            "componentScreenRefs": (
                "Component instances in a screen tree expose instanceOf. "
                "Screens list matching component ids under componentRefs."
            ),
        },
    }


def publish_transport(directory: Path) -> dict[str, str]:
    """Write reference files beside the extract. Existing JSON files stay."""
    root = Path(directory)
    from figma_extractor.extract.svg import write_vector_svgs
    from figma_extractor.extract.vectors import publish_vector_assets

    vectors = write_vector_svgs(root)
    shared = publish_vector_assets(root)
    catalog = build_catalog(root)
    catalog["assets"].extend(vectors)
    for row in shared:
        catalog["assets"].append(
            {
                "assetId": row.get("id"),
                "type": "svg",
                "format": "image/svg+xml",
                "localPath": row.get("localPath"),
                "kind": "derived",
                "source": "vector-dedup",
                "usageCount": row.get("usageCount"),
            }
        )
    attach_vector_screen_refs(catalog["screens"], vectors)
    catalog["screenHashes"] = screen_hashes(root)
    write_json(root / "catalog" / "index.json", catalog)
    write_json(root / "catalog" / "screen-hashes.json", catalog["screenHashes"])
    write_reference_layout(root, catalog)
    write_diagnostics(root, catalog, vectors)
    toon_dir = root / "toon"
    toon_dir.mkdir(parents=True, exist_ok=True)
    written = {"catalog": str(root / "catalog" / "index.json")}
    if shared:
        written["vectors"] = str(root / "assets" / "vectors.json")
    token_rows = build_token_toon_rows(root)
    for name, rows in (
        ("screens", catalog["screens"]),
        ("components", catalog["components"]),
        ("assets", catalog["assets"]),
        ("tokens", token_rows),
    ):
        path = toon_dir / f"{name}.toon"
        path.write_text(encode(rows, TOON_OPTIONS) + "\n", encoding="utf-8")
        written[name] = str(path)
    return written


def build_token_toon_rows(directory: Path, *, limit: int = 600) -> list[dict[str, Any]]:
    """Flatten token JSON into uniform rows for ``toon/tokens.toon``."""
    root = Path(directory)
    rows: list[dict[str, Any]] = []
    flat = load_json(root / "tokens" / "color-styles.flat.json", {})
    if isinstance(flat, dict):
        for name, value in flat.items():
            if len(rows) >= limit:
                break
            rows.append({"source": "color", "name": name, "value": value})
    variables = load_json(root / "tokens" / "variables.json", {})
    if isinstance(variables, dict) and len(rows) < limit:
        for entry in variables.get("variables") or []:
            if len(rows) >= limit:
                break
            if not isinstance(entry, dict):
                continue
            rows.append(
                {
                    "source": "variable",
                    "name": entry.get("name") or entry.get("id"),
                    "value": entry.get("resolved") or entry.get("type"),
                }
            )
    typography = load_json(root / "tokens" / "typography.json", {})
    if isinstance(typography, dict) and len(rows) < limit:
        for group, styles in typography.items():
            if not isinstance(styles, list):
                continue
            for style in styles:
                if len(rows) >= limit:
                    break
                if isinstance(style, dict):
                    rows.append(
                        {
                            "source": "typography",
                            "name": style.get("name") or group,
                            "value": style.get("fontFamily") or style.get("fontSize"),
                        }
                    )
    return rows[:limit]


def screen_hashes(directory: Path) -> dict[str, str]:
    """SHA-256 of each screen tree file, keyed by screen id."""
    root = Path(directory)
    screens = _as_list(load_json(root / "screens.json", []))
    hashes: dict[str, str] = {}
    for screen in screens:
        if not isinstance(screen, dict) or not screen.get("id") or not screen.get("tree"):
            continue
        path = root / str(screen["tree"])
        if not path.is_file():
            continue
        hashes[str(screen["id"])] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def changed_screen_ids(directory: Path) -> set[str] | None:
    """Ids whose tree changed since the last annotation. None means annotate all."""
    root = Path(directory)
    if not (root / "llm-annotations.json").is_file():
        return None
    previous = load_json(root / "catalog" / "screen-hashes.json", None)
    if not isinstance(previous, dict) or not previous:
        return None
    current = screen_hashes(root)
    return {screen_id for screen_id, digest in current.items() if previous.get(screen_id) != digest}


def sync_annotation_transport(directory: Path, annotation: dict[str, Any]) -> dict[str, str]:
    """Copy ``llm`` overlays from an annotation file into catalog and screen bundles."""
    root = Path(directory)
    catalog_path = root / "catalog" / "index.json"
    if not catalog_path.is_file():
        return {}
    catalog = load_json(catalog_path, {})
    if not isinstance(catalog, dict):
        return {}
    screens_ann = annotation.get("screens")
    if not isinstance(screens_ann, list):
        screens_ann = []
    ann_by_id = {
        str(row.get("id")): row for row in screens_ann if isinstance(row, dict) and row.get("id") is not None
    }
    written: dict[str, str] = {}
    for screen in catalog.get("screens") or []:
        if not isinstance(screen, dict):
            continue
        screen_id = str(screen.get("id"))
        ann = ann_by_id.get(screen_id)
        if ann and ann.get("llm"):
            screen["llm"] = ann["llm"]
        slug = str(screen.get("slug") or screen.get("id") or "screen")
        bundle_path = root / "screens" / slug / "screen.json"
        if bundle_path.is_file():
            bundle = load_json(bundle_path, {})
            if isinstance(bundle, dict) and ann and ann.get("llm"):
                bundle["llm"] = ann["llm"]
                write_json(bundle_path, bundle)
                written[f"screens/{slug}"] = str(bundle_path)
    write_json(catalog_path, catalog)
    written["catalog"] = str(catalog_path)
    summary_path = root / "document" / "llm-summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    validation = annotation.get("validation") if isinstance(annotation.get("validation"), list) else []
    write_json(
        summary_path,
        {
            "version": 1,
            "llmEnabled": bool(annotation.get("llmEnabled")),
            "provider": annotation.get("provider"),
            "model": annotation.get("model"),
            "tasks": sorted((annotation.get("llmResults") or {}).keys()),
            "validationOk": sum(1 for item in validation if isinstance(item, dict) and item.get("ok")),
            "validationFailed": sum(1 for item in validation if isinstance(item, dict) and not item.get("ok")),
        },
    )
    written["document"] = str(summary_path)
    return written


def write_reference_layout(directory: Path, catalog: dict[str, Any]) -> None:
    """Screen, document, and pattern files that point at the existing extract."""
    root = Path(directory)
    write_json(
        root / "document" / "document.json",
        {
            "version": 1,
            "screens": len(catalog["screens"]),
            "components": len(catalog["components"]),
            "assets": len(catalog["assets"]),
        },
    )
    patterns: dict[str, list[str]] = {}
    screens_by_id = {
        str(row.get("id")): row
        for row in _as_list(load_json(root / "screens.json", []))
        if isinstance(row, dict) and row.get("id") is not None
    }
    for screen in catalog["screens"]:
        slug = str(screen.get("slug") or screen.get("id") or "screen")
        source = screens_by_id.get(str(screen.get("id") or ""), {})
        bundle_path = root / "screens" / slug / "screen.json"
        existing = load_json(bundle_path, {})
        if not isinstance(existing, dict):
            existing = {}
        role_value = (screen.get("role") or {}).get("value") if isinstance(screen.get("role"), dict) else screen.get("role")
        bundle = {
            **existing,
            "id": screen.get("id"),
            "name": screen.get("name"),
            "slug": slug,
            "tree": screen.get("tree"),
            "role": role_value or existing.get("role"),
            "componentRefs": screen.get("componentRefs") or existing.get("componentRefs") or [],
            "assetRefs": screen.get("assetRefs") or existing.get("assetRefs") or [],
            "schemaVersion": 2,
        }
        if source.get("origin"):
            bundle["origin"] = source["origin"]
        if source.get("sourceScreenId"):
            bundle["sourceScreenId"] = source["sourceScreenId"]
        if source.get("boardTree"):
            bundle["boardTree"] = source["boardTree"]
        if source.get("semantic"):
            bundle["semantic"] = source["semantic"]
        if screen.get("llm"):
            bundle["llm"] = screen["llm"]
        write_json(bundle_path, bundle)
        role = role_value or "unknown"
        patterns.setdefault(str(role), []).append(str(screen.get("id")))
    write_json(
        root / "patterns" / "screens.json",
        [
            {"name": name, "origin": "derived", "kind": "derived", "screenIds": ids}
            for name, ids in sorted(patterns.items())
        ],
    )


def write_diagnostics(directory: Path, catalog: dict[str, Any], vectors: list[dict[str, Any]]) -> None:
    root = Path(directory)
    write_json(
        root / "diagnostics" / "extraction-report.json",
        {
            "version": 1,
            "screens": len(catalog["screens"]),
            "components": len(catalog["components"]),
            "assets": len(catalog["assets"]),
            "vectorSvgFiles": len(vectors),
            "unsupported": [
                "BOOLEAN groups without resolved path geometry are skipped in SVG export.",
                "Sibling mask relationships are approximated as a bounds clipPath on the masked node.",
            ],
            "warnings": list((catalog.get("diagnostics") or {}).values()),
        },
    )


def attach_screen_component_refs(
    directory: Path,
    screens: list[dict[str, Any]],
    component_ids: set[str],
) -> None:
    """Fill each screen's componentRefs from ``instanceOf`` values in its tree."""
    for screen in screens:
        tree_rel = screen.get("tree")
        if not tree_rel:
            continue
        tree = load_json(directory / str(tree_rel), None)
        if not isinstance(tree, dict):
            continue
        found: list[str] = []
        seen: set[str] = set()
        for component_id in _component_instance_ids(tree):
            if component_id in seen:
                continue
            if component_ids and component_id not in component_ids:
                continue
            seen.add(component_id)
            found.append(component_id)
        screen["componentRefs"] = found


def attach_screen_asset_refs(
    directory: Path,
    screens: list[dict[str, Any]],
    assets: list[dict[str, Any]],
) -> None:
    """Fill each screen's assetRefs from image hashes found in its tree."""
    known = {str(asset.get("assetId")) for asset in assets if asset.get("assetId")}
    for screen in screens:
        tree_rel = screen.get("tree")
        if not tree_rel:
            continue
        tree = load_json(directory / str(tree_rel), None)
        if not isinstance(tree, dict):
            continue
        found: list[str] = []
        seen: set[str] = set()
        for asset_id in _image_hashes(tree):
            if asset_id in seen:
                continue
            if known and asset_id not in known:
                continue
            seen.add(asset_id)
            found.append(asset_id)
        screen["assetRefs"] = found


def attach_vector_screen_refs(screens: list[dict[str, Any]], vectors: list[dict[str, Any]]) -> None:
    by_screen: dict[str, list[str]] = {}
    for vector in vectors:
        screen_id = vector.get("screenId")
        asset_id = vector.get("assetId")
        if screen_id and asset_id:
            by_screen.setdefault(str(screen_id), []).append(str(asset_id))
    for screen in screens:
        extra = by_screen.get(str(screen.get("id")), [])
        if not extra:
            continue
        refs = list(screen.get("assetRefs") or [])
        for asset_id in extra:
            if asset_id not in refs:
                refs.append(asset_id)
        screen["assetRefs"] = refs


def _component_instance_ids(node: dict[str, Any]) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        instance_of = node.get("instanceOf")
        if instance_of is not None:
            found.append(str(instance_of))
        if node.get("type") == "COMPONENT" and node.get("id") is not None:
            found.append(str(node["id"]))
        for child in node.get("children") or []:
            if isinstance(child, dict):
                found.extend(_component_instance_ids(child))
    return found


def _image_hashes(node: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for fill in node.get("fills") or []:
        if isinstance(fill, dict) and fill.get("type") == "image" and fill.get("hash"):
            found.append(str(fill["hash"]))
    for child in node.get("children") or []:
        if isinstance(child, dict):
            found.extend(_image_hashes(child))
    return found


def _screen_ref(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "slug": row.get("slug"),
        "tree": row.get("tree"),
        "role": {
            "value": row.get("role"),
            "kind": "derived",
            "source": "name-keywords",
        },
        "componentRefs": [],
        "assetRefs": [],
    }


def _component_ref(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "componentId": row.get("id"),
        "name": row.get("name"),
        "origin": "figma",
        "kind": "source",
        "page": row.get("page"),
        "variantOfId": row.get("variantOfId"),
    }


def _set_ref(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "origin": "figma",
        "kind": "source",
        "variantCount": row.get("variantCount"),
    }


def _asset_ref(row: dict[str, Any]) -> dict[str, Any]:
    mime = str(row.get("mime") or "")
    asset_type = "svg" if "svg" in mime else "image"
    used = row.get("usedBy") if isinstance(row.get("usedBy"), list) else []
    return {
        "assetId": row.get("hash"),
        "type": asset_type,
        "format": mime,
        "localPath": row.get("file"),
        "width": row.get("width"),
        "height": row.get("height"),
        "usageCount": row.get("usageCount", len(used)),
        "nodeRefs": [
            item.get("node") for item in used if isinstance(item, dict) and item.get("node")
        ],
        "kind": "source",
    }


def _image_rows(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        images = payload.get("images")
        if isinstance(images, list):
            return images
    return []


def _as_list(payload: Any) -> list[Any]:
    return payload if isinstance(payload, list) else []
