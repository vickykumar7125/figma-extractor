"""Extraction stages that turn a decoded node stream into the output root."""

from figma_extractor.extract.flow import build_ui_flow
from figma_extractor.extract.images import build_images
from figma_extractor.extract.structure import build_structure
from figma_extractor.extract.tokens import build_tokens
from figma_extractor.extract.trees import build_screen_trees

__all__ = [
    "build_images",
    "build_screen_trees",
    "build_structure",
    "build_tokens",
    "build_ui_flow",
]
