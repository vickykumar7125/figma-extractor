"""Optional end-to-end load. Skipped unless a local model is provided.

Set HF_RUN_INTEGRATION=1 and HF_LOCAL_MODEL_PATH to a real Transformers directory.
This test is not part of the default suite.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("HF_RUN_INTEGRATION") != "1" or not os.environ.get("HF_LOCAL_MODEL_PATH"),
    reason="Set HF_RUN_INTEGRATION=1 and HF_LOCAL_MODEL_PATH to run the local model.",
)


def test_local_chat_model_answers() -> None:
    from langchain_core.messages import HumanMessage

    from figma_extractor.llm.config import LlmConfig
    from figma_extractor.llm.providers.huggingface import build

    config = LlmConfig.load(
        overrides={
            "enabled": True,
            "provider": "huggingface",
            "provider_options": {"backend": "local", "quantization": os.environ.get("HF_QUANTIZATION", "none")},
            "tasks": {"screen_classification": True},
        }
    )
    session = build(config)
    message = session.model.invoke([HumanMessage(content="Reply with the single word ready.")])
    assert str(message.content).strip()
