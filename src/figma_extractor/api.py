"""
Public API.

Examples
--------
Local file::

    from figma_extractor import extract, info

    result = extract(file="design.fig", output="out")
    print(result["design"])

Remote file with screen screenshots (Approach A)::

    result = extract(
        remote="https://www.figma.com/design/ABC123/MyFile",
        output="out",
        api_key="figd_...",
        screenshots=True,
    )

Local extract + cloud renders (same file must exist in Figma)::

    result = extract(
        file="design.fig",
        output="out",
        screenshots=True,
        file_key="ABC123",
        api_key="figd_...",
    )

Inspect a previous run::

    details = info("out")
    for screen in details["screens"]:
        print(screen["name"], screen.get("screenshot"))
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import orjson

from figma_extractor.extract import (
    build_images,
    build_screen_trees,
    build_screenshots,
    build_structure,
    build_tokens,
    render_screenshots,
)
from figma_extractor.fig import decode_canvas, unzip_fig
from figma_extractor.paths import design_dir, extracted_dir, source_dir
from figma_extractor.remote import (
    FigmaClient,
    download_remote_images,
    normalize_remote_document,
    parse_file_key,
)


def _clean_output(output_path: Path) -> None:
    """Wipe previous extract artifacts so each run is a fresh rebuild."""
    for name in ("design", "screenshot", "source", "extracted"):
        target = output_path / name
        if target.exists():
            shutil.rmtree(target)


def extract(
    *,
    file: str | Path | None = None,
    remote: str | None = None,
    output: str | Path,
    api_key: str | None = None,
    keep_intermediates: bool = False,
    screenshots: bool = False,
    file_key: str | None = None,
    screenshot_format: str = "png",
    screenshot_scale: float = 1.0,
    render: bool = False,
    render_limit: int | None = None,
    render_scale: float = 1.0,
    render_page: str | None = None,
    clean: bool = True,
) -> dict[str, Any]:
    """
    Extract a Figma file into ``<output>/design``.

    Pass exactly one of ``file`` (local ``.fig``) or ``remote`` (file key / URL).
    Remote extraction requires ``api_key`` (or set ``FIGMA_API_KEY`` when using the CLI).

    When ``clean=True`` (default), previous ``design/``, ``screenshot/``,
    ``source/``, and ``extracted/`` under the output directory are removed first
    so each run is a fresh rebuild.

    Multi-UI board frames (e.g. Auth - Branded containing Sign In + Sign Up) are
    split into one screen tree / PNG per nested UI.

    When ``render=True``, each screen tree is converted to HTML using ``design/``
    tokens/assets and captured into ``<output>/screenshot/`` (no Figma API).

    When ``screenshots=True``, each screen frame is also rendered through Figma's
    Images API into ``design/screenshots/`` (requires cloud ``file_key`` + ``api_key``).

    Returns a summary dict with keys: ``source``, ``output``, ``design``,
    ``decode``, ``tokens``, ``structure``, ``images``, ``trees``, ``render``,
    ``screenshots``, ``intermediatesKept``.
    """
    if bool(file) == bool(remote):
        raise ValueError("Provide exactly one of `file` or `remote`")

    output_path = Path(output).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    if clean:
        _clean_output(output_path)

    remote_file_key: str | None = None
    if file is not None:
        source_kind, source_value, decode_summary = _extract_local(file, output_path)
    else:
        source_kind, source_value, decode_summary = _extract_remote(
            remote or "",
            output_path,
            api_key,
        )
        remote_file_key = source_value

    tokens = build_tokens(output_path)
    structure = build_structure(output_path)
    images = build_images(output_path)
    trees = build_screen_trees(output_path)

    screenshot_summary: dict[str, Any] | None = None
    if screenshots:
        resolved_key = parse_file_key(file_key) if file_key else remote_file_key
        if not resolved_key:
            raise ValueError(
                "Cloud screenshots require a Figma file key. Pass file_key=... "
                "(local extract) or use remote=... so the key is known."
            )
        if not api_key:
            raise ValueError("Cloud screenshots require api_key (or FIGMA_API_KEY in the CLI)")
        screenshot_summary = build_screenshots(
            output_path,
            file_key=resolved_key,
            api_key=api_key,
            format=screenshot_format,
            scale=screenshot_scale,
        )

    if not keep_intermediates:
        shutil.rmtree(source_dir(output_path), ignore_errors=True)
        shutil.rmtree(extracted_dir(output_path), ignore_errors=True)

    render_summary: dict[str, Any] | None = None
    if render:
        render_summary = render_screenshots(
            output_path,
            limit=render_limit,
            scale=render_scale,
            page=render_page,
        )

    return {
        "source": {"type": source_kind, "value": source_value},
        "output": str(output_path),
        "design": str(design_dir(output_path)),
        "decode": decode_summary,
        "tokens": tokens,
        "structure": structure,
        "images": images,
        "trees": trees,
        "render": render_summary,
        "screenshots": screenshot_summary,
        "intermediatesKept": keep_intermediates,
    }


def render(
    directory: str | Path,
    *,
    limit: int | None = None,
    scale: float = 1.0,
    page: str | None = None,
) -> dict[str, Any]:
    """
    Rebuild local PNG screenshots from an existing ``design/`` extract.

    Requires ``design/trees/`` (produced by extract). Writes ``<root>/screenshot/``.
    """
    design = resolve_design_dir(directory)
    out = design.parent if design.name == "design" else design
    trees_dir = design / "trees"
    if not trees_dir.is_dir():
        raise FileNotFoundError(
            f"Missing {trees_dir}. Re-run extract to generate screen trees first."
        )
    return render_screenshots(out, limit=limit, scale=scale, page=page)


def export_screenshots(
    directory: str | Path,
    *,
    file_key: str,
    api_key: str,
    format: str = "png",
    scale: float = 1.0,
) -> dict[str, Any]:
    """
    Render screenshots for an existing extraction directory.

    ``directory`` may be the extraction root (contains ``design/``) or ``design/``.
    """
    design = resolve_design_dir(directory)
    out = design.parent if design.name == "design" else design
    return build_screenshots(
        out,
        file_key=parse_file_key(file_key),
        api_key=api_key,
        format=format,
        scale=scale,
    )


def info(directory: str | Path | None = None) -> dict[str, Any]:
    """
    Load a complete extraction report from ``directory``.

    ``directory`` may be the extraction root (contains ``design/``) or the
    ``design/`` folder itself. When omitted, the current working directory is used.

    Returns pages, screens, components, component sets, tokens, assets, and text,
    plus a compact ``summary`` block.
    """
    design = resolve_design_dir(directory)
    pages = _load_json(design / "pages.json", [])
    screens = _load_json(design / "screens.json", [])
    components = _load_json(design / "components.json", [])
    component_sets = _load_json(design / "component-sets.json", [])
    text = _load_json(design / "text-content.json", {})
    variables = _load_json(design / "tokens" / "variables.json", {})
    typography = _load_json(design / "tokens" / "typography.json", {})
    effects = _load_json(design / "tokens" / "effects.json", [])
    assets = _load_json(design / "assets" / "manifest.json", [])
    screenshot_manifest = _load_json(design / "screenshots" / "manifest.json", {})
    local_shot_manifest = _load_json(
        (design.parent / "screenshot" / "manifest.json")
        if design.name == "design"
        else (design / "screenshot" / "manifest.json"),
        {},
    )

    screens_with_cloud = sum(1 for screen in screens if screen.get("screenshot"))
    screens_with_local = sum(1 for screen in screens if screen.get("localScreenshot"))
    screens_with_trees = sum(1 for screen in screens if screen.get("tree"))
    return {
        "directory": str(design),
        "summary": {
            "pages": len(pages),
            "screens": len(screens),
            "components": len(components),
            "componentSets": len(component_sets),
            "variables": len(variables.get("variables") or []),
            "textStyles": sum(len(group) for group in typography.values()),
            "effects": len(effects),
            "assets": len(assets),
            "uniqueTextStrings": sum(len(items) for items in text.values()),
            "trees": screens_with_trees,
            "localScreenshots": screens_with_local,
            "cloudScreenshots": screens_with_cloud,
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
        "screenshotManifest": screenshot_manifest or None,
        "localScreenshotManifest": local_shot_manifest or None,
    }


def resolve_design_dir(directory: str | Path | None = None) -> Path:
    """Resolve an extraction root or ``design/`` path to the design directory."""
    base = Path(directory or Path.cwd()).expanduser().resolve()
    if (base / "design").is_dir():
        return base / "design"
    if (base / "screens.json").is_file():
        return base
    raise FileNotFoundError(
        f"No extraction found at {base}. "
        f"Expected {base / 'design' / 'screens.json'} or {base / 'screens.json'}."
    )


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
