"""
wf2wf.importers – pluggable input parsers that build a `Workflow` IR object.

Usage example:
    from wf2wf.importers import load
    wf = load('snakemake').to_workflow('Snakefile')
"""

from importlib import import_module
from typing import Dict

__all__ = [
    "load",
    "snakemake",
    "dagman",
    "nextflow",
    "cwl",
    "wdl",
    "galaxy",
]

_plugins: Dict[str, str] = {
    "snakemake": ".snakemake",
    "dagman": ".dagman",
    "nextflow": ".nextflow",
    "cwl": ".cwl",
    "wdl": ".wdl",
    "galaxy": ".galaxy",
}


def load(fmt: str):
    """Dynamically import the requested importer sub-module."""
    if fmt not in _plugins:
        raise ValueError(
            f"Unsupported importer format '{fmt}'. Available: {list(_plugins)}"
        )
    return import_module(__name__ + _plugins[fmt])
