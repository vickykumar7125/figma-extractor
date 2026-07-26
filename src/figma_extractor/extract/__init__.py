"""Extraction stages that turn a decoded node stream into ``design/``."""

from figma_extractor.extract.images import build_images
from figma_extractor.extract.structure import build_structure
from figma_extractor.extract.tokens import build_tokens

__all__ = ["build_images", "build_structure", "build_tokens"]
