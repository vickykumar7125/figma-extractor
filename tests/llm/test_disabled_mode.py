"""Core extract stays importable with no provider packages."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import orjson

ROOT = Path(__file__).resolve().parents[2]


def test_core_modules_do_not_import_providers() -> None:
    script = (
        "import sys\n"
        "import figma_extractor\n"
        "import figma_extractor.api\n"
        "import figma_extractor.cli\n"
        "import figma_extractor.extract.flow\n"
        "bad = [name for name in sys.modules if name.split('.')[0] in "
        "{'langchain','langchain_core','langgraph','torch','openai','anthropic'}]\n"
        "if bad:\n"
        "    raise SystemExit('\\n'.join(bad))\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env.pop("LLM_ENABLED", None)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout


def test_disabled_annotate_writes_deterministic_output(tmp_path: Path) -> None:
    screens = [
        {
            "id": "1:1",
            "name": "Home",
            "slug": "home",
            "width": 1440,
            "height": 900,
            "role": "page",
            "regions": [],
        }
    ]
    (tmp_path / "screens.json").write_bytes(orjson.dumps(screens))
    script = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from figma_extractor.llm.annotate import annotate\n"
        "from figma_extractor.llm.config import LlmConfig\n"
        "root = Path(sys.argv[1])\n"
        "result = annotate(root, LlmConfig(enabled=False))\n"
        "assert result['llmEnabled'] is False\n"
        "assert result['screens'][0]['slug'] == 'home'\n"
        "assert result['llmResults'] == {}\n"
        "bad = [name for name in sys.modules if name.split('.')[0] in "
        "{'langchain','langgraph','torch','openai'}]\n"
        "assert not bad, bad\n"
        "print('ok')\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["LLM_ENABLED"] = "false"
    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    written = orjson.loads((tmp_path / "llm-annotations.json").read_bytes())
    assert written["llmEnabled"] is False
