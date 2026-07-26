"""
Public API.

Examples
--------
Local file::

    from figma_extractor import extract, info

    result = extract(file="design.fig", output="out")
    print(result["output"])

Remote file::

    result = extract(
        remote="https://www.figma.com/design/ABC123/MyFile",
        output="out",
        api_key="figd_...",
    )

Inspect a previous run::

    details = info("out")
    for screen in details["screens"]:
        print(screen["name"], screen["width"], screen["height"])
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import orjson

from figma_extractor.extract import (
    build_images,
    build_screen_trees,
    build_structure,
    build_tokens,
    build_ui_flow,
)
from figma_extractor.fig import decode_canvas, unzip_fig
from figma_extractor.paths import (
    DELIVERABLE_DIRS,
    DELIVERABLE_FILES,
    INTERMEDIATE_DIRS,
    LEGACY_DIRS,
    design_dir,
    extracted_dir,
    source_dir,
)
from figma_extractor.remote import (
    FigmaClient,
    download_remote_images,
    normalize_remote_document,
    parse_file_key,
)


def _remove_path(target: Path) -> None:
    if target.is_dir():
        shutil.rmtree(target)
    elif target.is_file() or target.is_symlink():
        target.unlink()


def _clean_output(output_path: Path) -> None:
    """Wipe previous deliverables and intermediates so each run is a fresh rebuild."""
    for name in (*DELIVERABLE_DIRS, *INTERMEDIATE_DIRS, *LEGACY_DIRS):
        _remove_path(output_path / name)
    for name in DELIVERABLE_FILES:
        _remove_path(output_path / name)


def _clean_intermediates(output_path: Path) -> None:
    for name in INTERMEDIATE_DIRS:
        _remove_path(output_path / name)


def extract(
    *,
    file: str | Path | None = None,
    remote: str | None = None,
    output: str | Path,
    api_key: str | None = None,
    keep_intermediates: bool = False,
    clean: bool = True,
) -> dict[str, Any]:
    """
    Extract a Figma file into ``<output>/``.

    Pass exactly one of ``file`` (local ``.fig``) or ``remote`` (file key / URL).
    Remote extraction requires ``api_key`` (or set ``FIGMA_API_KEY`` when using the CLI).

    Deliverables (tokens, trees, ui-flow, assets, pages.json, …) are written at
    the output root — there is no nested ``design/`` folder. Temporary ``source/``
    and ``extracted/`` are removed after a successful run unless
    ``keep_intermediates=True``.

    When ``clean=True`` (default), previous deliverables and intermediates under
    the output directory are removed first so each run is a fresh rebuild.

    Returns a summary dict with keys: ``source``, ``output``, ``design`` (alias of
    ``output``), ``decode``, ``tokens``, ``structure``, ``images``, ``trees``,
    ``flow``, ``intermediatesKept``.
    """
    if bool(file) == bool(remote):
        raise ValueError("Provide exactly one of `file` or `remote`")

    output_path = Path(output).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if clean:
        _clean_output(output_path)

    if file is not None:
        source_kind, source_value, decode_summary = _extract_local(file, output_path)
    else:
        source_kind, source_value, decode_summary = _extract_remote(
            remote or "",
            output_path,
            api_key,
        )

    tokens = build_tokens(output_path)
    structure = build_structure(output_path)
    images = build_images(output_path)
    trees = build_screen_trees(output_path)
    flow = build_ui_flow(output_path)

    if not keep_intermediates:
        _clean_intermediates(output_path)

    root = str(design_dir(output_path))
    return {
        "source": {"type": source_kind, "value": source_value},
        "output": str(output_path),
        "design": root,
        "decode": decode_summary,
        "tokens": tokens,
        "structure": structure,
        "images": images,
        "trees": trees,
        "flow": flow,
        "intermediatesKept": keep_intermediates,
    }


def info(directory: str | Path | None = None) -> dict[str, Any]:
    """
    Load a complete extraction report from ``directory``.

    ``directory`` is the extraction root (contains ``pages.json`` / ``tokens/``).
    Older extracts that nested files under ``design/`` are still accepted.
    When omitted, the current working directory is used.

    Returns pages, screens, components, component sets, tokens, assets, and text,
    plus a compact ``summary`` block.
    """
    root = resolve_output_dir(directory)
    pages = _load_json(root / "pages.json", [])
    screens = _load_json(root / "screens.json", [])
    components = _load_json(root / "components.json", [])
    component_sets = _load_json(root / "component-sets.json", [])
    text = _load_json(root / "text-content.json", {})
    variables = _load_json(root / "tokens" / "variables.json", {})
    typography = _load_json(root / "tokens" / "typography.json", {})
    effects = _load_json(root / "tokens" / "effects.json", [])
    assets = _load_json(root / "assets" / "manifest.json", [])
    ui_flow = _load_json(root / "ui-flow.json", {})
    trees_with = sum(1 for screen in screens if screen.get("tree"))

    return {
        "directory": str(root),
        "summary": {
            "pages": len(pages),
            "screens": len(screens),
            "trees": trees_with,
            "components": len(components),
            "componentSets": len(component_sets),
            "variables": len(variables.get("variables") or []),
            "textStyles": sum(len(group) for group in typography.values()),
            "effects": len(effects),
            "assets": len(assets),
            "uniqueTextStrings": sum(len(items) for items in text.values()),
            "suggestedRoutes": len((ui_flow.get("suggestedRoutes") or [])),
        },
        "pages": pages,
        "screens": screens,
        "components": components,
        "componentSets": component_sets,
        "tokens": {
            "variables": variables,
            "typography": typography,
            "effects": effects,
        },
        "assets": assets,
        "text": text,
        "uiFlow": ui_flow or None,
    }


def resolve_output_dir(directory: str | Path | None = None) -> Path:
    """Resolve an extraction directory (root or legacy ``design/``)."""
    base = Path(directory or Path.cwd()).expanduser().resolve()
    if (base / "pages.json").is_file() or (base / "screens.json").is_file():
        return base
    legacy = base / "design"
    if (legacy / "pages.json").is_file() or (legacy / "screens.json").is_file():
        return legacy
    raise FileNotFoundError(
        f"No extraction found at {base}. "
        f"Expected {base / 'pages.json'} (or legacy {legacy / 'pages.json'})."
    )


# Backward-compatible alias.
resolve_design_dir = resolve_output_dir


def _extract_local(file: str | Path, output_path: Path) -> tuple[str, str, dict[str, Any]]:
    source = Path(file).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Fig file not found: {source}")
    unzip_fig(source, source_dir(output_path))
    summary = decode_canvas(source_dir(output_path) / "canvas.fig", extracted_dir(output_path))
    return "local", str(source), summary


def _extract_remote(
    remote: str,
    output_path: Path,
    api_key: str | None,
) -> tuple[str, str, dict[str, Any]]:
    if not api_key:
        raise ValueError("`api_key` is required when `remote` is used")

    file_key = parse_file_key(remote)
    src = source_dir(output_path)
    src.mkdir(parents=True, exist_ok=True)

    with FigmaClient(api_key) as client:
        payload = client.get_file(file_key)
        image_urls = client.get_images(file_key)

    (src / "figma-file.json").write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
    node_count = normalize_remote_document(payload, extracted_dir(output_path))
    image_count = download_remote_images(image_urls, src / "images")

    return (
        "remote",
        file_key,
        {"nodeChanges": node_count, "blobs": 0, "remoteImages": image_count},
    )


def _load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return orjson.loads(path.read_bytes())
