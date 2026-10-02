#!/usr/bin/env python3
"""
Corpus test harness for ``figma-extractor``.

Runs the full extract pipeline against every ``.fig`` file in a directory and
validates the produced output tree. Designed for a real-world corpus of local
Figma archives (ZIP and bare ``fig-kiwi``) rather than fixtures.

Expectations are derived from what each source file actually contains, so a
file with no components or no styles does not fail spuriously, while a file
that *does* declare them must surface them.

Usage
-----
    # every file in the corpus, isolated per file
    python tests/test_fig_corpus.py

    # one file, kept output for inspection
    python tests/test_fig_corpus.py --only Rocket --keep --outdir /tmp/rocket

    # as a pytest suite
    pytest tests/test_fig_corpus.py -v

Each file is extracted in a subprocess with an address-space cap so that one
pathological archive is reported as a resource limit instead of taking the
whole run down with it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
DEFAULT_CORPUS = "/run/media/kumar/DRIVE256/DataBackup/FigmaFiles"

# Deliverables promised by README.md at the output root.
REQUIRED_FILES = (
    "pages.json",
    "screens.json",
    "components.json",
    "component-sets.json",
    "text-content.json",
    "ui-flow.json",
    "STRUCTURE.md",
    "COMPONENTS.md",
    "LLM.md",
    "tokens/tokens.css",
    "trees/index.json",
    "assets/manifest.json",
)

GIB = 1024**3

CheckLevel = Literal["error", "warning"]


class CheckItem(TypedDict):
    name: str
    ok: bool
    detail: str
    level: CheckLevel


class SourceFacts(TypedDict):
    """Counts taken from the decoded kiwi message, before extraction."""

    kiwiVersion: int
    nodeChanges: int
    blobs: int
    symbols: int
    stateGroups: int
    propDefs: int
    canvases: int
    texts: int
    styleFill: int
    styleText: int
    styleEffect: int
    variables: int
    variableSets: int
    embeddedImages: int
    topLevelKeys: list[str]


class Report(TypedDict, total=False):
    """One file's machine-readable result, written to report.json."""

    file: str
    ok: bool
    outcome: str
    source: SourceFacts
    stage: str
    error: str
    elapsed: float
    decode: Any
    summary: dict[str, Any]
    checks: list[CheckItem]
    failures: list[str]
    warnings: list[str]
    deterministic: bool
    exit: int
    workdir: str


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #


class Checks:
    """Collects pass/fail results so one run reports every problem, not the first."""

    def __init__(self) -> None:
        self.items: list[CheckItem] = []

    def add(self, name: str, ok: bool, detail: str = "", *, level: CheckLevel = "error") -> bool:
        self.items.append({"name": name, "ok": bool(ok), "detail": detail, "level": level})
        return bool(ok)

    @property
    def failures(self) -> list[CheckItem]:
        return [c for c in self.items if not c["ok"] and c["level"] == "error"]

    @property
    def warnings(self) -> list[CheckItem]:
        return [c for c in self.items if not c["ok"] and c["level"] == "warning"]


def load_json(path: Path):
    return json.loads(path.read_bytes())


def tree_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# source introspection — what the raw decode actually contains
# --------------------------------------------------------------------------- #


def introspect_source(fig: Path) -> SourceFacts:
    """Decode far enough to learn what the file declares (symbols, styles, images)."""
    sys.path.insert(0, str(SRC_DIR))
    from collections import Counter

    from figma_extractor.fig import unzip_fig
    from figma_extractor.fig.canvas import decompress_chunk, read_chunks
    from figma_extractor.kiwi import compile_schema, decode_binary_schema

    work = Path(tempfile.mkdtemp(prefix="fig-corpus-probe-"))
    try:
        unzip_fig(fig, work / "src")
        version, chunks = read_chunks((work / "src" / "canvas.fig").read_bytes())
        if len(chunks) < 2:
            raise ValueError(f"expected >=2 kiwi chunks, got {len(chunks)}")
        schema = decode_binary_schema(decompress_chunk(chunks[0]))
        message = compile_schema(schema).decode_message(decompress_chunk(chunks[1]))

        nodes = message.get("nodeChanges") or []
        types = Counter(n.get("type") for n in nodes)
        styles = Counter(n.get("styleType") for n in nodes if n.get("styleType"))
        images_dir = work / "src" / "images"
        images = sum(1 for p in images_dir.iterdir() if p.is_file()) if images_dir.is_dir() else 0
        return {
            "kiwiVersion": version,
            "nodeChanges": len(nodes),
            "blobs": len(message.get("blobs") or []),
            "symbols": types.get("SYMBOL", 0),
            "stateGroups": sum(1 for n in nodes if n.get("isStateGroup")),
            "propDefs": sum(1 for n in nodes if n.get("componentPropDefs")),
            "canvases": types.get("CANVAS", 0),
            "texts": types.get("TEXT", 0),
            "styleFill": styles.get("FILL", 0),
            "styleText": styles.get("TEXT", 0),
            "styleEffect": styles.get("EFFECT", 0),
            "variables": types.get("VARIABLE", 0),
            "variableSets": types.get("VARIABLE_SET", 0),
            "embeddedImages": images,
            "topLevelKeys": sorted(str(k) for k in message if k not in ("nodeChanges", "blobs")),
        }
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)


# --------------------------------------------------------------------------- #
# output validation
# --------------------------------------------------------------------------- #


def validate_output(out: Path, source: SourceFacts) -> Checks:
    """Assert the output tree is complete, self-consistent, and faithful to the source."""
    checks = Checks()

    # --- required deliverables -------------------------------------------------
    missing = [name for name in REQUIRED_FILES if not (out / name).is_file()]
    checks.add(
        "deliverables present",
        not missing,
        "missing: " + ", ".join(missing) if missing else f"{len(REQUIRED_FILES)} files",
    )
    if missing:
        return checks

    pages = load_json(out / "pages.json")
    screens = load_json(out / "screens.json")
    components = load_json(out / "components.json")
    comp_sets = load_json(out / "component-sets.json")
    text_content = load_json(out / "text-content.json")
    flow = load_json(out / "ui-flow.json")
    tree_index = load_json(out / "trees" / "index.json")
    manifest = load_json(out / "assets" / "manifest.json")
    tokens_css = (out / "tokens" / "tokens.css").read_text()

    # --- structure -------------------------------------------------------------
    checks.add("pages non-empty", bool(pages), f"{len(pages)} pages")
    checks.add("screens non-empty", bool(screens), f"{len(screens)} screens")
    checks.add(
        "source canvases match pages",
        len(pages) == source["canvases"],
        f"pages={len(pages)} canvases={source['canvases']}",
    )

    for name in ("STRUCTURE.md", "COMPONENTS.md", "LLM.md"):
        text = (out / name).read_text().strip()
        checks.add(f"{name} non-empty", len(text) > 40, f"{len(text)} chars")

    # --- screens: identity, geometry, tree wiring ------------------------------
    bad_ids = [s for s in screens if not s.get("id")]
    checks.add("every screen has an id", not bad_ids, f"{len(bad_ids)} without id")

    no_dims = [
        s for s in screens
        if not (s.get("width") or 0) > 0 or not (s.get("height") or 0) > 0
    ]
    checks.add(
        "every screen has positive size",
        not no_dims,
        f"{len(no_dims)} without w/h: {[s.get('name') for s in no_dims][:3]}",
        level="warning",
    )

    slugs = [s.get("slug") for s in screens if s.get("slug")]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    checks.add("tree slugs unique", not dupes, f"duplicates: {sorted(dupes)[:3]}")

    missing_trees = [s for s in screens if not (out / str(s.get("tree") or "__none__")).is_file()]
    checks.add(
        "every screen tree exists on disk",
        not missing_trees,
        f"{len(missing_trees)} missing: {[s.get('slug') for s in missing_trees][:3]}",
    )

    untreed = [s for s in screens if not s.get("tree")]
    checks.add(
        "most screens have a tree",
        not untreed,
        f"{len(untreed)}/{len(screens)} screens without a tree",
        level="warning",
    )

    # --- trees are real, parseable, non-trivial --------------------------------
    broken, empty, nan_nodes = [], [], 0
    for screen in screens:
        rel = screen.get("tree")
        if not rel:
            continue
        path = out / rel
        try:
            tree = load_json(path)
        except Exception as exc:  # noqa: BLE001
            broken.append(f"{rel}: {type(exc).__name__}")
            continue
        if not isinstance(tree, dict) or "type" not in tree:
            broken.append(f"{rel}: not a tree root")
            continue
        if not tree.get("w") or not tree.get("h"):
            empty.append(rel)
        if "NaN" in path.read_text():
            nan_nodes += 1

    checks.add("trees parse cleanly", not broken, f"{len(broken)} broken: {broken[:2]}")
    checks.add("tree roots sized", not empty, f"{len(empty)} unsized: {empty[:2]}")
    checks.add("trees free of NaN/Infinity", nan_nodes == 0, f"{nan_nodes} trees affected")

    checks.add(
        "tree index lists screens",
        bool(tree_index.get("screens")),
        f"{len(tree_index.get('screens') or [])} indexed",
    )

    # --- ui-flow ---------------------------------------------------------------
    routes = flow.get("suggestedRoutes") or []
    bad_paths = [r for r in routes if not str(r.get("path", "")).startswith("/")]
    checks.add("routes are absolute", not bad_paths, f"{len(bad_paths)} bad: {bad_paths[:2]}")

    route_paths = [r.get("path") for r in routes]
    checks.add(
        "routes unique",
        len(set(route_paths)) == len(route_paths),
        f"{len(route_paths)} routes, {len(set(route_paths))} unique",
    )

    roles = {s.get("role") for s in screens if s.get("role")}
    checks.add("screens have roles", bool(roles), f"roles: {sorted(r for r in roles if r)}")

    flow_pages = flow.get("pages") or []
    checks.add(
        "flow page slugs unique",
        len({p.get("slug") for p in flow_pages}) == len(flow_pages),
        f"{len(flow_pages)} pages",
    )

    # --- conditional token checks, driven by what the file declares -------------
    if source["styleFill"]:
        groups = load_json(out / "tokens" / "color-styles.json")
        checks.add(
            "FILL styles -> colour tokens",
            bool(groups),
            f"{sum(len(v) for v in groups.values())} styles in {len(groups)} groups",
        )
        checks.add("--style- vars in tokens.css", "--style-" in tokens_css)
    else:
        checks.add(
            "FILL styles -> colour tokens",
            True,
            "skipped: file declares no FILL styles",
        )

    if source["styleText"]:
        typo = load_json(out / "tokens" / "typography.json")
        checks.add(
            "TEXT styles -> typography tokens",
            bool(typo),
            f"{sum(len(v) for v in typo.values())} styles in {len(typo)} groups",
        )
        checks.add("typography classes in tokens.css", ".text-" in tokens_css)
    else:
        checks.add(
            "TEXT styles -> typography tokens",
            True,
            "skipped: file declares no TEXT styles",
        )

    if source["styleEffect"]:
        effects = load_json(out / "tokens" / "effects.json")
        checks.add("EFFECT styles -> effects tokens", bool(effects), f"{len(effects)} styles")
    else:
        checks.add("EFFECT styles -> effects tokens", True, "skipped: file declares none")

    checks.add(
        "tokens.css has balanced braces",
        tokens_css.count("{") == tokens_css.count("}"),
        f"{tokens_css.count('{')} open / {tokens_css.count('}')} close",
    )
    checks.add("tokens.css starts with :root", ":root" in tokens_css)

    # --- components ------------------------------------------------------------
    if source["symbols"]:
        checks.add(
            "SYMBOL nodes -> components.json",
            bool(components),
            f"{len(components)} of {source['symbols']} symbols",
        )
    else:
        checks.add("SYMBOL nodes -> components.json", True, "skipped: file has no SYMBOL nodes")

    # Variant sets need state-group metadata. Pre-2021 archives (kiwi v1-v4)
    # organize components by name path only and declare no isStateGroup, so an
    # empty component-sets.json is correct for them rather than a failure.
    if source["stateGroups"]:
        checks.add(
            "state groups -> component-sets.json",
            bool(comp_sets),
            f"{len(comp_sets)} sets from {source['stateGroups']} state groups",
        )
    else:
        checks.add(
            "state groups -> component-sets.json",
            True,
            "skipped: file declares no isStateGroup nodes"
            + (f" ({source['symbols']} symbols, variant-less format)" if source["symbols"] else ""),
        )

    # --- text ------------------------------------------------------------------
    if source["texts"]:
        total = sum(len(v) for v in text_content.values())
        checks.add("TEXT nodes -> text-content.json", total > 0, f"{total} unique strings")
    else:
        checks.add("TEXT nodes -> text-content.json", True, "skipped: no TEXT nodes")

    # --- assets ----------------------------------------------------------------
    if source["embeddedImages"]:
        checks.add(
            "embedded images exported",
            len(manifest) > 0,
            f"{len(manifest)} of {source['embeddedImages']} source images",
        )
    else:
        checks.add("embedded images exported", True, "skipped: file embeds no images")

    broken_assets, size_mismatch = [], []
    for entry in manifest:
        asset = out / "assets" / str(entry.get("file", ""))
        if not asset.is_file():
            broken_assets.append(entry.get("file"))
            continue
        if entry.get("bytes") is not None and asset.stat().st_size != entry["bytes"]:
            size_mismatch.append(entry.get("file"))

    checks.add("asset files exist", not broken_assets, f"{len(broken_assets)} missing: {broken_assets[:2]}")
    checks.add("asset sizes match manifest", not size_mismatch, f"{len(size_mismatch)} mismatched")

    refs = [e for e in manifest if e.get("usageCount", 0) > 0]
    checks.add(
        "assets reference their nodes",
        bool(refs) if manifest else True,
        f"{len(refs)}/{len(manifest)} referenced",
    )

    used_ids = {u["node"] for e in manifest for u in e.get("usedBy", []) if u.get("node")}
    checks.add("usedBy ids look like GUIDs", all(":" in i for i in used_ids), f"{len(used_ids)} ids")

    # --- intermediates removed -------------------------------------------------
    checks.add(
        "intermediates removed",
        not (out / "extracted").exists() and not (out / "source").exists(),
        "source/ or extracted/ still present",
    )

    return checks


# --------------------------------------------------------------------------- #
# worker — runs one file, writes a JSON report
# --------------------------------------------------------------------------- #


def run_worker(fig: Path, out: Path, keep: bool, mem_bytes: int, determinism: bool) -> int:
    if mem_bytes:
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

    sys.path.insert(0, str(SRC_DIR))
    from figma_extractor import extract

    report: Report = {"file": fig.name, "ok": False}
    source: SourceFacts

    try:
        source = introspect_source(fig)
    except Exception as exc:  # noqa: BLE001
        report["stage"] = "introspect"
        report["error"] = f"{type(exc).__name__}: {exc}"
        Path(out).mkdir(parents=True, exist_ok=True)
        (out.parent / "report.json").write_text(json.dumps(report, indent=2))
        return 1

    report["source"] = source
    started = time.time()
    try:
        result = extract(file=str(fig), output=str(out), keep_intermediates=keep)
    except Exception as exc:  # noqa: BLE001
        report["stage"] = "extract"
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["elapsed"] = round(time.time() - started, 2)
        (out.parent / "report.json").write_text(json.dumps(report, indent=2))
        return 1

    report["elapsed"] = round(time.time() - started, 2)
    report["decode"] = result["decode"]
    report["summary"] = {
        "tokens": result["tokens"],
        "structure": result["structure"],
        "images": result["images"],
        "trees": result["trees"],
        "flow": result["flow"],
    }

    checks = validate_output(out, source)
    report["checks"] = checks.items
    report["failures"] = [c["name"] for c in checks.failures]
    report["warnings"] = [c["name"] for c in checks.warnings]

    if determinism:
        second = out.parent / "rerun"
        try:
            extract(file=str(fig), output=str(second), keep_intermediates=False)
            a = sorted(p.name for p in (out / "trees").glob("*.json"))
            b = sorted(p.name for p in (second / "trees").glob("*.json"))
            same_names = a == b
            same_body = same_names and all(
                tree_digest(out / "trees" / n) == tree_digest(second / "trees" / n) for n in a
            )
            report["deterministic"] = bool(same_body)
            checks.add("extraction is deterministic", same_body, "tree set/content differs between runs")
            import shutil

            shutil.rmtree(second, ignore_errors=True)
        except Exception as exc:  # noqa: BLE001
            report["deterministic"] = False
            checks.add("extraction is deterministic", False, f"rerun failed: {exc}")

    report["ok"] = not checks.failures
    report["failures"] = [c["name"] for c in checks.failures]
    report["warnings"] = [c["name"] for c in checks.warnings]
    (out.parent / "report.json").write_text(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


# --------------------------------------------------------------------------- #
# parent — discovery, isolation, matrix
# --------------------------------------------------------------------------- #


def discover(corpus: Path, only: str | None) -> list[Path]:
    files = sorted(corpus.glob("*.fig"), key=lambda p: p.stat().st_size)
    if only:
        needle = only.lower()
        files = [p for p in files if needle in p.name.lower()]
    return files


def run_isolated(fig: Path, work: Path, keep: bool, timeout: int, mem_bytes: int,
                 determinism: bool) -> Report:
    out = work / "out"
    cmd = [
        sys.executable, str(Path(__file__).resolve()),
        "--worker",
        "--fig", str(fig),
        "--out", str(out),
        "--mem-limit", str(mem_bytes),
        "--determinism" if determinism else "--no-determinism",
    ]
    if keep:
        cmd.append("--keep")

    started = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {
            "file": fig.name, "ok": False, "outcome": "timeout",
            "error": f"exceeded {timeout}s", "elapsed": timeout,
        }

    report_file = work / "report.json"
    if not report_file.is_file():
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-4:]
        return {
            "file": fig.name, "ok": False, "outcome": "crashed",
            "error": " | ".join(tail) or f"exit {proc.returncode} with no report",
            "elapsed": round(time.time() - started, 2),
        }

    report = cast(Report, json.loads(report_file.read_text()))
    report["outcome"] = "ok" if report.get("ok") else "failed"
    report["exit"] = proc.returncode
    report.setdefault("elapsed", round(time.time() - started, 2))
    report["workdir"] = str(work)
    return report


def cell(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def count_text(value: object) -> str:
    """Render a metric for the matrix. Missing or non-numeric values show a dash."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "-"
    return str(value)


def print_matrix(reports: list[Report]) -> None:
    header = (
        f"{'file':<40}{'outcome':<9}{'pages':>6}{'screens':>8}{'trees':>7}"
        f"{'tokens':>8}{'comps':>7}{'assets':>7}{'secs':>7}  detail"
    )
    print(header)
    print("-" * len(header))
    for report in reports:
        outcome = report.get("outcome") or "?"
        if outcome == "crashed":
            outcome = "CRASH"
        elif outcome == "timeout":
            outcome = "TIMEOUT"
        summary = mapping(report.get("summary"))
        structure = mapping(summary.get("structure"))
        tokens = mapping(summary.get("tokens"))
        images = mapping(summary.get("images"))
        trees = mapping(summary.get("trees"))
        split = mapping(trees.get("split"))
        tree_total = split.get("screensAfter", trees.get("trees"))
        if outcome in ("CRASH", "TIMEOUT"):
            detail = (report.get("error") or "")[:70]
        else:
            problems = report.get("failures") or []
            warns = report.get("warnings") or []
            detail = "; ".join(problems) if problems else (f"{len(warns)} warn" if warns else "clean")
        print(
            f"{cell(report.get('file', ''), 40):<40}{cell(outcome, 9):<9}"
            f"{count_text(structure.get('pages')):>6}{count_text(structure.get('screens')):>8}"
            f"{count_text(tree_total):>7}"
            f"{count_text(tokens.get('colorStyles')):>8}{count_text(structure.get('components')):>7}"
            f"{count_text(images.get('copied')):>7}{count_text(report.get('elapsed')):>7}  {detail}"
        )


def print_detail(report: Report) -> None:
    print(f"\n=== {report.get('file', '')} ===")
    src = report.get("source")
    if src:
        print(
            f"  source : kiwi v{src['kiwiVersion']} · {src['nodeChanges']} nodes"
            f" · {src['symbols']} symbols · styles F{src['styleFill']}"
            f"/T{src['styleText']}/E{src['styleEffect']} · {src['embeddedImages']} images"
        )
    outcome = report.get("outcome")
    if outcome in ("crashed", "timeout"):
        print(f"  {outcome.upper()}: {report.get('error', '')}")
        return
    error = report.get("error")
    if error:
        print(f"  {report.get('stage', 'extract')} FAILED: {error}")
        return
    for check in report.get("checks") or []:
        if check["ok"]:
            continue
        flag = "FAIL" if check["level"] == "error" else "warn"
        print(f"  {flag}  {check['name']}: {check['detail']}")
    if report.get("ok") and not report.get("warnings"):
        print("  all checks passed")


# --------------------------------------------------------------------------- #
# pytest entry points
# --------------------------------------------------------------------------- #


def pytest_corpus() -> Path:
    return Path(os.environ.get("FIGMA_CORPUS", DEFAULT_CORPUS))


def pytest_files():
    corpus = pytest_corpus()
    if not corpus.is_dir():
        return []
    return sorted(corpus.glob("*.fig"))


def test_corpus_dir_exists():
    corpus = pytest_corpus()
    assert corpus.is_dir(), (
        f"corpus dir not found: {corpus}\n"
        f"set FIGMA_CORPUS=/path/to/FigmaFiles or pass --corpus to the script"
    )


def pytest_generate_tests(metafunc):
    if "fig_file" in metafunc.fixturenames:
        metafunc.parametrize("fig_file", pytest_files(), ids=lambda p: p.name)


def test_extract_file(fig_file: Path, tmp_path: Path):
    report = run_isolated(
        fig_file, tmp_path / "work", keep=False, timeout=1800,
        mem_bytes=int(os.environ.get("FIGMA_MEM_LIMIT", 6 * GIB)), determinism=False,
    )
    if report.get("outcome") == "timeout":
        pytest.skip(report.get("error") or "timeout")
    assert report.get("outcome") != "crashed", report.get("error")
    assert report.get("ok"), (
        f"{fig_file.name} failed checks: {report.get('failures')}\n"
        f"error: {report.get('error')}\nworkdir: {report.get('workdir')}"
    )


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", default=DEFAULT_CORPUS, help="directory containing .fig files")
    parser.add_argument("--only", help="substring filter on the file name")
    parser.add_argument("--outdir", help="write each file's output here (default: temp dirs)")
    parser.add_argument("--keep", action="store_true", help="keep source/ and extracted/")
    parser.add_argument("--determinism", action="store_true", help="extract twice and compare")
    parser.add_argument("--timeout", type=int, default=1800, help="per-file timeout in seconds")
    parser.add_argument("--mem-limit", type=int, default=6 * GIB, help="per-file address space cap in bytes (0 = none)")
    parser.add_argument("--json", help="write the full machine-readable report here")
    parser.add_argument("--detail", action="store_true", help="print per-check detail for every file")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--fig", help=argparse.SUPPRESS)
    parser.add_argument("--out", help=argparse.SUPPRESS)
    parser.add_argument("--no-determinism", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.worker:
        return run_worker(
            Path(args.fig), Path(args.out), args.keep, args.mem_limit, args.determinism
        )

    corpus = Path(args.corpus).expanduser()
    if not corpus.is_dir():
        print(f"error: corpus directory not found: {corpus}", file=sys.stderr)
        return 2

    files = discover(corpus, args.only)
    if not files:
        print(f"error: no .fig files matched in {corpus}", file=sys.stderr)
        return 2

    root = Path(args.outdir).expanduser().resolve() if args.outdir else Path(tempfile.mkdtemp(prefix="fig-corpus-"))
    root.mkdir(parents=True, exist_ok=True)

    print(f"corpus : {corpus}")
    print(f"files  : {len(files)}")
    print(f"output : {root}")
    print(f"limits : {args.timeout}s / {args.mem_limit // GIB if args.mem_limit else 0} GiB per file\n")

    reports: list[Report] = []
    for index, fig in enumerate(files, 1):
        print(f"[{index}/{len(files)}] {fig.name} ...", end="\r", flush=True)
        work = root / f"{index:02d}-{fig.stem}"
        work.mkdir(parents=True, exist_ok=True)
        reports.append(run_isolated(fig, work, args.keep, args.timeout, args.mem_limit, args.determinism))
    print(" " * 60, end="\r")

    print_matrix(reports)
    if args.detail:
        for report in reports:
            print_detail(report)

    passed = sum(1 for r in reports if r.get("outcome") == "ok")
    warned = sum(1 for r in reports if r.get("warnings"))
    print(f"\n{passed}/{len(reports)} passed, {warned} with warnings")

    if args.json:
        Path(args.json).write_text(json.dumps(reports, indent=2))
        print(f"report : {args.json}")

    if not args.outdir:
        import shutil

        shutil.rmtree(root, ignore_errors=True)

    return 0 if passed == len(reports) else 1


if __name__ == "__main__":
    sys.exit(main())