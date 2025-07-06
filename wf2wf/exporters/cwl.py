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
    ParameterSpec,
    RequirementSpec,
    ProvenanceSpec,
    DocumentationSpec,
    BCOSpec,
    EnvironmentSpecificValue,
)
from wf2wf.exporters.base import BaseExporter

# -----------------------------------------------------------------------------
# Schema registry for complex types (record / enum).  Cleared at the beginning
# of every top-level export call and written into the `$schemas` block if non-empty.
# -----------------------------------------------------------------------------

_GLOBAL_SCHEMA_REGISTRY: Dict[str, Dict[str, Any]] = {}


class CWLExporter(BaseExporter):
    """CWL exporter using shared infrastructure."""
    
    def _get_target_format(self) -> str:
        """Get the target format name."""
        return "cwl"
    
    def _generate_output(self, workflow: Workflow, output_path: Path, **opts: Any) -> None:
        """Generate CWL output."""
        tools_dir = opts.get("tools_dir", "tools")
        output_format = opts.get("format", "yaml")
        cwl_version = opts.get("cwl_version", "v1.2")
        single_file = opts.get("single_file", False)
        preserve_metadata = opts.get("preserve_metadata", True)
        export_bco = opts.get("export_bco", False)
        use_graph = opts.get("graph", False)
        structure_prov = opts.get("structure_prov", False)
        root_id_override = opts.get("root_id")

        global _GLOBAL_SCHEMA_REGISTRY
        _GLOBAL_SCHEMA_REGISTRY = {}

        if self.verbose:
            print(f"Exporting workflow '{workflow.name}' to CWL {cwl_version} with enhanced features")

        try:
            # Create output directory
            output_path.parent.mkdir(parents=True, exist_ok=True)

            if use_graph:
                if self.verbose:
                    print("Exporting CWL using $graph representation")

                tool_docs = {}
                for task in workflow.tasks.values():
                    t_doc = _generate_tool_document_enhanced(
                        task,
                        preserve_metadata=preserve_metadata,
                        structure_prov=structure_prov,
                    )
                    t_doc["id"] = task.id  # ensure stable id
                    tool_docs[task.id] = t_doc

                # Workflow document with run refs pointing to '#id'
                wf_doc = _generate_workflow_document_enhanced(
                    workflow,
                    {tid: f"#{tid}" for tid in workflow.tasks},
                    "",
                    cwl_version,
                    preserve_metadata=preserve_metadata,
                    verbose=self.verbose,
                    structure_prov=structure_prov,
                )
                wf_doc["id"] = root_id_override or workflow.name or "wf"

                graph_list = [wf_doc] + list(tool_docs.values())
                cwl_doc = {"cwlVersion": cwl_version, "$graph": graph_list}

                # Attach $schemas if we gathered any complex type definitions
                if _GLOBAL_SCHEMA_REGISTRY:
                    cwl_doc["$schemas"] = list(_GLOBAL_SCHEMA_REGISTRY.values())

                _write_cwl_document(cwl_doc, output_path, output_format)

                if self.verbose:
                    print(f"CWL graph exported to {output_path}")
                return

            if single_file:
                # Generate single file with inline tools
                cwl_doc = _generate_single_file_workflow_enhanced(
                    workflow,
                    cwl_version,
                    preserve_metadata=preserve_metadata,
                    verbose=self.verbose,
                    structure_prov=structure_prov,
                )
            else:
                # Generate main workflow with separate tool files
                tools_path = output_path.parent / tools_dir
                tools_path.mkdir(parents=True, exist_ok=True)

                # Generate tool files
                tool_refs = _generate_tool_files_enhanced(
                    workflow,
                    tools_path,
                    output_format,
                    preserve_metadata=preserve_metadata,
                    verbose=self.verbose,
                    structure_prov=structure_prov,
                )

                # Generate main workflow document
                cwl_doc = _generate_workflow_document_enhanced(
                    workflow,
                    tool_refs,
                    tools_dir,
                    cwl_version,
                    preserve_metadata=preserve_metadata,
                    verbose=self.verbose,
                    structure_prov=structure_prov,
                )

            # Write main workflow file
            _write_cwl_document(cwl_doc, output_path, output_format)

            # Export BCO if requested
            if export_bco and workflow.bco_spec:
                bco_path = output_path.with_suffix(".bco.json")
                _export_bco_document(workflow.bco_spec, bco_path, verbose=self.verbose)

            if self.verbose:
                print(f"✓ CWL workflow exported to {output_path}")

        except Exception as e:
            raise RuntimeError(f"Failed to export CWL workflow: {e}")


# Legacy function for backward compatibility
def from_workflow(wf: Workflow, out_file: Union[str, Path], **opts: Any) -> None:
    """Export a wf2wf workflow to CWL v1.2 format with full feature preservation (legacy function)."""
    exporter = CWLExporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False)
    )
    exporter.export_workflow(wf, out_file, **opts)


# Helper functions (unchanged from original implementation)
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
    """Generate enhanced CWL workflow document."""
    wf_doc = {
        "cwlVersion": cwl_version,
        "class": "Workflow",
        "id": wf.name or "workflow",
    }

    # Add enhanced metadata if requested
    if preserve_metadata:
        if wf.label:
            wf_doc["label"] = wf.label
        if wf.doc:
            wf_doc["doc"] = wf.doc
        if wf.provenance:
            _add_provenance_to_doc(wf_doc, wf.provenance, structure=structure_prov)
        if wf.documentation:
            _add_documentation_to_doc(wf_doc, wf.documentation)

    # Add inputs
    if wf.inputs:
        wf_doc["inputs"] = _generate_workflow_inputs_enhanced(wf)

    # Add outputs
    if wf.outputs:
        wf_doc["outputs"] = _generate_workflow_outputs_enhanced(wf)

    # Add steps
    if wf.tasks:
        wf_doc["steps"] = _generate_workflow_steps_enhanced(
            wf, tool_refs, tools_dir, preserve_metadata=preserve_metadata, verbose=verbose
        )

    # Add requirements and hints
    requirements = wf.requirements.get_value_for("shared_filesystem") or []
    hints = wf.hints.get_value_for("shared_filesystem") or []
    
    if requirements:
        wf_doc["requirements"] = [_requirement_spec_to_cwl(req) for req in requirements]
    if hints:
        wf_doc["hints"] = [_requirement_spec_to_cwl(hint) for hint in hints]

    return wf_doc


def _generate_workflow_inputs_enhanced(wf: Workflow) -> Dict[str, Any]:
    """Generate enhanced workflow inputs."""
    inputs = {}
    for param in wf.inputs:
        if isinstance(param, ParameterSpec):
            inputs[param.id] = _parameter_spec_to_cwl(param)
        else:
            inputs[str(param)] = {"type": "string"}
    return inputs


def _generate_workflow_outputs_enhanced(wf: Workflow) -> Dict[str, Any]:
    """Generate enhanced workflow outputs."""
    outputs = {}
    for param in wf.outputs:
        if isinstance(param, ParameterSpec):
            outputs[param.id] = _parameter_spec_to_cwl(param)
        else:
            outputs[str(param)] = {"type": "string"}
    return outputs


def _generate_workflow_steps_enhanced(
    wf: Workflow,
    tool_refs: Dict[str, str],
    tools_dir: str,
    preserve_metadata: bool = True,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Generate enhanced workflow steps."""
    steps = {}
    
    for task in wf.tasks.values():
        step_doc = {
            "run": tool_refs[task.id],
            "in": _generate_step_inputs_enhanced(task, wf),
            "out": [output.id if isinstance(output, ParameterSpec) else str(output) 
                   for output in task.outputs],
        }

        # Add conditional execution if present
        when_value = task.when.get_value_for("shared_filesystem")
        if when_value:
            step_doc["when"] = when_value

        # Add scatter if present
        scatter_value = task.scatter.get_value_for("shared_filesystem")
        if scatter_value:
            step_doc["scatter"] = scatter_value.scatter
            step_doc["scatterMethod"] = scatter_value.scatter_method

        # Add enhanced metadata if requested
        if preserve_metadata:
            if task.label:
                step_doc["label"] = task.label
            if task.doc:
                step_doc["doc"] = task.doc

        steps[task.id] = step_doc

    return steps


def _generate_step_inputs_enhanced(task: Task, wf: Workflow) -> Dict[str, Any]:
    """Generate enhanced step inputs."""
    inputs = {}
    
    for param in task.inputs:
        if isinstance(param, ParameterSpec):
            # Handle parameter binding
            if param.value_from:
                inputs[param.id] = {"valueFrom": param.value_from}
            else:
                inputs[param.id] = param.id  # Simple parameter binding
        else:
            inputs[str(param)] = str(param)
    
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
    """Generate enhanced tool files."""
    tool_refs = {}
    
    for task in wf.tasks.values():
        tool_doc = _generate_tool_document_enhanced(
            task, preserve_metadata=preserve_metadata, structure_prov=structure_prov
        )
        
        tool_file = tools_path / f"{task.id}.{output_format}"
        _write_cwl_document(tool_doc, tool_file, output_format)
        
        tool_refs[task.id] = str(tool_file.relative_to(tools_path.parent))
        
        if verbose:
            print(f"  wrote tool {task.id} → {tool_file}")
    
    return tool_refs


def _generate_tool_document_enhanced(
    task: Task, *, preserve_metadata: bool = True, structure_prov: bool = False
) -> Dict[str, Any]:
    """Generate enhanced tool document."""
    tool_doc = {
        "class": "CommandLineTool",
        "id": task.id,
    }

    # Add enhanced metadata if requested
    if preserve_metadata:
        if task.label:
            tool_doc["label"] = task.label
        if task.doc:
            tool_doc["doc"] = task.doc
        if task.provenance:
            _add_provenance_to_doc(tool_doc, task.provenance, structure=structure_prov)
        if task.documentation:
            _add_documentation_to_doc(tool_doc, task.documentation)

    # Add inputs
    if task.inputs:
        tool_doc["inputs"] = _generate_tool_inputs_enhanced(task)

    # Add outputs
    if task.outputs:
        tool_doc["outputs"] = _generate_tool_outputs_enhanced(task)

    # Add command
    command = task.command.get_value_for("shared_filesystem")
    if command:
        if isinstance(command, str):
            # Parse command into baseCommand and arguments
            base_cmd, args = _parse_command_for_cwl(command)
            tool_doc["baseCommand"] = base_cmd
            if args:
                tool_doc["arguments"] = args
        else:
            tool_doc["baseCommand"] = command

    # Add requirements and hints
    requirements = task.requirements.get_value_for("shared_filesystem") or []
    hints = task.hints.get_value_for("shared_filesystem") or []
    
    if requirements:
        tool_doc["requirements"] = [_requirement_spec_to_cwl(req) for req in requirements]
    if hints:
        tool_doc["hints"] = [_requirement_spec_to_cwl(hint) for hint in hints]

    # Add resource requirements
    resource_req = _generate_resource_requirement_from_task(task)
    if resource_req:
        if "requirements" not in tool_doc:
            tool_doc["requirements"] = []
        tool_doc["requirements"].append(resource_req)

    # Add environment requirements
    env_req = _generate_environment_requirement(task)
    if env_req:
        if "requirements" not in tool_doc:
            tool_doc["requirements"] = []
        tool_doc["requirements"].append(env_req)

    return tool_doc


def _generate_resource_requirement(resources: Any) -> Optional[Dict[str, Any]]:
    """Generate CWL ResourceRequirement from resource specification."""
    if not resources:
        return None
    
    req = {"class": "ResourceRequirement"}
    
    # Map resource fields to CWL ResourceRequirement
    if hasattr(resources, 'cpu') and resources.cpu:
        req["coresMin"] = resources.cpu
    if hasattr(resources, 'mem_mb') and resources.mem_mb:
        req["ramMin"] = resources.mem_mb
    if hasattr(resources, 'disk_mb') and resources.disk_mb:
        req["tmpdirMin"] = resources.disk_mb
    
    return req if len(req) > 1 else None


def _generate_resource_requirement_from_task(task: Task) -> Optional[Dict[str, Any]]:
    """Generate CWL ResourceRequirement from task resources."""
    environment = "shared_filesystem"
    
    req = {"class": "ResourceRequirement"}
    
    # Get resource values
    cpu = task.cpu.get_value_for(environment)
    mem_mb = task.mem_mb.get_value_for(environment)
    disk_mb = task.disk_mb.get_value_for(environment)
    
    if cpu:
        req["coresMin"] = cpu
    if mem_mb:
        req["ramMin"] = mem_mb
    if disk_mb:
        req["tmpdirMin"] = disk_mb
    
    return req if len(req) > 1 else None


def _generate_environment_requirement(env: Any) -> Optional[Dict[str, Any]]:
    """Generate CWL environment requirement from environment specification."""
    if not env:
        return None
    
    # Handle container requirements
    container = env.container.get_value_for("shared_filesystem") if hasattr(env, 'container') else None
    if container:
        return {
            "class": "DockerRequirement",
            "dockerPull": container
        }
    
    # Handle conda requirements
    conda = env.conda.get_value_for("shared_filesystem") if hasattr(env, 'conda') else None
    if conda:
        return {
            "class": "SoftwareRequirement",
            "packages": [{"package": "conda", "version": [conda]}]
        }
    
    return None


def _parse_command_for_cwl(command: str) -> tuple[List[str], List[str]]:
    """Parse command string into baseCommand and arguments for CWL."""
    import shlex
    parts = shlex.split(command)
    if not parts:
        return [], []
    
    base_cmd = parts[0]
    args = parts[1:] if len(parts) > 1 else []
    
    return [base_cmd], args


def _generate_tool_inputs_enhanced(task: Task) -> Dict[str, Any]:
    """Generate enhanced tool inputs."""
    inputs = {}
    
    for param in task.inputs:
        if isinstance(param, ParameterSpec):
            inputs[param.id] = _parameter_spec_to_cwl(param)
        else:
            inputs[str(param)] = {"type": "string"}
    
    return inputs


def _generate_tool_outputs_enhanced(task: Task) -> Dict[str, Any]:
    """Generate enhanced tool outputs."""
    outputs = {}
    
    for param in task.outputs:
        if isinstance(param, ParameterSpec):
            outputs[param.id] = _parameter_spec_to_cwl(param)
        else:
            outputs[str(param)] = {"type": "string"}
    
    return outputs


def _generate_single_file_workflow_enhanced(
    wf: Workflow,
    cwl_version: str,
    preserve_metadata: bool = True,
    verbose: bool = False,
    *,
    structure_prov: bool = False,
) -> Dict[str, Any]:
    """Generate single file workflow with inline tools."""
    # Generate tool documents
    tool_docs = {}
    for task in wf.tasks.values():
        t_doc = _generate_tool_document_enhanced(
            task, preserve_metadata=preserve_metadata, structure_prov=structure_prov
        )
        t_doc["id"] = task.id
        tool_docs[task.id] = t_doc

    # Generate workflow document
    wf_doc = _generate_workflow_document_enhanced(
        wf,
        {tid: f"#{tid}" for tid in wf.tasks},
        "",
        cwl_version,
        preserve_metadata=preserve_metadata,
        verbose=verbose,
        structure_prov=structure_prov,
    )

    # Combine into single document
    cwl_doc = {
        "cwlVersion": cwl_version,
        "$graph": [wf_doc] + list(tool_docs.values())
    }

    # Attach $schemas if we gathered any complex type definitions
    if _GLOBAL_SCHEMA_REGISTRY:
        cwl_doc["$schemas"] = list(_GLOBAL_SCHEMA_REGISTRY.values())

    return cwl_doc


def _write_cwl_document(
    doc: Dict[str, Any], output_path: Path, output_format: str = "yaml"
) -> None:
    """Write CWL document to file."""
    if output_format.lower() == "json":
        with output_path.open('w') as f:
            json.dump(doc, f, indent=2, sort_keys=True)
    else:
        with output_path.open('w') as f:
            yaml.dump(doc, f, default_flow_style=False, sort_keys=False)


def _add_provenance_to_doc(
    cwl_doc: Dict[str, Any], provenance: ProvenanceSpec, *, structure: bool = False
) -> None:
    """Add provenance information to CWL document."""
    if structure:
        # Structured provenance
        cwl_doc["s:provenance"] = {
            "authors": provenance.authors,
            "contributors": provenance.contributors,
            "created": provenance.created,
            "modified": provenance.modified,
            "version": provenance.version,
            "license": provenance.license,
            "doi": provenance.doi,
            "citations": provenance.citations,
            "keywords": provenance.keywords,
            "derived_from": provenance.derived_from,
            "extras": provenance.extras,
        }
    else:
        # Simple metadata
        if provenance.authors:
            cwl_doc["s:author"] = provenance.authors[0].get("name", "Unknown") if provenance.authors else "Unknown"
        if provenance.created:
            cwl_doc["s:dateCreated"] = provenance.created
        if provenance.version:
            cwl_doc["s:version"] = provenance.version


def _add_documentation_to_doc(
    cwl_doc: Dict[str, Any], documentation: DocumentationSpec
) -> None:
    """Add documentation information to CWL document."""
    if documentation.description:
        cwl_doc["s:description"] = documentation.description
    if documentation.label:
        cwl_doc["s:label"] = documentation.label
    if documentation.doc:
        cwl_doc["s:documentation"] = documentation.doc


def _requirement_spec_to_cwl(req_spec: RequirementSpec) -> Dict[str, Any]:
    """Convert RequirementSpec to CWL requirement format."""
    return {"class": req_spec.class_name, **req_spec.data}


def _parameter_spec_to_cwl(param_spec: ParameterSpec) -> Dict[str, Any]:
    """Convert ParameterSpec to CWL parameter format."""
    def _type_to_cwl(ts):
        """Convert TypeSpec to CWL type format."""
        if isinstance(ts, str):
            return ts
        
        if ts.type == "array":
            return {"type": "array", "items": _type_to_cwl(ts.items)}
        elif ts.type == "record":
            return {"type": "record", "fields": {k: _type_to_cwl(v) for k, v in ts.fields.items()}}
        elif ts.type == "enum":
            return {"type": "enum", "symbols": ts.symbols}
        elif ts.type == "union":
            return {"type": "union", "members": [_type_to_cwl(m) for m in ts.members]}
        else:
            return ts.type
    
    param_doc = {"type": _type_to_cwl(param_spec.type)}
    
    if param_spec.label:
        param_doc["label"] = param_spec.label
    if param_spec.doc:
        param_doc["doc"] = param_spec.doc
    if param_spec.default is not None:
        param_doc["default"] = param_spec.default
    if param_spec.format:
        param_doc["format"] = param_spec.format
    if param_spec.secondary_files:
        param_doc["secondaryFiles"] = param_spec.secondary_files
    if param_spec.streamable:
        param_doc["streamable"] = param_spec.streamable
    if param_spec.load_contents:
        param_doc["loadContents"] = param_spec.load_contents
    if param_spec.load_listing:
        param_doc["loadListing"] = param_spec.load_listing
    if param_spec.input_binding:
        param_doc["inputBinding"] = param_spec.input_binding
    if param_spec.output_binding:
        param_doc["outputBinding"] = param_spec.output_binding
    if param_spec.value_from:
        param_doc["valueFrom"] = param_spec.value_from
    
    return param_doc


def _export_bco_document(
    bco_spec: BCOSpec, bco_path: Path, verbose: bool = False
) -> None:
    """Export BCO document alongside CWL."""
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
    
    with bco_path.open('w') as f:
        json.dump(bco_doc, f, indent=2, sort_keys=True)
    
    if verbose:
        print(f"  BCO document exported to {bco_path}")
