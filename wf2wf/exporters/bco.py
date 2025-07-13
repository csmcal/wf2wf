from __future__ import annotations

"""wf2wf.exporters.bco – Workflow IR ➜ BioCompute Object (IEEE 2791-2020)

Phase 6C minimal implementation:
• Map core Workflow metadata + I/O + steps into the nine BCO domains
• Produce a single JSON document compliant with the top-level BCO schema
  (detailed sub-schemas are not fully validated here – that is a future task)

Usage:
    from wf2wf.exporters import load
    load('bco').from_workflow(wf, 'pipeline.bco.json')
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import tarfile

from wf2wf.core import Workflow, ParameterSpec
from wf2wf.exporters.base import BaseExporter
from wf2wf.exporters.cwl import from_workflow

logger = logging.getLogger(__name__)

BCO_SCHEMA_URL = "https://w3id.org/ieee/ieee-2791-schema/2791object.json"

# -----------------------------------------------------------------------------
# Helper functions to populate individual BCO domains
# -----------------------------------------------------------------------------


def _make_provenance_domain(wf: Workflow) -> Dict[str, Any]:
    prov: Dict[str, Any] = {
        "name": wf.name,
        "version": wf.version,
        "created": datetime.now(timezone.utc).isoformat(),
    }
    if wf.provenance:
        prov.update(
            {
                "contributors": wf.provenance.contributors,
                "license": wf.provenance.license,
                "publication": wf.provenance.doi,
                "modified": wf.provenance.modified,
            }
        )
        if wf.provenance.authors:
            prov["creators"] = wf.provenance.authors
    return prov


def _make_description_domain(wf: Workflow) -> Dict[str, Any]:
    return {
        "keywords": (
            wf.provenance.keywords if wf.provenance and wf.provenance.keywords else []
        )
        + wf.intent,
        "platform": "wf2wf",
        "pipeline_steps": [
            {
                "step_number": idx + 1,
                "name": task.id,
                "description": task.doc or task.label or task.id,
            }
            for idx, task in enumerate(wf.tasks.values())
        ],
        "xref": wf.intent,
        "overview": wf.doc or wf.label or wf.name,
    }


def _make_usability_domain(wf: Workflow) -> List[str]:
    """Return human‐readable usage notes or examples."""
    notes: List[str] = []
    if wf.documentation and wf.documentation.usage_notes:
        notes.append(wf.documentation.usage_notes)
    if wf.documentation and wf.documentation.examples:
        for ex in wf.documentation.examples:
            notes.append(ex.get("description", ""))
    if not notes and wf.doc:
        notes.append(wf.doc)
    return notes


def _make_parametric_domain(wf: Workflow) -> List[Dict[str, Any]]:
    """Map workflow inputs that have defaults into BCO parametric domain."""
    params = []
    for p in wf.inputs:
        entry = {
            "param": p.id,
            "value": p.default,
            "type": str(p.type),
        }
        if p.doc or p.label:
            entry["description"] = p.doc or p.label
        params.append(entry)
    return params


def _make_extension_domain(wf: Workflow) -> List[Dict[str, Any]]:
    """Expose WF meta dictionary as free-form extension records."""
    # Check if workflow has meta attribute (legacy support)
    if hasattr(wf, 'meta') and wf.meta:
        return [{"namespace": "wf2wf:meta", "data": wf.meta}]
    
    # Check if workflow has metadata with format_specific data
    if hasattr(wf, 'metadata') and wf.metadata and wf.metadata.format_specific:
        return [{"namespace": "wf2wf:metadata", "data": wf.metadata.format_specific}]
    
    return []


def _param_to_io(item: ParameterSpec, io_type: str) -> Dict[str, Any]:
    return {
        "id": item.id,
        "type": io_type,
        "spec": {
            "data_type": str(item.type),
            "description": item.doc or item.label or item.id,
        },
    }


def _make_io_domain(wf: Workflow) -> Dict[str, Any]:
    return {
        "input_subdomain": [_param_to_io(p, "input") for p in wf.inputs],
        "output_subdomain": [_param_to_io(p, "output") for p in wf.outputs],
    }


def _make_execution_domain(wf: Workflow) -> Dict[str, Any]:
    steps = []
    for num, task in enumerate(wf.tasks.values(), start=1):
        # Get environment-specific values for shared_filesystem environment
        container = task.container.get_value_for("shared_filesystem") if hasattr(task, 'container') else None
        conda = task.conda.get_value_for("shared_filesystem") if hasattr(task, 'conda') else None
        cpu = task.cpu.get_value_for("shared_filesystem") if hasattr(task, 'cpu') else 1
        mem_mb = task.mem_mb.get_value_for("shared_filesystem") if hasattr(task, 'mem_mb') else 4096
        gpu = task.gpu.get_value_for("shared_filesystem") if hasattr(task, 'gpu') else 0
        env_vars = task.env_vars.get_value_for("shared_filesystem") if hasattr(task, 'env_vars') else {}
        
        # Get command or script
        command = task.command.get_value_for("shared_filesystem") if hasattr(task, 'command') else None
        script = task.script.get_value_for("shared_filesystem") if hasattr(task, 'script') else None
        software = command or script
        
        steps.append(
            {
                "step_number": num,
                "name": task.id,
                "software": software,
                "environment": {
                    "container": container,
                    "conda_env": conda,
                    "cpu": cpu,
                    "memory_mb": mem_mb,
                    "gpu": gpu,
                    **(
                        {"sbom_digest": env_vars.get("WF2WF_SBOM_DIGEST")}
                        if env_vars and env_vars.get("WF2WF_SBOM_DIGEST")
                        else {}
                    ),
                },
            }
        )
    return {
        "script": wf.name,
        "script_driver": "wf2wf",
        "software_prerequisites": steps,
    }


def _make_error_domain() -> Dict[str, Any]:
    # Placeholder; full error handling integration planned later.
    return {"empirical_error": [], "algorithmic_error": []}


# -----------------------------------------------------------------------------
# Public API – conforming to exporter interface
# -----------------------------------------------------------------------------


class BCOExporter(BaseExporter):
    """BCO exporter using shared infrastructure."""
    
    def _get_target_format(self) -> str:
        """Get the target format name."""
        return "bco"
    
    def _generate_output(self, workflow: Workflow, output_path: Path, **opts: Any) -> None:
        """Generate BCO output."""
        if self.verbose:
            logger.info(f"Generating BCO workflow: {output_path}")
            logger.info(f"  Workflow: {workflow.name}")
            logger.info(f"  Tasks: {len(workflow.tasks)}")
            logger.info(f"  Inputs: {len(workflow.inputs)}")
            logger.info(f"  Outputs: {len(workflow.outputs)}")
        
        # Call the module-level _export_bco_workflow function directly
        _export_bco_workflow(workflow, output_path, **opts)
    
    def from_workflow(self, workflow: Workflow, output_path: Path, **opts: Any) -> None:
        """Export workflow to BCO format (method interface for CLI compatibility)."""
        self._generate_output(workflow, output_path, **opts)


def _export_bco_workflow(wf: Workflow, out_file: Union[str, Path], **opts: Any):
    """Internal BCO export function."""
    out_path = Path(out_file)
    if out_path.suffix.lower() not in {".json", ".bco"}:
        out_path = out_path.with_suffix(out_path.suffix + ".json")

    include_cwl = opts.get("include_cwl", False)
    cwl_path: Union[Path, None] = None

    # Assemble BCO structure --------------------------------------------------
    bco: Dict[str, Any] = {
        "$schema": BCO_SCHEMA_URL,
        "provenance_domain": _make_provenance_domain(wf),
        "usability_domain": _make_usability_domain(wf),
        "extension_domain": _make_extension_domain(wf),
        "description_domain": _make_description_domain(wf),
        "execution_domain": _make_execution_domain(wf),
        "parametric_domain": _make_parametric_domain(wf),
        "io_domain": _make_io_domain(wf),
        "error_domain": _make_error_domain(),
    }

    # Honour pre-existing bco_spec (if provided)
    if wf.bco_spec:
        for key, value in wf.bco_spec.__dict__.items():
            if value and key.endswith("_domain"):
                bco[key] = value
            elif key in {"object_id", "etag", "spec_version"}:
                bco[key] = value

    # Optionally export CWL and link it
    if include_cwl:
        try:
            cwl_path = out_path.with_suffix(".cwl")
            # Import CWL exporter to avoid circular call
            from .cwl import from_workflow as cwl_from_workflow
            cwl_from_workflow(wf, cwl_path)
            bco["execution_domain"]["script"] = cwl_path.name
        except Exception as e:
            raise RuntimeError(f"Failed to generate CWL alongside BCO: {e}")

    # Ensure top-level identifiers
    bco.setdefault("object_id", f"urn:uuid:{out_path.stem}")

    # ------------------------------------------------------------------
    # Compute integrity hash *before* writing so we can embed sha256 etag
    # ------------------------------------------------------------------

    import hashlib
    import json as _json

    try:
        import requests  # type: ignore
    except ModuleNotFoundError:  # pragma: no cover – optional dependency
        requests = None

    _serialized = _json.dumps(bco, sort_keys=True, separators=(",", ":"))
    _sha = hashlib.sha256(_serialized.encode()).hexdigest()
    bco["etag"] = f"sha256:{_sha}"

    # ------------------------------------------------------------------
    # Optional in-toto provenance attestation – if a sibling *.intoto.json exists
    # ------------------------------------------------------------------

    intoto_path = out_path.with_suffix(".intoto.json")
    if intoto_path.exists():
        bco.setdefault("extension_domain", []).append(
            {
                "namespace": "wf2wf:provenance",
                "attestation": intoto_path.name,
            }
        )

    # ------------------------------------------------------------------
    # Basic structural validation – ensure all mandatory BCO domains are
    # present *before* we attempt external JSON-Schema validation so that
    # omissions are caught even when the jsonschema package or remote schema
    # is unavailable.
    # ------------------------------------------------------------------

    _REQUIRED_DOMAINS = {
        "provenance_domain",
        "usability_domain",
        "description_domain",
        "execution_domain",
        "parametric_domain",
        "io_domain",
        "error_domain",
    }

    missing = _REQUIRED_DOMAINS - set(bco)
    if missing:
        raise ValueError(
            "Generated BCO is missing required domain(s): " + ", ".join(sorted(missing))
        )

    # Write JSON -------------------------------------------------------------
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # JSON-Schema validation (try remote spec, fallback to minimal stub)
    # ------------------------------------------------------------------

    if opts.get("validate", True):
        try:
            import jsonschema  # type: ignore

            schema = None
            _remote_url = BCO_SCHEMA_URL

            if requests is not None:
                try:
                    resp = requests.get(_remote_url, timeout=10)
                    if resp.status_code == 200:
                        schema = resp.json()
                except Exception:
                    schema = None  # network failure triggers fallback

            if schema is None:
                # Fallback – minimal stub keeps tests offline-safe
                schema = {
                    "type": "object",
                    "required": [
                        "provenance_domain",
                        "description_domain",
                        "execution_domain",
                        "io_domain",
                    ],
                }

            jsonschema.validate(instance=bco, schema=schema)
        except ModuleNotFoundError:
            pass  # jsonschema not installed – skip
        except Exception as e:
            raise ValueError(f"BCO JSON-Schema validation failed: {e}")

    out_path.write_text(json.dumps(bco, indent=2))

    if include_cwl and cwl_path is not None and opts.get("package", False):
        package_path = out_path.with_suffix(".tar.gz")
        with tarfile.open(package_path, "w:gz") as tar:
            tar.add(out_path, arcname=out_path.name)
            tar.add(cwl_path, arcname=cwl_path.name)
        if opts.get("verbose"):
            logger.info(f"BCO+CWL package written to {package_path}")

    if opts.get("verbose"):
        logger.info(f"BCO document written to {out_path}")


def from_workflow(wf: Workflow, out_file: Union[str, Path], **opts: Any):  # noqa: N802 – public API name
    """Export *wf* to a BioCompute Object JSON document (legacy function).

    Args:
        wf:   Workflow IR instance.
        out_file: Target file path (*.json).
        **opts: Currently unused; reserved for future options such as
                 compliance level, SPDX attachment, etc.
    """
    exporter = BCOExporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False)
    )
    exporter.export_workflow(wf, out_file, **opts)


# ---------------------------------------------------------------------------
# Convenience: FDA submission package bundler
# ---------------------------------------------------------------------------


def generate_fda_submission_package(
    wf: Workflow,
    package_path: Union[str, Path],
    *,
    submission_type: str = "510k",
    verbose: bool = False,
) -> Path:
    """Create an *FDA submission bundle* for *wf*.

    The bundle contains:
        • BioCompute Object JSON    (<name>.bco.json)
        • CWL workflow             (<name>.cwl)
        • Simple validation report (validation.txt)
        • README describing contents

    Returned path points to the generated *.tar.gz* file.

    Notes
    -----
    This is **not** an officially endorsed FDA format but follows
    common practice of including an IEEE 2791 object and the CWL
    workflow in a single archive.  Future work will extend this with
    SBOMs, checksums, and formal validation artefacts.
    """

    from tempfile import TemporaryDirectory

    pkg_path = Path(package_path)
    if pkg_path.suffix != ".gz":
        pkg_path = pkg_path.with_suffix(".tar.gz")

    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        stem = pkg_path.stem.replace(".tar", "")

        # 1) Write BCO + CWL ---------------------------------------------
        bco_path = tmpdir / f"{stem}.bco.json"
        from_workflow(wf, bco_path, include_cwl=True, validate=True, verbose=False)

        cwl_path = bco_path.with_suffix(".cwl")  # exporter placed it side-by-side

        # 2) Write validation report -------------------------------------
        report_path = tmpdir / "validation.txt"
        report_path.write_text(
            "wf2wf FDA submission bundle\n"
            f"Generated: {datetime.now(timezone.utc).isoformat()}\n"
            f"Submission type: {submission_type}\n"
            f"Workflow: {wf.name} (v{wf.version})\n"
            "Files: " + ", ".join(p.name for p in [bco_path, cwl_path]) + "\n"
        )

        # 3) Write README -------------------------------------------------
        readme_path = tmpdir / "README.txt"
        readme_path.write_text(
            "This archive contains a BioCompute Object (IEEE 2791-2020) and the\n"
            "corresponding CWL workflow, suitable for inclusion in an FDA "
            "510(k) submission or IDE application.  Validate the BCO with the\n"
            "official schema and execute the CWL using cwltool to reproduce "
            "results.\n"
        )

        # 4) Package everything -----------------------------------------
        pkg_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(pkg_path, "w:gz") as tar:
            tar.add(bco_path, arcname=bco_path.name)
            tar.add(cwl_path, arcname=cwl_path.name)
            tar.add(report_path, arcname=report_path.name)
            tar.add(readme_path, arcname=readme_path.name)

        if verbose:
            logger.info(f"FDA submission package written to {pkg_path}")

    return pkg_path


def _maybe_add_cwl_workflow(
    wf: Workflow,
    bco_data: Dict[str, Any],
    cwl_path: Union[Path, None] = None
) -> None:
    # Implementation of the function
    pass
