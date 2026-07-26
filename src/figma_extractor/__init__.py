"""
figma_extractor
===============

Extract design tokens, screens, components, and assets from Figma.

CLI name: ``figma-extractor``
Import name: ``figma_extractor``

Quick start
-----------

CLI::

    figma-extractor extract --file ./design.fig --output ./out --render
    figma-extractor render --dir ./out
    figma-extractor info --dir ./out

Python::

    from figma_extractor import extract, info, render

    extract(file="./design.fig", output="./out", render=True)
    details = info("./out")
    print(details["summary"])
"""

from figma_extractor.api import export_screenshots, extract, info, render

__version__ = "1.8.1"
__all__ = ["extract", "info", "render", "export_screenshots", "__version__"]
