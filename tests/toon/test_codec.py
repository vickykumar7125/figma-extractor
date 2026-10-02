"""The included TOON codec encodes and decodes the shapes annotation sends."""

from __future__ import annotations

import pytest

from figma_extractor.toon import ToonDecodeError, decode, encode
from figma_extractor.toon.types import DecodeOptions


def test_object_round_trip() -> None:
    value = {"name": "Home", "width": 800, "ready": True, "note": None}
    text = encode(value)
    assert text == "name: Home\nwidth: 800\nready: true\nnote: null"
    assert decode(text) == value


def test_table_round_trip_with_length_marker() -> None:
    rows = [
        {"id": "1:1", "name": "Home, page", "role": "page"},
        {"id": "1:2", "name": "Login", "role": "page"},
    ]
    text = encode(rows, {"lengthMarker": "#"})
    assert text.splitlines()[0] == "[#2]{id,name,role}:"
    assert decode(text) == rows


def test_tab_delimiter_is_marked_in_the_header() -> None:
    text = encode([1, 2, 3], {"delimiter": "\t", "lengthMarker": "#"})
    assert text.startswith("[#3\t]:")
    assert decode(text) == [1, 2, 3]


def test_nested_layout_round_trip() -> None:
    value = {
        "id": "1:1",
        "children": [{"id": "2:2", "type": "VECTOR", "name": "star"}],
    }
    assert decode(encode(value, {"lengthMarker": "#"})) == value


def test_bad_text_is_rejected() -> None:
    with pytest.raises(ToonDecodeError):
        decode("screens[#2]{id}:\n  only-one", DecodeOptions(strict=True))
