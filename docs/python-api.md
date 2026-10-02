# Python API

```python
from figma_extractor import extract, info, annotate
from figma_extractor.llm.config import LlmConfig, LlmTasks

extract(file="./design.fig", output="./out")
extract(remote="ABC123", output="./out", api_key="figd_xxx")

print(info("./out")["summary"])

# Deterministic. Does not import a provider SDK.
annotate("./out", LlmConfig(enabled=False))

# Calls the selected provider. Requires that extra to be installed.
annotate(
    "./out",
    LlmConfig(
        enabled=True,
        provider="ollama",
        model="llama3.2",
        tasks=LlmTasks(screen_classification=True),
    ),
)
```

`from figma_extractor import extract, info` does not import LangChain, LangGraph, or torch. `annotate` imports them only when `enabled=True`.
