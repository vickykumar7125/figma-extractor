"""Build pages, screens, components, and per-page structure outlines."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from rich.console import Console

from figma_extractor.paths import design_dir, nodes_path, require_file
from figma_extractor.util import ascii_name, gid, iter_ndjson, round_num, slug, write_json, write_text

console = Console(stderr=True)


def _slim(node: dict[str, Any]) -> dict[str, Any]:
    parent = node.get("parentIndex") or {}
    size = node.get("size") or {}
    transform = node.get("transform") or {}
    text_data = node.get("textData") or {}
    symbol_data = node.get("symbolData") or {}
    return {
        "id": gid(node.get("guid")),
        "parentId": gid(parent.get("guid")),
        "pos": parent.get("position") or "",
        "type": node.get("type"),
        "name": node.get("name") or "",
        "visible": node.get("visible") is not False,
        "w": round_num(size.get("x"), 1) if "x" in size else None,
        "h": round_num(size.get("y"), 1) if "y" in size else None,
        "x": round_num(transform.get("m02"), 1) if "m02" in transform else None,
        "y": round_num(transform.get("m12"), 1) if "m12" in transform else None,
        "stackMode": node.get("stackMode"),
        "isStateGroup": bool(node.get("isStateGroup")),
        "componentKey": node.get("componentKey"),
        "text": text_data.get("characters"),
        "propDefs": [
            {"name": d.get("name"), "type": d.get("type")}
            for d in (node.get("componentPropDefs") or [])
        ],
        "symbolRef": gid((symbol_data.get("symbolID"))),
    }


def _children_of(child_ids: dict[str, list[str]], nodes: dict[str, dict[str, Any]], node_id: str):
    kids = [nodes[cid] for cid in child_ids.get(node_id, []) if cid in nodes]
    kids.sort(key=lambda n: n.get("pos") or "")
    return kids


def _page_of(nodes: dict[str, dict[str, Any]], node_id: str) -> dict[str, Any] | None:
    cur = nodes.get(node_id)
    for _ in range(200):
        if not cur:
            return None
        if cur.get("type") == "CANVAS":
            return cur
        cur = nodes.get(cur.get("parentId") or "")
    return None


def _subtree_stats(child_ids, nodes, node_id: str) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    total = 0
    stack = [node_id]
    while stack:
        cur = stack.pop()
        for child in _children_of(child_ids, nodes, cur):
            counts[child["type"]] += 1
            total += 1
            stack.append(child["id"])
    return {"total": total, "counts": dict(counts)}


def _outline(child_ids, nodes, node_id: str, max_depth: int, lines: list[str], depth: int = 0) -> None:
    if depth >= max_depth:
        return
    for child in _children_of(child_ids, nodes, node_id):
        dims = f" [{child['w']}x{child['h']}]" if child.get("w") is not None else ""
        label = ""
        if child.get("text"):
            snippet = " ".join(str(child["text"]).split())[:60]
            label = f' "{snippet}"'
        lines.append(f"{'  ' * depth}- {child['type']} · {child['name']}{dims}{label}")
        _outline(child_ids, nodes, child["id"], max_depth, lines, depth + 1)


def _parse_variant(name: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for part in name.split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        props[key.strip()] = value.strip()
    return props


def build_structure(out: Path) -> dict[str, Any]:
    nodes_file = require_file(
        nodes_path(out),
        "Decoded nodes not found. Run figma-extractor extract first.",
    )

    nodes: dict[str, dict[str, Any]] = {}
    child_ids: dict[str, list[str]] = defaultdict(list)

    for raw in iter_ndjson(nodes_file):
        slim = _slim(raw)
        if not slim["id"]:
            continue
        nodes[slim["id"]] = slim
        if slim["parentId"]:
            child_ids[slim["parentId"]].append(slim["id"])

    canvases = [n for n in nodes.values() if n["type"] == "CANVAS"]

    pages = []
    for canvas in canvases:
        stats = _subtree_stats(child_ids, nodes, canvas["id"])
        pages.append(
            {
                "id": canvas["id"],
                "name": ascii_name(canvas["name"]),
                "rawName": canvas["name"],
                "slug": slug(ascii_name(canvas["name"])),
                "visible": canvas["visible"],
                "nodeCount": stats["total"],
                "typeCounts": stats["counts"],
                "topLevel": [
                    {
                        "id": n["id"],
                        "type": n["type"],
                        "name": n["name"],
                        "width": n["w"],
                        "height": n["h"],
                        "x": n["x"],
                        "y": n["y"],
                    }
                    for n in _children_of(child_ids, nodes, canvas["id"])
                ],
            }
        )

    screens = []
    for canvas in canvases:
        for child in _children_of(child_ids, nodes, canvas["id"]):
            if child["type"] not in ("FRAME", "SECTION"):
                continue
            stats = _subtree_stats(child_ids, nodes, child["id"])
            screens.append(
                {
                    "page": ascii_name(canvas["name"]),
                    "pageId": canvas["id"],
                    "id": child["id"],
                    "type": child["type"],
                    "name": child["name"],
                    "width": child["w"],
                    "height": child["h"],
                    "nodeCount": stats["total"],
                }
            )
    screens.sort(key=lambda s: (s["page"], -s["nodeCount"]))

    symbols = [n for n in nodes.values() if n["type"] == "SYMBOL"]
    components = []
    for symbol in symbols:
        parent = nodes.get(symbol["parentId"] or "")
        page = _page_of(nodes, symbol["id"])
        entry: dict[str, Any] = {
            "id": symbol["id"],
            "name": symbol["name"],
            "key": symbol.get("componentKey"),
            "page": ascii_name(page["name"]) if page else None,
            "width": symbol["w"],
            "height": symbol["h"],
            "layout": symbol.get("stackMode"),
        }
        if parent and parent.get("isStateGroup"):
            entry["variantOf"] = parent["name"]
            entry["variantOfId"] = parent["id"]
        if symbol.get("propDefs"):
            entry["props"] = symbol["propDefs"]
        components.append(entry)
    components.sort(key=lambda c: ((c.get("page") or ""), c["name"]))

    sets = []
    for node in nodes.values():
        if not node.get("isStateGroup"):
            continue
        page = _page_of(nodes, node["id"])
        axes: dict[str, set[str]] = defaultdict(set)
        variants = []
        for child in _children_of(child_ids, nodes, node["id"]):
            if child["type"] != "SYMBOL":
                continue
            props = _parse_variant(child["name"])
            for key, value in props.items():
                axes[key].add(value)
            variants.append(
                {
                    "id": child["id"],
                    "name": child["name"],
                    "width": child["w"],
                    "height": child["h"],
                    "props": props,
                }
            )
        sets.append(
            {
                "id": node["id"],
                "name": node["name"],
                "page": ascii_name(page["name"]) if page else None,
                "variantCount": len(variants),
                "propDefs": node.get("propDefs") or None,
                "axes": {k: sorted(v) for k, v in axes.items()},
                "variants": variants,
            }
        )
    sets.sort(key=lambda s: ((s.get("page") or ""), s["name"]))

    design = design_dir(out)
    write_json(design / "pages.json", pages)
    write_json(design / "screens.json", screens)
    write_json(design / "components.json", components)
    write_json(design / "component-sets.json", sets)

    index_lines = [
        "# Design structure",
        "",
        f"Source extraction ({len(nodes):,} nodes, {len(canvases)} pages)",
        "",
    ]
    for page in pages:
        lines = [
            f"# {page['name']}",
            "",
            f"Page id: `{page['id']}` · nodes: {page['nodeCount']}",
            "",
            "```",
        ]
        _outline(child_ids, nodes, page["id"], 4, lines)
        lines.extend(["```", ""])
        write_text(design / "structure" / f"{page['slug']}.md", "\n".join(lines))
        index_lines.append(
            f"- [{page['name']}](structure/{page['slug']}.md) — "
            f"{page['nodeCount']} nodes, {len(page['topLevel'])} top-level frames"
        )
    write_text(design / "STRUCTURE.md", "\n".join(index_lines) + "\n")

    # Component catalog
    catalog = [
        "# Component catalog",
        "",
        f"{len(sets)} variant sets · {len(symbols)} total components",
        "",
    ]
    by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in sets:
        by_page[s.get("page") or "unknown"].append(s)
    for page_name, items in by_page.items():
        catalog.append(f"## {page_name}")
        catalog.append("")
        for s in sorted(items, key=lambda x: -x["variantCount"]):
            axes_text = "  ·  ".join(
                f"{k}: {' | '.join(v)}" for k, v in (s.get("axes") or {}).items()
            )
            catalog.append(f"### {s['name']}  `{s['id']}`")
            catalog.append(f"{s['variantCount']} variants")
            if axes_text:
                catalog.extend(["", axes_text])
            catalog.append("")
    write_text(design / "COMPONENTS.md", "\n".join(catalog) + "\n")

    # Unique text content by page
    text_by_page: dict[str, set[str]] = defaultdict(set)
    for node in nodes.values():
        if node["type"] != "TEXT" or not node.get("text"):
            continue
        page = _page_of(nodes, node["id"])
        key = ascii_name(page["name"]) if page else "unknown"
        text_by_page[key].add(str(node["text"]).strip())
    write_json(design / "text-content.json", {k: sorted(v) for k, v in text_by_page.items()})

    summary = {
        "pages": len(pages),
        "screens": len(screens),
        "components": len(components),
        "variants": sum(1 for c in components if c.get("variantOf")),
        "componentSets": len(sets),
        "uniqueStrings": sum(len(v) for v in text_by_page.values()),
    }
    console.print(
        f"[green]Structure[/] {summary['pages']} pages · {summary['screens']} screens · "
        f"{summary['components']} components ({summary['componentSets']} sets) → {design}"
    )
    return summary
