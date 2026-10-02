"""Local Hugging Face plans. These tests do not download or load weights."""

from __future__ import annotations

import json

import pytest

from figma_extractor.llm.config import LlmConfig, LlmTasks
from figma_extractor.llm.device import DeviceStatus
from figma_extractor.llm.errors import ModelLoadError
from figma_extractor.llm.huggingface_local import (
    PIPELINES,
    build_local_plan,
    describe,
    download_model,
    load_pipeline,
)
from figma_extractor.llm.huggingface_settings import normalize_backend


def causal_dir(tmp_path, *, architecture="LlamaForCausalLM", chat_template=True):
    payload = {"architectures": [architecture], "model_type": "llama"}
    (tmp_path / "config.json").write_text(json.dumps(payload), encoding="utf-8")
    tokenizer = {"chat_template": "{{ messages }}"} if chat_template else {}
    (tmp_path / "tokenizer_config.json").write_text(json.dumps(tokenizer), encoding="utf-8")
    return tmp_path


def config_for(path, **options: str) -> LlmConfig:
    base = {"backend": "local", "model_path": str(path), "quantization": "none"}
    base.update(options)
    return LlmConfig(
        enabled=False,
        provider="huggingface",
        provider_options=base,
    )


def cpu_status() -> DeviceStatus:
    return DeviceStatus("cpu", True, "CPU", "test")


def cuda_status() -> DeviceStatus:
    return DeviceStatus("cuda", True, "NVIDIA test", "test")


def test_backend_defaults_to_local_and_accepts_endpoint_alias() -> None:
    assert normalize_backend(None) == "local"
    assert normalize_backend("endpoint") == "remote"
    assert normalize_backend("remote") == "remote"


def test_missing_path_is_reported(tmp_path) -> None:
    missing = tmp_path / "absent"
    with pytest.raises(ModelLoadError, match="does not exist"):
        build_local_plan(config_for(missing), device=cpu_status())


def test_directory_without_config_is_rejected(tmp_path) -> None:
    with pytest.raises(ModelLoadError, match="config.json"):
        build_local_plan(config_for(tmp_path), device=cpu_status())


def test_non_causal_architecture_is_rejected(tmp_path) -> None:
    causal_dir(tmp_path, architecture="BertModel")
    with pytest.raises(ModelLoadError, match="not a text-generation"):
        build_local_plan(config_for(tmp_path), device=cpu_status())


def test_cpu_plan_is_full_precision(tmp_path) -> None:
    causal_dir(tmp_path)
    plan = build_local_plan(config_for(tmp_path), device=cpu_status())
    assert plan.quantization_active == "none"
    assert plan.dtype_name == "float32"
    assert plan.device_map is None
    assert plan.pipeline_device == -1
    text = describe(plan)
    assert "Quantization active: none" in text
    assert "4-bit" not in text.split("Quantization active:", 1)[1].split("Chat template", 1)[0]


def test_four_bit_on_cpu_fails(tmp_path) -> None:
    causal_dir(tmp_path)
    with pytest.raises(ModelLoadError, match="NVIDIA CUDA"):
        build_local_plan(config_for(tmp_path, quantization="4bit"), device=cpu_status())


def test_four_bit_on_cpu_can_fall_back(tmp_path) -> None:
    causal_dir(tmp_path)
    plan = build_local_plan(
        config_for(tmp_path, quantization="4bit", quantization_unsupported="fallback"),
        device=cpu_status(),
    )
    assert plan.quantization_requested == "4bit"
    assert plan.quantization_active == "none"
    assert plan.warnings


def test_eight_bit_on_cuda_without_bitsandbytes_fails(tmp_path, monkeypatch) -> None:
    causal_dir(tmp_path)
    monkeypatch.setattr(
        "figma_extractor.llm.huggingface_local.bitsandbytes_installed",
        lambda: False,
    )
    with pytest.raises(ModelLoadError, match="bitsandbytes"):
        build_local_plan(config_for(tmp_path, quantization="8bit"), device=cuda_status())


def test_four_bit_on_cuda_is_active_when_bitsandbytes_is_present(tmp_path, monkeypatch) -> None:
    causal_dir(tmp_path)
    monkeypatch.setattr(
        "figma_extractor.llm.huggingface_local.bitsandbytes_installed",
        lambda: True,
    )
    plan = build_local_plan(config_for(tmp_path, quantization="4bit"), device=cuda_status())
    assert plan.quantization_active == "4bit"
    assert "nf4" in plan.quant_detail
    assert plan.device_map == "auto"
    assert "4-bit nf4" in describe(plan)


def test_missing_chat_template_is_a_warning(tmp_path) -> None:
    causal_dir(tmp_path, chat_template=False)
    plan = build_local_plan(config_for(tmp_path), device=cpu_status())
    assert plan.chat_template is False
    assert any("chat_template" in item for item in plan.warnings)


def test_offline_download_does_not_touch_the_hub(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HF_OFFLINE", "true")
    with pytest.raises(ModelLoadError, match="HF_OFFLINE"):
        download_model("Qwen/Qwen3-0.6B", tmp_path / "model")


def test_pipeline_is_cached_and_does_not_download(tmp_path, monkeypatch) -> None:
    causal_dir(tmp_path)
    calls: list[dict] = []

    class Pipeline:
        @classmethod
        def from_model_id(cls, **kwargs):
            calls.append(kwargs)
            return object()

    monkeypatch.setenv("HF_HUB_OFFLINE", "")
    monkeypatch.setattr("figma_extractor.llm.huggingface_local.require_local_packages", lambda: None)
    monkeypatch.setattr("figma_extractor.llm.huggingface_local.torch_dtype", lambda name: name)
    config = config_for(tmp_path, offline="true")
    PIPELINES.clear()
    first = load_pipeline(config, Pipeline)
    second = load_pipeline(config, Pipeline)
    assert first is second
    assert len(calls) == 1
    assert calls[0]["model_kwargs"]["local_files_only"] is True
    assert calls[0]["model_id"] == str(tmp_path.resolve())


def test_env_sets_local_path_only_for_huggingface(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "huggingface")
    monkeypatch.setenv("HF_LOCAL_MODEL_PATH", str(tmp_path))
    monkeypatch.setenv("HF_BACKEND", "local")
    loaded = LlmConfig.from_env()
    assert loaded.provider_options["model_path"] == str(tmp_path)
    assert loaded.provider_options["backend"] == "local"

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    other = LlmConfig.load(
        overrides={"enabled": True, "tasks": {"screen_classification": True}}
    )
    assert other.provider == "ollama"
    assert "model_path" not in other.provider_options


def test_greedy_sampling_omits_unused_flags() -> None:
    from figma_extractor.llm.huggingface_local import sampling_kwargs
    from figma_extractor.llm.huggingface_settings import HuggingFaceSettings

    config = LlmConfig(enabled=False, provider="huggingface", temperature=0.0)
    greedy = sampling_kwargs(config, HuggingFaceSettings(do_sample=False, max_new_tokens=8))
    assert greedy["do_sample"] is False
    assert "temperature" not in greedy
    assert "top_p" not in greedy

    sampled = sampling_kwargs(
        config,
        HuggingFaceSettings(do_sample=True, max_new_tokens=8, top_p=0.9, top_k=20),
    )
    assert sampled["temperature"] == 0.0
    assert sampled["top_p"] == 0.9
    assert sampled["top_k"] == 20


def test_load_uses_the_plan_it_was_given(tmp_path, monkeypatch) -> None:
    causal_dir(tmp_path)
    seen: list[str] = []

    class Pipeline:
        @classmethod
        def from_model_id(cls, **kwargs):
            seen.append(kwargs["model_id"])
            return object()

    monkeypatch.setattr("figma_extractor.llm.huggingface_local.require_local_packages", lambda: None)
    monkeypatch.setattr("figma_extractor.llm.huggingface_local.torch_dtype", lambda name: name)
    config = config_for(tmp_path)
    plan = build_local_plan(config, device=cpu_status())

    def rebuilt(*_args, **_kwargs):
        raise AssertionError("the supplied plan was rebuilt")

    monkeypatch.setattr("figma_extractor.llm.huggingface_local.build_local_plan", rebuilt)
    PIPELINES.clear()
    loaded = load_pipeline(config, Pipeline, plan=plan)
    assert seen == [str(plan.path)]
    assert loaded is load_pipeline(config, Pipeline, plan=plan)


def test_int8_prompt_pad_aligns_rejected_lengths() -> None:
    from figma_extractor.llm.huggingface_local import int8_pad_count

    assert int8_pad_count(19) == 13
    assert int8_pad_count(16) == 0
    assert int8_pad_count(32) == 0
    assert int8_pad_count(1) == 15


def test_quantized_kwargs_keep_the_runtime_dtype(tmp_path, monkeypatch) -> None:
    causal_dir(tmp_path)
    monkeypatch.setattr(
        "figma_extractor.llm.huggingface_local.bitsandbytes_installed",
        lambda: True,
    )
    monkeypatch.setattr("figma_extractor.llm.huggingface_local.torch_dtype", lambda name: name)
    monkeypatch.setattr(
        "figma_extractor.llm.huggingface_local.bitsandbytes_config",
        lambda plan: {"mode": plan.quantization_active},
    )
    from figma_extractor.llm.huggingface_local import build_local_plan, model_kwargs_for

    config = config_for(tmp_path, quantization="8bit")
    plan = build_local_plan(config, device=cuda_status())
    kwargs = model_kwargs_for(plan)
    assert kwargs["dtype"] == plan.dtype_name
    assert kwargs["quantization_config"] == {"mode": "8bit"}
    assert kwargs["local_files_only"] is True


def test_int8_matmul_uses_the_fallback_when_cublas_rejects_the_shape() -> None:
    from figma_extractor.llm.huggingface_local import recover_int8_matmul

    def broken(*_args):
        raise RuntimeError("cublasLt ran into an error!")

    assert recover_int8_matmul(broken, lambda *_args: "fp32", None, None, None) == "fp32"


def test_int8_matmul_keeps_other_runtime_errors() -> None:
    from figma_extractor.llm.huggingface_local import recover_int8_matmul

    def broken(*_args):
        raise RuntimeError("out of memory")

    with pytest.raises(RuntimeError, match="out of memory"):
        recover_int8_matmul(broken, lambda *_args: "fp32", None, None, None)


def test_local_prompt_turns_thinking_off() -> None:
    from figma_extractor.llm.providers.huggingface import render_local_prompt

    class Tokenizer:
        def __init__(self) -> None:
            self.kwargs = None

        def apply_chat_template(self, messages, **kwargs):
            self.kwargs = kwargs
            assert messages[0]["role"] == "user"
            return "prompt"

    tokenizer = Tokenizer()
    text = render_local_prompt(tokenizer, [{"role": "user", "content": "ready"}])
    assert text == "prompt"
    assert tokenizer.kwargs["enable_thinking"] is False
    assert tokenizer.kwargs["add_generation_prompt"] is True


def test_local_prompt_falls_back_when_thinking_is_rejected() -> None:
    from figma_extractor.llm.providers.huggingface import render_local_prompt

    class Tokenizer:
        def apply_chat_template(self, messages, **kwargs):
            if "enable_thinking" in kwargs:
                raise TypeError("unexpected")
            return "plain"

    assert render_local_prompt(Tokenizer(), [{"role": "user", "content": "ready"}]) == "plain"


def test_remote_still_requires_a_token(monkeypatch) -> None:
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACEHUB_API_TOKEN", raising=False)
    from figma_extractor.llm.factory import require_credentials
    from figma_extractor.llm.registry import get_provider

    config = LlmConfig(
        enabled=True,
        provider="huggingface",
        tasks=LlmTasks(screen_classification=True),
        provider_options={"backend": "endpoint"},
    )
    with pytest.raises(Exception, match="HF_TOKEN"):
        require_credentials(get_provider("huggingface"), config)
