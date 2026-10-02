"""Load one local Transformers model for ChatHuggingFace.

The caller-facing sequence is ``build_local_plan`` then ``load_pipeline``.
The plan holds the path, device, dtype, and quantization recipe. Loading
reuses that plan: prepare the runtime, construct the pipeline, then adapt
8-bit prompts. ``model download`` is the only path that talks to the Hub.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.device import (
    DeviceStatus,
    ExecutionPlacement,
    detect_device,
    execution_placement,
)
from figma_extractor.llm.errors import ModelLoadError
from figma_extractor.llm.huggingface_settings import HuggingFaceSettings

PIPELINES: dict[tuple[Any, ...], Any] = {}


@dataclass
class LocalLoadPlan:
    path: Path
    task: str
    architecture: str
    device_kind: str
    device_map: str | None
    pipeline_device: int | None
    dtype_name: str
    quantization_requested: str
    quantization_active: str
    quant_detail: str
    quant_type: str
    compute_dtype: str
    double_quant: bool
    offline: bool
    pipeline_kwargs: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    chat_template: bool = False


def settings_for(config: LlmConfig) -> HuggingFaceSettings:
    try:
        return HuggingFaceSettings.from_options(
            config.provider_options,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
    except ValueError as exc:
        raise ModelLoadError(str(exc)) from exc


def read_model_directory(path: Path) -> tuple[str, bool]:
    config_path = path / "config.json"
    if not config_path.is_file():
        raise ModelLoadError(
            format_model_error(
                path=path,
                backend="local",
                device="unknown",
                quantization="unknown",
                cause="config.json is missing.",
                fix="Point HF_LOCAL_MODEL_PATH at a Transformers model directory, or run model download first.",
            )
        )
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ModelLoadError(
            format_model_error(
                path=path,
                backend="local",
                device="unknown",
                quantization="unknown",
                cause=f"config.json is not valid JSON ({exc}).",
                fix="Replace the directory with a complete Transformers checkout.",
            )
        ) from exc
    architectures = payload.get("architectures") or []
    architecture = ", ".join(str(item) for item in architectures) or str(payload.get("model_type") or "unknown")
    tokenizer_config = path / "tokenizer_config.json"
    chat_template = False
    if tokenizer_config.is_file():
        try:
            tokenizer_payload = json.loads(tokenizer_config.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            tokenizer_payload = {}
        chat_template = bool(tokenizer_payload.get("chat_template"))
    return architecture, chat_template


def assert_text_generation(path: Path, architecture: str, task: str) -> None:
    if task != "text-generation":
        raise ModelLoadError(
            format_model_error(
                path=path,
                backend="local",
                device="unknown",
                quantization="unknown",
                cause=f"Task {task!r} is not supported. This provider builds a text-generation pipeline.",
                fix="Set HF_TASK=text-generation.",
            )
        )
    if architecture == "unknown":
        return
    names = [part.strip() for part in architecture.split(",")]
    causal = any("CausalLM" in name or name.endswith("LMHeadModel") for name in names)
    if not causal:
        raise ModelLoadError(
            format_model_error(
                path=path,
                backend="local",
                device="unknown",
                quantization="unknown",
                cause=f"Architecture {architecture} is not a text-generation causal model.",
                fix="Choose a causal LM directory, or keep this model off the huggingface provider.",
            )
        )


def resolve_local_path(settings: HuggingFaceSettings, model: str | None) -> Path:
    raw = settings.model_path
    if not raw and model and Path(model).expanduser().is_dir():
        raw = model
    if not raw:
        raise ModelLoadError(
            "Model loading failed.\n\n"
            "Backend:\nlocal\n\n"
            "Likely cause:\nHF_LOCAL_MODEL_PATH is unset. A Hub id is not used for local execution.\n\n"
            "Suggested fix:\nSet HF_LOCAL_MODEL_PATH to a directory that already contains config.json, "
            "then run: figma-extractor model validate --path /that/directory"
        )
    path = Path(raw).expanduser()
    if not path.exists():
        raise ModelLoadError(
            format_model_error(
                path=path,
                backend="local",
                device="unknown",
                quantization=settings.quantization,
                cause="The model path does not exist.",
                fix="Create the directory with figma-extractor model download, or correct HF_LOCAL_MODEL_PATH.",
            )
        )
    if not path.is_dir():
        raise ModelLoadError(
            format_model_error(
                path=path,
                backend="local",
                device="unknown",
                quantization=settings.quantization,
                cause="The model path is not a directory.",
                fix="Pass the directory that contains config.json.",
            )
        )
    return path.resolve()


def quantization_decision(
    settings: HuggingFaceSettings,
    device_kind: str,
    *,
    bitsandbytes_installed: bool,
) -> tuple[str, str, list[str]]:
    """Return the active mode, a detail line, and warnings.

    The active mode is ``none`` when quantization is not applied. The detail
    never claims 4-bit or 8-bit unless that mode is active.
    """
    requested = settings.quantization
    if requested == "none":
        return "none", "disabled", []
    if device_kind != "cuda":
        message = (
            f"{requested} BitsAndBytes quantization is implemented for NVIDIA CUDA. "
            f"This runtime is {device_kind}."
        )
        if settings.quantization_unsupported == "fallback":
            return "none", "disabled", [message + " Full precision is being used instead."]
        raise ModelLoadError(
            format_model_error(
                path=settings.model_path or "(unset)",
                backend="local",
                device=device_kind,
                quantization=requested,
                cause=message,
                fix="Set HF_QUANTIZATION=none, or HF_QUANTIZATION_ON_UNSUPPORTED=fallback, or run on NVIDIA CUDA.",
            )
        )
    if not bitsandbytes_installed:
        message = "bitsandbytes is not installed."
        if settings.quantization_unsupported == "fallback":
            return "none", "disabled", [message + " Full precision is being used instead."]
        raise ModelLoadError(
            format_model_error(
                path=settings.model_path or "(unset)",
                backend="local",
                device=device_kind,
                quantization=requested,
                cause=message,
                fix="pip install 'figma-extractor[huggingface-quant]'",
            )
        )
    if requested == "4bit":
        detail = (
            f"4-bit {settings.quant_type}, compute {settings.compute_dtype}, "
            f"double_quant={settings.double_quant}"
        )
        return "4bit", detail, []
    return "8bit", "8-bit", []


def bitsandbytes_installed() -> bool:
    try:
        version("bitsandbytes")
    except PackageNotFoundError:
        return False
    return True


def sampling_kwargs(config: LlmConfig, settings: HuggingFaceSettings) -> dict[str, Any]:
    """Generation flags shared by the local pipeline and the hosted endpoint.

    Sampling flags are omitted when ``do_sample`` is false, so a greedy call
    does not pass temperature or top-p into a library that will ignore them.
    """
    max_new = settings.max_new_tokens or config.max_tokens or 512
    kwargs: dict[str, Any] = {
        "max_new_tokens": int(max_new),
        "repetition_penalty": settings.repetition_penalty,
        "do_sample": bool(settings.do_sample),
    }
    if settings.do_sample:
        kwargs["temperature"] = config.temperature
        kwargs["top_p"] = settings.top_p
        if settings.top_k is not None:
            kwargs["top_k"] = settings.top_k
    return kwargs


def generation_kwargs(config: LlmConfig, settings: HuggingFaceSettings) -> dict[str, Any]:
    return {"return_full_text": False, **sampling_kwargs(config, settings)}


def decide_runtime(
    settings: HuggingFaceSettings,
    status: DeviceStatus,
) -> tuple[ExecutionPlacement, str, str, list[str]]:
    """Place the model after the quantization decision, from one device status.

    Device kind is known before quantization. Placement then follows the active
    mode, because a quantized CUDA load uses ``device_map`` and a full-precision
    load can use a single pipeline device.
    """
    preview = execution_placement(
        status,
        device=settings.device,
        device_map="none",
        dtype=settings.dtype,
        quantized=False,
    )
    active, detail, warnings = quantization_decision(
        settings,
        preview.kind,
        bitsandbytes_installed=bitsandbytes_installed(),
    )
    placement = execution_placement(
        status,
        device=settings.device,
        device_map=settings.device_map,
        dtype=settings.dtype,
        quantized=active in {"4bit", "8bit"},
    )
    return placement, active, detail, warnings


def build_local_plan(
    config: LlmConfig,
    *,
    device: DeviceStatus | None = None,
    settings: HuggingFaceSettings | None = None,
) -> LocalLoadPlan:
    resolved = settings if settings is not None else settings_for(config)
    if resolved.backend != "local":
        raise ModelLoadError("build_local_plan is only for HF_BACKEND=local.")
    path = resolve_local_path(resolved, config.model)
    architecture, chat_template = read_model_directory(path)
    assert_text_generation(path, architecture, resolved.task)
    status = device if device is not None else detect_device()
    try:
        placement, active, detail, warnings = decide_runtime(resolved, status)
    except ValueError as exc:
        raise ModelLoadError(str(exc)) from exc
    if not chat_template:
        warnings.append(
            "tokenizer_config.json has no chat_template. ChatHuggingFace still sends messages; "
            "the tokenizer may not format them as a chat."
        )
    return LocalLoadPlan(
        path=path,
        task=resolved.task,
        architecture=architecture,
        device_kind=placement.kind,
        device_map=placement.device_map,
        pipeline_device=placement.pipeline_device,
        dtype_name=placement.dtype_name,
        quantization_requested=resolved.quantization,
        quantization_active=active,
        quant_detail=detail,
        quant_type=resolved.quant_type,
        compute_dtype=resolved.compute_dtype,
        double_quant=resolved.double_quant,
        offline=resolved.offline,
        pipeline_kwargs=generation_kwargs(config, resolved),
        warnings=warnings,
        chat_template=chat_template,
    )


def apply_offline_environment(enabled: bool) -> None:
    if not enabled:
        return
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def package_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "not installed"


def describe(plan: LocalLoadPlan, *, status: str = "READY") -> str:
    warnings = "\n".join(f"warning: {item}" for item in plan.warnings)
    lines = [
        "Hugging Face Local Model",
        "------------------------",
        f"Path: {plan.path}",
        f"Architecture: {plan.architecture}",
        f"Task: {plan.task}",
        f"Device: {plan.device_kind}",
        f"Device map: {plan.device_map or 'none'}",
        f"Dtype: {plan.dtype_name}",
        f"Quantization requested: {plan.quantization_requested}",
        f"Quantization active: {plan.quantization_active} ({plan.quant_detail})",
        f"Chat template: {'present' if plan.chat_template else 'absent'}",
        f"Offline: {plan.offline}",
        f"BitsAndBytes package: {package_version('bitsandbytes')}",
        f"Transformers: {package_version('transformers')}",
        f"Accelerate: {package_version('accelerate')}",
        f"PyTorch: {package_version('torch')}",
        f"langchain-huggingface: {package_version('langchain-huggingface')}",
        f"Status: {status}",
    ]
    if warnings:
        lines.append(warnings)
    return "\n".join(lines)


def require_local_packages() -> None:
    missing = [
        name
        for name in ("transformers", "accelerate", "torch")
        if package_version(name) == "not installed"
    ]
    if missing:
        names = ", ".join(missing)
        raise ModelLoadError(
            "Model loading failed.\n\n"
            "Backend:\nlocal\n\n"
            f"Likely cause:\n{names} is not installed.\n\n"
            "Suggested fix:\n"
            "pip install 'figma-extractor[huggingface-local]'\n"
            "Then run python setup.py, or pip install -r requirements/cuda132.txt "
            "(cuda130.txt, cuda129.txt, cpu.txt, xpu.txt, gpu.txt, or macos.txt)."
        )


def torch_dtype(name: str) -> Any:
    import torch

    mapping = {
        "float32": torch.float32,
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
    }
    try:
        return mapping[name]
    except KeyError as exc:
        raise ModelLoadError(f"Unsupported dtype {name}.") from exc


def bitsandbytes_config(plan: LocalLoadPlan) -> Any:
    try:
        from transformers import BitsAndBytesConfig
    except ImportError as exc:
        raise ModelLoadError(
            "Model loading failed.\n\nLikely cause:\ntransformers is installed without BitsAndBytesConfig.\n\n"
            "Suggested fix:\npip install 'figma-extractor[huggingface-local]'"
        ) from exc
    if plan.quantization_active == "8bit":
        return BitsAndBytesConfig(load_in_8bit=True)
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type=plan.quant_type,
        bnb_4bit_compute_dtype=torch_dtype(plan.compute_dtype),
        bnb_4bit_use_double_quant=plan.double_quant,
    )


def model_kwargs_for(plan: LocalLoadPlan) -> dict[str, Any]:
    """Weight-load arguments taken only from the plan."""
    kwargs: dict[str, Any] = {
        "local_files_only": True,
        "dtype": torch_dtype(plan.dtype_name),
    }
    if plan.quantization_active in {"4bit", "8bit"}:
        kwargs["quantization_config"] = bitsandbytes_config(plan)
    return kwargs


def pipeline_call_kwargs(plan: LocalLoadPlan) -> dict[str, Any]:
    """Constructor arguments for ``HuggingFacePipeline.from_model_id``."""
    kwargs: dict[str, Any] = {
        "model_id": str(plan.path),
        "task": plan.task,
        "pipeline_kwargs": plan.pipeline_kwargs,
        "model_kwargs": model_kwargs_for(plan),
    }
    if plan.device_map:
        kwargs["device_map"] = plan.device_map
    elif plan.pipeline_device is not None:
        kwargs["device"] = plan.pipeline_device
    return kwargs


def int8_pad_count(length: int, multiple: int = 16) -> int:
    """Tokens to add so a prompt length is a multiple of 16.

    The 8-bit CUDA kernel rejects some lengths, including 19. A multiple of 16
    stays on that kernel instead of the full-precision recovery path.
    """
    if length <= 0 or multiple <= 0:
        return 0
    return (-length) % multiple


def cache_key(plan: LocalLoadPlan) -> tuple[Any, ...]:
    return (
        str(plan.path),
        plan.task,
        plan.device_kind,
        plan.device_map,
        plan.dtype_name,
        plan.quantization_active,
        plan.quant_detail,
        tuple(sorted(plan.pipeline_kwargs.items())),
    )


def recover_int8_matmul(impl, recover, left, right, out):
    """Run an int8 matmul, and use recover when cuBLAS has no kernel for the shape.

    Turing cards reject some prompt lengths with a cuBLAS error that is not the
    documented "not implemented" code. The arithmetic is the same fallback
    BitsAndBytes already uses for unaligned dimensions.
    """
    try:
        return impl(left, right, out)
    except RuntimeError as exc:
        if "cublasLt" not in str(exc):
            raise
        return recover(left, right, out)


def install_int8_shape_fallback() -> None:
    import torch
    from bitsandbytes.backends.cuda import ops as cuda_ops

    current = cuda_ops._int8_linear_matmul_impl
    if getattr(current, "_figma_fallback", False):
        return

    def fallback(left, right, out):
        def recover(first, second, destination):
            # BitsAndBytes swaps the arguments inside the kernel. These names are
            # the ones the caller passed in, before that swap.
            result = torch.matmul(first.float(), second.float().t()).to(torch.int32)
            return destination.copy_(result)

        return recover_int8_matmul(current, recover, left, right, out)

    fallback._figma_fallback = True
    cuda_ops._int8_linear_matmul_impl = fallback


def align_int8_prompt(pipeline: Any) -> None:
    """Left-pad 8-bit prompts so the fast integer kernel can run.

    The mask stays zero on the pad, so those tokens do not change the answer.
    The pipeline sees the padded length and returns only the new text.
    """
    inner = getattr(pipeline, "pipeline", None)
    model = getattr(inner, "model", None)
    tokenizer = getattr(inner, "tokenizer", None)
    if inner is None or not getattr(model, "is_loaded_in_8bit", False):
        return
    if getattr(inner.preprocess, "_figma_aligned", False):
        return
    original = inner.preprocess
    pad_id = getattr(tokenizer, "pad_token_id", None)
    if pad_id is None:
        pad_id = getattr(tokenizer, "eos_token_id", None) or 0

    def preprocess(*args, **kwargs):
        import torch

        inputs = original(*args, **kwargs)
        token_ids = inputs.get("input_ids")
        if token_ids is None:
            return inputs
        extra = int8_pad_count(int(token_ids.shape[-1]))
        if extra == 0:
            return inputs
        inputs["input_ids"] = torch.nn.functional.pad(token_ids, (extra, 0), value=pad_id)
        mask = inputs.get("attention_mask")
        if mask is None:
            mask = torch.ones_like(token_ids)
        inputs["attention_mask"] = torch.nn.functional.pad(mask, (extra, 0), value=0)
        return inputs

    preprocess._figma_aligned = True
    inner.preprocess = preprocess


def prepare_quant_runtime(plan: LocalLoadPlan) -> None:
    """Set process flags that must exist before the weights are constructed."""
    apply_offline_environment(plan.offline)
    if plan.quantization_active == "8bit":
        install_int8_shape_fallback()


def finish_quant_runtime(plan: LocalLoadPlan, pipeline: Any) -> None:
    """Adapt a loaded pipeline. Prompt padding runs after tokenization exists."""
    if plan.quantization_active == "8bit":
        align_int8_prompt(pipeline)


def load_pipeline(
    config: LlmConfig,
    pipeline_cls: type,
    *,
    plan: LocalLoadPlan | None = None,
    settings: HuggingFaceSettings | None = None,
) -> Any:
    """Build or reuse one HuggingFacePipeline. Weights stay in process memory.

    Pass ``plan`` when the caller already called ``build_local_plan``. Otherwise
    the plan is built here, reusing ``settings`` when the caller already parsed them.
    """
    require_local_packages()
    resolved = plan if plan is not None else build_local_plan(config, settings=settings)
    key = cache_key(resolved)
    cached = PIPELINES.get(key)
    if cached is not None:
        return cached
    prepare_quant_runtime(resolved)
    try:
        pipeline = pipeline_cls.from_model_id(**pipeline_call_kwargs(resolved))
    except Exception as exc:
        raise ModelLoadError(
            format_model_error(
                path=resolved.path,
                backend="local",
                device=resolved.device_kind,
                quantization=resolved.quantization_active,
                cause=f"{type(exc).__name__}: {exc}",
                fix="Run figma-extractor model validate --path and confirm the files and the torch profile.",
            )
        ) from exc
    finish_quant_runtime(resolved, pipeline)
    PIPELINES[key] = pipeline
    return pipeline


def download_model(repo_id: str, dest: Path) -> Path:
    if os.environ.get("HF_OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}:
        raise ModelLoadError(
            "Model download is disabled because HF_OFFLINE is set. "
            "Copy the model directory onto this machine instead."
        )
    if not repo_id or "/" not in repo_id:
        raise ModelLoadError(
            "Pass a Hub repo id such as Qwen/Qwen3-0.6B. Local execution will use the destination directory."
        )
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise ModelLoadError(
            "huggingface_hub is not installed.\n\n"
            "Install:\npip install 'figma-extractor[huggingface-local]'"
        ) from exc
    dest.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=repo_id, local_dir=str(dest))
    return dest


def format_model_error(
    *,
    path: Path | str,
    backend: str,
    device: str,
    quantization: str,
    cause: str,
    fix: str,
) -> str:
    return (
        "Model loading failed.\n\n"
        f"Model:\n{path}\n\n"
        f"Backend:\n{backend}\n\n"
        f"Device:\n{device}\n\n"
        f"Quantization:\n{quantization}\n\n"
        f"Likely cause:\n{cause}\n\n"
        f"Suggested fix:\n{fix}\n\n"
        f"Transformers: {package_version('transformers')}\n"
        f"PyTorch: {package_version('torch')}\n"
        f"bitsandbytes: {package_version('bitsandbytes')}\n"
        f"langchain-huggingface: {package_version('langchain-huggingface')}"
    )
