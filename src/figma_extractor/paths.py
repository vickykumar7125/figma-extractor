"""Output directory layout for an extraction run."""

from __future__ import annotations

from pathlib import Path


def resolve_out(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def source_dir(out: Path) -> Path:
    """Raw unzip / remote download cache."""
    return out / "source"


def extracted_dir(out: Path) -> Path:
    """Decoded node stream and binary blobs."""
    return out / "extracted"


def design_dir(out: Path) -> Path:
    """Curated deliverable consumed by UI tooling."""
    return out / "design"


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
