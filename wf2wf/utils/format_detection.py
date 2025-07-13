"""
wf2wf.utils.format_detection – Shared format detection utilities.

This module provides centralized format detection functionality that can be
used by both the CLI and individual importers/exporters.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, List
import warnings


# Format detection mappings
INPUT_FORMAT_MAP = {
    ".smk": "snakemake",
    ".snakefile": "snakemake",
    ".dag": "dagman",
    ".nf": "nextflow",
    ".cwl": "cwl",
    ".wdl": "wdl",
    ".ga": "galaxy",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
}

OUTPUT_FORMAT_MAP = {
    ".dag": "dagman",
    ".smk": "snakemake",
    ".nf": "nextflow",
    ".cwl": "cwl",
    ".wdl": "wdl",
    ".ga": "galaxy",
    ".bco": "bco",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
}

# Format-specific filename patterns
FORMAT_FILENAMES = {
    "snakemake": ["snakefile", "makefile"],
    "dagman": ["dagfile"],
    "nextflow": ["main.nf", "workflow.nf"],
    "cwl": ["workflow.cwl", "tool.cwl"],
    "wdl": ["workflow.wdl", "task.wdl"],
    "galaxy": ["tool.xml", "workflow.ga"],
}


def detect_format_from_content(path: Path) -> Optional[str]:
    """
    Detect workflow format by examining file content.
    
    This function looks for format-specific patterns in the file content
    to determine the actual format, regardless of file extension.
    
    Args:
        path: Path to the workflow file
        
    Returns:
        Detected format name or None if not detected
    """
    try:
        content = path.read_text(encoding='utf-8', errors='ignore')
        content_lower = content.lower()
        
        # IR format patterns (JSON/YAML with wf2wf structure) - check FIRST
        if any(pattern in content_lower for pattern in [
            '"name":', '"version":', '"tasks":', '"edges":',
            '"inputs":', '"outputs":', '"requirements":',
            '"provenance":', '"documentation":'
        ]):
            # Check if it's a complete IR structure
            if '"tasks":' in content_lower and '"edges":' in content_lower:
                return "json" if path.suffix.lower() in [".json"] else "yaml"
        
        # Snakemake patterns
        if any(pattern in content_lower for pattern in [
            'rule ', 'input:', 'output:', 'shell:', 'run:', 'script:',
            'wildcards:', 'params:', 'threads:', 'resources:',
            'conda:', 'container:', 'benchmark:', 'log:'
        ]):
            return "snakemake"
        
        # DAGMan patterns
        if any(pattern in content_lower for pattern in [
            'job ', 'parent ', 'child ', 'retry ', 'priority ',
            'executable =', 'request_cpus =', 'request_memory =',
            'universe =', 'queue'
        ]):
            return "dagman"
        
        # Nextflow patterns
        if any(pattern in content_lower for pattern in [
            'process ', 'workflow ', 'channel ', 'publishdir ',
            'input:', 'output:', 'script:', 'shell:', 'exec:',
            'publishdir', 'tag ', 'label '  # Add space after tag and label to avoid JSON field matches
        ]):
            return "nextflow"
        
        # CWL patterns
        if any(pattern in content_lower for pattern in [
            'cwlversion:', 'class:', 'inputs:', 'outputs:', 'steps:',
            'requirements:', 'hints:', 'basecommand:', 'arguments:',
            'stdin:', 'stdout:', 'stderr:', 'env:', 'doc:'
        ]):
            return "cwl"
        
        # WDL patterns
        if any(pattern in content_lower for pattern in [
            'workflow ', 'task ', 'call ', 'scatter ', 'if ',
            'input {', 'output {', 'runtime {', 'command {',
            'version', 'import '
        ]):
            return "wdl"
        
        # Galaxy patterns
        if any(pattern in content_lower for pattern in [
            'tool id=', 'tool name=', 'tool version=',
            '<tool', '</tool>', '<param', '</param>',
            '<inputs>', '</inputs>', '<outputs>', '</outputs>'
        ]):
            return "galaxy"
        
        # IR format patterns (JSON/YAML with wf2wf structure)
        if any(pattern in content_lower for pattern in [
            '"name":', '"version":', '"tasks":', '"edges":',
            '"inputs":', '"outputs":', '"requirements":',
            '"provenance":', '"documentation":'
        ]):
            # Check if it's a complete IR structure
            if '"tasks":' in content_lower and '"edges":' in content_lower:
                return "json" if path.suffix.lower() in [".json"] else "yaml"
        
        return None
        
    except (UnicodeDecodeError, IOError, OSError):
        # File is binary or unreadable
        return None


def detect_input_format(path: Path) -> Optional[str]:
    """
    Auto-detect input format from file extension and content.
    
    Args:
        path: Path to the input file
        
    Returns:
        Detected format name or None if not detected
    """
    suffix = path.suffix.lower()
    name = path.name.lower()

    # Check suffix first
    if suffix in INPUT_FORMAT_MAP:
        detected_format = INPUT_FORMAT_MAP[suffix]
        content_format = detect_format_from_content(path)
        if content_format and content_format != detected_format:
            warnings.warn(
                f"File '{path}' has extension '{suffix}' (detected as {detected_format}), "
                f"but content appears to be {content_format}. Proceeding with {detected_format} based on '{suffix}' extension."
            )
        return detected_format

    # Check specific filenames without extensions
    for format_name, filenames in FORMAT_FILENAMES.items():
        if name in filenames:
            return format_name

    # If no extension match, try content-based detection
    return detect_format_from_content(path)


def detect_output_format(path: Path) -> Optional[str]:
    """
    Auto-detect output format from file extension.
    
    Args:
        path: Path to the output file
        
    Returns:
        Detected format name or None if not detected
    """
    suffix = path.suffix.lower()
    return OUTPUT_FORMAT_MAP.get(suffix)


def get_supported_extensions(format_type: str = "input") -> Dict[str, List[str]]:
    """
    Get supported extensions for a given format type.
    
    Args:
        format_type: Type of format ("input" or "output")
        
    Returns:
        Dictionary mapping format names to lists of supported extensions
    """
    if format_type == "input":
        format_map = INPUT_FORMAT_MAP
    elif format_type == "output":
        format_map = OUTPUT_FORMAT_MAP
    else:
        raise ValueError(f"Invalid format_type: {format_type}. Must be 'input' or 'output'")
    
    # Invert the mapping
    extensions_by_format = {}
    for ext, fmt in format_map.items():
        if fmt not in extensions_by_format:
            extensions_by_format[fmt] = []
        extensions_by_format[fmt].append(ext)
    
    return extensions_by_format


def can_import(path: Path, supported_extensions: List[str]) -> bool:
    """
    Check if a file can be imported based on its extension.
    
    Args:
        path: Path to the file
        supported_extensions: List of supported extensions (with dots)
        
    Returns:
        True if the file can be imported
    """
    return path.suffix.lower() in supported_extensions


def get_format_from_extension(extension: str, format_type: str = "input") -> Optional[str]:
    """
    Get format name from file extension.
    
    Args:
        extension: File extension (with or without dot)
        format_type: Type of format ("input" or "output")
        
    Returns:
        Format name or None if not supported
    """
    # Normalize extension
    if not extension.startswith('.'):
        extension = '.' + extension
    
    if format_type == "input":
        return INPUT_FORMAT_MAP.get(extension.lower())
    elif format_type == "output":
        return OUTPUT_FORMAT_MAP.get(extension.lower())
    else:
        raise ValueError(f"Invalid format_type: {format_type}. Must be 'input' or 'output'") 