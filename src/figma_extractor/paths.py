"""Output directory layout for an extraction run."""

from __future__ import annotations

from pathlib import Path

# Curated files written at the output root (no nested design/ folder).
DELIVERABLE_DIRS: tuple[str, ...] = (
    "tokens",
    "assets",
    "structure",
    "trees",
    "components",
)
DELIVERABLE_FILES: tuple[str, ...] = (
    "pages.json",
    "screens.json",
    "components.json",
    "component-sets.json",
    "text-content.json",
    "ui-flow.json",
    "STRUCTURE.md",
    "COMPONENTS.md",
    "LLM.md",
)
# Temporary decode cache — removed after extract unless keep_intermediates.
INTERMEDIATE_DIRS: tuple[str, ...] = ("source", "extracted")
# Older extracts nested everything under design/; still wiped on --clean.
LEGACY_DIRS: tuple[str, ...] = ("design",)


def resolve_out(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def source_dir(out: Path) -> Path:
    """Raw unzip / remote download cache."""
    return out / "source"


def extracted_dir(out: Path) -> Path:
    """Decoded node stream and binary blobs."""
    return out / "extracted"


def design_dir(out: Path) -> Path:
    """Curated deliverable root — same as ``out`` (tokens, assets, JSON live here)."""
    return out


def nodes_path(out: Path) -> Path:
    return extracted_dir(out) / "nodes.ndjson"


def require_file(path: Path, hint: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path}\n{hint}")
    return path


def require_dir(path: Path, hint: str) -> Path:
    if not path.is_dir():
        raise FileNotFoundError(f"Missing {path}\n{hint}")
    return path
