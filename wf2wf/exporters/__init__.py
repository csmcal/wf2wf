"""
wf2wf.exporters – pluggable back-ends that serialise a `Workflow` IR to a
specific engine format.

Example:
    from wf2wf.exporters import load
    load('dagman').from_workflow(wf, out_dir='out/')
"""

from importlib import import_module
from typing import Dict

__all__ = [
    'load',
    'snakemake',
    'dagman',
    'nextflow',
    'cwl',
    'wdl',
    'galaxy',
    'bco',
]

_plugins: Dict[str, str] = {
    'snakemake': '.snakemake',
    'dagman': '.dagman',
    'nextflow': '.nextflow',
    'cwl': '.cwl',
    'wdl': '.wdl',
    'galaxy': '.galaxy',
    'bco': '.bco',
}

def load(fmt: str):
    if fmt not in _plugins:
        raise ValueError(f"Unknown exporter format '{fmt}'.")
    return import_module(__name__ + _plugins[fmt]) 