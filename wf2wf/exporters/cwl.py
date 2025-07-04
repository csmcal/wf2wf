"""wf2wf.exporters.cwl – Workflow IR ➜ CWL v1.2

This module exports wf2wf intermediate representation workflows to
Common Workflow Language (CWL) v1.2 format with full feature preservation.

Enhanced features supported:
- Advanced metadata and provenance export
- Conditional execution (when expressions)
- Scatter/gather operations with all scatter methods
- Complete parameter specifications with CWL type system
- Requirements and hints export
- File management with secondary files and validation
- BCO integration for regulatory compliance
"""

from __future__ import annotations

import json
import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from wf2wf.core import (
    Workflow,
    Task,
    ResourceSpec,
    EnvironmentSpec,
    ParameterSpec,
    RequirementSpec,
    ProvenanceSpec,
    DocumentationSpec,
    BCOSpec,
)
from wf2wf.loss import (
    reset as loss_reset,
    record as loss_record,
    write as loss_write,
    as_list as loss_list,
    prepare as loss_prepare,
)

# -----------------------------------------------------------------------------
# Schema registry for complex types (record / enum).  Cleared at the beginning
# of every top-level export call and written into the `$schemas` block if non-empty.
# -----------------------------------------------------------------------------

_GLOBAL_SCHEMA_REGISTRY: Dict[str, Dict[str, Any]] = {}

# -----------------------------------------------------------------------------
# Loss recording now handled by wf2wf.loss module
# -----------------------------------------------------------------------------


def from_workflow(wf: Workflow, out_file: Union[str, Path], **opts: Any) -> None:
    """Export a wf2wf workflow to CWL v1.2 format with full feature preservation.

    Args:
        wf: The workflow to export
        out_file: Path for the output CWL workflow file
        **opts: Additional options:
            - tools_dir: str = "tools" - Directory for tool definitions
            - format: str = "yaml" - Output format (yaml or json)
            - cwl_version: str = "v1.2" - CWL version to target
            - single_file: bool = False - Generate single file with inline tools
            - preserve_metadata: bool = True - Preserve all enhanced metadata
            - export_bco: bool = False - Export BCO alongside CWL
            - verbose: bool = False - Enable verbose output
            - graph: bool = False - Export graph representation
            - structure_prov: bool = False - Structure provenance
            - root_id: str - Override root ID

    Raises:
        RuntimeError: If the workflow cannot be exported
    """
    output_path = Path(out_file).resolve()
    tools_dir = opts.get("tools_dir", "tools")
    output_format = opts.get("format", "yaml")
    cwl_version = opts.get("cwl_version", "v1.2")
    single_file = opts.get("single_file", False)
    preserve_metadata = opts.get("preserve_metadata", True)
    export_bco = opts.get("export_bco", False)
    verbose = opts.get("verbose", False)
    use_graph = opts.get("graph", False)
    structure_prov = opts.get("structure_prov", False)
    root_id_override = opts.get("root_id")

    global _GLOBAL_SCHEMA_REGISTRY
    _GLOBAL_SCHEMA_REGISTRY = {}

    # Initialise loss tracking
    loss_prepare(wf.loss_map)
    loss_reset()

    if verbose:
        print(
            f"Exporting workflow '{wf.name}' to CWL {cwl_version} with enhanced features"
        )

    try:
        # Record unsupported features prior to generation

        for task in wf.tasks.values():
            # GPU resources partially unsupported in CWL 1.2 ResourceRequirement
            if getattr(task.resources, "gpu", None):
                loss_record(
                    f"/tasks/{task.id}/resources/gpu",
                    "gpu",
                    task.resources.gpu,
                    "CWL ResourceRequirement lacks GPU fields",
                    "user",
                )
            if getattr(task.resources, "gpu_mem_mb", None):
                loss_record(
                    f"/tasks/{task.id}/resources/gpu_mem_mb",
                    "gpu_mem_mb",
                    task.resources.gpu_mem_mb,
                    "CWL ResourceRequirement lacks GPU memory",
                    "user",
                )
            if getattr(task.resources, "gpu_capability", None):
                loss_record(
                    f"/tasks/{task.id}/resources/gpu_capability",
                    "gpu_capability",
                    task.resources.gpu_capability,
                    "CWL cannot express GPU capability",
                    "user",
                )

            # Priority and retry are not part of CWL core spec
            if task.priority:
                loss_record(
                    f"/tasks/{task.id}",
                    "priority",
                    task.priority,
                    "CWL lacks job priority field",
                    "user",
                )
            if task.retry:
                loss_record(
                    f"/tasks/{task.id}",
                    "retry",
                    task.retry,
                    "CWL lacks retry mechanism; use engine hints instead",
                    "user",
                )

        # Create output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if use_graph:
            if verbose:
                print("Exporting CWL using $graph representation")

            tool_docs = {}
            for task in wf.tasks.values():
                t_doc = _generate_tool_document_enhanced(
                    task,
                    preserve_metadata=preserve_metadata,
                    structure_prov=structure_prov,
                )
                t_doc["id"] = task.id  # ensure stable id
                tool_docs[task.id] = t_doc

            # Workflow document with run refs pointing to '#id'
            wf_doc = _generate_workflow_document_enhanced(
                wf,
                {tid: f"#{tid}" for tid in wf.tasks},
                "",
                cwl_version,
                preserve_metadata=preserve_metadata,
                verbose=verbose,
                structure_prov=structure_prov,
            )
            wf_doc["id"] = root_id_override or wf.name or "wf"

            graph_list = [wf_doc] + list(tool_docs.values())
            cwl_doc = {"cwlVersion": cwl_version, "$graph": graph_list}

            # Attach $schemas if we gathered any complex type definitions
            if _GLOBAL_SCHEMA_REGISTRY:
                cwl_doc["$schemas"] = list(_GLOBAL_SCHEMA_REGISTRY.values())

            _write_cwl_document(cwl_doc, output_path, output_format)

            if verbose:
                print(f"CWL graph exported to {output_path}")
            return

        if single_file:
            # Generate single file with inline tools
            cwl_doc = _generate_single_file_workflow_enhanced(
                wf,
                cwl_version,
                preserve_metadata=preserve_metadata,
                verbose=verbose,
                structure_prov=structure_prov,
            )
        else:
            # Generate main workflow with separate tool files
            tools_path = output_path.parent / tools_dir
            tools_path.mkdir(parents=True, exist_ok=True)

            # Generate tool files with enhanced features
            tool_refs = _generate_tool_files_enhanced(
                wf,
                tools_path,
                output_format,
                preserve_metadata=preserve_metadata,
                verbose=verbose,
                structure_prov=structure_prov,
            )

            # Generate main workflow with enhanced features
            cwl_doc = _generate_workflow_document_enhanced(
                wf,
                tool_refs,
                tools_dir,
                cwl_version,
                preserve_metadata=preserve_metadata,
                verbose=verbose,
                structure_prov=structure_prov,
            )

        # Attach $schemas if present
        if _GLOBAL_SCHEMA_REGISTRY:
            cwl_doc["$schemas"] = list(_GLOBAL_SCHEMA_REGISTRY.values())

        # Write main workflow file
        _write_cwl_document(cwl_doc, output_path, output_format)

        # Export BCO if requested
        if export_bco and wf.bco_spec:
            bco_path = output_path.with_suffix(".bco.json")
            _export_bco_document(wf.bco_spec, bco_path, verbose=verbose)

        if verbose:
            print(f"Enhanced CWL workflow exported to: {output_path}")
            if not single_file:
                print(f"Tool definitions in: {output_path.parent / tools_dir}")
            if export_bco and wf.bco_spec:
                print(f"BCO document exported to: {bco_path}")

    except Exception as e:
        raise RuntimeError(f"Failed to export enhanced CWL workflow: {e}")

    # Report hooks
    try:
        from wf2wf import report as _rpt

        _rpt.add_artefact(output_path)
        _rpt.add_action("Exported CWL workflow")
    except ImportError:
        pass

    loss_write(output_path.with_suffix(".loss.json"), target_engine="cwl")
    wf.loss_map = loss_list()


def _generate_workflow_document_enhanced(
    wf: Workflow,
    tool_refs: Dict[str, str],
    tools_dir: str,
    cwl_version: str,
    preserve_metadata: bool = True,
    verbose: bool = False,
    *,
    structure_prov: bool = False,
) -> Dict[str, Any]:
    """Generate the main CWL workflow document with enhanced features."""

    cwl_doc = {"cwlVersion": cwl_version, "class": "Workflow"}

    # Add enhanced metadata - use workflow name as label if no label is set
    cwl_doc["label"] = wf.label or wf.name
    if wf.doc:
        cwl_doc["doc"] = wf.doc

    # Add provenance information
    if preserve_metadata and wf.provenance:
        _add_provenance_to_doc(cwl_doc, wf.provenance, structure=structure_prov)

    # Add documentation
    if preserve_metadata and wf.documentation:
        _add_documentation_to_doc(cwl_doc, wf.documentation)

    # Add intent (ontology IRIs)
    if wf.intent:
        cwl_doc["intent"] = wf.intent

    # expressionLib preserved in meta
    expr_lib = wf.meta.get("expressionLib") if wf.meta else None
    if expr_lib:
        cwl_doc["expressionLib"] = expr_lib

    # Add requirements with enhanced features
    requirements = []

    # Add workflow-level requirements
    for req_spec in wf.requirements:
        requirements.append(_requirement_spec_to_cwl(req_spec))

    # Check if we need additional requirements based on workflow features
    if len(wf.tasks) > 1:
        requirements.append({"class": "SubworkflowFeatureRequirement"})

    # Check for conditional execution
    has_conditional = any(task.when for task in wf.tasks.values())
    if has_conditional:
        requirements.append({"class": "ConditionalWhenRequirement"})

    # Check for scatter operations
    has_scatter = any(task.scatter for task in wf.tasks.values())
    if has_scatter:
        requirements.append({"class": "ScatterFeatureRequirement"})

    # Check for step input expressions
    needs_step_input_expr = any(
        task.meta and "step_inputs" in task.meta for task in wf.tasks.values()
    )
    if needs_step_input_expr:
        requirements.append({"class": "StepInputExpressionRequirement"})

    if requirements:
        cwl_doc["requirements"] = requirements

    # Add hints with enhanced features
    if wf.hints:
        cwl_doc["hints"] = [_requirement_spec_to_cwl(hint) for hint in wf.hints]

    # Generate workflow inputs from enhanced parameter specifications
    cwl_doc["inputs"] = _generate_workflow_inputs_enhanced(wf)

    # Generate workflow outputs from enhanced parameter specifications
    cwl_doc["outputs"] = _generate_workflow_outputs_enhanced(wf)

    # Generate workflow steps with enhanced features
    cwl_doc["steps"] = _generate_workflow_steps_enhanced(
        wf, tool_refs, tools_dir, preserve_metadata=preserve_metadata, verbose=verbose
    )

    return cwl_doc


def _generate_workflow_inputs_enhanced(wf: Workflow) -> Dict[str, Any]:
    """Generate CWL workflow inputs from enhanced parameter specifications or config."""

    inputs = {}

    # If workflow has enhanced parameter specifications, use them
    if wf.inputs:
        for param in wf.inputs:
            inputs[param.id] = _parameter_spec_to_cwl(param)
        return inputs

    # Fallback to config-based generation for backward compatibility
    for key, value in wf.config.items():
        input_def = {}

        # Infer type from value
        if isinstance(value, bool):
            input_def["type"] = "boolean"
        elif isinstance(value, int):
            input_def["type"] = "int"
        elif isinstance(value, float):
            input_def["type"] = "float"
        elif isinstance(value, str):
            # Check if it looks like a file path (platform-agnostic)
            if "." in value and (os.sep in value or (os.altsep and os.altsep in value)):
                input_def["type"] = "File"
            else:
                input_def["type"] = "string"
        else:
            input_def["type"] = "string"

        # Add default value
        if value is not None:
            input_def["default"] = value

        # Add documentation
        input_def["doc"] = f"Workflow parameter: {key}"

        inputs[key] = input_def

    # Add a default input_data file if no file inputs exist
    has_file_input = any(inp.get("type") == "File" for inp in inputs.values())

    if not has_file_input:
        inputs["input_data"] = {"type": "File", "doc": "Primary input data file"}

    return inputs


def _generate_workflow_outputs_enhanced(wf: Workflow) -> Dict[str, Any]:
    """Generate CWL workflow outputs from enhanced parameter specifications or inferred outputs."""

    outputs = {}

    # If workflow has enhanced parameter specifications, use them
    if wf.outputs:
        for param in wf.outputs:
            outputs[param.id] = _parameter_spec_to_cwl(param)
        return outputs

    # Fallback to inferred outputs for backward compatibility
    # Find tasks with no children (final outputs)
    final_tasks = []
    for task in wf.tasks.values():
        has_children = any(edge.parent == task.id for edge in wf.edges)
        if not has_children:
            final_tasks.append(task)

    # If no final tasks found, use all tasks
    if not final_tasks:
        final_tasks = list(wf.tasks.values())

    for task in final_tasks:
        output_name = f"{task.id}_output"
        outputs[output_name] = {
            "type": "File",
            "outputSource": f"{task.id}/output_file",
            "doc": f"Output from {task.id}",
        }

    return outputs


def _generate_workflow_steps_enhanced(
    wf: Workflow,
    tool_refs: Dict[str, str],
    tools_dir: str,
    preserve_metadata: bool = True,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Generate CWL workflow steps."""

    steps = {}

    for task in wf.tasks.values():
        if verbose:
            print(f"Generating step: {task.id}")

        # For single file mode (empty tool_refs), use placeholder that will be replaced
        tool_ref = tool_refs.get(task.id, f"PLACEHOLDER_{task.id}")

        step_def = {
            "run": tool_ref,
            "in": _generate_step_inputs_enhanced(task, wf),
            "out": ["output_file"],  # Standard output
        }
        # Conditional execution
        if task.when:
            step_def["when"] = task.when
        if task.retry:
            loss_record(
                f"/tasks/{task.id}/retry",
                "retry",
                task.retry,
                "Retry count not supported in CWL",
                "user",
            )
        if task.priority:
            loss_record(
                f"/tasks/{task.id}/priority",
                "priority",
                task.priority,
                "Priority not representable in CWL",
                "user",
            )

        # Scatter handling
        if task.scatter:
            scat_list = task.scatter.scatter
            if len(scat_list) == 1 and (
                task.scatter.scatter_method in (None, "", "dotproduct")
            ):
                # Shorthand scalar form
                step_def["scatter"] = scat_list[0]
            else:
                step_def["scatter"] = scat_list
                if (
                    task.scatter.scatter_method
                    and task.scatter.scatter_method != "dotproduct"
                ):
                    step_def["scatterMethod"] = task.scatter.scatter_method

        # Propagate SBOM/SIF paths as simple annotations for easy parsing in
        # downstream tooling and regression tests.
        sbom = task.environment.env_vars.get("WF2WF_SBOM") if task.environment else None
        if sbom:
            step_def["wf2wf_sbom"] = str(sbom)
        sif = task.environment.env_vars.get("WF2WF_SIF") if task.environment else None
        if sif:
            step_def["wf2wf_sif"] = str(sif)

        steps[task.id] = step_def

    return steps


def _generate_step_inputs_enhanced(task: Task, wf: Workflow) -> Dict[str, Any]:
    """Generate inputs for a workflow step."""

    inputs = {}

    # ------------------------------------------------------------------
    # Dependency-based wiring (as before)
    # ------------------------------------------------------------------
    parent_tasks = [edge.parent for edge in wf.edges if edge.child == task.id]

    if parent_tasks:
        for i, parent in enumerate(parent_tasks):
            input_name = f"input_file_{i}" if i > 0 else "input_file"
            inputs[input_name] = f"{parent}/output_file"
    else:
        inputs["input_file"] = "input_data"

    # Workflow-level config params (legacy demo logic)
    for param_name in ["threshold", "max_iterations", "output_dir"]:
        if param_name in wf.config:
            inputs[param_name] = param_name

    # ------------------------------------------------------------------
    # Inject valueFrom expressions from ParameterSpec annotations
    # ------------------------------------------------------------------
    for ps in task.inputs:
        if ps.value_from is None:
            continue

        # Ensure entry exists
        if ps.id not in inputs:
            # Without explicit source we create empty mapping allowing pure valueFrom
            inputs[ps.id] = {}

        if isinstance(inputs[ps.id], str):
            inputs[ps.id] = {"source": inputs[ps.id], "valueFrom": ps.value_from}
        elif isinstance(inputs[ps.id], dict):
            inputs[ps.id]["valueFrom"] = ps.value_from

    return inputs


def _generate_tool_files_enhanced(
    wf: Workflow,
    tools_path: Path,
    output_format: str,
    preserve_metadata: bool = True,
    verbose: bool = False,
    *,
    structure_prov: bool = False,
) -> Dict[str, str]:
    """Generate individual CWL tool files for each task."""

    tool_refs = {}

    for task in wf.tasks.values():
        if verbose:
            print(f"Generating tool file for: {task.id}")

        # Generate tool document
        tool_doc = _generate_tool_document_enhanced(
            task, preserve_metadata=preserve_metadata, structure_prov=structure_prov
        )

        # Write tool file
        tool_filename = f"{task.id}.cwl"
        tool_path = tools_path / tool_filename
        _write_cwl_document(tool_doc, tool_path, output_format)

        # Store relative reference
        tool_refs[task.id] = f"tools/{tool_filename}"

    return tool_refs


def _generate_tool_document_enhanced(
    task: Task, *, preserve_metadata: bool = True, structure_prov: bool = False
) -> Dict[str, Any]:
    """Generate a CWL CommandLineTool document with enhanced features."""

    tool_doc = {"cwlVersion": "v1.2", "class": "CommandLineTool"}

    # Add enhanced metadata
    if task.label:
        tool_doc["label"] = task.label
    if task.doc:
        tool_doc["doc"] = task.doc

    # Add provenance and documentation if available
    if preserve_metadata:
        if task.provenance:
            _add_provenance_to_doc(tool_doc, task.provenance, structure=structure_prov)
        if task.documentation:
            _add_documentation_to_doc(tool_doc, task.documentation)

    # Add intent
    if task.intent:
        tool_doc["intent"] = task.intent

    # Parse command for CWL
    if task.command:
        base_command, arguments = _parse_command_for_cwl(task.command)
        if base_command:  # Only set if we got a valid command
            tool_doc["baseCommand"] = base_command
            if arguments:
                tool_doc["arguments"] = arguments
        else:
            # Fallback for comments or empty commands
            tool_doc["baseCommand"] = ["echo", "No command specified"]
    else:
        tool_doc["baseCommand"] = ["echo", "No command specified"]

    # Add requirements with enhanced features
    requirements = []

    # Add task-level requirements
    for req_spec in task.requirements:
        requirements.append(_requirement_spec_to_cwl(req_spec))

    # Generate resource requirement
    resource_req = _generate_resource_requirement(task.resources)
    if resource_req:
        requirements.append(resource_req)

    # Generate environment requirement
    env_req = _generate_environment_requirement(task.environment)
    if env_req:
        requirements.append(env_req)

    if requirements:
        tool_doc["requirements"] = requirements

    # Add hints (existing + auto-injected SBOM/SIF)
    hints = (
        [_requirement_spec_to_cwl(hint) for hint in task.hints] if task.hints else []
    )

    # Auto-inject wf2wf SBOM / SIF provenance as generic hints so they survive round-trip
    sbom_path = (
        task.environment.env_vars.get("WF2WF_SBOM") if task.environment else None
    )
    sif_path = task.environment.env_vars.get("WF2WF_SIF") if task.environment else None

    if sbom_path:
        hints.append({"class": "wf2wf:SBOM", "location": str(sbom_path)})
        # Legacy compatibility: also embed as plain key for simple grep tests
        tool_doc["wf2wf_sbom"] = str(sbom_path)

    if sif_path and sif_path.endswith(".sif"):
        hints.append({"class": "wf2wf:SIF", "location": str(sif_path)})

    if hints:
        tool_doc["hints"] = hints

    # Generate inputs and outputs with enhanced features
    tool_doc["inputs"] = _generate_tool_inputs_enhanced(task)
    tool_doc["outputs"] = _generate_tool_outputs_enhanced(task)

    return tool_doc


def _generate_resource_requirement(resources: ResourceSpec) -> Optional[Dict[str, Any]]:
    """Generate CWL ResourceRequirement from ResourceSpec."""

    req = {"class": "ResourceRequirement"}
    added_any = False

    if resources.cpu:
        req["coresMin"] = resources.cpu
        added_any = True

    if resources.mem_mb:
        req["ramMin"] = resources.mem_mb
        added_any = True

    if resources.disk_mb:
        req["tmpdirMin"] = resources.disk_mb
        added_any = True

    # GPU resources not directly representable in CWL ResourceRequirement
    if resources.gpu:
        loss_record(
            "/resources/gpu",
            "gpu",
            resources.gpu,
            "GPU resource specification is not representable in CWL",
            "user",
        )
    if resources.gpu_mem_mb:
        loss_record(
            "/resources/gpu_mem_mb",
            "gpu_mem_mb",
            resources.gpu_mem_mb,
            "GPU memory specification is not representable in CWL",
            "user",
        )
    if resources.extra:
        loss_record(
            "/resources/extra",
            "extra",
            resources.extra,
            "Extra HTCondor resource attributes dropped in CWL export",
            "user",
        )

    return req if added_any else None


def _generate_environment_requirement(env: EnvironmentSpec) -> Optional[Dict[str, Any]]:
    """Generate CWL environment requirement from EnvironmentSpec."""

    if env.container:
        from wf2wf.environ import format_container_for_target_format
        
        # Extract Docker image from container spec
        docker_image = format_container_for_target_format(env.container, "cwl")
        return {"class": "DockerRequirement", "dockerPull": docker_image}

    elif env.conda:
        # Convert conda environment to SoftwareRequirement
        packages = []

        if isinstance(env.conda, dict) and "dependencies" in env.conda:
            for dep in env.conda["dependencies"]:
                if isinstance(dep, str):
                    if "=" in dep:
                        name, version = dep.split("=", 1)
                        packages.append({"package": name, "version": [version]})
                    else:
                        packages.append({"package": dep})

        if packages:
            return {"class": "SoftwareRequirement", "packages": packages}

    return None


def _parse_command_for_cwl(command: str) -> tuple[List[str], List[str]]:
    """Parse a command string into baseCommand and arguments for CWL."""

    if not command or command.startswith("#"):
        return [], []

    # Simple command parsing (could be more sophisticated)
    parts = command.strip().split()

    if not parts:
        return [], []

    # First part is base command, rest are arguments
    base_command = [parts[0]]
    arguments = parts[1:] if len(parts) > 1 else []

    return base_command, arguments


def _generate_tool_inputs_enhanced(task: Task) -> Dict[str, Any]:
    """Generate CWL tool inputs from enhanced parameter specifications or defaults."""

    inputs = {}

    # If task has enhanced parameter specifications, use them
    if task.inputs:
        for param in task.inputs:
            inputs[param.id] = _parameter_spec_to_cwl(param)
        return inputs

    # Fallback to default inputs for backward compatibility
    inputs = {"input_file": {"type": "File", "doc": "Input data file"}}

    # Add common parameters
    inputs.update(
        {
            "threshold": {
                "type": "float?",
                "doc": "Analysis threshold",
                "default": 0.05,
            },
            "max_iterations": {
                "type": "int?",
                "doc": "Maximum iterations",
                "default": 1000,
            },
            "output_dir": {
                "type": "string?",
                "doc": "Output directory",
                "default": "results",
            },
        }
    )

    return inputs


def _generate_tool_outputs_enhanced(task: Task) -> Dict[str, Any]:
    """Generate CWL tool outputs from enhanced parameter specifications or defaults."""

    outputs = {}

    # If task has enhanced parameter specifications, use them
    if task.outputs:
        for param in task.outputs:
            outputs[param.id] = _parameter_spec_to_cwl(param)
        return outputs

    # Fallback to default outputs for backward compatibility
    return {
        "output_file": {
            "type": "File",
            "outputBinding": {"glob": f"{task.id}_output.*"},
            "doc": f"Output file from {task.id}",
        }
    }


def _generate_single_file_workflow_enhanced(
    wf: Workflow,
    cwl_version: str,
    preserve_metadata: bool = True,
    verbose: bool = False,
    *,
    structure_prov: bool = False,
) -> Dict[str, Any]:
    """Generate a single CWL file with inline tools and enhanced features."""

    # Generate the main workflow document with inline tool definitions
    cwl_doc = _generate_workflow_document_enhanced(
        wf,
        {},
        "",
        cwl_version,
        preserve_metadata=preserve_metadata,
        verbose=verbose,
        structure_prov=structure_prov,
    )

    # Replace tool references with inline tool definitions
    for step_id, step_def in cwl_doc["steps"].items():
        task = wf.tasks[step_id]
        # Replace the 'run' reference with inline tool definition
        step_def["run"] = _generate_tool_document_enhanced(
            task, preserve_metadata=preserve_metadata, structure_prov=structure_prov
        )

    return cwl_doc


def _write_cwl_document(
    doc: Dict[str, Any], output_path: Path, output_format: str = "yaml"
) -> None:
    """Write a CWL document to file in specified format."""

    if output_format.lower() == "json":
        with open(output_path.with_suffix(".json"), "w") as f:
            json.dump(doc, f, indent=2)
    else:
        # Default to YAML
        with open(output_path, "w") as f:
            # Add CWL shebang
            f.write("#!/usr/bin/env cwl-runner\n\n")
            yaml.dump(doc, f, default_flow_style=False, indent=2, sort_keys=False)


def _add_provenance_to_doc(
    cwl_doc: Dict[str, Any], provenance: ProvenanceSpec, *, structure: bool = False
) -> None:
    """Add provenance information to CWL document."""
    if provenance.authors:
        cwl_doc["author"] = provenance.authors
    if provenance.version:
        cwl_doc["version"] = provenance.version
    if provenance.license:
        cwl_doc["license"] = provenance.license
    if provenance.doi:
        cwl_doc["doi"] = provenance.doi
    if provenance.keywords:
        cwl_doc["keywords"] = provenance.keywords

    # Namespaced extras
    if structure:
        # Split extras into nested dicts by prefix
        grouped: Dict[str, Dict[str, Any]] = {}
        for k, v in provenance.extras.items():
            if ":" in k:
                prefix, local = k.split(":", 1)
                grouped.setdefault(prefix, {})[local] = v
            else:
                cwl_doc.setdefault(k, v)
        for prefix, mapping in grouped.items():
            sect = cwl_doc.setdefault(prefix, {})
            if isinstance(sect, dict):
                sect.update({k: v for k, v in mapping.items() if k not in sect})
    else:
        for k, v in provenance.extras.items():
            if k not in cwl_doc:
                cwl_doc[k] = v


def _add_documentation_to_doc(
    cwl_doc: Dict[str, Any], documentation: DocumentationSpec
) -> None:
    """Add documentation to CWL document."""
    if documentation.label and "label" not in cwl_doc:
        cwl_doc["label"] = documentation.label
    if documentation.doc and "doc" not in cwl_doc:
        cwl_doc["doc"] = documentation.doc
    if documentation.intent:
        cwl_doc["intent"] = documentation.intent


def _requirement_spec_to_cwl(req_spec: RequirementSpec) -> Dict[str, Any]:
    """Convert RequirementSpec to CWL requirement format."""
    req_dict = {"class": req_spec.class_name}
    req_dict.update(req_spec.data)
    return req_dict


def _parameter_spec_to_cwl(param_spec: ParameterSpec) -> Dict[str, Any]:
    """Convert ParameterSpec to CWL parameter format."""

    def _type_to_cwl(ts):
        from wf2wf.core import TypeSpec

        if isinstance(ts, str):
            return ts
        if isinstance(ts, TypeSpec):
            # Nullable → union with null
            _type_to_cwl(ts.type) if isinstance(ts.type, TypeSpec) else ts.type
            t_repr: Any
            if ts.type == "array":
                t_repr = {
                    "type": "array",
                    "items": _type_to_cwl(ts.items) if ts.items else "File",
                }
            elif ts.type == "record":
                t_repr = {
                    "type": "record",
                    "fields": [
                        {"name": name, "type": _type_to_cwl(sub)}
                        for name, sub in ts.fields.items()
                    ],
                }
                if ts.name:
                    t_repr["name"] = ts.name
                    # Register schema and return reference string
                    _GLOBAL_SCHEMA_REGISTRY.setdefault(ts.name, t_repr)
                    ref: Any = ts.name
                    if ts.nullable:
                        return ["null", ref]
                    return ref
            elif ts.type == "enum":
                t_repr = {"type": "enum", "symbols": ts.symbols}
                if ts.name:
                    t_repr["name"] = ts.name
                    _GLOBAL_SCHEMA_REGISTRY.setdefault(ts.name, t_repr)
                    ref: Any = ts.name
                    if ts.nullable:
                        return ["null", ref]
                    return ref
            else:
                t_repr = ts.type
            # Handle nullable via union
            if ts.nullable:
                return ["null", t_repr]
            return t_repr
        # list/union as-is
        return ts

    _type_repr = _type_to_cwl(param_spec.type)

    cwl_param = {"type": _type_repr}

    if param_spec.label:
        cwl_param["label"] = param_spec.label
    if param_spec.doc:
        cwl_param["doc"] = param_spec.doc
    if param_spec.default is not None:
        cwl_param["default"] = param_spec.default
    if param_spec.value_from is not None:
        cwl_param["valueFrom"] = param_spec.value_from

    # File-specific attributes
    if param_spec.format:
        cwl_param["format"] = param_spec.format
    if param_spec.secondary_files:
        cwl_param["secondaryFiles"] = param_spec.secondary_files
    if param_spec.streamable:
        cwl_param["streamable"] = param_spec.streamable
    if param_spec.load_contents:
        cwl_param["loadContents"] = param_spec.load_contents
    if param_spec.load_listing:
        cwl_param["loadListing"] = param_spec.load_listing

    # Binding information
    if param_spec.input_binding:
        cwl_param["inputBinding"] = param_spec.input_binding
    if param_spec.output_binding:
        cwl_param["outputBinding"] = param_spec.output_binding

    return cwl_param


def _export_bco_document(
    bco_spec: BCOSpec, bco_path: Path, verbose: bool = False
) -> None:
    """Export BCO document for regulatory compliance."""
    bco_doc = {
        "object_id": bco_spec.object_id,
        "spec_version": bco_spec.spec_version,
        "etag": bco_spec.etag,
        "provenance_domain": bco_spec.provenance_domain,
        "usability_domain": bco_spec.usability_domain,
        "extension_domain": bco_spec.extension_domain,
        "description_domain": bco_spec.description_domain,
        "execution_domain": bco_spec.execution_domain,
        "parametric_domain": bco_spec.parametric_domain,
        "io_domain": bco_spec.io_domain,
        "error_domain": bco_spec.error_domain,
    }

    # Remove None values
    bco_doc = {k: v for k, v in bco_doc.items() if v is not None}

    with open(bco_path, "w") as f:
        json.dump(bco_doc, f, indent=2, sort_keys=True)

    if verbose:
        print(f"BCO document exported to: {bco_path}")
