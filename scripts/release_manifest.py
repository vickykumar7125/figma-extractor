"""Write SHA256SUMS and release-manifest.json for files in a directory.

The package is pure Python. One sdist and one py3-none-any wheel are the
distribution. CUDA, CPU, XPU, and macOS are PyTorch install profiles, not
separate wheels.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_kind(path: Path) -> str:
    name = path.name
    if name.endswith(".whl"):
        return "wheel"
    if name.endswith(".tar.gz"):
        return "sdist"
    return "file"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/release_manifest.py DIST_DIR", file=sys.stderr)
        return 2
    dist = Path(sys.argv[1])
    files = sorted(
        path
        for path in dist.iterdir()
        if path.is_file() and path.suffix != ".json" and path.name != "SHA256SUMS"
    )
    if not files:
        print(f"no artifacts in {dist}", file=sys.stderr)
        return 1
    sums = []
    artifacts = []
    for path in files:
        digest = sha256(path)
        sums.append(f"{digest}  {path.name}")
        artifacts.append(
            {
                "filename": path.name,
                "sha256": digest,
                "type": artifact_kind(path),
                "python": ">=3.11",
                "platform": "any",
                "architecture": "any",
            }
        )
    (dist / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    version = os.environ.get("FIGMA_EXTRACTOR_VERSION", "")
    if not version:
        wheel = next((item for item in artifacts if item["type"] == "wheel"), None)
        if wheel:
            version = wheel["filename"].split("-")[1]
    manifest = {
        "name": "figma-extractor",
        "version": version,
        "git_tag": os.environ.get("GITHUB_REF_NAME", ""),
        "commit": os.environ.get("GITHUB_SHA", ""),
        "python": [">=3.11"],
        "platforms": ["linux", "windows", "macos"],
        "architectures": ["any"],
        "accelerators": [
            "The wheel is accelerator-neutral. CUDA 12.9, 13.0, and 13.2, "
            "CPU, XPU, ROCm, and macOS are requirements files for PyTorch, "
            "not separate figma-extractor wheels."
        ],
        "artifacts": artifacts,
    }
    (dist / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(artifacts)} checksums in {dist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
