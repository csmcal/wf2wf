#!/usr/bin/env python3
"""
wf2wf.cli – Unified command-line interface

Implements the CLI described in the design document:
    wf2wf convert --in-format snakemake --out-format dagman \
                  --snakefile Snakefile --out workflow.dag

The CLI follows the IR-based architecture: engine-A → IR → engine-B
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional, Union
import os
import zipfile
import hashlib
import datetime
import shutil
import time
import platform
import logging
import subprocess
import tempfile

import click

# Handle imports when running as script vs installed package
try:
    from wf2wf.core import Workflow
    from wf2wf.validate import validate_workflow
except ImportError:
    # Running as script, use relative imports
    import pathlib

    # Add current directory to path for imports
    current_dir = pathlib.Path(__file__).parent
    sys.path.insert(0, str(current_dir))

    from core import Workflow
    from validate import validate_workflow


# Import all available importers and exporters
try:
    from wf2wf.importers import snakemake as snakemake_importer

    SNAKEMAKE_AVAILABLE = True
except ImportError:
    try:
        from importers import snakemake as snakemake_importer

        SNAKEMAKE_AVAILABLE = True
    except ImportError:
        SNAKEMAKE_AVAILABLE = False
        snakemake_importer = None

try:
    from wf2wf.importers import cwl as cwl_importer

    CWL_AVAILABLE = True
except ImportError:
    try:
        from importers import cwl as cwl_importer

        CWL_AVAILABLE = True
    except ImportError:
        CWL_AVAILABLE = False
        cwl_importer = None

try:
    from wf2wf.importers import nextflow as nextflow_importer

    NEXTFLOW_AVAILABLE = True
except ImportError:
    try:
        from importers import nextflow as nextflow_importer

        NEXTFLOW_AVAILABLE = True
    except ImportError:
        NEXTFLOW_AVAILABLE = False
        nextflow_importer = None

try:
    from wf2wf.importers import dagman as dagman_importer

    DAGMAN_IMPORT_AVAILABLE = True
except ImportError:
    try:
        from importers import dagman as dagman_importer

        DAGMAN_IMPORT_AVAILABLE = True
    except ImportError:
        DAGMAN_IMPORT_AVAILABLE = False
        dagman_importer = None

try:
    from wf2wf.importers import wdl as wdl_importer

    WDL_AVAILABLE = True
except ImportError:
    try:
        from importers import wdl as wdl_importer

        WDL_AVAILABLE = True
    except ImportError:
        WDL_AVAILABLE = False
        wdl_importer = None

try:
    from wf2wf.importers import galaxy as galaxy_importer

    GALAXY_AVAILABLE = True
except ImportError:
    try:
        from importers import galaxy as galaxy_importer

        GALAXY_AVAILABLE = True
    except ImportError:
        GALAXY_AVAILABLE = False
        galaxy_importer = None

try:
    from wf2wf.exporters.dagman import DAGManExporter as dagman_exporter

    DAGMAN_EXPORT_AVAILABLE = True
except ImportError:
    try:
        from exporters.dagman import DAGManExporter as dagman_exporter

        DAGMAN_EXPORT_AVAILABLE = True
    except ImportError:
        DAGMAN_EXPORT_AVAILABLE = False
        dagman_exporter = None

try:
    from wf2wf.exporters.snakemake import SnakemakeExporter as snakemake_exporter

    SNAKEMAKE_EXPORT_AVAILABLE = True
except ImportError:
    try:
        from exporters.snakemake import SnakemakeExporter as snakemake_exporter

        SNAKEMAKE_EXPORT_AVAILABLE = True
    except ImportError:
        SNAKEMAKE_EXPORT_AVAILABLE = False
        snakemake_exporter = None

try:
    from wf2wf.exporters.cwl import CWLExporter as cwl_exporter

    CWL_EXPORT_AVAILABLE = True
except ImportError:
    try:
        from exporters.cwl import CWLExporter as cwl_exporter

        CWL_EXPORT_AVAILABLE = True
    except ImportError:
        CWL_EXPORT_AVAILABLE = False
        cwl_exporter = None

try:
    from wf2wf.exporters.nextflow import NextflowExporter as nextflow_exporter

    NEXTFLOW_EXPORT_AVAILABLE = True
except ImportError:
    try:
        from exporters.nextflow import NextflowExporter as nextflow_exporter

        NEXTFLOW_EXPORT_AVAILABLE = True
    except ImportError:
        NEXTFLOW_EXPORT_AVAILABLE = False
        nextflow_exporter = None

try:
    from wf2wf.exporters.wdl import WDLExporter as wdl_exporter

    WDL_EXPORT_AVAILABLE = True
except ImportError:
    try:
        from exporters.wdl import WDLExporter as wdl_exporter

        WDL_EXPORT_AVAILABLE = True
    except ImportError:
        WDL_EXPORT_AVAILABLE = False
        wdl_exporter = None

try:
    from wf2wf.exporters.galaxy import GalaxyExporter as galaxy_exporter

    GALAXY_EXPORT_AVAILABLE = True
except ImportError:
    try:
        from exporters.galaxy import GalaxyExporter as galaxy_exporter

        GALAXY_EXPORT_AVAILABLE = True
    except ImportError:
        GALAXY_EXPORT_AVAILABLE = False
        galaxy_exporter = None

# Import adaptation system
try:
    from wf2wf.adaptation import adapt_workflow, AdaptationRegistry, EnvironmentMapper
    ADAPTATION_AVAILABLE = True
except ImportError:
    try:
        from adaptation import adapt_workflow, AdaptationRegistry, EnvironmentMapper
        ADAPTATION_AVAILABLE = True
    except ImportError:
        ADAPTATION_AVAILABLE = False
        adapt_workflow = None
        AdaptationRegistry = None
        EnvironmentMapper = None


# Import shared format detection utilities
from wf2wf.utils.format_detection import (
    detect_input_format,
    detect_output_format,
    detect_format_from_content,
    INPUT_FORMAT_MAP,
    OUTPUT_FORMAT_MAP
)


logger = logging.getLogger(__name__)


def get_importer(fmt: str):
    """Get the appropriate importer for the given format."""
    importers = {
        "snakemake": snakemake_importer if SNAKEMAKE_AVAILABLE else None,
        "cwl": cwl_importer if CWL_AVAILABLE else None,
        "nextflow": nextflow_importer if NEXTFLOW_AVAILABLE else None,
        "dagman": dagman_importer if DAGMAN_IMPORT_AVAILABLE else None,
        "wdl": wdl_importer if WDL_AVAILABLE else None,
        "galaxy": galaxy_importer if GALAXY_AVAILABLE else None,
        "json": None,  # JSON handled specially
        "yaml": None,  # YAML handled specially
    }

    importer = importers.get(fmt)
    if importer is None and fmt not in ["json", "yaml"]:
        if fmt == "snakemake":
            raise click.ClickException(
                f"Snakemake importer is not available. Please install snakemake: 'pip install snakemake' or 'conda install snakemake'"
            )
        else:
            raise click.ClickException(
                f"Importer for format '{fmt}' is not available or not implemented"
            )

    return importer


def get_exporter(fmt: str):
    """Get the appropriate exporter for the given format."""
    exporters = {
        "dagman": dagman_exporter if DAGMAN_EXPORT_AVAILABLE else None,
        "snakemake": snakemake_exporter if SNAKEMAKE_EXPORT_AVAILABLE else None,
        "cwl": cwl_exporter if CWL_EXPORT_AVAILABLE else None,
        "nextflow": nextflow_exporter if NEXTFLOW_EXPORT_AVAILABLE else None,
        "wdl": wdl_exporter if WDL_EXPORT_AVAILABLE else None,
        "galaxy": galaxy_exporter if GALAXY_EXPORT_AVAILABLE else None,
        "bco": None,  # will be resolved via exporters.get_exporter
        "json": None,
        "yaml": None,
    }

    exporter = exporters.get(fmt)
    if exporter is None:
        if fmt in ["json", "yaml"]:
            return None
        if fmt == "snakemake":
            raise click.ClickException(
                f"Snakemake exporter is not available. Please install snakemake: 'pip install snakemake' or 'conda install snakemake'"
            )
        try:
            from wf2wf.exporters import get_exporter as _get_exporter

            exporter = _get_exporter(fmt)
        except Exception as e:
            raise click.ClickException(
                f"Exporter for format '{fmt}' is not available or not implemented: {e}"
            )

    return exporter


def load_workflow_from_json_yaml(path: Path) -> Workflow:
    """Load workflow from JSON or YAML file."""
    try:
        if path.suffix.lower() in [".yaml", ".yml"]:
            import yaml

            data = yaml.safe_load(path.read_text())
        else:  # JSON
            data = json.loads(path.read_text())

        return Workflow.from_dict(data)
    except Exception as e:
        raise click.ClickException(f"Failed to load workflow from {path}: {e}")


def save_workflow_to_json_yaml(wf: Workflow, path: Path) -> None:
    """Save workflow to JSON or YAML file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.suffix.lower() in [".yaml", ".yml"]:
            import yaml

            data = wf.to_dict()
            path.write_text(yaml.dump(data, default_flow_style=False, indent=2))
        else:  # JSON
            wf.save_json(path)
    except Exception as e:
        raise click.ClickException(f"Failed to save workflow to {path}: {e}")


@click.group()
@click.version_option()
def cli():
    """wf2wf - Workflow-to-Workflow Converter

    Convert workflows between different formats using a unified intermediate representation.

    Supported formats:
    - Snakemake (.smk, .snakefile)
    - HTCondor DAGMan (.dag)
    - CWL (.cwl)
    - Nextflow (.nf)
    - WDL (.wdl)
    - Galaxy (.ga)
    - JSON (.json) - IR format
    - YAML (.yaml, .yml) - IR format
    """
    pass


@cli.command()
@click.option(
    "--input",
    "-i",
    "input_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to the input workflow file",
)
@click.option(
    "--in-format",
    "--input-format",
    "input_format",
    type=click.Choice(
        ["snakemake", "dagman", "nextflow", "cwl", "wdl", "galaxy", "json", "yaml"]
    ),
    help="Format of the input workflow (auto-detected if not specified)",
)
@click.option(
    "--out",
    "-o",
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    help="Path to output workflow file (auto-generated if not specified)",
)
@click.option(
    "--out-format",
    "--output-format",
    "output_format",
    type=click.Choice(
        [
            "snakemake",
            "dagman",
            "nextflow",
            "cwl",
            "wdl",
            "galaxy",
            "bco",
            "json",
            "yaml",
        ]
    ),
    help="Desired output format (auto-detected from output path if not specified)",
)
# Snakemake-specific options
@click.option(
    "--snakefile",
    type=click.Path(exists=True, path_type=Path),
    help="Path to Snakefile (alias for --input when input format is snakemake)",
)
@click.option(
    "--configfile",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Snakemake config file",
)
@click.option(
    "--workdir",
    "-d",
    type=click.Path(path_type=Path),
    help="Working directory for Snakemake workflow",
)
@click.option(
    "--cores",
    type=int,
    default=1,
    help="Number of cores for Snakemake operations (default: 1)",
)
@click.option(
    "--snakemake-args",
    multiple=True,
    help="Additional arguments to pass to snakemake commands (can be used multiple times)",
)
@click.option(
    "--parse-only",
    is_flag=True,
    help="Parse Snakefile without requiring snakemake executable (limited functionality)",
)
@click.option(
    "--resource-profile",
    type=click.Choice(["shared", "cluster", "cloud", "hpc", "gpu", "memory_intensive", "io_intensive"]),
    help="Apply resource profile to fill in missing resource specifications",
)
@click.option(
    "--infer-resources",
    is_flag=True,
    help="Infer resource requirements from command/script content",
)
@click.option(
    "--validate-resources",
    is_flag=True,
    help="Validate resource specifications and report issues",
)
@click.option(
    "--target-environment",
    type=click.Choice(["shared_filesystem", "distributed_computing", "hybrid", "cloud_native", "unknown"]),
    help="Target execution environment (auto-detected from output format if not specified)",
)
# DAGMan export options
@click.option(
    "--scripts-dir",
    type=click.Path(path_type=Path),
    help="Directory for generated wrapper scripts (DAGMan export)",
)
@click.option(
    "--default-memory",
    default="4GB",
    help="Default memory request for jobs (default: 4GB)",
)
@click.option(
    "--default-disk",
    default="4GB",
    help="Default disk request for jobs (default: 4GB)",
)
@click.option(
    "--default-cpus",
    type=int,
    default=1,
    help="Default CPU request for jobs (default: 1)",
)
@click.option(
    "--inline-submit",
    is_flag=True,
    help="Use inline submit descriptions in DAG file instead of separate .sub files",
)
# Generic options
@click.option(
    "--validate/--no-validate",
    default=True,
    help="Validate workflow against JSON schema (default: enabled)",
)
@click.option(
    "--fail-on-loss",
    is_flag=True,
    help="Exit with non-zero status if any information loss occurred during conversion",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--debug", is_flag=True, help="Enable debug output")
@click.option(
    "--auto-env",
    type=click.Choice(["off", "reuse", "build"], case_sensitive=False),
    default="off",
    help="Automatically build or reuse Conda/container images and replace env specs (Phase2)",
)
@click.option(
    "--oci-backend",
    type=click.Choice(["buildx", "podman", "buildah"]),
    default="buildx",
    help="OCI builder backend to use when --auto-env is active (default: buildx)",
)
@click.option(
    "--push-registry", default="", help="Registry to push images (enables push)"
)
@click.option(
    "--confirm-push",
    is_flag=True,
    help="Actually push to registry; without this only probing is performed",
)
@click.option(
    "--apptainer",
    is_flag=True,
    help="Convert OCI image to Apptainer SIF and reference that",
)
@click.option(
    "--sbom",
    is_flag=True,
    help="Generate SBOM via syft and attach to environment metadata",
)
@click.option(
    "--platform",
    default="linux/amd64",
    help="Target platform for OCI buildx/buildah (e.g. linux/arm64)",
)
@click.option(
    "--build-cache",
    default="",
    help="Remote cache location for BuildKit --build-cache",
)
@click.option(
    "--report-md",
    "report_md",
    type=click.Path(path_type=Path),
    help="Write human-readable Markdown report to this file",
)
@click.option(
    "--interactive",
    is_flag=True,
    help="Enable interactive prompting for missing resource specifications, environment configurations, and execution parameters",
)
@click.option(
    "--intent",
    multiple=True,
    help="Ontology IRI describing workflow intent (can repeat)",
)
# Adaptation options
@click.option(
    "--adapt-environments",
    is_flag=True,
    default=True,
    help="Enable environment adaptation (default: enabled)",
)
@click.option(
    "--adaptation-strategy",
    type=click.Choice(["conservative", "aggressive", "balanced"]),
    default="balanced",
    help="Adaptation strategy for resource scaling (default: balanced)",
)
@click.option(
    "--source-environment",
    type=click.Choice(["shared_filesystem", "distributed_computing", "hybrid", "cloud_native", "unknown"]),
    help="Source execution environment (auto-detected if not specified)",
)
@click.option(
    "--adaptation-report",
    type=click.Path(path_type=Path),
    help="Write adaptation report to this file",
)
def convert(
    input_path: Path,
    input_format: Optional[str],
    output_path: Optional[Path],
    output_format: Optional[str],
    snakefile: Optional[Path],
    configfile: Optional[Path],
    workdir: Optional[Path],
    cores: int,
    snakemake_args: tuple,
    parse_only: bool,
    resource_profile: Optional[str],
    infer_resources: bool,
    validate_resources: bool,
    target_environment: Optional[str],
    scripts_dir: Optional[Path],
    default_memory: str,
    default_disk: str,
    default_cpus: int,
    validate: bool,
    verbose: bool,
    debug: bool,
    inline_submit: bool,
    fail_on_loss: bool,
    auto_env: str,
    oci_backend: str,
    push_registry: str,
    confirm_push: bool,
    apptainer: bool,
    sbom: bool,
    platform: str,
    build_cache: str,
    intent: tuple,
    report_md: Union[Path, None],
    interactive: bool,
    # Adaptation parameters
    adapt_environments: bool,
    adaptation_strategy: str,
    source_environment: Optional[str],
    adaptation_report: Optional[Path],
):
    """Convert workflows between different formats.

    Examples:
    \b
        # Single input file (defaults to IR format with warning)
        wf2wf convert -i workflow.smk

        # Snakemake to DAGMan
        wf2wf convert -i workflow.smk --out-format dagman

        # Auto-detect formats from extensions
        wf2wf convert -i Snakefile -o workflow.dag

        # With additional options
        wf2wf convert -i workflow.smk -o pipeline.dag --configfile config.yaml --verbose

        # Convert to intermediate JSON format
        wf2wf convert -i workflow.smk -o workflow.json
    """

    # Set prompt module interactive flag early
    from wf2wf import prompt as _prompt_mod
    from wf2wf import prompt as _prompt

    _prompt_mod.set_interactive(interactive)

    # Handle snakefile alias
    if snakefile and not input_path:
        input_path = snakefile
        input_format = "snakemake"
    elif snakefile and input_path:
        click.echo(
            "Warning: Both --input and --snakefile specified. Using --input.",
            err=True,
        )

    # Auto-detect input format
    if not input_format:
        input_format = detect_input_format(input_path)
        if not input_format:
            raise click.ClickException(
                f"Could not auto-detect input format from {input_path}. "
                "Please specify --in-format."
            )
        if verbose:
            click.echo(f"Auto-detected input format: {input_format}")

    # Generate output path if not provided
    if not output_path:
        if output_format:
            # Generate appropriate extension
            ext_map = {
                "dagman": ".dag",
                "snakemake": ".smk",
                "json": ".json",
                "yaml": ".yaml",
                "cwl": ".cwl",
                "nextflow": ".nf",
                "wdl": ".wdl",
                "galaxy": ".ga",
                "bco": ".bco",
            }
            ext = ext_map.get(output_format, ".out")
            output_path = input_path.with_suffix(ext)
        else:
            # Default to JSON (IR format) when no output format is specified
            output_path = input_path.with_suffix(".json")
            output_format = "json"
            
            # Warn user about defaulting to IR format
            click.echo(
                f"⚠ No output format specified. Defaulting to Intermediate Representation (IR) format: {output_path}",
                err=True
            )
            click.echo(
                "  Use --out-format to specify a different target format (dagman, cwl, nextflow, etc.)",
                err=True
            )

        if verbose:
            click.echo(f"Auto-generated output path: {output_path}")

    # Auto-detect output format from output path
    if not output_format:
        output_format = detect_output_format(output_path)
        if not output_format:
            raise click.ClickException(
                f"Could not auto-detect output format from {output_path}. "
                "Please specify --out-format."
            )
        if verbose:
            click.echo(f"Auto-detected output format: {output_format}")

    # Always show the conversion message
    click.echo(f"Converting {input_path.name} → {output_path.name}")
    if verbose:
        click.echo(f"Input: {input_path}")
        click.echo(f"Output: {output_path}")

    # Initialize content_analysis for both interactive and non-interactive modes
    content_analysis = None

    # ------------------------------------------------------------------
    # Interactive execution model selection (REMOVED: now handled by interactive module)
    # ------------------------------------------------------------------
    # (Old prompt code removed)

    # ------------------------------------------------------------------
    # Interactive prompt: overwrite existing output?
    # ------------------------------------------------------------------

    if interactive and output_path.exists():
        if not _prompt.ask(
            f"Output file {output_path} exists. Overwrite?", default=False
        ):
            raise click.ClickException("Aborted by user")

    # Step 1: Import to IR
    if verbose:
        click.echo(f"\nStep 1: Loading {input_format} workflow...")

    if input_format in ["json", "yaml"]:
        wf = load_workflow_from_json_yaml(input_path)
    else:
        importer = get_importer(input_format)
        if not importer:
            raise click.ClickException(
                f"No importer available for format: {input_format}"
            )

        # Build importer options
        import_opts = {}
        if input_format == "snakemake":
            if configfile:
                import_opts["configfile"] = configfile
            if workdir:
                import_opts["workdir"] = workdir
            if cores:
                import_opts["cores"] = cores
            if snakemake_args:
                import_opts["snakemake_args"] = list(snakemake_args)
            if parse_only:
                import_opts["parse_only"] = True
                click.echo("⚠ Parse-only mode enabled. This has limitations:")
                click.echo("  - No wildcard expansion")
                click.echo("  - No job instantiation") 
                click.echo("  - No dependency resolution")
                click.echo("  - No actual workflow execution plan")
                click.echo("  - Limited resource and environment detection")
                click.echo("")
            
            # Resource handling options
            if resource_profile or infer_resources or validate_resources:
                try:
                    from wf2wf.resource_utils import (
                        apply_resource_profile,
                        infer_resources_from_command,
                        validate_resources,
                        suggest_resource_profile,
                        get_available_profiles
                    )
                    
                    if verbose:
                        click.echo("🔧 Resource management enabled")
                    
                    # Store resource options for post-processing
                    import_opts["resource_profile"] = resource_profile
                    import_opts["infer_resources"] = infer_resources
                    import_opts["validate_resources"] = validate_resources
                    import_opts["target_environment"] = target_environment
                    
                except ImportError:
                    click.echo("⚠ Resource utilities not available - skipping resource management")
            
            if verbose:
                import_opts["verbose"] = verbose
            if debug:
                import_opts["debug"] = debug
            if interactive:
                import_opts["interactive"] = interactive

        try:
            wf = importer.to_workflow(input_path, **import_opts)
        except Exception as e:
            raise click.ClickException(
                f"Failed to import {input_format} workflow: {e}"
            )

    # Store original workflow for reporting (before any modifications)
    import copy

    wf_before = copy.deepcopy(wf)

    if verbose:
        click.echo(
            f"Loaded workflow '{wf.name}' with {len(wf.tasks)} tasks and {len(wf.edges)} edges"
        )

    # ------------------------------------------------------------------
    # Environment Adaptation
    # ------------------------------------------------------------------
    
    if adapt_environments and ADAPTATION_AVAILABLE:
        if verbose:
            click.echo("\n🔧 Applying environment adaptation...")
        
        # Determine source and target environments
        actual_source_env = source_environment
        actual_target_env = target_environment
        
        # Auto-detect source environment if not specified
        if not actual_source_env:
            if content_analysis and content_analysis.execution_model:
                actual_source_env = content_analysis.execution_model
            else:
                # Default based on input format
                format_to_env = {
                    "snakemake": "shared_filesystem",
                    "dagman": "distributed_computing", 
                    "nextflow": "hybrid",
                    "cwl": "shared_filesystem",
                    "wdl": "shared_filesystem",
                    "galaxy": "shared_filesystem"
                }
                actual_source_env = format_to_env.get(input_format, "unknown")
        
        # Auto-detect target environment if not specified
        if not actual_target_env:
            # Default based on output format
            format_to_env = {
                "snakemake": "shared_filesystem",
                "dagman": "distributed_computing",
                "nextflow": "hybrid", 
                "cwl": "shared_filesystem",
                "wdl": "shared_filesystem",
                "galaxy": "shared_filesystem",
                "bco": "unknown"
            }
            actual_target_env = format_to_env.get(output_format, "unknown")
        
        if verbose:
            click.echo(f"  Source environment: {actual_source_env}")
            click.echo(f"  Target environment: {actual_target_env}")
        
        # Only adapt if environments are different
        if actual_source_env != actual_target_env:
            try:
                # Apply adaptation
                wf = adapt_workflow(
                    wf, 
                    actual_source_env, 
                    actual_target_env,
                    strategy=adaptation_strategy
                )
                
                if verbose:
                    click.echo("✓ Environment adaptation completed")
                
                # Write adaptation report if requested
                if adaptation_report:
                    from wf2wf.adaptation.logging import export_adaptation_report
                    report_content = export_adaptation_report("json")
                    adaptation_report.write_text(report_content)
                    if verbose:
                        click.echo(f"  Adaptation report written to: {adaptation_report}")
                
            except Exception as e:
                if verbose:
                    click.echo(f"⚠ Environment adaptation failed: {e}")
                # Continue without adaptation rather than failing
        else:
            if verbose:
                click.echo("  No adaptation needed (same environment)")
    elif adapt_environments and not ADAPTATION_AVAILABLE:
        if verbose:
            click.echo("⚠ Environment adaptation requested but adaptation system not available")
    else:
        if verbose:
            click.echo("  Environment adaptation disabled")

    # ------------------------------------------------------------------
    # Interactive prompt: Check for missing configurations
    # ------------------------------------------------------------------
    
    if interactive:
        from wf2wf.importers.resource_processor import check_workflow_compatibility
        
        # Check workflow compatibility with target format
        check_workflow_compatibility(
            workflow=wf,
            target_format=output_format,
            interactive=interactive,
            verbose=verbose
        )

    # ------------------------------------------------------------------
    # Intent ontology IRIs (OBO etc.)
    # ------------------------------------------------------------------

    if intent:
        wf.intent.extend(list(intent))

    # Step 2: Validate IR (optional)
    if validate:
        if verbose:
            click.echo("\nStep 2: Validating workflow IR...")
        try:
            validate_workflow(wf)
            if verbose:
                click.echo("✓ Workflow validation passed")
        except Exception as e:
            raise click.ClickException(f"Workflow validation failed: {e}")

    # ------------------------------------------------------------------
    # Phase-2 environment automation: build or reuse images and inject
    # digest-pinned container refs.
    # ------------------------------------------------------------------

    if auto_env.lower() != "off":
        if interactive:
            if not _prompt.ask(
                "Automatic environment build/reuse is enabled and may invoke external tools. Continue?",
                default=True,
            ):
                raise click.ClickException("Aborted by user")
        
        # Only import environ helpers if auto_env is enabled
        from wf2wf.environ import (
            build_or_reuse_env_image,
            convert_to_sif,
            generate_sbom,
        )

        env_cache: dict[str, str] = {}

        backend_choice = (
            "buildah" if oci_backend in ("podman", "buildah") else "buildx"
        )
        registry_val = push_registry or None
        do_push = bool(push_registry and confirm_push)

        # Interactive prompt for registry push if not already confirmed
        if interactive and push_registry and not confirm_push:
            if _prompt.ask(
                f"Push images to registry {push_registry}?", default=False
            ):
                do_push = True

        # Honour env var – when WF2WF_ENVIRON_DRYRUN=0 we perform real builds
        env_dry_run = os.environ.get("WF2WF_ENVIRON_DRYRUN", "1") != "0"

        for task in wf.tasks.values():
            # Get environment-specific values for shared_filesystem environment
            conda = task.conda.get_value_for('shared_filesystem')
            container = task.container.get_value_for('shared_filesystem')
            env_vars = task.env_vars.get_value_for('shared_filesystem') or {}
            
            if conda and not container:
                path = Path(conda).expanduser()
                if path.exists():
                    cache_key = (str(path), backend_choice, registry_val, apptainer)
                    if cache_key not in env_cache:
                        entry = build_or_reuse_env_image(
                            path,
                            registry=registry_val,
                            push=do_push,
                            backend=backend_choice,
                            dry_run=env_dry_run,
                            build_cache=build_cache or None,
                            interactive=interactive,
                        )
                        if apptainer:
                            if interactive and not env_dry_run:
                                if not _prompt.ask(
                                    "Convert OCI image to Apptainer SIF?",
                                    default=True,
                                ):
                                    apptainer = False
                            sif_path = (
                                convert_to_sif(entry["digest"], dry_run=env_dry_run)
                                if apptainer
                                else None
                            )
                            if sif_path:
                                env_vars["WF2WF_SIF"] = str(sif_path)
                                task.env_vars.set_for_environment(env_vars, 'shared_filesystem')
                        else:
                            env_cache[cache_key] = f"docker://{entry['digest']}"

                        # SBOM generation
                        if sbom:
                            sbom_info = generate_sbom(
                                entry["digest"], dry_run=env_dry_run
                            )
                            env_vars["WF2WF_SBOM"] = str(sbom_info)
                            env_vars["WF2WF_SBOM_DIGEST"] = sbom_info.digest
                            task.env_vars.set_for_environment(env_vars, 'shared_filesystem')

                    container_value = env_cache[cache_key]
                    task.container.set_for_environment(container_value, 'shared_filesystem')
                    if verbose:
                        print(f"[auto-env] {task.id}: -> {container_value}")

    # Step 3: Export from IR – propagate intent flag to exporter opts (for BCO keywords)
    if verbose:
        click.echo(f"\nStep 3: Exporting to {output_format}...")

    from wf2wf import report as _report_hook

    _report_hook.start_collection()

    if output_format in ["json", "yaml"]:
        save_workflow_to_json_yaml(wf, output_path)
    else:
        exporter_class = get_exporter(output_format)
        if not exporter_class:
            raise click.ClickException(
                f"No exporter available for format: {output_format}"
            )

        # Instantiate the exporter with interactive and verbose options
        exporter = exporter_class(interactive=interactive, verbose=verbose)

        # Build exporter options
        export_opts = {}
        if output_format == "dagman":
            if scripts_dir:
                export_opts["scripts_dir"] = scripts_dir
            export_opts["default_memory"] = default_memory
            export_opts["default_disk"] = default_disk
            export_opts["default_cpus"] = default_cpus
            export_opts["inline_submit"] = inline_submit
        elif output_format == "snakemake":
            if workdir:
                export_opts["workdir"] = workdir

        if debug:
            export_opts["debug"] = debug

        try:
            exporter.export_workflow(wf, output_path, **export_opts)
        except Exception as e:
            raise click.ClickException(
                f"Failed to export {output_format} workflow: {e}"
            )

    # ------------------------------------------------------------------
    # Loss reporting and user interaction
    # ------------------------------------------------------------------

    # Collect loss entries from workflow object
    loss_entries = wf.loss_map

    # Fallback: read side-car if exporter did not update wf.loss_map
    if not loss_entries:
        loss_path = output_path.with_suffix(".loss.json")
        if loss_path.exists():
            with open(loss_path) as fh:
                loss_doc = json.load(fh)
                from wf2wf.validate import validate_loss

                try:
                    validate_loss(loss_doc)
                except Exception as e:
                    raise click.ClickException(
                        f"Loss side-car validation failed: {e}"
                    )
                loss_entries = loss_doc.get("entries", [])

    if loss_entries:

        def _sev(e):
            return (e.get("severity") or "warn").lower()

        lost = [
            e
            for e in loss_entries
            if e.get("status") in (None, "lost", "lost_again")
        ]
        prompt_eligible = [e for e in lost if _sev(e) in ("warn", "error")]

        reapplied = [e for e in loss_entries if e.get("status") == "reapplied"]
        lost_again = [e for e in loss_entries if e.get("status") == "lost_again"]

        click.echo(
            f"⚠ Conversion losses: {len(lost)} (lost), {len(lost_again)} (lost again), {len(reapplied)} (reapplied)"
        )
        if verbose and lost:
            for e in lost[:20]:
                click.echo(f"  • {e.get('json_pointer')} – {e.get('reason')}")
            if len(lost) > 20:
                click.echo(f"  ... {len(lost) - 20} more")

        if interactive and prompt_eligible and not fail_on_loss:
            if not _prompt.ask(
                f"{len(prompt_eligible)} unresolved losses detected. Continue anyway?",
                default=False,
            ):
                raise click.ClickException("Aborted by user")

        if fail_on_loss and lost:
            raise click.ClickException(
                f"Conversion resulted in {len(lost)} unresolved losses."
            )

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    if report_md:
        if verbose:
            click.echo(f"\nGenerating report: {report_md}")

        from wf2wf import report as _report

        _report.generate(
            report_md,
            src_path=input_path,
            dst_path=output_path,
            wf_before=wf_before,
            wf_after=wf,
            actions=_report_hook.get_actions(),
            losses=loss_entries or [],
            artefacts=_report_hook.get_artefacts(),
        )

    # ------------------------------------------------------------------
    # Success message
    # ------------------------------------------------------------------

    if verbose:
        click.echo(f"\n✓ Conversion completed successfully!")
        click.echo(f"Output: {output_path}")
        if loss_entries:
            click.echo(f"Losses: {len(lost)} (see {output_path.with_suffix('.loss.json')})")
    else:
        click.echo(f"✓ {output_path}")


@cli.command()
@click.argument("workflow_file", type=click.Path(exists=True, path_type=Path))
def validate(workflow_file: Path):
    """Validate a workflow file against the wf2wf JSON schema.

    WORKFLOW_FILE can be JSON or YAML format.
    """
    try:
        wf = None
        loss_entries: list[dict[str, Any]] = []
        if workflow_file.suffix.lower() in [".json", ".yaml", ".yml"]:
            wf = load_workflow_from_json_yaml(workflow_file)
        else:
            loss_path = workflow_file.with_suffix(".loss.json")
            if loss_path.exists():
                with open(loss_path) as fh:
                    loss_doc = json.load(fh)
                    from wf2wf.validate import validate_loss

                    try:
                        validate_loss(loss_doc)
                    except Exception as e:
                        raise click.ClickException(
                            f"Loss side-car validation failed: {e}"
                        )
                    loss_entries = loss_doc.get("entries", [])

        # Structural validation (if IR available)
        if wf is not None:
            validate_workflow(wf)

        # Check unresolved user losses
        unresolved = [
            e
            for e in loss_entries
            if e.get("origin") == "user" and e.get("status") != "reapplied"
        ]
        if unresolved:
            raise click.ClickException(
                f"Validation failed: {len(unresolved)} unresolved information-loss entries"
            )

        click.echo(f"✓ {workflow_file} is valid")
    except Exception as e:
        raise click.ClickException(f"Validation failed: {e}")


@cli.command()
@click.argument("workflow_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "-f",
    type=click.Choice(["json", "yaml"]),
    default="json",
    help="Output format (default: json)",
)
def info(workflow_file: Path, format: str):
    """Display information about a workflow file.

    Shows workflow metadata, task count, and dependency structure.
    """
    try:
        logger.debug(f"Starting info command for {workflow_file}")
        
        # Try to load as IR format first
        if workflow_file.suffix.lower() in [".json", ".yaml", ".yml"]:
            logger.debug(f"Loading {workflow_file} as IR format")
            wf = load_workflow_from_json_yaml(workflow_file)
            logger.debug(f"Successfully loaded IR workflow with {len(wf.tasks)} tasks")
        else:
            logger.debug(f"Attempting to auto-detect format for {workflow_file}")
            # Try to auto-detect and import
            input_format = detect_input_format(workflow_file)
            if not input_format:
                logger.error(f"Cannot detect format of {workflow_file}")
                raise click.ClickException(
                    f"Cannot detect format of {workflow_file}"
                )

            logger.debug(f"Detected format: {input_format}")
            importer = get_importer(input_format)
            if not importer:
                logger.error(f"No importer available for format: {input_format}")
                raise click.ClickException(
                    f"No importer available for format: {input_format}"
                )

            logger.debug(f"Importing with {importer.__class__.__name__}")
            wf = importer.to_workflow(workflow_file)
            logger.debug(f"Successfully imported workflow with {len(wf.tasks)} tasks")

        logger.debug("Building info data structure")
        info_data = {
            "name": wf.name,
            "version": wf.version,
            "tasks": len(wf.tasks),
            "edges": len(wf.edges),
            "task_list": list(wf.tasks.keys()),
            "dependencies": [(e.parent, e.child) for e in wf.edges],
            "metadata": wf.metadata.to_dict() if wf.metadata else {},
        }

        logger.debug(f"Serializing info data to {format} format")
        if format == "yaml":
            import yaml

            click.echo(yaml.dump(info_data, default_flow_style=False, indent=2))
        else:
            click.echo(json.dumps(info_data, indent=2))
        
        logger.debug("Info command completed successfully")

    except Exception as e:
        logger.error(f"Failed to read workflow: {e}")
        raise click.ClickException(f"Failed to read workflow: {e}")


@cli.group()
def bco():
    """BioCompute Object utilities (packaging, validation, etc.)."""


@bco.command("package")
@click.argument("bco_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "pkg_format",
    type=click.Choice(["estar"]),
    default="estar",
    help="Packaging format (currently only: estar)",
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(path_type=Path),
    help="Output ZIP file path",
)
@click.option("--verbose", "verbose", is_flag=True, help="Verbose output")
@click.option(
    "--interactive", is_flag=True, help="Prompt before overwriting output ZIP"
)
def bco_package(
    bco_file: Path,
    pkg_format: str,
    out_path: Union[Path, None],
    verbose: bool,
    interactive: bool,
):
    """Create an FDA eSTAR Technical Data Package from *BCO_FILE*."""

    if pkg_format != "estar":
        raise click.ClickException("Only --format=estar is supported currently")

    bco_path = bco_file.resolve()
    if out_path is None:
        out_path = bco_path.with_suffix(".estar.zip")

    if interactive and out_path.exists():
        from wf2wf import prompt as _prompt

        if not _prompt.ask(
            f"Output package {out_path} exists. Overwrite?", default=False
        ):
            raise click.ClickException("Aborted by user")

    if verbose:
        click.echo("Gathering assets for eSTAR package…")

    assets = _gather_bco_assets(bco_path)

    # Generate conversion report and embed as report.md
    from wf2wf import report as _report
    import tempfile

    with tempfile.TemporaryDirectory() as _tmp:
        rpt_path = Path(_tmp) / "report.md"
        _report.generate(
            rpt_path,
            src_path=bco_path,
            dst_path=out_path,
            wf_before=None,
            wf_after=None,
            actions=["Created FDA eSTAR package"],
            losses=[],
            artefacts=list(assets.values()),
        )
        assets["report.md"] = rpt_path

        _write_estar_package(assets, out_path, verbose=verbose)

    # TODO: ORAS push or tar OCI images into software/ – placeholder implementation above.
    if verbose:
        click.echo("✓ eSTAR packaging complete")


@bco.command("sign")
@click.argument("bco_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--key",
    "priv_key",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Private key (PEM) for openssl sha256 signing",
)
@click.option(
    "--sig",
    "sig_file",
    type=click.Path(path_type=Path),
    help="Output detached signature path (.sig)",
)
@click.option("--verbose", is_flag=True)
@click.option(
    "--interactive",
    is_flag=True,
    help="Prompt before overwriting signature/attestation files",
)
def bco_sign(
    bco_file: Path,
    priv_key: Path,
    sig_file: Union[Path, None],
    verbose: bool,
    interactive: bool,
):
    """Compute sha256 digest and produce detached signature using *openssl*.

    The BCO's `etag` field is updated to ``sha256:<hex>`` if not already.
    """

    if sig_file is None:
        sig_file = bco_file.with_suffix(".sig")

    if interactive and (
        sig_file.exists() or bco_file.with_suffix(".intoto.json").exists()
    ):
        from wf2wf import prompt as _prompt

        if not _prompt.ask(
            "Existing signature or attestation found. Overwrite?", default=False
        ):
            raise click.ClickException("Aborted by user")

    # 1. Ensure etag digest
    import json
    import hashlib
    import os
    import shutil
    import subprocess
    import tempfile

    data = json.loads(bco_file.read_text())
    if not str(data.get("etag", "")).startswith("sha256:"):
        digest = hashlib.sha256(
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        data["etag"] = f"sha256:{digest}"
        # write back via temp file for atomicity
        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=str(bco_file.parent)
        ) as tmp:
            json.dump(data, tmp, indent=2)
            tmp.flush()
            
        shutil.move(tmp.name, bco_file)
            
        if verbose:
            click.echo(f"Updated etag to sha256:{digest}")

    # 2. Sign using openssl (requires external tool)
    cmd = [
        "openssl",
        "dgst",
        "-sha256",
        "-sign",
        str(priv_key),
        "-out",
        str(sig_file),
        str(bco_file),
    ]
    try:
        subprocess.check_call(cmd)
        if verbose:
            click.echo(f"Signature written to {sig_file}")
    except FileNotFoundError:
        raise click.ClickException(
            "openssl not found – cannot sign. Install OpenSSL CLI or use a different signing method."
        )
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"openssl failed: {e}")

    # 3. Generate lightweight in-toto provenance attestation (unsigned JSON)
    import json as _json

    # Get version using modern importlib.metadata instead of deprecated pkg_resources
    try:
        from importlib.metadata import version

        wf2wf_version = version("wf2wf")
    except ImportError:
        # Fallback for Python < 3.8
        try:
            from importlib_metadata import version

            wf2wf_version = version("wf2wf")
        except ImportError:
            wf2wf_version = "unknown"
    except Exception:
        wf2wf_version = "unknown"

    att = {
        "_type": "https://in-toto.io/Statement/v0.1",
        "subject": [
            {
                "name": bco_file.name,
                "digest": {"sha256": data["etag"].split(":", 1)[1]},
            }
        ],
        "predicateType": "https://wf2wf.dev/Provenance/v0.1",
        "builder": {"id": os.getenv("USER", "wf2wf")},
        "metadata": {
            "buildStartedOn": datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
        },
        "predicate": {
            "wf2wf_version": wf2wf_version,
            "command": "wf2wf bco sign",
        },
    }
    att_path = bco_file.with_suffix(".intoto.json")
    att_path.write_text(_json.dumps(att, indent=2))

    # Embed reference in BCO extension_domain
    data.setdefault("extension_domain", []).append(
        {
            "namespace": "wf2wf:provenance",
            "attestation": att_path.name,
        }
    )
    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=str(bco_file.parent)
    ) as tmp2:
        _json.dump(data, tmp2, indent=2)
        tmp2.flush()
            
    shutil.move(tmp2.name, bco_file)

    if verbose:
        click.echo(f"Provenance attestation written to {att_path}")


@bco.command("diff")
@click.argument("first", type=click.Path(exists=True, path_type=Path))
@click.argument("second", type=click.Path(exists=True, path_type=Path))
def bco_diff(first: Path, second: Path):
    """Show domain-level differences between two BCO JSON documents."""

    import json
    import difflib

    a = json.loads(first.read_text())
    b = json.loads(second.read_text())

    domains = [d for d in a.keys() if d.endswith("_domain")] + [
        d for d in b.keys() if d.endswith("_domain")
    ]
    for dom in sorted(set(domains)):
        if a.get(dom) != b.get(dom):
            click.echo(click.style(f"\n### {dom}", fg="yellow"))
            a_lines = json.dumps(a.get(dom, {}), indent=2).splitlines()
            b_lines = json.dumps(b.get(dom, {}), indent=2).splitlines()
            for line in difflib.unified_diff(
                a_lines,
                b_lines,
                fromfile=str(first),
                tofile=str(second),
                lineterm="",
            ):
                click.echo(line)


if __name__ == "__main__":
    cli()


# ---------------------------------------------------------------------------
# BCO packaging utilities (FDA eSTAR Technical Data Package)
# ---------------------------------------------------------------------------


def _gather_bco_assets(bco_path: Path) -> dict[str, Path]:
    """Return mapping of *arcname* → *source_path* for assets referenced by *bco_path*.

    Currently collects:
        • the BCO JSON itself (as root file)
        • CWL workflow referenced in execution_domain.script (same dir)
        • Any SBOM JSON files sitting next to the BCO / CWL
        • Placeholder text files for container images listed in software_prerequisites
    """

    import json

    assets: dict[str, Path] = {}

    # 1. BCO file
    assets["manifest.json"] = bco_path  # rename to manifest.json per eSTAR naming

    data_dir = Path("data")
    software_dir = Path("software")

    # 2. Parse BCO
    doc = json.loads(bco_path.read_text())

    # CWL workflow script (relative path expected)
    script_name = doc.get("execution_domain", {}).get("script")
    if script_name:
        script_path = bco_path.with_name(script_name)
        if script_path.exists():
            assets[str(data_dir / script_path.name)] = script_path

    # 3. SBOM files – collect any *.sbom.json next to BCO/CWL
    for sbom in bco_path.parent.glob("*.sbom.json"):
        assets[str(software_dir / sbom.name)] = sbom

    # 4. Container images – create placeholder text files per image ref
    prereq = doc.get("execution_domain", {}).get("software_prerequisites", [])
    img_idx = 1
    for step in prereq:
        env = step.get("environment", {})
        img = env.get("container")
        if img:
            placeholder = bco_path.parent / f"image_{img_idx}.txt"
            placeholder.write_text(img)
            assets[str(software_dir / placeholder.name)] = placeholder
            img_idx += 1

    return assets


def _write_estar_package(
    assets: dict[str, Path], out_zip: Path, *, verbose: bool = False
):
    """Create ZIP *out_zip* with *assets* and generate content table."""

    out_zip.parent.mkdir(parents=True, exist_ok=True)

    content_lines = ["Index\tPath\tSize\tSHA256"]

    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, (arcname, src) in enumerate(sorted(assets.items()), start=1):
            zf.write(src, arcname)
            data = src.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            content_lines.append(f"{idx}\t{arcname}\t{len(data)}\tsha256:{digest}")

        # Write content table inside ZIP
        table_data = "\n".join(content_lines).encode()
        zf.writestr("content_table.tsv", table_data)

    if verbose:
        click.echo(f"eSTAR package written to {out_zip} with {len(assets)} assets")


def _package_placeholder():
    """Placeholder removed duplication block (cleanup)."""
    pass
