"""Extraction stages that turn a decoded node stream into ``design/``."""

from figma_extractor.extract.images import build_images
from figma_extractor.extract.render import render_screenshots
from figma_extractor.extract.screenshots import build_screenshots
from figma_extractor.extract.split import split_screen_boards
from figma_extractor.extract.structure import build_structure
from figma_extractor.extract.tokens import build_tokens
from figma_extractor.extract.trees import build_screen_trees

__all__ = [
    "build_images",
    "build_screenshots",
    "build_screen_trees",
    "build_structure",
    "build_tokens",
    "render_screenshots",
    "split_screen_boards",
]
