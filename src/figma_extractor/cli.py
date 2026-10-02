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
        "  figma-extractor info --dir ./out\n"
        "  figma-extractor annotate --dir ./out --llm-disabled\n"
        "  figma-extractor model validate --path /models/Qwen3-0.6B\n"
        "  figma-extractor model download Qwen/Qwen3-0.6B --dest /models/Qwen3-0.6B"
    ),
)
console = Console(stderr=True)


def show_version(value: bool) -> None:
    if value:
        console.print(f"figma-extractor {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=show_version,
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


@app.command("annotate")
def annotate_cmd(
    directory: Path = typer.Option(Path("."), "--dir", "-d", help="Extract directory."),
    llm: Optional[bool] = typer.Option(
        None,
        "--llm/--llm-disabled",
        help="Enable or skip the model. When omitted, LLM_ENABLED is used (default false).",
    ),
    provider: Optional[str] = typer.Option(None, "--llm-provider", help="Provider id."),
    model: Optional[str] = typer.Option(None, "--llm-model", help="Model id for the provider."),
    temperature: Optional[float] = typer.Option(None, "--llm-temperature"),
    config_path: Optional[Path] = typer.Option(None, "--llm-config", help="JSON config file."),
    tasks: Optional[list[str]] = typer.Option(
        None,
        "--llm-task",
        help="Repeat to enable a task. Ignored when LLM mode is off.",
    ),
) -> None:
    """Write llm-annotations.json. Defaults to deterministic mode, with no model call."""
    from figma_extractor.llm.annotate import annotate
    from figma_extractor.llm.config import LlmConfig
    from figma_extractor.llm.errors import LlmError

    task_map = None
    if tasks:
        task_map = {name: True for name in tasks}
    overrides: dict[str, object] = {}
    if llm is not None:
        overrides["enabled"] = llm
    if provider is not None:
        overrides["provider"] = provider
    if model is not None:
        overrides["model"] = model
    if temperature is not None:
        overrides["temperature"] = temperature
    if task_map is not None:
        overrides["tasks"] = task_map
    try:
        config = LlmConfig.load(path=config_path, overrides=overrides)
        result = annotate(directory, config)
    except (LlmError, FileNotFoundError, OSError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from None
    mode = "enabled" if result["llmEnabled"] else "disabled"
    console.print(
        f"[green]Annotations[/] {mode} · {len(result['screens'])} screens → "
        f"{directory / 'llm-annotations.json'}"
    )


model_app = typer.Typer(help="Prepare and check a local Hugging Face model directory.")
app.add_typer(model_app, name="model")


@model_app.command("validate")
def model_validate_cmd(
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        help="Local model directory. Defaults to HF_LOCAL_MODEL_PATH.",
    ),
    load: bool = typer.Option(
        False,
        "--load",
        help="Load the weights. The default inspects files and does not download or load them.",
    ),
) -> None:
    """Report architecture, device, dtype, and quantization for a local model."""
    from figma_extractor.llm.config import LlmConfig
    from figma_extractor.llm.errors import LlmError
    from figma_extractor.llm.huggingface_local import build_local_plan, describe, load_pipeline
    from figma_extractor.llm.registry import get_provider

    options = {"backend": "local"}
    if path is not None:
        options["model_path"] = str(path)
    try:
        config = LlmConfig.load(
            overrides={"provider": "huggingface", "enabled": False, "provider_options": options}
        )
        plan = build_local_plan(config)
        if load:
            from figma_extractor.llm.factory import load_class

            pipeline_cls = load_class(
                "langchain_huggingface",
                "HuggingFacePipeline",
                get_provider("huggingface"),
            )
            pipeline = load_pipeline(config, pipeline_cls)
            footprint = memory_footprint(pipeline)
            text = describe(plan)
            if footprint:
                text = f"{text}\nMemory footprint: {footprint}"
        else:
            text = describe(plan)
    except (LlmError, OSError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from None
    console.print(text)


@model_app.command("download")
def model_download_cmd(
    repo: str = typer.Argument(..., help="Hub repo id, for example Qwen/Qwen3-0.6B."),
    dest: Path = typer.Option(..., "--dest", help="Directory that will hold the model files."),
) -> None:
    """Download weights into a directory. Local runs load that directory and do not download again."""
    from figma_extractor.llm.errors import LlmError
    from figma_extractor.llm.huggingface_local import download_model

    try:
        saved = download_model(repo, dest)
    except (LlmError, OSError, ValueError) as exc:
        console.print(str(exc))
        raise typer.Exit(1) from None
    console.print(f"Saved {repo} to {saved}")


def memory_footprint(pipeline: object) -> str:
    model = getattr(getattr(pipeline, "pipeline", None), "model", None)
    reporter = getattr(model, "get_memory_footprint", None)
    if reporter is None:
        return ""
    try:
        size = int(reporter())
    except Exception:
        return ""
    return f"{size / (1024 ** 2):.1f} MiB"


@app.command("devices")
def devices_cmd() -> None:
    """Show the PyTorch device, if a hardware profile is installed."""
    from figma_extractor.llm.device import detect_device

    status = detect_device()
    console.print(status.summary())


if __name__ == "__main__":
    app()
