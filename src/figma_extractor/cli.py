"""
Command-line interface.

Examples
--------
::

    figma-extractor extract --file ./design.fig --output ./out --render
    figma-extractor render --dir ./out
    figma-extractor info --dir ./out
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import orjson
import typer
from rich.console import Console
from rich.table import Table

from figma_extractor import __version__
from figma_extractor.api import export_screenshots
from figma_extractor.api import extract as run_extract
from figma_extractor.api import info as run_info
from figma_extractor.api import render as run_render

app = typer.Typer(
    name="figma-extractor",
    help="Extract and inspect local or remote Figma files.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    epilog=(
        "Examples:\n"
        "  figma-extractor extract --file design.fig --output ./out --render\n"
        "  figma-extractor render --dir ./out\n"
        "  figma-extractor info --dir ./out"
    ),
)
console = Console(stderr=True)


def _show_version(value: bool) -> None:
    if value:
        console.print(f"figma-extractor {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_show_version,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """Extract design tokens, structure, and assets from Figma."""


@app.command("extract")
def extract_cmd(
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Local .fig archive."),
    remote: Optional[str] = typer.Option(None, "--remote", "-r", help="Figma URL or file key."),
    output: Path = typer.Option(..., "--output", "-o", help="Destination directory."),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        envvar="FIGMA_API_KEY",
        help="Figma personal access token.",
        show_default=False,
    ),
    keep_intermediates: bool = typer.Option(
        False,
        "--keep-intermediates",
        help="Keep temporary source/ and extracted/ folders.",
    ),
    clean: bool = typer.Option(
        True,
        "--clean/--no-clean",
        help="Wipe previous design/screenshot under OUTPUT before extracting.",
    ),
    render: bool = typer.Option(
        False,
        "--render",
        help="Rebuild one PNG per UI screen into OUTPUT/screenshot/.",
    ),
    render_limit: Optional[int] = typer.Option(
        None,
        "--render-limit",
        help="Only render the first N screens (for testing).",
    ),
    render_scale: float = typer.Option(
        1.0,
        "--render-scale",
        help="Device scale factor for local PNGs.",
    ),
    render_page: Optional[str] = typer.Option(
        None,
        "--render-page",
        help="Only render screens from this Figma page.",
    ),
    screenshots: bool = typer.Option(
        False,
        "--screenshots",
        help="Also pull cloud renders via Figma Images API into design/screenshots/.",
    ),
    file_key: Optional[str] = typer.Option(
        None,
        "--file-key",
        help="Cloud file key/URL when using --screenshots with --file.",
    ),
    screenshot_format: str = typer.Option(
        "png",
        "--screenshot-format",
        help="Cloud screenshot format: png, jpg, svg, or pdf.",
    ),
    screenshot_scale: float = typer.Option(
        1.0,
        "--screenshot-scale",
        help="Cloud screenshot scale between 0.01 and 4.0.",
    ),
) -> None:
    """Extract one local or remote Figma file into OUTPUT/design."""
    try:
        result = run_extract(
            file=file,
            remote=remote,
            output=output,
            api_key=api_key,
            keep_intermediates=keep_intermediates,
            clean=clean,
            screenshots=screenshots,
            file_key=file_key,
            screenshot_format=screenshot_format,
            screenshot_scale=screenshot_scale,
            render=render,
            render_limit=render_limit,
            render_scale=render_scale,
            render_page=render_page,
        )
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from None

    structure = result["structure"]
    trees = result.get("trees") or {}
    split = trees.get("split") or {}
    screen_count = split.get("screensAfter") or trees.get("screens") or structure["screens"]
    table = Table(title="Extraction complete")
    table.add_column("Output")
    table.add_column("Pages", justify="right")
    table.add_column("UI screens", justify="right")
    table.add_column("Components", justify="right")
    if result.get("render"):
        table.add_column("Local shots", justify="right")
        table.add_row(
            result["design"],
            str(structure["pages"]),
            str(screen_count),
            str(structure["components"]),
            str(result["render"].get("rendered", 0)),
        )
    else:
        table.add_row(
            result["design"],
            str(structure["pages"]),
            str(screen_count),
            str(structure["components"]),
        )
    console.print(table)


@app.command("render")
def render_cmd(
    directory: Path = typer.Option(
        ...,
        "--dir",
        "-d",
        help="Existing extraction root (contains design/).",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        help="Only render the first N screens.",
    ),
    scale: float = typer.Option(1.0, "--scale", help="Device scale factor."),
    page: Optional[str] = typer.Option(
        None,
        "--page",
        help="Only render screens from this Figma page.",
    ),
) -> None:
    """Rebuild screen PNGs from design/trees into DIR/screenshot/ (no Figma API)."""
    try:
        summary = run_render(directory, limit=limit, scale=scale, page=page)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from None

    table = Table(title="Local screenshots")
    table.add_column("Requested", justify="right")
    table.add_column("Rendered", justify="right")
    table.add_column("Failed", justify="right")
    table.add_column("Output")
    table.add_row(
        str(summary["requested"]),
        str(summary["rendered"]),
        str(summary["failed"]),
        str(summary["output"]),
    )
    console.print(table)


@app.command("screenshots")
def screenshots_cmd(
    directory: Path = typer.Option(
        ...,
        "--dir",
        "-d",
        help="Existing extraction root or design/ directory.",
    ),
    file_key: str = typer.Option(
        ...,
        "--file-key",
        "-k",
        help="Figma cloud file key or URL (required for Images API).",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        envvar="FIGMA_API_KEY",
        help="Figma personal access token.",
        show_default=False,
    ),
    screenshot_format: str = typer.Option(
        "png",
        "--format",
        help="png, jpg, svg, or pdf.",
    ),
    screenshot_scale: float = typer.Option(
        1.0,
        "--scale",
        help="Scale between 0.01 and 4.0.",
    ),
) -> None:
    """Optional: pull exact cloud PNGs via Figma Images API."""
    if not api_key:
        console.print("[red]--api-key or FIGMA_API_KEY is required for cloud screenshots[/]")
        raise typer.Exit(1)
    try:
        summary = export_screenshots(
            directory,
            file_key=file_key,
            api_key=api_key,
            format=screenshot_format,
            scale=screenshot_scale,
        )
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from None

    table = Table(title="Cloud screenshots")
    table.add_column("Requested", justify="right")
    table.add_column("Rendered", justify="right")
    table.add_column("Failed", justify="right")
    table.add_column("Format")
    table.add_row(
        str(summary["requested"]),
        str(summary["rendered"]),
        str(summary["failed"]),
        str(summary["format"]),
    )
    console.print(table)


@app.command("info")
def info_cmd(
    directory: Optional[Path] = typer.Option(
        None,
        "--dir",
        "-d",
        help="Extraction root or design/ directory (default: current directory).",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print full JSON."),
) -> None:
    """
    Show pages, screens, components, tokens, and assets from a previous extract.

    Without ``--dir``, inspects the current directory and prints full JSON.
    With ``--dir``, prints a summary unless ``--json`` is set.
    """
    try:
        details = run_info(directory)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from None

    if as_json or directory is None:
        typer.echo(orjson.dumps(details, option=orjson.OPT_INDENT_2).decode("utf-8"))
        return

    table = Table(title=f"Extraction · {details['directory']}")
    table.add_column("Item")
    table.add_column("Count", justify="right")
    for key, value in details["summary"].items():
        table.add_row(key, f"{value:,}")
    console.print(table)


if __name__ == "__main__":
    app()
