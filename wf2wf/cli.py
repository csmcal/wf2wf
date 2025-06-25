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
from typing import Any, Dict, Optional
import os
import zipfile
import hashlib

try:
    import click
except ImportError:
    click = None

# Handle imports when running as script vs installed package
try:
    from wf2wf.core import Workflow
    from wf2wf.validate import validate_workflow
except ImportError:
    # Running as script, use relative imports
    import importlib.util
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
    from wf2wf.exporters import dagman as dagman_exporter
    DAGMAN_EXPORT_AVAILABLE = True
except ImportError:
    try:
        from exporters import dagman as dagman_exporter
        DAGMAN_EXPORT_AVAILABLE = True
    except ImportError:
        DAGMAN_EXPORT_AVAILABLE = False
        dagman_exporter = None

try:
    from wf2wf.exporters import snakemake as snakemake_exporter
    SNAKEMAKE_EXPORT_AVAILABLE = True
except ImportError:
    try:
        from exporters import snakemake as snakemake_exporter
        SNAKEMAKE_EXPORT_AVAILABLE = True
    except ImportError:
        SNAKEMAKE_EXPORT_AVAILABLE = False
        snakemake_exporter = None

try:
    from wf2wf.exporters import cwl as cwl_exporter
    CWL_EXPORT_AVAILABLE = True
except ImportError:
    try:
        from exporters import cwl as cwl_exporter
        CWL_EXPORT_AVAILABLE = True
    except ImportError:
        CWL_EXPORT_AVAILABLE = False
        cwl_exporter = None

try:
    from wf2wf.exporters import nextflow as nextflow_exporter
    NEXTFLOW_EXPORT_AVAILABLE = True
except ImportError:
    try:
        from exporters import nextflow as nextflow_exporter
        NEXTFLOW_EXPORT_AVAILABLE = True
    except ImportError:
        NEXTFLOW_EXPORT_AVAILABLE = False
        nextflow_exporter = None

try:
    from wf2wf.exporters import wdl as wdl_exporter
    WDL_EXPORT_AVAILABLE = True
except ImportError:
    try:
        from exporters import wdl as wdl_exporter
        WDL_EXPORT_AVAILABLE = True
    except ImportError:
        WDL_EXPORT_AVAILABLE = False
        wdl_exporter = None

try:
    from wf2wf.exporters import galaxy as galaxy_exporter
    GALAXY_EXPORT_AVAILABLE = True
except ImportError:
    try:
        from exporters import galaxy as galaxy_exporter
        GALAXY_EXPORT_AVAILABLE = True
    except ImportError:
        GALAXY_EXPORT_AVAILABLE = False
        galaxy_exporter = None


# Format detection mappings
INPUT_FORMAT_MAP = {
    '.smk': 'snakemake',
    '.snakefile': 'snakemake',
    '.dag': 'dagman',
    '.nf': 'nextflow',
    '.cwl': 'cwl',
    '.wdl': 'wdl',
    '.ga': 'galaxy',
    '.json': 'json',
    '.yaml': 'yaml',
    '.yml': 'yaml',
}

OUTPUT_FORMAT_MAP = {
    '.dag': 'dagman',
    '.smk': 'snakemake',
    '.nf': 'nextflow',
    '.cwl': 'cwl',
    '.wdl': 'wdl',
    '.ga': 'galaxy',
    '.bco': 'bco',
    '.json': 'json',
    '.yaml': 'yaml',
    '.yml': 'yaml',
}


def detect_input_format(path: Path) -> Optional[str]:
    """Auto-detect input format from file extension."""
    suffix = path.suffix.lower()
    name = path.name.lower()
    
    # Check suffix first
    if suffix in INPUT_FORMAT_MAP:
        return INPUT_FORMAT_MAP[suffix]
    
    # Check specific filenames without extensions
    if name in ['snakefile', 'makefile']:
        return 'snakemake'
    
    return None


def detect_output_format(path: Path) -> Optional[str]:
    """Auto-detect output format from file extension."""
    suffix = path.suffix.lower()
    return OUTPUT_FORMAT_MAP.get(suffix)


def get_importer(fmt: str):
    """Get the appropriate importer for the given format."""
    importers = {
        'snakemake': snakemake_importer if SNAKEMAKE_AVAILABLE else None,
        'cwl': cwl_importer if CWL_AVAILABLE else None,
        'nextflow': nextflow_importer if NEXTFLOW_AVAILABLE else None,
        'dagman': dagman_importer if DAGMAN_IMPORT_AVAILABLE else None,
        'wdl': wdl_importer if WDL_AVAILABLE else None,
        'galaxy': galaxy_importer if GALAXY_AVAILABLE else None,
        'json': None,  # JSON handled specially
        'yaml': None,  # YAML handled specially
    }
    
    importer = importers.get(fmt)
    if importer is None and fmt not in ['json', 'yaml']:
        if click:
            raise click.ClickException(f"Importer for format '{fmt}' is not available or not implemented")
        else:
            raise RuntimeError(f"Importer for format '{fmt}' is not available or not implemented")
    
    return importer


def get_exporter(fmt: str):
    """Get the appropriate exporter for the given format."""
    exporters = {
        'dagman': dagman_exporter if DAGMAN_EXPORT_AVAILABLE else None,
        'snakemake': snakemake_exporter if SNAKEMAKE_EXPORT_AVAILABLE else None,
        'cwl': cwl_exporter if CWL_EXPORT_AVAILABLE else None,
        'nextflow': nextflow_exporter if NEXTFLOW_EXPORT_AVAILABLE else None,
        'wdl': wdl_exporter if WDL_EXPORT_AVAILABLE else None,
        'galaxy': galaxy_exporter if GALAXY_EXPORT_AVAILABLE else None,
        'bco': None,  # will be resolved via exporters.load dynamic import
        'json': None,
        'yaml': None,
    }
    
    exporter = exporters.get(fmt)
    if exporter is None:
        if fmt in ['json', 'yaml']:
            return None
        try:
            from wf2wf.exporters import load as _load_exporter
            exporter = _load_exporter(fmt)
        except Exception as e:
            if click:
                raise click.ClickException(f"Exporter for format '{fmt}' is not available or not implemented: {e}")
            else:
                raise RuntimeError(f"Exporter for format '{fmt}' is not available or not implemented: {e}")
    
    return exporter


def load_workflow_from_json_yaml(path: Path) -> Workflow:
    """Load workflow from JSON or YAML file."""
    try:
        if path.suffix.lower() in ['.yaml', '.yml']:
            import yaml
            data = yaml.safe_load(path.read_text())
        else:  # JSON
            data = json.loads(path.read_text())
        
        return Workflow.from_dict(data)
    except Exception as e:
        if click:
            raise click.ClickException(f"Failed to load workflow from {path}: {e}")
        else:
            raise RuntimeError(f"Failed to load workflow from {path}: {e}")


def save_workflow_to_json_yaml(wf: Workflow, path: Path) -> None:
    """Save workflow to JSON or YAML file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        
        if path.suffix.lower() in ['.yaml', '.yml']:
            import yaml
            data = wf.to_dict()
            path.write_text(yaml.dump(data, default_flow_style=False, indent=2))
        else:  # JSON
            wf.save_json(path)
    except Exception as e:
        if click:
            raise click.ClickException(f"Failed to save workflow to {path}: {e}")
        else:
            raise RuntimeError(f"Failed to save workflow to {path}: {e}")


if click:
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
    @click.option('--input', '-i', 'input_path', required=True, type=click.Path(exists=True, path_type=Path),
                  help='Path to the input workflow file')
    @click.option('--in-format', '--input-format', 'input_format', 
                  type=click.Choice(['snakemake', 'dagman', 'nextflow', 'cwl', 'wdl', 'galaxy', 'json', 'yaml']),
                  help='Format of the input workflow (auto-detected if not specified)')
    @click.option('--out', '-o', '--output', 'output_path', type=click.Path(path_type=Path),
                  help='Path to output workflow file (auto-generated if not specified)')
    @click.option('--out-format', '--output-format', 'output_format',
                  type=click.Choice(['snakemake', 'dagman', 'nextflow', 'cwl', 'wdl', 'galaxy', 'bco', 'json', 'yaml']),
                  help='Desired output format (auto-detected from output path if not specified)')
    # Snakemake-specific options
    @click.option('--snakefile', type=click.Path(exists=True, path_type=Path),
                  help='Path to Snakefile (alias for --input when input format is snakemake)')
    @click.option('--configfile', '-c', type=click.Path(exists=True, path_type=Path),
                  help='Snakemake config file')
    @click.option('--workdir', '-d', type=click.Path(path_type=Path),
                  help='Working directory for Snakemake workflow')
    @click.option('--cores', type=int, default=1,
                  help='Number of cores for Snakemake operations (default: 1)')
    @click.option('--snakemake-args', multiple=True,
                  help='Additional arguments to pass to snakemake commands (can be used multiple times)')
    # DAGMan export options
    @click.option('--scripts-dir', type=click.Path(path_type=Path),
                  help='Directory for generated wrapper scripts (DAGMan export)')
    @click.option('--default-memory', default='4GB',
                  help='Default memory request for jobs (default: 4GB)')
    @click.option('--default-disk', default='4GB', 
                  help='Default disk request for jobs (default: 4GB)')
    @click.option('--default-cpus', type=int, default=1,
                  help='Default CPU request for jobs (default: 1)')
    @click.option('--inline-submit', is_flag=True,
                  help='Use inline submit descriptions in DAG file instead of separate .sub files')
    # Generic options
    @click.option('--validate/--no-validate', default=True,
                  help='Validate workflow against JSON schema (default: enabled)')
    @click.option('--fail-on-loss', is_flag=True,
                  help='Exit with non-zero status if any information loss occurred during conversion')
    @click.option('--verbose', '-v', is_flag=True,
                  help='Enable verbose output')
    @click.option('--debug', is_flag=True,
                  help='Enable debug output')
    @click.option('--auto-env', type=click.Choice(['off', 'reuse', 'build'], case_sensitive=False), default='off',
                  help='Automatically build or reuse Conda/container images and replace env specs (Phase2)')
    @click.option('--oci-backend', type=click.Choice(['buildx', 'podman', 'buildah']), default='buildx',
                  help='OCI builder backend to use when --auto-env is active (default: buildx)')
    @click.option('--push-registry', default='', help='Registry to push images (enables push)')
    @click.option('--confirm-push', is_flag=True, help='Actually push to registry; without this only probing is performed')
    @click.option('--apptainer', is_flag=True, help='Convert OCI image to Apptainer SIF and reference that')
    @click.option('--sbom', is_flag=True, help='Generate SBOM via syft and attach to environment metadata')
    @click.option('--platform', default='linux/amd64', help='Target platform for OCI buildx/buildah (e.g. linux/arm64)')
    @click.option('--build-cache', default='', help='Remote cache location for BuildKit --build-cache')
    @click.option('--report-md', 'report_md', type=click.Path(path_type=Path), help='Write human-readable Markdown report to this file')
    @click.option('--interactive', is_flag=True, help='Prompt before potentially destructive or lossy actions')
    @click.option('--intent', multiple=True, help='Ontology IRI describing workflow intent (can repeat)')
    def convert(input_path: Path, input_format: Optional[str], output_path: Optional[Path], 
               output_format: Optional[str], snakefile: Optional[Path], configfile: Optional[Path],
               workdir: Optional[Path], cores: int, snakemake_args: tuple, scripts_dir: Optional[Path],
               default_memory: str, default_disk: str, default_cpus: int, validate: bool,
               verbose: bool, debug: bool, inline_submit: bool, fail_on_loss: bool, auto_env: str,
               oci_backend: str, push_registry: str, confirm_push: bool, apptainer: bool, sbom: bool,
               platform: str, build_cache: str, intent: tuple, report_md: Path | None, interactive: bool):
        """Convert workflows between different formats.
        
        Examples:
        \b
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
        _prompt_mod.set_interactive(interactive)

        # Handle snakefile alias
        if snakefile and not input_path:
            input_path = snakefile
            input_format = 'snakemake'
        elif snakefile and input_path:
            click.echo("Warning: Both --input and --snakefile specified. Using --input.", err=True)
        
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
                ext_map = {'dagman': '.dag', 'snakemake': '.smk', 'json': '.json', 
                          'yaml': '.yaml', 'cwl': '.cwl', 'nextflow': '.nf', 'wdl': '.wdl', 'galaxy': '.ga', 'bco': '.bco'}
                ext = ext_map.get(output_format, '.out')
                output_path = input_path.with_suffix(ext)
            else:
                # Default to DAGMan if input is Snakemake, otherwise JSON
                if input_format == 'snakemake':
                    output_path = input_path.with_suffix('.dag')
                    output_format = 'dagman'
                else:
                    output_path = input_path.with_suffix('.json')
                    output_format = 'json'
            
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
        
        if verbose:
            click.echo(f"Converting {input_format} → {output_format}")
            click.echo(f"Input: {input_path}")
            click.echo(f"Output: {output_path}")
        
        # ------------------------------------------------------------------
        # Interactive prompt: overwrite existing output?
        # ------------------------------------------------------------------

        if interactive and output_path.exists():
            from wf2wf import prompt as _prompt
            if not _prompt.ask(f"Output file {output_path} exists. Overwrite?", default=False):
                raise click.ClickException("Aborted by user")
        
        # Step 1: Import to IR
        if verbose:
            click.echo(f"\nStep 1: Loading {input_format} workflow...")
        
        if input_format in ['json', 'yaml']:
            wf = load_workflow_from_json_yaml(input_path)
        else:
            importer = get_importer(input_format)
            if not importer:
                raise click.ClickException(f"No importer available for format: {input_format}")
            
            # Build importer options
            import_opts = {}
            if input_format == 'snakemake':
                if configfile:
                    import_opts['configfile'] = configfile
                if workdir:
                    import_opts['workdir'] = workdir
                if cores:
                    import_opts['cores'] = cores
                if snakemake_args:
                    import_opts['snakemake_args'] = list(snakemake_args)
                if verbose:
                    import_opts['verbose'] = verbose
                if debug:
                    import_opts['debug'] = debug
            
            try:
                wf = importer.to_workflow(input_path, **import_opts)
            except Exception as e:
                raise click.ClickException(f"Failed to import {input_format} workflow: {e}")
        
        if verbose:
            click.echo(f"Loaded workflow '{wf.name}' with {len(wf.tasks)} tasks and {len(wf.edges)} edges")
        
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

        if auto_env.lower() != 'off':
            if interactive:
                from wf2wf import prompt as _prompt
                if not _prompt.ask("Automatic environment build/reuse is enabled and may invoke external tools. Continue?", default=True):
                    raise click.ClickException("Aborted by user")
            from wf2wf.environ import build_or_reuse_env_image, convert_to_sif, generate_sbom
            env_cache: dict[str, str] = {}

            backend_choice = 'buildah' if oci_backend in ('podman', 'buildah') else 'buildx'
            registry_val = push_registry or None
            do_push = bool(push_registry and confirm_push)

            # Interactive prompt for registry push if not already confirmed
            if interactive and push_registry and not confirm_push:
                from wf2wf import prompt as _prompt
                if _prompt.ask(f"Push images to registry {push_registry}?", default=False):
                    do_push = True

            # Honour env var – when WF2WF_ENVIRON_DRYRUN=0 we perform real builds
            env_dry_run = os.environ.get("WF2WF_ENVIRON_DRYRUN", "1") != "0"

            for task in wf.tasks.values():
                env = task.environment
                if env.conda and not env.container:
                    path = Path(env.conda).expanduser()
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
                            )
                            if apptainer:
                                if interactive and not env_dry_run:
                                    from wf2wf import prompt as _prompt
                                    if not _prompt.ask("Convert OCI image to Apptainer SIF?", default=True):
                                        apptainer = False
                                sif_path = convert_to_sif(entry['digest'], dry_run=env_dry_run) if apptainer else None
                                if sif_path:
                                    env.env_vars['WF2WF_SIF'] = str(sif_path)
                            else:
                                env_cache[cache_key] = f"docker://{entry['digest']}"

                            # SBOM generation
                            if sbom:
                                sbom_info = generate_sbom(entry['digest'], dry_run=env_dry_run)
                                env.env_vars['WF2WF_SBOM'] = str(sbom_info)
                                env.env_vars['WF2WF_SBOM_DIGEST'] = sbom_info.digest

                        env.container = env_cache[cache_key]
                        if verbose:
                            print(f"[auto-env] {task.id}: -> {env.container}")
        
        # Step 3: Export from IR – propagate intent flag to exporter opts (for BCO keywords)
        if verbose:
            click.echo(f"\nStep 3: Exporting to {output_format}...")
        
        from wf2wf import report as _report_hook
        _report_hook.start_collection()
        
        if output_format in ['json', 'yaml']:
            save_workflow_to_json_yaml(wf, output_path)
        else:
            exporter = get_exporter(output_format)
            if not exporter:
                raise click.ClickException(f"No exporter available for format: {output_format}")
            
            # Build exporter options
            export_opts = {}
            if output_format == 'dagman':
                if scripts_dir:
                    export_opts['scripts_dir'] = scripts_dir
                export_opts['default_memory'] = default_memory
                export_opts['default_disk'] = default_disk
                export_opts['default_cpus'] = default_cpus
                export_opts['inline_submit'] = inline_submit
                if workdir:
                    export_opts['workdir'] = workdir
                if verbose:
                    export_opts['verbose'] = verbose
                if debug:
                    export_opts['debug'] = debug
            export_opts['intent'] = list(intent)
            
            try:
                exporter.from_workflow(wf, output_path, **export_opts)
            except Exception as e:
                raise click.ClickException(f"Failed to export {output_format} workflow: {e}")
        
        # ------------------------------------------------------------------
        # Step 4: Summarise losses (if any)
        # ------------------------------------------------------------------

        loss_entries = wf.loss_map or []

        # Fallback: read side-car if exporter did not update wf.loss_map
        if not loss_entries:
            loss_path = output_path.with_suffix('.loss.json')
            if loss_path.exists():
                with open(loss_path) as fh:
                    loss_doc = json.load(fh)
                    from wf2wf.validate import validate_loss
                    try:
                        validate_loss(loss_doc)
                    except Exception as e:
                        raise click.ClickException(f"Loss side-car validation failed: {e}")
                    loss_entries = loss_doc.get('entries', [])

        if loss_entries:
            def _sev(e):
                return (e.get('severity') or 'warn').lower()

            lost = [e for e in loss_entries if e.get('status') in (None, 'lost', 'lost_again')]
            prompt_eligible = [e for e in lost if _sev(e) in ('warn', 'error')]

            reapplied = [e for e in loss_entries if e.get('status') == 'reapplied']
            lost_again = [e for e in loss_entries if e.get('status') == 'lost_again']

            click.echo(f"⚠ Conversion losses: {len(lost)} (lost), {len(lost_again)} (lost again), {len(reapplied)} (reapplied)")
            if verbose and lost:
                for e in lost[:20]:
                    click.echo(f"  • {e.get('json_pointer')} – {e.get('reason')}")
                if len(lost) > 20:
                    click.echo(f"  ... {len(lost) - 20} more")

            if interactive and prompt_eligible and not fail_on_loss:
                from wf2wf import prompt as _prompt
                if not _prompt.ask(f"{len(prompt_eligible)} unresolved losses detected. Continue anyway?", default=False):
                    raise click.ClickException("Aborted by user")

            if fail_on_loss and lost:
                raise click.ClickException(f"Conversion resulted in {len(lost)} unresolved losses.")
        
        # --------------------------------------------------------------
        # Determine if report should be auto-generated (env var support)
        # --------------------------------------------------------------

        from wf2wf import config as _cfg

        if report_md is None:
            env_val = os.environ.get("WF2WF_REPORT_MD")
            if env_val is not None:
                # If set to empty or "1", use default output path; otherwise explicit path
                if env_val.strip().lower() in ("", "1", "true", "yes", "on"):
                    report_md = output_path.with_suffix(".report.md")
                elif env_val.strip().lower() in ("off", "0", "false", "no"):
                    report_md = None
                else:
                    report_md = Path(env_val).expanduser()
            else:
                cfg_val = _cfg.get("reports.default")
                if cfg_val is not None and cfg_val is not False:
                    if isinstance(cfg_val, (bool, int)) or str(cfg_val).lower() in ("on", "1", "true", "yes"):
                        report_md = output_path.with_suffix(".report.md")
                    elif str(cfg_val).lower() in ("off", "0", "false", "no"):
                        report_md = None
                    else:
                        report_md = Path(str(cfg_val)).expanduser()

        if report_md:
            from wf2wf import report as _report_hook

            # extra actions/artifacts were collected earlier

            cli_actions = []
            if auto_env.lower() != 'off':
                cli_actions.append("Automatic environment handling enabled")
            if sbom:
                cli_actions.append("SBOM generated via syft or stub")
            if apptainer:
                cli_actions.append("Apptainer SIF conversion performed")

            next_steps = [
                "Run `wf2wf validate` to ensure no unresolved losses", 
            ]
            if push_registry and not confirm_push:
                next_steps.append("Re-run with --confirm-push to upload images to registry")

            # Merge exporter-provided actions & artefacts
            extra_actions, extra_artefacts = _report_hook.end_collection()

            actions = extra_actions + cli_actions
            artefact_list = [output_path] + extra_artefacts

            # HTML generation option
            html_opt: Path | bool | None = None
            env_html = os.environ.get("WF2WF_REPORT_HTML")
            if env_html is not None:
                html_opt = True if env_html.strip().lower() in ("", "1", "true", "yes", "on") else Path(env_html).expanduser()
            else:
                cfg_html = _cfg.get("reports.html")
                if cfg_html not in (None, False):
                    if isinstance(cfg_html, (bool, int)) or str(cfg_html).lower() in ("on", "1", "true", "yes"):
                        html_opt = True
                    elif str(cfg_html).lower() in ("off", "0", "false", "no"):
                        html_opt = None
                    else:
                        html_opt = Path(str(cfg_html)).expanduser()

            _report_hook.generate(
                Path(report_md).expanduser(),
                src_path=input_path,
                dst_path=output_path,
                wf_before=wf_before,
                wf_after=wf,
                losses=loss_entries,
                actions=actions,
                artefacts=artefact_list,
                next_steps=next_steps,
                html_path=html_opt,
            )
            if verbose:
                click.echo(f"Markdown report written to {report_md}")
                if html_opt is not None:
                    html_path_written = Path(report_md).with_suffix('.html') if html_opt is True else html_opt
                    click.echo(f"HTML report written to {html_path_written}")
        
        if verbose:
            click.echo(f"✓ Successfully converted {input_format} → {output_format}")
            click.echo(f"Output written to: {output_path}")
        else:
            click.echo(f"Converted {input_path} → {output_path}")


    @cli.command()
    @click.argument('workflow_file', type=click.Path(exists=True, path_type=Path))
    def validate_cmd(workflow_file: Path):
        """Validate a workflow file against the wf2wf JSON schema.
        
        WORKFLOW_FILE can be JSON or YAML format.
        """
        try:
            wf = None
            loss_entries: list[dict[str, Any]] = []
            if workflow_file.suffix.lower() in ['.json', '.yaml', '.yml']:
                wf = load_workflow_from_json_yaml(workflow_file)
            else:
                loss_path = workflow_file.with_suffix('.loss.json')
                if loss_path.exists():
                    with open(loss_path) as fh:
                        loss_doc = json.load(fh)
                        from wf2wf.validate import validate_loss
                        try:
                            validate_loss(loss_doc)
                        except Exception as e:
                            raise click.ClickException(f"Loss side-car validation failed: {e}")
                        loss_entries = loss_doc.get('entries', [])

            # Structural validation (if IR available)
            if wf is not None:
                validate_workflow(wf)

            # Check unresolved user losses
            unresolved = [e for e in loss_entries if e.get('origin') == 'user' and e.get('status') != 'reapplied']
            if unresolved:
                raise click.ClickException(f"Validation failed: {len(unresolved)} unresolved information-loss entries")

            click.echo(f"✓ {workflow_file} is valid")
        except Exception as e:
            raise click.ClickException(f"Validation failed: {e}")


    @cli.command()
    @click.argument('workflow_file', type=click.Path(exists=True, path_type=Path))
    @click.option('--format', '-f', type=click.Choice(['json', 'yaml']), default='json',
                  help='Output format (default: json)')
    def info(workflow_file: Path, format: str):
        """Display information about a workflow file.
        
        Shows workflow metadata, task count, and dependency structure.
        """
        try:
            # Try to load as IR format first
            if workflow_file.suffix.lower() in ['.json', '.yaml', '.yml']:
                wf = load_workflow_from_json_yaml(workflow_file)
            else:
                # Try to auto-detect and import
                input_format = detect_input_format(workflow_file)
                if not input_format:
                    raise click.ClickException(f"Cannot detect format of {workflow_file}")
                
                importer = get_importer(input_format)
                if not importer:
                    raise click.ClickException(f"No importer available for format: {input_format}")
                
                wf = importer.to_workflow(workflow_file)
            
            info_data = {
                'name': wf.name,
                'version': wf.version,
                'tasks': len(wf.tasks),
                'edges': len(wf.edges),
                'task_list': list(wf.tasks.keys()),
                'dependencies': [(e.parent, e.child) for e in wf.edges],
                'config': wf.config,
                'meta': wf.meta
            }
            
            if format == 'yaml':
                import yaml
                click.echo(yaml.dump(info_data, default_flow_style=False, indent=2))
            else:
                click.echo(json.dumps(info_data, indent=2))
                
        except Exception as e:
            raise click.ClickException(f"Failed to read workflow: {e}")


    @cli.group()
    def bco():
        """BioCompute Object utilities (packaging, validation, etc.)."""


    @bco.command("package")
    @click.argument("bco_file", type=click.Path(exists=True, path_type=Path))
    @click.option("--format", "pkg_format", type=click.Choice(["estar"]), default="estar", help="Packaging format (currently only: estar)")
    @click.option("--out", "out_path", type=click.Path(path_type=Path), help="Output ZIP file path")
    @click.option("--verbose", "verbose", is_flag=True, help="Verbose output")
    @click.option("--interactive", is_flag=True, help="Prompt before overwriting output ZIP")
    def bco_package(bco_file: Path, pkg_format: str, out_path: Path | None, verbose: bool, interactive: bool):
        """Create an FDA eSTAR Technical Data Package from *BCO_FILE*."""

        if pkg_format != "estar":
            raise click.ClickException("Only --format=estar is supported currently")

        bco_path = bco_file.resolve()
        if out_path is None:
            out_path = bco_path.with_suffix(".estar.zip")

        if interactive and out_path.exists():
            from wf2wf import prompt as _prompt
            if not _prompt.ask(f"Output package {out_path} exists. Overwrite?", default=False):
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
                wf_before=wf,
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
    @click.option("--key", "priv_key", required=True, type=click.Path(exists=True, path_type=Path), help="Private key (PEM) for openssl sha256 signing")
    @click.option("--sig", "sig_file", type=click.Path(path_type=Path), help="Output detached signature path (.sig)")
    @click.option("--verbose", is_flag=True)
    @click.option("--interactive", is_flag=True, help="Prompt before overwriting signature/attestation files")
    def bco_sign(bco_file: Path, priv_key: Path, sig_file: Path | None, verbose: bool, interactive: bool):
        """Compute sha256 digest and produce detached signature using *openssl*.

        The BCO's `etag` field is updated to ``sha256:<hex>`` if not already.
        """

        if sig_file is None:
            sig_file = bco_file.with_suffix(".sig")

        if interactive and (sig_file.exists() or bco_file.with_suffix(".intoto.json").exists()):
            from wf2wf import prompt as _prompt
            if not _prompt.ask("Existing signature or attestation found. Overwrite?", default=False):
                raise click.ClickException("Aborted by user")

        # 1. Ensure etag digest
        import json, hashlib, shutil, subprocess, tempfile

        data = json.loads(bco_file.read_text())
        if not str(data.get("etag", "")).startswith("sha256:"):
            digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            data["etag"] = f"sha256:{digest}"
            # write back via temp file for atomicity
            with tempfile.NamedTemporaryFile("w", delete=False, dir=str(bco_file.parent)) as tmp:
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
            raise click.ClickException("openssl not found – cannot sign. Install OpenSSL CLI or use a different signing method.")
        except subprocess.CalledProcessError as e:
            raise click.ClickException(f"openssl failed: {e}")

        # 3. Generate lightweight in-toto provenance attestation (unsigned JSON)
        import datetime, pkg_resources, os, json as _json
        att = {
            "_type": "https://in-toto.io/Statement/v0.1",
            "subject": [{"name": bco_file.name, "digest": {"sha256": data["etag"].split(":",1)[1]}}],
            "predicateType": "https://wf2wf.dev/Provenance/v0.1",
            "builder": {"id": os.getenv("USER", "wf2wf")},
            "metadata": {"buildStartedOn": datetime.datetime.utcnow().isoformat() + "Z"},
            "predicate": {
                "wf2wf_version": pkg_resources.get_distribution("wf2wf").version if pkg_resources else "unknown",
                "command": "wf2wf bco sign",
            },
        }
        att_path = bco_file.with_suffix(".intoto.json")
        att_path.write_text(_json.dumps(att, indent=2))

        # Embed reference in BCO extension_domain
        data.setdefault("extension_domain", []).append({
            "namespace": "wf2wf:provenance",
            "attestation": att_path.name,
        })
        with tempfile.NamedTemporaryFile("w", delete=False, dir=str(bco_file.parent)) as tmp2:
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

        import json, difflib

        a = json.loads(first.read_text())
        b = json.loads(second.read_text())

        domains = [d for d in a.keys() if d.endswith("_domain")] + [d for d in b.keys() if d.endswith("_domain")]
        for dom in sorted(set(domains)):
            if a.get(dom) != b.get(dom):
                click.echo(click.style(f"\n### {dom}", fg="yellow"))
                a_lines = json.dumps(a.get(dom, {}), indent=2).splitlines()
                b_lines = json.dumps(b.get(dom, {}), indent=2).splitlines()
                for line in difflib.unified_diff(a_lines, b_lines, fromfile=str(first), tofile=str(second), lineterm=""):
                    click.echo(line)


# Fallback for when click is not available
def simple_main():
    """Simple main function for when click is not available."""
    if len(sys.argv) < 2:
        print("wf2wf - Workflow-to-Workflow Converter")
        print("Please install click for full CLI functionality: pip install click")
        print("Basic usage: python -m wf2wf.cli <input_file> <output_file>")
        sys.exit(1)
    
    # Very basic conversion without click
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path.with_suffix('.dag')
    
    # Auto-detect formats
    input_format = detect_input_format(input_path)
    output_format = detect_output_format(output_path)
    
    if not input_format:
        print(f"Error: Cannot detect input format from {input_path}")
        sys.exit(1)
    
    if not output_format:
        output_format = 'dagman' if input_format == 'snakemake' else 'json'
    
    print(f"Converting {input_format} → {output_format}")
    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    
    # Load workflow
    if input_format in ['json', 'yaml']:
        wf = load_workflow_from_json_yaml(input_path)
    else:
        importer = get_importer(input_format)
        if not importer:
            print(f"Error: No importer available for format: {input_format}")
            sys.exit(1)
        wf = importer.to_workflow(input_path)
    
    # Save workflow
    if output_format in ['json', 'yaml']:
        save_workflow_to_json_yaml(wf, output_path)
    else:
        exporter = get_exporter(output_format)
        if not exporter:
            print(f"Error: No exporter available for format: {output_format}")
            sys.exit(1)
        exporter.from_workflow(wf, output_path)
    
    print(f"✓ Conversion completed: {output_path}")


if __name__ == '__main__':
    if click:
        cli()
    else:
        simple_main()


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


def _write_estar_package(assets: dict[str, Path], out_zip: Path, *, verbose: bool = False):
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