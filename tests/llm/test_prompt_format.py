"""Prompt context is a compact table and stays smaller than the same JSON."""

from __future__ import annotations

import json

from figma_extractor.llm.prompt_format import encode_context, prompt_messages
from figma_extractor.toon import decode


def test_user_context_is_a_table_and_shorter_than_json() -> None:
    screens = [
        {"id": f"1:{index}", "name": f"Screen {index}", "role": "page", "width": 800}
        for index in range(8)
    ]
    payload = {"screens": screens}
    messages = prompt_messages("screen_classification", payload, [])
    user = messages[1]["content"]
    packed = json.dumps({"task": "screen_classification", "context": payload})
    assert len(user) < len(packed)
    restored = decode(user)
    assert restored["task"] == "screen_classification"
    assert restored["context"]["screens"][0]["name"] == "Screen 0"
    assert "screens[#8]{id,name,role,width}:" in user
    assert "JSON object" in messages[0]["content"]
    assert "[#3]{id,name}" in messages[0]["content"]


def test_nested_layout_keeps_children_under_their_parent() -> None:
    text = encode_context(
        {
            "id": "1:1",
            "children": [{"id": "2:2", "type": "VECTOR", "name": "star"}],
        }
    )
    assert text.splitlines() == [
        'id: "1:1"',
        "children[#1]{id,type,name}:",
        '  "2:2",VECTOR,star',
    ]


def test_quoted_names_keep_a_row_together() -> None:
    text = encode_context([{"name": "Home, page"}])
    assert text.splitlines()[1] == '  "Home, page"'


def test_invalid_feedback_stays_structured() -> None:
    messages = prompt_messages(
        "screen_classification",
        {"screens": []},
        [{"task": "screen_classification", "ok": False, "problems": ["missing role"]}],
    )
    restored = decode(messages[1]["content"])
    assert restored["invalid"] == [["missing role"]]
    assert restored["context"] == {"screens": []}
