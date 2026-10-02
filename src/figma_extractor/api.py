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


def remove_path(target: Path) -> None:
    if target.is_dir():
        shutil.rmtree(target)
    elif target.is_file() or target.is_symlink():
        target.unlink()


def clean_output(output_path: Path) -> None:
    """Wipe previous deliverables and intermediates so each run is a fresh rebuild."""
    for name in (*DELIVERABLE_DIRS, *INTERMEDIATE_DIRS, *LEGACY_DIRS):
        remove_path(output_path / name)
    for name in DELIVERABLE_FILES:
        remove_path(output_path / name)


def clean_intermediates(output_path: Path) -> None:
    for name in INTERMEDIATE_DIRS:
        remove_path(output_path / name)


def extract(
    *,
    file: str | Path | None = None,
    remote: str | None = None,
    output: str | Path,
    api_key: str | None = None,
    keep_intermediates: bool = False,
    clean: bool = True,
    write_toon: bool = False,
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
    ``vectors``, ``flow``, ``intermediatesKept``, ``transport``, ``schemaVersion``.
    """
    if bool(file) == bool(remote):
        raise ValueError("Provide exactly one of `file` or `remote`")

    output_path = Path(output).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if clean:
        clean_output(output_path)

    if file is not None:
        source_kind, source_value, decode_summary = extract_local(file, output_path)
    else:
        source_kind, source_value, decode_summary = extract_remote(
            remote or "",
            output_path,
            api_key,
        )

    tokens = build_tokens(output_path)
    structure = build_structure(output_path)
    images = build_images(output_path)
    trees = build_screen_trees(output_path)
    from figma_extractor.extract.vectors import publish_vector_assets

    vectors = publish_vector_assets(output_path)
    flow = build_ui_flow(output_path)
    write_schema_artifacts(output_path)

    if not keep_intermediates:
        clean_intermediates(output_path)

    transport = None
    if write_toon:
        from figma_extractor.catalog import publish_transport

        transport = publish_transport(output_path)

    return {
        "source": {"type": source_kind, "value": source_value},
        "output": str(output_path),
        "design": str(design_dir(output_path)),  # legacy alias of "output"
        "decode": decode_summary,
        "tokens": tokens,
        "structure": structure,
        "images": images,
        "trees": trees,
        "vectors": len(vectors) if isinstance(vectors, list) else 0,
        "flow": flow,
        "intermediatesKept": keep_intermediates,
        "transport": transport,
        "schemaVersion": 2,
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
    pages = load_json(root / "pages.json", [])
    screens = load_json(root / "screens.json", [])
    components = load_json(root / "components.json", [])
    component_sets = load_json(root / "component-sets.json", [])
    text = load_json(root / "text-content.json", {})
    variables = load_json(root / "tokens" / "variables.json", {})
    typography = load_json(root / "tokens" / "typography.json", {})
    effects = load_json(root / "tokens" / "effects.json", [])
    assets = load_json(root / "assets" / "manifest.json", [])
    ui_flow = load_json(root / "ui-flow.json", {})
    trees_with = sum(1 for screen in screens if screen.get("tree"))
    llm = llm_info_summary(root)

    summary = {
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
    }
    if llm is not None:
        summary["llmEnabled"] = bool(llm.get("llmEnabled"))
        summary["llmTasks"] = len(llm.get("tasks") or [])

    return {
        "directory": str(root),
        "summary": summary,
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
        "llm": llm,
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


def extract_local(file: str | Path, output_path: Path) -> tuple[str, str, dict[str, Any]]:
    import shutil

    source = Path(file).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Fig file not found: {source}")
    dest_source = source_dir(output_path)
    unzip_fig(source, dest_source)
    # Bare canvas.fig kits often keep rasters in a sibling images/ folder.
    sibling_images = source.parent / "images"
    dest_images = dest_source / "images"
    if sibling_images.is_dir():
        dest_images.mkdir(parents=True, exist_ok=True)
        if not any(dest_images.iterdir()):
            for path in sibling_images.iterdir():
                if path.is_file():
                    shutil.copy2(path, dest_images / path.name)
    summary = decode_canvas(dest_source / "canvas.fig", extracted_dir(output_path))
    return "local", str(source), summary


def extract_remote(
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


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return orjson.loads(path.read_bytes())


def write_schema_artifacts(directory: Path) -> None:
    """Write root schema markers and empty optional arrays every extract needs."""
    from figma_extractor.util import write_json

    root = Path(directory)
    screens = load_json(root / "screens.json", [])
    components = load_json(root / "components.json", [])
    assets = load_json(root / "assets" / "manifest.json", [])
    vectors = load_json(root / "assets" / "vectors.json", [])
    tokens_css = (root / "tokens" / "tokens.css").is_file()
    primary = 0
    if isinstance(screens, list):
        for screen in screens:
            if not isinstance(screen, dict):
                continue
            semantic = screen.get("semantic") if isinstance(screen.get("semantic"), dict) else {}
            kind = semantic.get("kind") if isinstance(semantic, dict) else None
            if kind in {"specimens", "component-gallery"}:
                continue
            if screen.get("role") == "component-gallery":
                continue
            primary += 1
    asset_rows = assets if isinstance(assets, list) else []
    vector_rows = vectors if isinstance(vectors, list) else []
    raster_count = sum(
        1 for row in asset_rows if isinstance(row, dict) and row.get("kind") not in {"vector", "svg"}
    )
    write_json(
        root / "manifest.json",
        {
            "schemaVersion": 2,
            "source": root.name,
            "screens": len(screens) if isinstance(screens, list) else 0,
            "primaryScreens": primary,
            "components": len(components) if isinstance(components, list) else 0,
            "assets": len(asset_rows),
            "rasters": raster_count,
            "vectors": len(vector_rows),
            "tokensCss": tokens_css,
            "treesIndex": "trees/index.json",
            "uiFlow": "ui-flow.json",
            "diagnostics": "diagnostics/",
            "assetsIndex": "assets/index.json",
            "screenBundles": "screens/",
            "llmGuide": "LLM.md",
        },
    )
    vectors_path = root / "assets" / "vectors.json"
    if not vectors_path.is_file():
        write_json(vectors_path, [])
    index_path = root / "assets" / "index.json"
    if not index_path.is_file():
        write_json(
            index_path,
            {
                "version": 1,
                "rasters": "manifest.json",
                "vectors": "vectors.json",
                "unified": "manifest.json",
                "missing": "missing-hashes.json",
            },
        )
    diagnostics = root / "diagnostics"
    for name in (
        "truncated.json",
        "unsupported.json",
        "assets.json",
        "layout.json",
        "interactions.json",
        "performance.json",
    ):
        path = diagnostics / name
        if not path.is_file():
            if name == "layout.json":
                write_json(path, {
                    "nodes": 0,
                    "note": "No breakpoint table is written.",
                    "breakpoints": None,
                })
            elif name == "performance.json":
                write_json(path, {
                    "vectorAssets": 0,
                    "vectorUsages": 0,
                    "duplicateRefsAvoided": 0,
                    "approxPathBytesSaved": 0,
                    "note": "No vector dedupe measurements yet.",
                })
            else:
                write_json(path, [])


def llm_info_summary(directory: Path) -> dict[str, Any] | None:
    """Compact annotation status for ``info()``. Does not load provider SDKs."""
    root = Path(directory)
    summary = load_json(root / "document" / "llm-summary.json", None)
    if isinstance(summary, dict) and summary:
        return {
            "llmEnabled": bool(summary.get("llmEnabled")),
            "provider": summary.get("provider"),
            "model": summary.get("model"),
            "tasks": list(summary.get("tasks") or []),
            "validationOk": summary.get("validationOk"),
            "validationFailed": summary.get("validationFailed"),
            "source": "document/llm-summary.json",
        }
    annotations = load_json(root / "llm-annotations.json", None)
    if not isinstance(annotations, dict):
        return None
    results = annotations.get("llmResults")
    tasks = sorted(results) if isinstance(results, dict) else []
    validation = annotations.get("validation") if isinstance(annotations.get("validation"), list) else []
    return {
        "llmEnabled": bool(annotations.get("llmEnabled")),
        "provider": annotations.get("provider"),
        "model": annotations.get("model"),
        "tasks": tasks,
        "validationOk": sum(1 for item in validation if isinstance(item, dict) and item.get("ok")),
        "validationFailed": sum(
            1 for item in validation if isinstance(item, dict) and not item.get("ok")
        ),
        "source": "llm-annotations.json",
    }
