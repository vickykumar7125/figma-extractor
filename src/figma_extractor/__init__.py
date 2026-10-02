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

__version__ = "2.2.1"
__all__ = ["extract", "info", "annotate", "__version__"]


def __getattr__(name):
    if name in {"extract", "info"}:
        from figma_extractor.api import extract, info

        return {"extract": extract, "info": info}[name]
    raise AttributeError(name)


def annotate(*args, **kwargs):
    """Run optional LLM annotation. Import is deferred so extract stays provider-free."""
    from figma_extractor.llm.annotate import annotate as run_annotate

    return run_annotate(*args, **kwargs)
