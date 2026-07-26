"""
Command-line interface.

Examples
--------
::

    figma-extractor extract --file ./design.fig --output ./out
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
from figma_extractor.api import extract as run_extract
from figma_extractor.api import info as run_info

app = typer.Typer(
    name="figma-extractor",
    help="Extract and inspect local or remote Figma files.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    epilog=(
        "Examples:\n"
        "  figma-extractor extract --file design.fig --output ./out\n"
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
        help="Wipe previous extract files under OUTPUT before extracting.",
    ),
) -> None:
    """Extract one local or remote Figma file into OUTPUT/ (flat layout)."""
    try:
        result = run_extract(
            file=file,
            remote=remote,
            output=output,
            api_key=api_key,
            keep_intermediates=keep_intermediates,
            clean=clean,
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
    table.add_column("Screens", justify="right")
    table.add_column("Trees", justify="right")
    table.add_column("Components", justify="right")
    table.add_row(
        result["output"],
        str(structure["pages"]),
        str(screen_count),
        str(trees.get("trees") or 0),
        str(structure["components"]),
    )
    console.print(table)


@app.command("info")
def info_cmd(
    directory: Optional[Path] = typer.Option(
        None,
        "--dir",
        "-d",
        help="Extraction root directory (default: current directory).",
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
