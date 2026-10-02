"""Deduplicate vector path geometry into shared SVG assets."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import orjson

from figma_extractor.extract.svg import svg_markup
from figma_extractor.util import write_json


def publish_vector_assets(directory: Path, *, limit: int = 1200) -> list[dict[str, Any]]:
    """Write ``assets/vectors.json`` and shared ``assets/svg/*.svg`` files.

    Repeated geometry shares one asset id (path + paint signature, size-independent).
    Tree nodes gain ``vectorRef`` when they participate; differing instance sizes
    get ``vectorScale``. One-off non-icon vectors keep inline ``paths``.

    All screens are scanned. When more candidate geometries exist than ``limit``,
    the highest-usage groups win so repeated icons are not skipped.
    """
    root = Path(directory)
    screens = _load(root / "screens.json", [])
    if not isinstance(screens, list):
        return []
    image_files = _image_file_map(root)
    groups: dict[str, dict[str, Any]] = {}
    for screen in screens:
        if not isinstance(screen, dict) or not screen.get("tree"):
            continue
        tree_rel = str(screen["tree"])
        tree = _load(root / tree_rel, None)
        if not isinstance(tree, dict):
            continue
        _collect(tree, groups, str(screen.get("id") or ""), tree_rel)

    candidates: list[tuple[str, dict[str, Any]]] = []
    for digest, group in groups.items():
        usage = len(group["occurrences"])
        width = float(group["width"])
        height = float(group["height"])
        icon_like = width <= 64 and height <= 64
        if usage < 2 and not icon_like:
            continue
        candidates.append((digest, group))
    candidates.sort(
        key=lambda item: (-len(item[1]["occurrences"]), item[0]),
    )
    selected = candidates[:limit]

    destination = root / "assets" / "svg"
    records: list[dict[str, Any]] = []
    refs_by_tree: dict[str, dict[str, dict[str, Any]]] = {}
    for digest, group in selected:
        sample = group["sample"]
        markup = svg_markup(sample, image_files=image_files)
        if "<path " not in markup:
            continue
        usage = len(group["occurrences"])
        width = float(group["width"])
        height = float(group["height"])
        asset_id = digest[:16]
        destination.mkdir(parents=True, exist_ok=True)
        filename = f"{asset_id}.svg"
        (destination / filename).write_text(markup, encoding="utf-8")
        for tree_rel, node_id, _node_w, _node_h in group["occurrences"]:
            refs_by_tree.setdefault(tree_rel, {})[node_id] = {
                "assetId": asset_id,
                "masterW": width,
                "masterH": height,
            }
        records.append(
            {
                "id": asset_id,
                "kind": "vector",
                "sourceNodeId": group["sourceNodeId"],
                "name": group["name"],
                "width": width,
                "height": height,
                "viewBox": f"0 0 {width} {height}",
                "usageCount": usage,
                "hash": digest,
                "file": f"svg/{filename}",
                "localPath": f"svg/{filename}",
                "screenIds": sorted(group["screenIds"]),
            }
        )

    for tree_rel, mapping in refs_by_tree.items():
        path = root / tree_rel
        tree = _load(path, None)
        if isinstance(tree, dict) and _apply_refs(tree, mapping):
            path.write_bytes(orjson.dumps(tree, option=orjson.OPT_INDENT_2))

    write_json(root / "assets" / "vectors.json", records)
    merge_vectors_into_manifest(root, records)
    write_performance_note(root, records, refs_by_tree)
    return records


def write_performance_note(
    directory: Path,
    records: list[dict[str, Any]],
    refs_by_tree: dict[str, dict[str, dict[str, Any]]],
) -> None:
    """Record path-byte savings from ``vectorRef`` (prompt 14)."""
    root = Path(directory)
    shared_usages = sum(int(row.get("usageCount") or 0) for row in records)
    unique_assets = len(records)
    duplicate_refs = max(0, shared_usages - unique_assets)
    approx_bytes_saved = 0
    for row in records:
        path = root / "assets" / str(row.get("localPath") or row.get("file") or "")
        if path.is_file():
            size = path.stat().st_size
            usage = int(row.get("usageCount") or 1)
            approx_bytes_saved += size * max(0, usage - 1)
    write_json(
        root / "diagnostics" / "performance.json",
        {
            "vectorAssets": unique_assets,
            "vectorUsages": shared_usages,
            "duplicateRefsAvoided": duplicate_refs,
            "approxPathBytesSaved": approx_bytes_saved,
            "treesWithVectorRefs": len(refs_by_tree),
            "note": (
                "vectorRef dedupes repeated path geometry into assets/svg. "
                "Instance position/size/overrides stay on the tree. "
                "No kiwi decoder rewrite."
            ),
        },
    )


def merge_vectors_into_manifest(directory: Path, records: list[dict[str, Any]] | None = None) -> None:
    """Append vector rows into ``assets/manifest.json`` and refresh ``assets/index.json``."""
    root = Path(directory)
    assets_dir = root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    if records is None:
        loaded = _load(assets_dir / "vectors.json", [])
        records = loaded if isinstance(loaded, list) else []
    manifest_path = assets_dir / "manifest.json"
    existing = _load(manifest_path, [])
    rows = existing if isinstance(existing, list) else (
        existing.get("images") if isinstance(existing, dict) else []
    )
    if not isinstance(rows, list):
        rows = []
    kept = [
        row
        for row in rows
        if isinstance(row, dict) and row.get("kind") not in {"vector", "svg"}
    ]
    for record in records:
        if not isinstance(record, dict):
            continue
        kept.append(
            {
                "id": record.get("id"),
                "kind": "vector",
                "hash": record.get("hash"),
                "file": record.get("file") or record.get("localPath"),
                "mime": "image/svg+xml",
                "width": record.get("width"),
                "height": record.get("height"),
                "usageCount": record.get("usageCount", 0),
                "usedBy": [
                    {"node": record.get("sourceNodeId"), "name": record.get("name"), "type": "VECTOR"}
                ],
                "screenIds": record.get("screenIds") or [],
            }
        )
    write_json(manifest_path, kept)
    write_json(
        assets_dir / "index.json",
        {
            "version": 1,
            "rasters": "manifest.json",
            "vectors": "vectors.json",
            "unified": "manifest.json",
            "missing": "missing-hashes.json",
            "rasterCount": sum(1 for row in kept if isinstance(row, dict) and row.get("kind") == "raster"),
            "vectorCount": sum(1 for row in kept if isinstance(row, dict) and row.get("kind") == "vector"),
        },
    )


def geometry_signature(node: dict[str, Any]) -> str:
    """Stable size-independent fingerprint of path geometry + paints."""
    payload = {
        "paths": node.get("paths") or [],
        "strokePaths": node.get("strokePaths") or [],
        "fills": node.get("fills") or [],
        "stroke": {
            "paints": (node.get("stroke") or {}).get("paints")
            if isinstance(node.get("stroke"), dict)
            else None,
            "weight": (node.get("stroke") or {}).get("weight")
            if isinstance(node.get("stroke"), dict)
            else None,
            "cap": (node.get("stroke") or {}).get("cap")
            if isinstance(node.get("stroke"), dict)
            else None,
            "join": (node.get("stroke") or {}).get("join")
            if isinstance(node.get("stroke"), dict)
            else None,
            "dash": (node.get("stroke") or {}).get("dash")
            if isinstance(node.get("stroke"), dict)
            else None,
        },
        "opacity": node.get("opacity"),
    }
    return hashlib.sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()


def _sample_node(node: dict[str, Any]) -> dict[str, Any]:
    """Minimal node fields needed to rebuild SVG markup."""
    sample: dict[str, Any] = {
        "id": node.get("id"),
        "name": node.get("name") or "",
        "w": node.get("w"),
        "h": node.get("h"),
    }
    for key in ("paths", "strokePaths", "fills", "stroke", "opacity", "radius", "clip", "mask", "blend"):
        if key in node:
            sample[key] = node[key]
    return sample


def _collect(
    node: dict[str, Any],
    groups: dict[str, dict[str, Any]],
    screen_id: str,
    tree_rel: str,
) -> None:
    paths = node.get("paths") or node.get("strokePaths")
    if node.get("id") and paths:
        width = float(node.get("w") or 1)
        height = float(node.get("h") or 1)
        digest = geometry_signature(node)
        group = groups.get(digest)
        if group is None:
            groups[digest] = {
                "sample": _sample_node(node),
                "width": width,
                "height": height,
                "name": node.get("name") or "",
                "sourceNodeId": node.get("id"),
                "occurrences": [(tree_rel, str(node["id"]), width, height)],
                "screenIds": {screen_id} if screen_id else set(),
            }
        else:
            group["occurrences"].append((tree_rel, str(node["id"]), width, height))
            if screen_id:
                group["screenIds"].add(screen_id)
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _collect(child, groups, screen_id, tree_rel)


def _scale(
    node_w: float,
    node_h: float,
    master_w: float,
    master_h: float,
) -> list[float] | None:
    if master_w <= 0 or master_h <= 0:
        return None
    sx = round(node_w / master_w, 4)
    sy = round(node_h / master_h, 4)
    if abs(sx - 1.0) < 0.001 and abs(sy - 1.0) < 0.001:
        return None
    return [sx, sy]


def _apply_refs(node: dict[str, Any], mapping: dict[str, dict[str, Any]]) -> bool:
    changed = False
    node_id = str(node.get("id") or "")
    if node_id in mapping:
        payload = mapping[node_id]
        asset_id = payload.get("assetId")
        if asset_id and node.get("vectorRef") != asset_id:
            node["vectorRef"] = asset_id
            changed = True
        scale = _scale(
            float(node.get("w") or 0),
            float(node.get("h") or 0),
            float(payload.get("masterW") or 0),
            float(payload.get("masterH") or 0),
        )
        if scale is not None:
            if node.get("vectorScale") != scale:
                node["vectorScale"] = scale
                changed = True
        elif "vectorScale" in node:
            node.pop("vectorScale", None)
            changed = True
        if node.pop("paths", None) is not None:
            changed = True
        if node.pop("strokePaths", None) is not None:
            changed = True
    for child in node.get("children") or []:
        if isinstance(child, dict) and _apply_refs(child, mapping):
            changed = True
    return changed


def _load(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return orjson.loads(path.read_bytes())


def _image_file_map(root: Path) -> dict[str, str]:
    payload = _load(root / "assets" / "manifest.json", [])
    rows = payload if isinstance(payload, list) else (
        payload.get("images") if isinstance(payload, dict) else []
    )
    if not isinstance(rows, list):
        return {}
    found: dict[str, str] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("hash") and row.get("file"):
            if row.get("kind") in {"vector", "svg"}:
                continue
            found[str(row["hash"])] = str(row["file"]).lstrip("/")
    return found
