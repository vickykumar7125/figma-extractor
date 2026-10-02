"""Deterministic semantic kinds for tree nodes and screens.

``type`` stays the Figma enum. ``semantic`` is optional and only present when a
closed vocabulary rule matches. Name-only matches stay at confidence ≤ 0.6.
"""

from __future__ import annotations

import re
from typing import Any

SEMANTIC_KINDS = frozenset(
    {
        "screen",
        "section",
        "header",
        "nav",
        "sidebar",
        "footer",
        "card",
        "button",
        "icon-button",
        "input",
        "image",
        "icon",
        "component-gallery",
        "specimens",
    }
)

_VARIANT_AXIS = re.compile(r"\b\w+\s*=\s*\w+\b")
_NAME_RULES: tuple[tuple[str, tuple[str, ...], float], ...] = (
    ("header", ("header", "page header", "top bar", "app bar", "appbar"), 0.55),
    ("nav", ("navbar", "navigation", "nav bar", "topnav", "breadcrumb"), 0.55),
    ("sidebar", ("sidebar", "side nav", "sidenav", "rail"), 0.55),
    ("footer", ("footer", "page footer"), 0.55),
    ("card", ("card", "tile", "panel"), 0.5),
    ("input", ("input", "text field", "textfield", "search field", "textarea"), 0.55),
    ("button", ("button", "btn", "cta"), 0.5),
    ("icon-button", ("icon button", "icon-button", "iconbtn"), 0.55),
    ("icon", ("icon", "glyph", "symbol"), 0.45),
    ("image", ("image", "photo", "picture", "avatar", "thumbnail"), 0.5),
    ("section", ("section", "block", "region"), 0.45),
)


def classify_semantic(node: dict[str, Any], *, parent: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return a ``semantic`` object or None. Pure function of node + children."""
    name = str(node.get("name") or "")
    lowered = name.lower()
    node_type = str(node.get("type") or "")
    children = [child for child in (node.get("children") or []) if isinstance(child, dict)]

    gallery = _gallery_or_specimens(node, children, lowered)
    if gallery:
        return gallery

    if node_type == "VECTOR" or (node.get("paths") and node.get("w", 999) <= 64 and node.get("h", 999) <= 64):
        if any(token in lowered for token in ("icon", "glyph", "star", "check", "close", "menu")):
            return _result("icon", 0.55, ["name-keyword", "small-vector"])

    if node_type == "TEXT" and any(token in lowered for token in ("label", "placeholder", "hint")):
        return _result("input", 0.4, ["text-label-name"])

    for kind, keywords, confidence in _NAME_RULES:
        hit = next((keyword for keyword in keywords if keyword in lowered), None)
        if hit:
            evidence = [f"name:{hit}"]
            if kind == "button" and ("icon" in lowered or _has_icon_child(children)):
                return _result("icon-button", min(confidence + 0.05, 0.6), evidence + ["icon-child-or-name"])
            return _result(kind, confidence, evidence)

    if node_type in ("FRAME", "COMPONENT", "INSTANCE") and _looks_like_card(node, children):
        return _result("card", 0.5, ["frame-with-fill-and-children"])

    if parent is None and node_type in ("FRAME", "SECTION", "COMPONENT", "INSTANCE"):
        width = float(node.get("w") or 0)
        height = float(node.get("h") or 0)
        if width >= 320 and height >= 320:
            return _result("screen", 0.4, ["root-frame-size"])

    return None


def attach_semantic(node: dict[str, Any], *, parent: dict[str, Any] | None = None) -> None:
    """Walk a tree and attach ``semantic`` where a rule matches."""
    if not isinstance(node, dict):
        return
    for child in node.get("children") or []:
        if isinstance(child, dict):
            attach_semantic(child, parent=node)
    semantic = classify_semantic(node, parent=parent)
    if semantic:
        node["semantic"] = semantic
    elif "semantic" in node:
        node.pop("semantic", None)


def screen_semantic(screen: dict[str, Any], tree: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Screen-level semantic. Prefer tree evidence for gallery/specimen crops."""
    if isinstance(tree, dict):
        attached = tree.get("semantic")
        if isinstance(attached, dict) and attached.get("kind") in {"specimens", "component-gallery"}:
            return dict(attached)
        sample = classify_semantic(tree, parent=None)
        if sample and sample.get("kind") in {"specimens", "component-gallery"}:
            return sample
    name = str(screen.get("name") or "")
    page = str(screen.get("page") or "")
    combined = f"{page} {name}".lower()
    if any(token in combined for token in ("crop", "specimen", "variants", "ui kit", "style guide")):
        return _result("component-gallery", 0.55, ["screen-name-gallery"])
    if float(screen.get("width") or 0) >= 320 and float(screen.get("height") or 0) >= 320:
        return _result("screen", 0.45, ["screen-record-size"])
    return None


def _gallery_or_specimens(
    node: dict[str, Any],
    children: list[dict[str, Any]],
    lowered: str,
) -> dict[str, Any] | None:
    # Specimen sheets are often wrapped in a single named container frame.
    effective = children
    if len(children) == 1 and isinstance(children[0], dict):
        nested = [child for child in (children[0].get("children") or []) if isinstance(child, dict)]
        if len(nested) >= 4:
            effective = nested

    symbol_children = [
        child
        for child in effective
        if child.get("type") in {"INSTANCE", "COMPONENT", "SYMBOL"}
        or child.get("instanceOf")
    ]
    variantish = sum(1 for child in symbol_children if _VARIANT_AXIS.search(str(child.get("name") or "")))
    if len(symbol_children) >= 4 and variantish >= 2:
        return _result(
            "specimens",
            0.7,
            ["symbol-children", "variant-axis-names", f"count:{len(symbol_children)}"],
        )
    if "crop" in lowered and symbol_children:
        return _result("specimens", 0.65, ["name:crop", "symbol-children"])
    if any(token in lowered for token in ("components", "ui kit", "style guide", "foundation")):
        return _result("component-gallery", 0.55, ["name-gallery-keyword"])
    return None


def _has_icon_child(children: list[dict[str, Any]]) -> bool:
    for child in children:
        if child.get("type") == "VECTOR" or child.get("paths"):
            return True
        if "icon" in str(child.get("name") or "").lower():
            return True
    return False


def _looks_like_card(node: dict[str, Any], children: list[dict[str, Any]]) -> bool:
    if len(children) < 2:
        return False
    fills = node.get("fills") or []
    has_surface = any(isinstance(fill, dict) and fill.get("type") in {"solid", "gradient"} for fill in fills)
    return bool(has_surface and node.get("radius") is not None)


def _result(kind: str, confidence: float, evidence: list[str]) -> dict[str, Any]:
    assert kind in SEMANTIC_KINDS
    return {
        "kind": kind,
        "confidence": round(min(max(confidence, 0.0), 1.0), 3),
        "evidence": sorted(set(evidence)),
    }
