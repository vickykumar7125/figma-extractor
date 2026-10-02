"""Hugging Face settings for local Transformers and optional remote inference.

JSON ``provider_options`` are applied first, then ``HF_*`` environment variables
replace those keys, then explicit overrides win. Other providers never receive
these keys.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping

REMOTE_BACKENDS = frozenset({"remote", "endpoint"})
QUANT_MODES = frozenset({"none", "4bit", "8bit"})
DTYPES = frozenset({"auto", "float32", "float16", "bfloat16"})

HF_ENV_KEYS: dict[str, str] = {
    "HF_BACKEND": "backend",
    "HF_LOCAL_MODEL_PATH": "model_path",
    "HF_TASK": "task",
    "HF_DEVICE_MAP": "device_map",
    "HF_DEVICE": "device",
    "HF_DTYPE": "dtype",
    "HF_QUANTIZATION": "quantization",
    "HF_BNB_4BIT_QUANT_TYPE": "quant_type",
    "HF_BNB_4BIT_COMPUTE_DTYPE": "compute_dtype",
    "HF_BNB_4BIT_USE_DOUBLE_QUANT": "double_quant",
    "HF_OFFLINE": "offline",
    "HF_MAX_NEW_TOKENS": "max_new_tokens",
    "HF_TOP_P": "top_p",
    "HF_TOP_K": "top_k",
    "HF_REPETITION_PENALTY": "repetition_penalty",
    "HF_DO_SAMPLE": "do_sample",
    "HF_QUANTIZATION_ON_UNSUPPORTED": "quantization_unsupported",
}

ALLOWED_HUGGINGFACE_OPTIONS = frozenset(HF_ENV_KEYS.values())


def options_from_env() -> dict[str, str]:
    found: dict[str, str] = {}
    for env_name, key in HF_ENV_KEYS.items():
        if env_name in os.environ and os.environ[env_name] != "":
            found[key] = os.environ[env_name]
    return found


def merge_into_config_data(
    data: dict[str, Any],
    overrides: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Fold ``HF_*`` into provider options when the provider is Hugging Face.

    Returns the overrides mapping with ``provider_options`` already merged, so
    the caller can apply the remaining overrides without dropping the env values.
    """
    provider = str(data.get("provider") or "openai")
    override_map = dict(overrides or {})
    if override_map.get("provider"):
        provider = str(override_map["provider"])
    if provider != "huggingface":
        return overrides
    options = dict(data.get("provider_options") or data.get("options") or {})
    options.update(options_from_env())
    incoming = override_map.get("provider_options") or override_map.get("options")
    if isinstance(incoming, dict):
        options.update({str(key): str(value) for key, value in incoming.items()})
        override_map.pop("provider_options", None)
        override_map.pop("options", None)
    data["provider_options"] = options
    return override_map or None


def normalize_backend(value: str | None) -> str:
    if value is None or value.strip() == "" or value.strip().lower() == "local":
        return "local"
    lowered = value.strip().lower()
    if lowered in REMOTE_BACKENDS:
        return "remote"
    raise ValueError(
        "HF_BACKEND must be 'local' or 'remote'. 'endpoint' is accepted as 'remote'."
    )


@dataclass(frozen=True)
class HuggingFaceSettings:
    backend: str = "local"
    model_path: str = ""
    task: str = "text-generation"
    device_map: str = "auto"
    device: str = "auto"
    dtype: str = "auto"
    quantization: str = "none"
    quant_type: str = "nf4"
    compute_dtype: str = "float16"
    double_quant: bool = True
    offline: bool = False
    max_new_tokens: int | None = None
    top_p: float = 1.0
    top_k: int | None = None
    repetition_penalty: float = 1.0
    do_sample: bool | None = None
    quantization_unsupported: str = "error"

    @classmethod
    def from_options(cls, options: Mapping[str, str], *, temperature: float, max_tokens: int | None) -> HuggingFaceSettings:
        backend = normalize_backend(options.get("backend"))
        quantization = (options.get("quantization") or "none").strip().lower()
        if quantization not in QUANT_MODES:
            raise ValueError("HF_QUANTIZATION must be none, 4bit, or 8bit.")
        dtype = (options.get("dtype") or "auto").strip().lower()
        if dtype not in DTYPES:
            raise ValueError("HF_DTYPE must be auto, float32, float16, or bfloat16.")
        unsupported = (options.get("quantization_unsupported") or "error").strip().lower()
        if unsupported not in {"error", "fallback"}:
            raise ValueError("HF_QUANTIZATION_ON_UNSUPPORTED must be error or fallback.")
        max_new = options.get("max_new_tokens")
        top_k = options.get("top_k")
        do_sample_raw = options.get("do_sample")
        do_sample = None if do_sample_raw is None else do_sample_raw.strip().lower() in {"1", "true", "yes", "on"}
        if do_sample is None:
            do_sample = temperature > 0
        return cls(
            backend=backend,
            model_path=(options.get("model_path") or "").strip(),
            task=(options.get("task") or "text-generation").strip(),
            device_map=(options.get("device_map") or "auto").strip(),
            device=(options.get("device") or "auto").strip().lower(),
            dtype=dtype,
            quantization=quantization,
            quant_type=(options.get("quant_type") or "nf4").strip(),
            compute_dtype=(options.get("compute_dtype") or "float16").strip().lower(),
            double_quant=(options.get("double_quant") or "true").strip().lower() in {"1", "true", "yes", "on"},
            offline=(options.get("offline") or "false").strip().lower() in {"1", "true", "yes", "on"},
            max_new_tokens=int(max_new) if max_new else max_tokens,
            top_p=float(options.get("top_p") or 1.0),
            top_k=int(top_k) if top_k else None,
            repetition_penalty=float(options.get("repetition_penalty") or 1.0),
            do_sample=do_sample,
            quantization_unsupported=unsupported,
        )
