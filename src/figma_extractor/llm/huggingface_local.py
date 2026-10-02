"""Load one local Transformers model for ChatHuggingFace.

The weight files must already be on disk. This module does not download a
repository. ``model download`` is the only path that talks to the Hub.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from figma_extractor.llm.config import LlmConfig
from figma_extractor.llm.device import DeviceStatus, detect_device, execution_placement
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


def generation_kwargs(config: LlmConfig, settings: HuggingFaceSettings) -> dict[str, Any]:
    max_new = settings.max_new_tokens or config.max_tokens or 512
    kwargs: dict[str, Any] = {
        "max_new_tokens": int(max_new),
        "return_full_text": False,
        "repetition_penalty": settings.repetition_penalty,
        "do_sample": bool(settings.do_sample),
    }
    if settings.do_sample:
        kwargs["temperature"] = config.temperature
        kwargs["top_p"] = settings.top_p
        if settings.top_k is not None:
            kwargs["top_k"] = settings.top_k
    return kwargs


def build_local_plan(config: LlmConfig, *, device: DeviceStatus | None = None) -> LocalLoadPlan:
    settings = settings_for(config)
    if settings.backend != "local":
        raise ModelLoadError("build_local_plan is only for HF_BACKEND=local.")
    path = resolve_local_path(settings, config.model)
    architecture, chat_template = read_model_directory(path)
    assert_text_generation(path, architecture, settings.task)
    status = device if device is not None else detect_device()
    try:
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
    except ValueError as exc:
        raise ModelLoadError(str(exc)) from exc
    if not chat_template:
        warnings.append(
            "tokenizer_config.json has no chat_template. ChatHuggingFace still sends messages; "
            "the tokenizer may not format them as a chat."
        )
    return LocalLoadPlan(
        path=path,
        task=settings.task,
        architecture=architecture,
        device_kind=placement.kind,
        device_map=placement.device_map,
        pipeline_device=placement.pipeline_device,
        dtype_name=placement.dtype_name,
        quantization_requested=settings.quantization,
        quantization_active=active,
        quant_detail=detail,
        offline=settings.offline,
        pipeline_kwargs=generation_kwargs(config, settings),
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
            "Then install one file from requirements/torch/ as a separate pip command."
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


def bitsandbytes_config(settings: HuggingFaceSettings, active: str) -> Any:
    try:
        from transformers import BitsAndBytesConfig
    except ImportError as exc:
        raise ModelLoadError(
            "Model loading failed.\n\nLikely cause:\ntransformers is installed without BitsAndBytesConfig.\n\n"
            "Suggested fix:\npip install 'figma-extractor[huggingface-local]'"
        ) from exc
    if active == "8bit":
        return BitsAndBytesConfig(load_in_8bit=True)
    compute = torch_dtype(settings.compute_dtype)
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type=settings.quant_type,
        bnb_4bit_compute_dtype=compute,
        bnb_4bit_use_double_quant=settings.double_quant,
    )


def model_kwargs_for(plan: LocalLoadPlan, settings: HuggingFaceSettings) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"local_files_only": True}
    if plan.quantization_active in {"4bit", "8bit"}:
        kwargs["quantization_config"] = bitsandbytes_config(settings, plan.quantization_active)
    else:
        kwargs["dtype"] = torch_dtype(plan.dtype_name)
    return kwargs


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


def load_pipeline(config: LlmConfig, pipeline_cls: type) -> Any:
    """Build or reuse one HuggingFacePipeline. Weights stay in process memory."""
    require_local_packages()
    plan = build_local_plan(config)
    key = cache_key(plan)
    cached = PIPELINES.get(key)
    if cached is not None:
        return cached
    settings = settings_for(config)
    apply_offline_environment(plan.offline)
    kwargs: dict[str, Any] = {
        "model_id": str(plan.path),
        "task": plan.task,
        "pipeline_kwargs": plan.pipeline_kwargs,
        "model_kwargs": model_kwargs_for(plan, settings),
    }
    if plan.device_map:
        kwargs["device_map"] = plan.device_map
    elif plan.pipeline_device is not None:
        kwargs["device"] = plan.pipeline_device
    try:
        pipeline = pipeline_cls.from_model_id(**kwargs)
    except Exception as exc:
        raise ModelLoadError(
            format_model_error(
                path=plan.path,
                backend="local",
                device=plan.device_kind,
                quantization=plan.quantization_active,
                cause=f"{type(exc).__name__}: {exc}",
                fix="Run figma-extractor model validate --path and confirm the files and the torch profile.",
            )
        ) from exc
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
