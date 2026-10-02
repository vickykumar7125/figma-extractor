"""Install the local wheel plus the CUDA 13.2 torch wheels and exercise Hugging Face.

This machine path is:

    non-quant CUDA (float16 on Turing)
    8-bit BitsAndBytes
    4-bit BitsAndBytes (nf4)

Each load runs in its own process so a 4 GB GPU does not keep the previous weights.
CPU 4-bit is checked as a plan only. BitsAndBytes quantization stays on NVIDIA CUDA.

Run from the repository root:

    python scripts/test_hf_local_quant.py
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = Path("/tmp/fe-hf-quant")
MODEL_DIR = ROOT / "models" / "Qwen3-0.6B"
REPORT = ROOT / "models" / "hf-local-quant-report.json"
REPO = "Qwen/Qwen3-0.6B"
TORCH = "torch==2.14.1+cu132"
VISION = "torchvision==0.29.1+cu132"
INDEX = "https://download.pytorch.org/whl/cu132"
PYPI = "https://pypi.org/simple"


def venv_python() -> Path:
    return VENV / "bin" / "python"


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def ensure_venv() -> None:
    if venv_python().is_file():
        return
    run([sys.executable, "-m", "venv", str(VENV)])
    run([str(venv_python()), "-m", "pip", "install", "--upgrade", "pip", "build"])


def install_wheels() -> None:
    ensure_venv()
    python = str(venv_python())
    run([python, "-m", "build", "--wheel"])
    wheels = sorted((ROOT / "dist").glob("figma_extractor-*.whl"))
    if not wheels:
        raise SystemExit("python -m build did not write a wheel")
    wheel = wheels[-1]
    print(f"package wheel: {wheel.name}", flush=True)
    run(
        [
            python, "-m", "pip", "install", "--upgrade",
            TORCH, VISION,
            "--index-url", INDEX,
            "--extra-index-url", PYPI,
        ]
    )
    run([python, "-m", "pip", "install", "--force-reinstall", "--no-deps", str(wheel)])
    constraint = VENV / "torch-constraint.txt"
    constraint.write_text(f"{TORCH}\n{VISION}\n", encoding="utf-8")
    run(
        [
            python, "-m", "pip", "install",
            "transformers>=4.46,<6",
            "accelerate>=1.2,<2",
            "bitsandbytes>=0.45,<1",
            "langchain-huggingface>=1.2,<2",
            "langchain>=1.4,<2",
            "langchain-core>=1.6,<2",
            "langgraph>=1.2,<2",
            "-c", str(constraint),
            "--extra-index-url", INDEX,
        ]
    )
    pinned = subprocess.check_output([python, "-m", "pip", "show", "torch"], text=True)
    if "+cu132" not in pinned:
        raise SystemExit("torch was replaced by a PyPI build. Expected the cu132 wheel.")


def download_if_needed() -> None:
    if (MODEL_DIR / "config.json").is_file():
        print(f"model already present: {MODEL_DIR}", flush=True)
        return
    MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    code = (
        "from pathlib import Path\n"
        "from figma_extractor.llm.huggingface_local import download_model\n"
        f"download_model({REPO!r}, Path({str(MODEL_DIR)!r}))\n"
    )
    run([str(venv_python()), "-c", code])


def run_stage(mode: str) -> int:
    os.environ["HF_BACKEND"] = "local"
    os.environ["HF_LOCAL_MODEL_PATH"] = str(MODEL_DIR)
    os.environ["HF_DEVICE"] = "cuda"
    os.environ["HF_DTYPE"] = "auto"
    os.environ["HF_QUANTIZATION"] = mode
    os.environ["HF_QUANTIZATION_ON_UNSUPPORTED"] = "error"
    os.environ["HF_MAX_NEW_TOKENS"] = "32"
    os.environ["HF_DO_SAMPLE"] = "false"
    os.environ["LLM_TEMPERATURE"] = "0"
    from figma_extractor.llm.config import LlmConfig, LlmTasks
    from figma_extractor.llm.factory import load_class
    from figma_extractor.llm.huggingface_local import (
        PIPELINES,
        build_local_plan,
        describe,
        load_pipeline,
    )
    from figma_extractor.llm.registry import get_provider

    PIPELINES.clear()
    config = LlmConfig(
        enabled=True,
        provider="huggingface",
        temperature=0.0,
        tasks=LlmTasks(screen_classification=True),
        provider_options={
            "backend": "local",
            "model_path": str(MODEL_DIR),
            "device": "cuda",
            "quantization": mode,
            "max_new_tokens": "32",
            "do_sample": "false",
        },
    )
    plan = build_local_plan(config)
    report: dict = {
        "mode": mode,
        "requested": plan.quantization_requested,
        "active": plan.quantization_active,
        "detail": plan.quant_detail,
        "device": plan.device_kind,
        "dtype": plan.dtype_name,
        "device_map": plan.device_map,
        "warnings": plan.warnings,
    }
    if plan.quantization_active != mode:
        report["ok"] = False
        report["error"] = f"active quantization is {plan.quantization_active}, expected {mode}"
        print(describe(plan))
        print(json.dumps(report))
        return 1
    pipeline_cls = load_class(
        "langchain_huggingface", "HuggingFacePipeline", get_provider("huggingface")
    )
    pipeline = load_pipeline(config, pipeline_cls, plan=plan)
    inner = getattr(pipeline, "pipeline", None)
    model = getattr(inner, "model", None)
    layer_names = sorted({type(module).__name__ for module in model.modules()}) if model is not None else []
    report["layers"] = [
        name for name in layer_names
        if "4bit" in name.lower() or "8bit" in name.lower() or "Int8" in name
    ]
    param = next(model.parameters())
    report["param_dtype"] = str(param.dtype)
    report["param_device"] = str(param.device)
    import torch

    native_bf16 = bool(torch.cuda.is_bf16_supported(including_emulation=False))
    expected_dtype = "torch.bfloat16" if native_bf16 else "torch.float16"
    if mode == "none":
        quant_ok = (
            not report["layers"]
            and report["param_dtype"] == expected_dtype
            and plan.dtype_name == expected_dtype.removeprefix("torch.")
            and report["param_device"].startswith("cuda")
        )
    elif mode == "8bit":
        quant_ok = any("8bit" in name or "Int8" in name for name in report["layers"])
    else:
        quant_ok = any("4bit" in name for name in report["layers"])
    from langchain_core.messages import HumanMessage
    from figma_extractor.llm.providers.huggingface import build

    answer = build(config).model.invoke([HumanMessage(content="Reply with the single word ready.")])
    text = str(getattr(answer, "content", answer)).strip()
    report["answer"] = text[:500]
    answer_ok = "ready" in text.lower() and "<think>" not in text.lower()
    report["ok"] = bool(quant_ok and answer_ok)
    if not report["ok"]:
        if "<think>" in text.lower():
            report["error"] = "generation stayed inside a think block"
        elif "ready" not in text.lower():
            report["error"] = "generation did not contain the requested word"
        else:
            report["error"] = "loaded weights do not match the requested quantization"
    print(describe(plan))
    print(json.dumps(report))
    return 0 if report["ok"] else 1


def reject_cpu_quant() -> int:
    os.environ["HF_BACKEND"] = "local"
    os.environ["HF_LOCAL_MODEL_PATH"] = str(MODEL_DIR)
    os.environ["HF_DEVICE"] = "cpu"
    os.environ["HF_QUANTIZATION"] = "4bit"
    os.environ["HF_QUANTIZATION_ON_UNSUPPORTED"] = "error"
    from figma_extractor.llm.config import LlmConfig
    from figma_extractor.llm.device import DeviceStatus
    from figma_extractor.llm.errors import ModelLoadError
    from figma_extractor.llm.huggingface_local import build_local_plan

    config = LlmConfig(
        enabled=False,
        provider="huggingface",
        provider_options={
            "backend": "local",
            "model_path": str(MODEL_DIR),
            "device": "cpu",
            "quantization": "4bit",
        },
    )
    cpu = DeviceStatus("cpu", True, "CPU", "test")
    try:
        plan = build_local_plan(config, device=cpu)
    except ModelLoadError as exc:
        print(json.dumps({"ok": True, "rejected": True, "message": str(exc).splitlines()[0]}))
        return 0
    print(json.dumps({"ok": False, "active": plan.quantization_active}))
    return 1


def invoke(arguments: list[str]) -> dict:
    completed = subprocess.run(
        [str(venv_python()), str(Path(__file__).resolve()), *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    lines = [line for line in completed.stdout.splitlines() if line.startswith("{")]
    try:
        payload = json.loads(lines[-1]) if lines else {}
    except json.JSONDecodeError:
        payload = {"raw": completed.stdout[-4000:]}
    payload.setdefault("returncode", completed.returncode)
    if completed.returncode != 0:
        payload["ok"] = False
        payload["stderr"] = completed.stderr[-8000:]
        payload["stdout"] = completed.stdout[-4000:]
    return payload


def orchestrate(skip_install: bool) -> int:
    if not skip_install:
        install_wheels()
    download_if_needed()
    device = subprocess.check_output(
        [
            str(venv_python()), "-c",
            "from figma_extractor.llm.device import detect_device; print(detect_device().summary())",
        ],
        text=True,
    ).strip()
    print(device, flush=True)
    cpu = invoke(["--cpu-reject"])
    print("cpu 4-bit rejection:", json.dumps(cpu), flush=True)
    stages = []
    for mode in ("none", "8bit", "4bit"):
        print(f"stage {mode}", flush=True)
        item = invoke(["--stage", mode])
        stages.append(item)
        summary = {
            key: item.get(key)
            for key in ("mode", "ok", "active", "dtype", "param_dtype", "param_device", "layers", "answer", "error")
        }
        print(json.dumps(summary, indent=2), flush=True)
    results = {
        "device": device,
        "model": str(MODEL_DIR),
        "torch": TORCH,
        "cpu_4bit_rejected": cpu,
        "stages": stages,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"report: {REPORT}", flush=True)
    ok = cpu.get("ok") and all(item.get("ok") for item in stages)
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Install CUDA 13.2 wheels and run local Hugging Face quantization.")
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--stage", choices=("none", "8bit", "4bit"))
    parser.add_argument("--cpu-reject", action="store_true")
    args = parser.parse_args()
    if args.stage:
        try:
            return run_stage(args.stage)
        except SystemExit:
            raise
        except Exception:
            traceback.print_exc()
            print(json.dumps({"ok": False, "mode": args.stage, "error": traceback.format_exc()[-4000:]}))
            return 1
    if args.cpu_reject:
        try:
            return reject_cpu_quant()
        except Exception:
            traceback.print_exc()
            print(json.dumps({"ok": False, "error": traceback.format_exc()[-2000:]}))
            return 1
    return orchestrate(args.skip_install)


if __name__ == "__main__":
    raise SystemExit(main())
