"""wf2wf.exporters – Export workflows from IR to target formats.

This module provides exporters for converting wf2wf intermediate representation
workflows to various target formats including CWL, DAGMan, Nextflow, WDL, and Galaxy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Type

from wf2wf.core import Workflow
from wf2wf.exporters.base import BaseExporter
from wf2wf.exporters.cwl import CWLExporter
from wf2wf.exporters.dagman import DAGManExporter
from wf2wf.exporters.nextflow import NextflowExporter
from wf2wf.exporters.snakemake import SnakemakeExporter
from wf2wf.exporters.wdl import WDLExporter
from wf2wf.exporters.galaxy import GalaxyExporter
from wf2wf.exporters.bco import BCOExporter

# Registry of available exporters
_EXPORTERS: Dict[str, Type[BaseExporter]] = {
    "cwl": CWLExporter,
    "dagman": DAGManExporter,
    "nextflow": NextflowExporter,
    "snakemake": SnakemakeExporter,
    "wdl": WDLExporter,
    "galaxy": GalaxyExporter,
    "bco": BCOExporter,
}

# Format aliases
_FORMAT_ALIASES = {
    "condor": "dagman",
    "htcondor": "dagman",
    "nf": "nextflow",
    "workflow": "cwl",
    "ga": "galaxy",
}


def get_exporter(format_name: str) -> Type[BaseExporter]:
    """Get exporter class for the specified format.
    
    Args:
        format_name: Name of the target format
        
    Returns:
        Exporter class
        
    Raises:
        ValueError: If format is not supported
    """
    # Check aliases first
    if format_name in _FORMAT_ALIASES:
        format_name = _FORMAT_ALIASES[format_name]
    
    if format_name not in _EXPORTERS:
        supported = ", ".join(sorted(_EXPORTERS.keys()))
        raise ValueError(f"Unsupported export format '{format_name}'. Supported: {supported}")
    
    return _EXPORTERS[format_name]


def list_formats() -> list[str]:
    """List all supported export formats."""
    return sorted(_EXPORTERS.keys())


def export_workflow(
    workflow: Workflow,
    output_path: Path,
    format_name: str,
    *,
    interactive: bool = False,
    verbose: bool = False,
    **opts: Any,
) -> None:
    """Export workflow to target format using the new shared infrastructure.
    
    Args:
        workflow: The workflow to export
        output_path: Path for the output file
        format_name: Target format name
        interactive: Enable interactive mode
        verbose: Enable verbose output
        **opts: Format-specific options
        
    Raises:
        ValueError: If format is not supported
        RuntimeError: If export fails
    """
    exporter_class = get_exporter(format_name)
    exporter = exporter_class(interactive=interactive, verbose=verbose)
    exporter.export_workflow(workflow, output_path, **opts)


def load(format_name: str) -> Type[BaseExporter]:
    """Load exporter for the specified format (backward compatibility).
    
    Args:
        format_name: Name of the target format
        
    Returns:
        Exporter class
        
    Raises:
        ValueError: If format is not supported
    """
    return get_exporter(format_name)


# Legacy functions for backward compatibility
def from_workflow(workflow: Workflow, output_path: Path, format_name: str, **opts: Any) -> None:
    """Legacy function for backward compatibility."""
    export_workflow(workflow, output_path, format_name, **opts)


# Individual exporter functions for backward compatibility
def export_cwl(workflow: Workflow, output_path: Path, **opts: Any) -> None:
    """Export workflow to CWL format."""
    export_workflow(workflow, output_path, "cwl", **opts)


def export_dagman(workflow: Workflow, output_path: Path, **opts: Any) -> None:
    """Export workflow to DAGMan format."""
    export_workflow(workflow, output_path, "dagman", **opts)


def export_nextflow(workflow: Workflow, output_path: Path, **opts: Any) -> None:
    """Export workflow to Nextflow format."""
    export_workflow(workflow, output_path, "nextflow", **opts)


def export_snakemake(workflow: Workflow, output_path: Path, **opts: Any) -> None:
    """Export workflow to Snakemake format."""
    export_workflow(workflow, output_path, "snakemake", **opts)


def export_wdl(workflow: Workflow, output_path: Path, **opts: Any) -> None:
    """Export workflow to WDL format."""
    export_workflow(workflow, output_path, "wdl", **opts)


def export_galaxy(workflow: Workflow, output_path: Path, **opts: Any) -> None:
    """Export workflow to Galaxy format."""
    export_workflow(workflow, output_path, "galaxy", **opts)


def export_bco(workflow: Workflow, output_path: Path, **opts: Any) -> None:
    """Export workflow to BCO format."""
    export_workflow(workflow, output_path, "bco", **opts)


__all__ = [
    "BaseExporter",
    "CWLExporter",
    "DAGManExporter", 
    "NextflowExporter",
    "SnakemakeExporter",
    "WDLExporter",
    "GalaxyExporter",
    "BCOExporter",
    "get_exporter",
    "list_formats",
    "export_workflow",
    "load",           # Backward compatibility
    "from_workflow",  # Legacy
    "export_cwl",     # Legacy
    "export_dagman",  # Legacy
    "export_nextflow", # Legacy
    "export_snakemake", # Legacy
    "export_wdl",     # Legacy
    "export_galaxy",  # Legacy
    "export_bco",     # Legacy
]
