"""
figma_extractor
===============

Extract design tokens, screens, components, and assets from Figma.

CLI name: ``figma-extractor``
Import name: ``figma_extractor``

Quick start
-----------

CLI::

    figma-extractor extract --file ./design.fig --output ./out
    figma-extractor info --dir ./out

Python::

    from figma_extractor import extract, info

    extract(file="./design.fig", output="./out")
    details = info("./out")
    print(details["summary"])
"""

from figma_extractor.api import extract, info

__version__ = "2.1.0"
__all__ = ["extract", "info", "__version__"]
