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
import logging
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

logger = logging.getLogger(__name__)

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
            logger.info(f"Generating CWL workflow: {output_path}")
            logger.info(f"  CWL version: {cwl_version}")
            logger.info(f"  Format: {output_format}")
            logger.info(f"  Single file: {single_file}")
            logger.info(f"  Use graph: {use_graph}")
            logger.info(f"  Export BCO: {export_bco}")
            logger.info(f"  Tasks: {len(workflow.tasks)}")
            logger.info(f"  Dependencies: {len(workflow.edges)}")

        try:
            if use_graph:
                if self.verbose:
                    logger.info("Exporting CWL using $graph representation")

                tool_docs = {}
                for task in workflow.tasks.values():
                    t_doc = self._generate_tool_document_enhanced(
                        task,
                        preserve_metadata=preserve_metadata,
                        structure_prov=structure_prov,
                    )
                    t_doc["id"] = task.id  # ensure stable id
                    tool_docs[task.id] = t_doc

                # Workflow document with run refs pointing to '#id'
                wf_doc = self._generate_workflow_document_enhanced(
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

                self._write_cwl_document(cwl_doc, output_path, output_format)

                if self.verbose:
                    logger.info(f"CWL graph exported to {output_path}")
                return

            if single_file:
                # Generate single file with inline tools
                cwl_doc = self._generate_single_file_workflow_enhanced(
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
                tool_refs = self._generate_tool_files_enhanced(
                    workflow,
                    tools_path,
                    output_format,
                    preserve_metadata=preserve_metadata,
                    verbose=self.verbose,
                    structure_prov=structure_prov,
                )

                # Generate main workflow document
                cwl_doc = self._generate_workflow_document_enhanced(
                    workflow,
                    tool_refs,
                    tools_dir,
                    cwl_version,
                    preserve_metadata=preserve_metadata,
                    verbose=self.verbose,
                    structure_prov=structure_prov,
                )

            # Write main workflow file using shared infrastructure
            self._write_cwl_document(cwl_doc, output_path, output_format)

            # Export BCO if requested
            if export_bco and workflow.bco_spec:
                bco_path = output_path.with_suffix(".bco.json")
                self._export_bco_document(workflow.bco_spec, bco_path)

            if self.verbose:
                logger.info(f"✓ CWL workflow exported to {output_path}")

        except Exception as e:
            raise RuntimeError(f"Failed to export CWL workflow: {e}")

    def _generate_workflow_document_enhanced(
        self,
        wf: Workflow,
        tool_refs: Dict[str, str],
        tools_dir: str,
        cwl_version: str,
        preserve_metadata: bool = True,
        verbose: bool = False,
        *,
        structure_prov: bool = False,
    ) -> Dict[str, Any]:
        """Generate enhanced CWL workflow document using shared infrastructure."""
        wf_doc = {
            "cwlVersion": cwl_version,
            "class": "Workflow",
            "id": wf.name or "workflow",
        }

        # Add enhanced metadata if requested using shared infrastructure
        if preserve_metadata:
            metadata = self._get_workflow_metadata(wf)
            if metadata:
                wf_doc.update(metadata)
            
            # Add provenance and documentation if present
            if wf.provenance:
                self._add_provenance_to_doc(wf_doc, wf.provenance, structure=structure_prov)
            if wf.documentation:
                self._add_documentation_to_doc(wf_doc, wf.documentation)

        # Add inputs
        if wf.inputs:
            wf_doc["inputs"] = self._generate_workflow_inputs_enhanced(wf)

        # Add outputs
        if wf.outputs:
            wf_doc["outputs"] = self._generate_workflow_outputs_enhanced(wf)

        # Add steps
        if wf.tasks:
            wf_doc["steps"] = self._generate_workflow_steps_enhanced(
                wf, tool_refs, tools_dir, preserve_metadata=preserve_metadata, verbose=verbose
            )

        # Add requirements and hints using shared infrastructure
        requirements = self._get_workflow_requirements_for_target(wf)
        hints = self._get_workflow_hints_for_target(wf)
        
        if requirements:
            wf_doc["requirements"] = [self._requirement_spec_to_cwl(req) for req in requirements]
        if hints:
            wf_doc["hints"] = [self._requirement_spec_to_cwl(hint) for hint in hints]

        return wf_doc

    def _generate_workflow_inputs_enhanced(self, wf: Workflow) -> Dict[str, Any]:
        """Generate enhanced workflow inputs."""
        inputs = {}
        for param in wf.inputs:
            if isinstance(param, ParameterSpec):
                inputs[param.id] = self._parameter_spec_to_cwl(param)
            else:
                inputs[str(param)] = {"type": "string"}
        return inputs

    def _generate_workflow_outputs_enhanced(self, wf: Workflow) -> Dict[str, Any]:
        """Generate enhanced workflow outputs."""
        outputs = {}
        for param in wf.outputs:
            if isinstance(param, ParameterSpec):
                outputs[param.id] = self._parameter_spec_to_cwl(param)
            else:
                outputs[str(param)] = {"type": "string"}
        return outputs

    def _generate_workflow_steps_enhanced(
        self,
        wf: Workflow,
        tool_refs: Dict[str, str],
        tools_dir: str,
        preserve_metadata: bool = True,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """Generate enhanced workflow steps using shared infrastructure."""
        steps = {}
        
        for task in wf.tasks.values():
            step_doc = {
                "run": tool_refs[task.id],
                "in": self._generate_step_inputs_enhanced(task, wf),
                "out": [output.id if isinstance(output, ParameterSpec) else str(output) 
                       for output in task.outputs],
            }

            # Add conditional execution if present using shared infrastructure
            when_value = self._get_environment_specific_value_for_target(task.when)
            if when_value:
                step_doc["when"] = when_value

            # Add scatter if present using shared infrastructure
            scatter_value = self._get_environment_specific_value_for_target(task.scatter)
            if scatter_value:
                step_doc["scatter"] = scatter_value.scatter
                step_doc["scatterMethod"] = scatter_value.scatter_method

            # Add enhanced metadata if requested using shared infrastructure
            if preserve_metadata:
                metadata = self._get_task_metadata(task)
                if metadata:
                    step_doc.update(metadata)

            steps[task.id] = step_doc

        return steps

    def _generate_step_inputs_enhanced(self, task: Task, wf: Workflow) -> Dict[str, Any]:
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
        self,
        wf: Workflow,
        tools_path: Path,
        output_format: str,
        preserve_metadata: bool = True,
        verbose: bool = False,
        *,
        structure_prov: bool = False,
    ) -> Dict[str, str]:
        """Generate enhanced tool files using shared infrastructure."""
        tool_refs = {}
        
        for task in wf.tasks.values():
            tool_doc = self._generate_tool_document_enhanced(
                task, preserve_metadata=preserve_metadata, structure_prov=structure_prov
            )
            
            tool_file = tools_path / f"{task.id}.{output_format}"
            self._write_cwl_document(tool_doc, tool_file, output_format)
            
            tool_refs[task.id] = str(tool_file.relative_to(tools_path.parent))
            
            if verbose:
                logger.info(f"  wrote tool {task.id} → {tool_file}")
        
        return tool_refs

    def _generate_tool_document_enhanced(
        self, task: Task, *, preserve_metadata: bool = True, structure_prov: bool = False
    ) -> Dict[str, Any]:
        """Generate enhanced tool document using shared infrastructure."""
        tool_doc = {
            "class": "CommandLineTool",
            "id": task.id,
        }

        # Add enhanced metadata if requested using shared infrastructure
        if preserve_metadata:
            metadata = self._get_task_metadata(task)
            if metadata:
                tool_doc.update(metadata)
            
            # Add provenance and documentation if present
            if task.provenance:
                self._add_provenance_to_doc(tool_doc, task.provenance, structure=structure_prov)
            if task.documentation:
                self._add_documentation_to_doc(tool_doc, task.documentation)

        # Add inputs
        if task.inputs:
            tool_doc["inputs"] = self._generate_tool_inputs_enhanced(task)

        # Add outputs
        if task.outputs:
            tool_doc["outputs"] = self._generate_tool_outputs_enhanced(task)

        # Add command using shared infrastructure
        command = self._get_environment_specific_value_for_target(task.command)
        if command:
            if isinstance(command, str):
                # Parse command into baseCommand and arguments
                base_cmd, args = self._parse_command_for_cwl(command)
                tool_doc["baseCommand"] = base_cmd
                if args:
                    tool_doc["arguments"] = args
            else:
                tool_doc["baseCommand"] = command

        # Add requirements and hints using shared infrastructure
        requirements = self._get_workflow_requirements_for_target(task)
        hints = self._get_workflow_hints_for_target(task)
        
        if requirements:
            tool_doc["requirements"] = [self._requirement_spec_to_cwl(req) for req in requirements]
        if hints:
            tool_doc["hints"] = [self._requirement_spec_to_cwl(hint) for hint in hints]

        # Add resource requirements using shared infrastructure
        resource_req = self._generate_resource_requirement_from_task(task)
        if resource_req:
            if "requirements" not in tool_doc:
                tool_doc["requirements"] = []
            tool_doc["requirements"].append(resource_req)

        # Add environment requirements using shared infrastructure
        env_req = self._generate_environment_requirement(task)
        if env_req:
            if "requirements" not in tool_doc:
                tool_doc["requirements"] = []
            tool_doc["requirements"].append(env_req)

        # Record losses for unsupported features
        self._record_loss_if_present_for_target(task, "gpu", "GPU resources not supported in CWL")
        self._record_loss_if_present_for_target(task, "gpu_mem_mb", "GPU memory not supported in CWL")
        self._record_loss_if_present_for_target(task, "time_s", "Time limits not supported in CWL")
        self._record_loss_if_present_for_target(task, "threads", "Thread specification not supported in CWL")

        return tool_doc

    def _generate_resource_requirement_from_task(self, task: Task) -> Optional[Dict[str, Any]]:
        """Generate CWL ResourceRequirement from task resources using shared infrastructure."""
        
        # Use shared infrastructure to get resources for target environment
        resources = self._get_task_resources_for_target(task)
        
        if not resources:
            return None
        
        req = {"class": "ResourceRequirement"}
        
        # Map resource fields to CWL ResourceRequirement
        if 'cpu' in resources:
            req["coresMin"] = resources['cpu']
        if 'mem_mb' in resources:
            req["ramMin"] = resources['mem_mb']
        if 'disk_mb' in resources:
            req["tmpdirMin"] = resources['disk_mb']
        
        return req if len(req) > 1 else None

    def _generate_environment_requirement(self, task: Task) -> Optional[Dict[str, Any]]:
        """Generate CWL environment requirement using shared infrastructure."""
        
        # Use shared infrastructure to get environment for target environment
        env_spec = self._get_task_environment_for_target(task)
        
        # Handle container requirements
        if 'container' in env_spec:
            return {
                "class": "DockerRequirement",
                "dockerPull": env_spec['container']
            }
        
        # Handle conda requirements
        if 'conda' in env_spec:
            return {
                "class": "SoftwareRequirement",
                "packages": [{"package": "conda", "version": [env_spec['conda']]}]
            }
        
        return None

    def _parse_command_for_cwl(self, command: str) -> tuple[List[str], List[str]]:
        """Parse command string into baseCommand and arguments for CWL."""
        import shlex
        parts = shlex.split(command)
        if not parts:
            return [], []
        
        base_cmd = parts[0]
        args = parts[1:] if len(parts) > 1 else []
        
        return [base_cmd], args

    def _generate_tool_inputs_enhanced(self, task: Task) -> Dict[str, Any]:
        """Generate enhanced tool inputs."""
        inputs = {}
        
        for param in task.inputs:
            if isinstance(param, ParameterSpec):
                inputs[param.id] = self._parameter_spec_to_cwl(param)
            else:
                inputs[str(param)] = {"type": "string"}
        
        return inputs

    def _generate_tool_outputs_enhanced(self, task: Task) -> Dict[str, Any]:
        """Generate enhanced tool outputs."""
        outputs = {}
        
        for param in task.outputs:
            if isinstance(param, ParameterSpec):
                outputs[param.id] = self._parameter_spec_to_cwl(param)
            else:
                outputs[str(param)] = {"type": "string"}
        
        return outputs

    def _generate_single_file_workflow_enhanced(
        self,
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
            t_doc = self._generate_tool_document_enhanced(
                task, preserve_metadata=preserve_metadata, structure_prov=structure_prov
            )
            t_doc["id"] = task.id
            tool_docs[task.id] = t_doc

        # Generate workflow document
        wf_doc = self._generate_workflow_document_enhanced(
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
        self, doc: Dict[str, Any], output_path: Path, output_format: str = "yaml"
    ) -> None:
        """Write CWL document to file using shared infrastructure."""
        if output_format.lower() == "json":
            self._write_json(doc, output_path)
        else:
            self._write_yaml(doc, output_path)

    def _add_provenance_to_doc(
        self, cwl_doc: Dict[str, Any], provenance: ProvenanceSpec, *, structure: bool = False
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
        self, cwl_doc: Dict[str, Any], documentation: DocumentationSpec
    ) -> None:
        """Add documentation information to CWL document."""
        if documentation.description:
            cwl_doc["s:description"] = documentation.description
        if documentation.label:
            cwl_doc["s:label"] = documentation.label
        if documentation.doc:
            cwl_doc["s:documentation"] = documentation.doc

    def _requirement_spec_to_cwl(self, req_spec: RequirementSpec) -> Dict[str, Any]:
        """Convert RequirementSpec to CWL requirement format."""
        return {"class": req_spec.class_name, **req_spec.data}

    def _parameter_spec_to_cwl(self, param_spec: ParameterSpec) -> Dict[str, Any]:
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

    def _export_bco_document(self, bco_spec: BCOSpec, bco_path: Path) -> None:
        """Export BCO document alongside CWL using shared infrastructure."""
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
        
        # Use shared infrastructure for JSON writing
        self._write_json(bco_doc, bco_path)
        
        if self.verbose:
            logger.info(f"  BCO document exported to {bco_path}")


# Legacy function for backward compatibility
def from_workflow(wf: Workflow, out_file: Union[str, Path], **opts: Any) -> None:
    """Export a wf2wf workflow to CWL v1.2 format with full feature preservation (legacy function)."""
    exporter = CWLExporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False)
    )
    exporter.export_workflow(wf, out_file, **opts)


# Legacy helper functions for backward compatibility (deprecated)
def _generate_workflow_document_enhanced(*args, **kwargs):
    """Legacy function - use CWLExporter._generate_workflow_document_enhanced instead."""
    raise DeprecationWarning("Use CWLExporter._generate_workflow_document_enhanced instead")

def _generate_workflow_inputs_enhanced(*args, **kwargs):
    """Legacy function - use CWLExporter._generate_workflow_inputs_enhanced instead."""
    raise DeprecationWarning("Use CWLExporter._generate_workflow_inputs_enhanced instead")

def _generate_workflow_outputs_enhanced(*args, **kwargs):
    """Legacy function - use CWLExporter._generate_workflow_outputs_enhanced instead."""
    raise DeprecationWarning("Use CWLExporter._generate_workflow_outputs_enhanced instead")

def _generate_workflow_steps_enhanced(*args, **kwargs):
    """Legacy function - use CWLExporter._generate_workflow_steps_enhanced instead."""
    raise DeprecationWarning("Use CWLExporter._generate_workflow_steps_enhanced instead")

def _generate_step_inputs_enhanced(*args, **kwargs):
    """Legacy function - use CWLExporter._generate_step_inputs_enhanced instead."""
    raise DeprecationWarning("Use CWLExporter._generate_step_inputs_enhanced instead")

def _generate_tool_files_enhanced(*args, **kwargs):
    """Legacy function - use CWLExporter._generate_tool_files_enhanced instead."""
    raise DeprecationWarning("Use CWLExporter._generate_tool_files_enhanced instead")

def _generate_tool_document_enhanced(*args, **kwargs):
    """Legacy function - use CWLExporter._generate_tool_document_enhanced instead."""
    raise DeprecationWarning("Use CWLExporter._generate_tool_document_enhanced instead")

def _generate_resource_requirement(*args, **kwargs):
    """Legacy function - use CWLExporter._generate_resource_requirement_from_task instead."""
    raise DeprecationWarning("Use CWLExporter._generate_resource_requirement_from_task instead")

def _generate_resource_requirement_from_task(*args, **kwargs):
    """Legacy function - use CWLExporter._generate_resource_requirement_from_task instead."""
    raise DeprecationWarning("Use CWLExporter._generate_resource_requirement_from_task instead")

def _generate_environment_requirement(*args, **kwargs):
    """Legacy function - use CWLExporter._generate_environment_requirement instead."""
    raise DeprecationWarning("Use CWLExporter._generate_environment_requirement instead")

def _parse_command_for_cwl(*args, **kwargs):
    """Legacy function - use CWLExporter._parse_command_for_cwl instead."""
    raise DeprecationWarning("Use CWLExporter._parse_command_for_cwl instead")

def _generate_tool_inputs_enhanced(*args, **kwargs):
    """Legacy function - use CWLExporter._generate_tool_inputs_enhanced instead."""
    raise DeprecationWarning("Use CWLExporter._generate_tool_inputs_enhanced instead")

def _generate_tool_outputs_enhanced(*args, **kwargs):
    """Legacy function - use CWLExporter._generate_tool_outputs_enhanced instead."""
    raise DeprecationWarning("Use CWLExporter._generate_tool_outputs_enhanced instead")

def _generate_single_file_workflow_enhanced(*args, **kwargs):
    """Legacy function - use CWLExporter._generate_single_file_workflow_enhanced instead."""
    raise DeprecationWarning("Use CWLExporter._generate_single_file_workflow_enhanced instead.")

def _write_cwl_document(*args, **kwargs):
    """Legacy function - use CWLExporter._write_cwl_document instead."""
    raise DeprecationWarning("Use CWLExporter._write_cwl_document instead")

def _add_provenance_to_doc(*args, **kwargs):
    """Legacy function - use CWLExporter._add_provenance_to_doc instead."""
    raise DeprecationWarning("Use CWLExporter._add_provenance_to_doc instead")

def _add_documentation_to_doc(*args, **kwargs):
    """Legacy function - use CWLExporter._add_documentation_to_doc instead."""
    raise DeprecationWarning("Use CWLExporter._add_documentation_to_doc instead")

def _requirement_spec_to_cwl(*args, **kwargs):
    """Legacy function - use CWLExporter._requirement_spec_to_cwl instead."""
    raise DeprecationWarning("Use CWLExporter._requirement_spec_to_cwl instead")

def _parameter_spec_to_cwl(*args, **kwargs):
    """Legacy function - use CWLExporter._parameter_spec_to_cwl instead."""
    raise DeprecationWarning("Use CWLExporter._parameter_spec_to_cwl instead")

def _export_bco_document(*args, **kwargs):
    """Legacy function - use CWLExporter._export_bco_document instead."""
    raise DeprecationWarning("Use CWLExporter._export_bco_document instead.")
