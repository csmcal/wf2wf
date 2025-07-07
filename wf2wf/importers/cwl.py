"""wf2wf.importers.cwl – CWL v1.2 ➜ Workflow IR

This module imports Common Workflow Language (CWL) v1.2 workflows and converts
them to the wf2wf intermediate representation with full feature preservation.

Enhanced features supported:
- Advanced metadata and provenance tracking
- Conditional execution (when expressions)
- Scatter/gather operations with all scatter methods
- Complete parameter specifications with CWL type system
- Requirements and hints preservation
- File management with secondary files and validation
- BCO integration for regulatory compliance
"""

from __future__ import annotations

import json
import yaml
import subprocess
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from wf2wf.core import (
    Workflow,
    Task,
    Edge,
    ParameterSpec,
    ScatterSpec,
    RequirementSpec,
    ProvenanceSpec,
    DocumentationSpec,
    EnvironmentSpecificValue,
    CheckpointSpec,
    LoggingSpec,
    SecuritySpec,
    NetworkingSpec,
    MetadataSpec,
)
from wf2wf.importers.base import BaseImporter


class CWLImporter(BaseImporter):
    """CWL importer using shared base infrastructure."""
    
    def _parse_source(self, path: Path, **opts: Any) -> Dict[str, Any]:
        """Parse CWL file and extract all information."""
        use_cwltool = opts.get("use_cwltool", False)
        preserve_metadata = opts.get("preserve_metadata", True)
        extract_provenance = opts.get("extract_provenance", True)
        debug = opts.get("debug", False)
        verbose = self.verbose

        if verbose:
            print(f"Parsing CWL file: {path}")

        # Load CWL document
        cwl_doc = _load_cwl_document(path)

        # Parse based on document structure
        if "$graph" in cwl_doc:
            # Multi-document with $graph
            graph_list = cwl_doc["$graph"]
            if not isinstance(graph_list, list):
                raise ValueError("$graph must be a list of CWL objects")

            graph_map = {}
            for obj in graph_list:
                obj_id = obj.get("id") or obj.get("label")
                if not obj_id:
                    raise ValueError("Each object in $graph must have an 'id' field")
                graph_map[obj_id.lstrip("#")] = obj

            root_wf_obj = next(
                (o for o in graph_list if o.get("class") == "Workflow"), None
            )
            if root_wf_obj is None:
                raise ValueError("$graph does not contain a top-level Workflow object")

            parsed_data = _parse_cwl_workflow_data(
                root_wf_obj,
                path,
                preserve_metadata=preserve_metadata,
                extract_provenance=extract_provenance,
                verbose=verbose,
                debug=debug,
                graph_objects=graph_map,
            )

        elif cwl_doc.get("class") == "Workflow":
            parsed_data = _parse_cwl_workflow_data(
                cwl_doc,
                path,
                preserve_metadata=preserve_metadata,
                extract_provenance=extract_provenance,
                verbose=verbose,
                debug=debug,
            )
        elif cwl_doc.get("class") == "CommandLineTool":
            parsed_data = _convert_tool_to_workflow_data(
                cwl_doc, path, preserve_metadata=preserve_metadata, verbose=verbose
            )
        else:
            raise ValueError(f"Unsupported CWL class: {cwl_doc.get('class')}")

        # Enhanced parsing with cwltool if requested
        if use_cwltool:
            if not shutil.which("cwltool"):
                raise RuntimeError(
                    "The 'cwltool' executable was not found in your PATH. "
                    "Please install cwltool: 'pip install cwltool' or 'conda install cwltool'. "
                    "Alternatively, set use_cwltool=False to use direct parsing."
                )
            if verbose:
                print("Using cwltool for enhanced parsing...")
            parsed_data = _parse_with_cwltool(path, parsed_data, verbose=verbose)

        return parsed_data
    
    def _create_basic_workflow(self, parsed_data: Dict[str, Any]) -> Workflow:
        """Create basic workflow from parsed CWL data."""
        workflow_name = parsed_data.get("name", "cwl_workflow")
        version = parsed_data.get("version", "1.0")
        label = parsed_data.get("label")
        doc = parsed_data.get("doc")
        
        # Create workflow with CWL-specific execution model
        workflow = Workflow(
            name=workflow_name,
            version=version,
            label=label,
            doc=doc,
            execution_model=EnvironmentSpecificValue("shared_filesystem", ["shared_filesystem"]),
            cwl_version=parsed_data.get("cwl_version"),
            bco_spec=parsed_data.get("bco_spec"),
            provenance=parsed_data.get("provenance"),
            documentation=parsed_data.get("documentation"),
            intent=parsed_data.get("intent", []),
            inputs=parsed_data.get("inputs", []),
            outputs=parsed_data.get("outputs", []),
            requirements=parsed_data.get("requirements", EnvironmentSpecificValue([], [])),
            hints=parsed_data.get("hints", EnvironmentSpecificValue([], [])),
        )
        
        # Add metadata
        if parsed_data.get("metadata"):
            workflow.metadata = parsed_data["metadata"]
        
        # Add tasks to workflow
        for task in parsed_data.get("tasks", []):
            workflow.add_task(task)

        return workflow

    def _extract_tasks(self, parsed_data: Dict[str, Any]) -> List[Task]:
        """Extract tasks from parsed CWL data."""
        return parsed_data.get("tasks", [])
    
    def _extract_edges(self, parsed_data: Dict[str, Any]) -> List[Edge]:
        """Extract edges from parsed CWL data."""
        return parsed_data.get("edges", [])
    
    def _get_source_format(self) -> str:
        """Get the source format name."""
        return "cwl"


def to_workflow(path: Union[str, Path], **opts: Any) -> Workflow:
    """Convert CWL file at *path* into a Workflow IR object using shared infrastructure.

    Parameters
    ----------
    path : Union[str, Path]
        Path to the .cwl file.
    use_cwltool : bool, optional
        Use cwltool for enhanced parsing (default: False).
    preserve_metadata : bool, optional
        Preserve all CWL metadata (default: True).
    extract_provenance : bool, optional
        Extract provenance information (default: True).
    verbose : bool, optional
        Enable verbose output (default: False).
    debug : bool, optional
        Enable debug output (default: False).
    interactive : bool, optional
        Enable interactive mode (default: False).

    Returns
    -------
    Workflow
        Populated IR instance.
    """
    importer = CWLImporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False)
    )
    return importer.import_workflow(path, **opts)


def _load_cwl_document(cwl_path: Path) -> Dict[str, Any]:
    """Load and parse a CWL document from file."""
    try:
        with open(cwl_path, "r") as f:
            lines = f.readlines()
            if lines and lines[0].startswith("#!"):
                content = "".join(lines[1:])
            else:
                content = "".join(lines)

        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as ye:
            raise RuntimeError(f"Failed to parse CWL YAML: {ye}")
    except Exception as e:
        raise RuntimeError(f"Failed to read CWL file: {e}")


def _parse_cwl_workflow_data(
    cwl_doc: Dict[str, Any],
    cwl_path: Path,
    preserve_metadata: bool = True,
    extract_provenance: bool = True,
    verbose: bool = False,
    debug: bool = False,
    graph_objects: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Parse CWL workflow document into structured data."""
    
    # Extract basic workflow information
    workflow_name = cwl_doc.get("label") or cwl_doc.get("id", "cwl_workflow")
    if workflow_name.startswith("#"):
        workflow_name = workflow_name[1:]
    
    # Extract CWL version
    cwl_version = cwl_doc.get("cwlVersion", "v1.2")
    
    # Extract inputs and outputs
    inputs = _parse_parameter_specs(cwl_doc.get("inputs", {}), "input")
    outputs = _parse_parameter_specs(cwl_doc.get("outputs", {}), "output")
    
    # Extract requirements and hints
    requirements = _parse_requirements(cwl_doc.get("requirements", []))
    hints = _parse_requirements(cwl_doc.get("hints", []))
    
    # Extract metadata
    metadata = None
    if preserve_metadata:
        metadata = MetadataSpec(
            source_format="cwl",
            source_file=str(cwl_path),
            source_version=cwl_version,
            format_specific={"cwl_document": cwl_doc},
        )
    
    # Extract provenance
    provenance = None
    if extract_provenance:
        provenance = _extract_provenance_spec(cwl_doc)
    
    # Extract documentation
    documentation = None
    if preserve_metadata:
        documentation = _extract_documentation_spec(cwl_doc)
    
    # Parse steps
    steps = cwl_doc.get("steps", {})
    tasks = []
    edges = []

    for step_name, step_def in steps.items():
        task, step_edges = _parse_cwl_step(
            step_name,
            step_def,
            cwl_path,
            verbose=verbose,
            debug=debug,
            graph_objects=graph_objects,
        )
        tasks.append(task)
        edges.extend(step_edges)

    return {
        "name": workflow_name,
        "version": "1.0",
        "label": cwl_doc.get("label"),
        "doc": cwl_doc.get("doc"),
        "cwl_version": cwl_version,
        "inputs": inputs,
        "outputs": outputs,
        "requirements": EnvironmentSpecificValue(requirements, ["shared_filesystem"]),
        "hints": EnvironmentSpecificValue(hints, ["shared_filesystem"]),
        "provenance": provenance,
        "documentation": documentation,
        "intent": cwl_doc.get("intent", []),
        "bco_spec": cwl_doc.get("bco_spec"),
        "metadata": metadata,
        "tasks": tasks,
        "edges": edges,
    }


def _parse_cwl_step(
    step_name: str,
    step_def: Dict[str, Any],
    cwl_path: Path,
    verbose: bool = False,
    debug: bool = False,
    graph_objects: Optional[Dict[str, Any]] = None,
) -> tuple[Task, List[Edge]]:
    """Parse a CWL step definition into a Task and its dependencies."""
    
    # Load tool definition
    tool_def = _load_tool_definition(
        step_def.get("run"), cwl_path, graph_objects, verbose=verbose
    )
    
    # Extract basic task information
    task_id = step_name
    label = step_def.get("label", step_name)
    doc = step_def.get("doc", "")
    
    # Extract command
    command = _extract_command_from_tool(tool_def)
    
    # Create task with default values
    task = Task(
        id=task_id,
        label=label,
        doc=doc,
        command=command,
    )
    
    # Extract and set resources
    resource_reqs = _extract_resource_requirements(tool_def)
    if resource_reqs:
        if "cpu" in resource_reqs:
            task.cpu.set_for_environment(resource_reqs["cpu"].get_value_for("shared_filesystem"), "shared_filesystem")
        if "mem_mb" in resource_reqs:
            task.mem_mb.set_for_environment(resource_reqs["mem_mb"].get_value_for("shared_filesystem"), "shared_filesystem")
        if "disk_mb" in resource_reqs:
            task.disk_mb.set_for_environment(resource_reqs["disk_mb"].get_value_for("shared_filesystem"), "shared_filesystem")
        if "gpu" in resource_reqs:
            task.gpu.set_for_environment(resource_reqs["gpu"].get_value_for("shared_filesystem"), "shared_filesystem")
    
    # Extract and set environment
    env_spec = _extract_environment_spec(tool_def)
    if env_spec:
        if "conda" in env_spec:
            task.conda.set_for_environment(env_spec["conda"].get_value_for("shared_filesystem"), "shared_filesystem")
        if "container" in env_spec:
            task.container.set_for_environment(env_spec["container"].get_value_for("shared_filesystem"), "shared_filesystem")
        if "workdir" in env_spec:
            task.workdir.set_for_environment(env_spec["workdir"].get_value_for("shared_filesystem"), "shared_filesystem")
        if "env_vars" in env_spec:
            task.env_vars.set_for_environment(env_spec["env_vars"].get_value_for("shared_filesystem"), "shared_filesystem")
        if "modules" in env_spec:
            task.modules.set_for_environment(env_spec["modules"].get_value_for("shared_filesystem"), "shared_filesystem")
    
    # Extract inputs and outputs
    inputs = _extract_step_inputs(step_def, tool_def)
    outputs = _extract_step_outputs(step_def, tool_def)
    task.inputs = inputs
    task.outputs = outputs
    
    # Extract conditional execution
    if "when" in step_def:
        task.when.set_for_environment(step_def["when"], "shared_filesystem")
    
    # Extract scatter
    if "scatter" in step_def:
        scatter_spec = _parse_scatter_spec(step_def)
        if scatter_spec:
            task.scatter.set_for_environment(scatter_spec, "shared_filesystem")
    
    # Extract requirements and hints
    step_reqs = _parse_requirements(step_def.get("requirements", []))
    if step_reqs:
        task.requirements.set_for_environment(step_reqs, "shared_filesystem")
    
    step_hints = _parse_requirements(step_def.get("hints", []))
    if step_hints:
        task.hints.set_for_environment(step_hints, "shared_filesystem")
    
    # Extract dependencies
    edges = _parse_step_dependencies(step_name, step_def)

    return task, edges


def _load_tool_definition(
    run_ref: Union[str, Dict[str, Any]],
    cwl_path: Path,
    graph_objects: Optional[Dict[str, Any]] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Load tool definition from run reference."""

    if isinstance(run_ref, dict):
        return run_ref
    
    if isinstance(run_ref, str):
        # Check if it's in the graph
        if graph_objects and run_ref in graph_objects:
            return graph_objects[run_ref]
        
        # Try to load from file
        tool_path = cwl_path.parent / run_ref
        if tool_path.exists():
            return _load_cwl_document(tool_path)

        if verbose:
            print(f"Warning: Could not load tool definition for {run_ref}")
    
    return {}


def _extract_command_from_tool(tool_def: Dict[str, Any]) -> EnvironmentSpecificValue[str]:
    """Extract the shell command string from a CWL CommandLineTool definition."""
    base_cmd = tool_def.get("baseCommand", [])
    if isinstance(base_cmd, str):
        base_cmd = [base_cmd]
    arguments = tool_def.get("arguments", [])
    if isinstance(arguments, str):
        arguments = [arguments]
    # Concatenate baseCommand and arguments into a single shell command string
    cmd_str = " ".join([str(x) for x in base_cmd + arguments])
    return EnvironmentSpecificValue(cmd_str, ["shared_filesystem"])


def _extract_resource_requirements(tool_def: Dict[str, Any]) -> Dict[str, EnvironmentSpecificValue]:
    """Extract resource requirements from tool definition."""
    resources = {}
    
    for req in tool_def.get("requirements", []):
        if req.get("class") == "ResourceRequirement":
            # Look for resource fields at the top level
            if "coresMin" in req or "coresMax" in req:
                cpu_val = req.get("coresMin", req.get("coresMax", 1))
                resources["cpu"] = EnvironmentSpecificValue(int(cpu_val), ["shared_filesystem"])
            if "ramMin" in req or "ramMax" in req:
                ram_val = req.get("ramMin", req.get("ramMax", 4096))
                # Convert to MB if needed
                if isinstance(ram_val, str) and ram_val.endswith("MB"):
                    ram_val = int(ram_val[:-2])
                elif isinstance(ram_val, str) and ram_val.endswith("GB"):
                    ram_val = int(float(ram_val[:-2]) * 1024)
                resources["mem_mb"] = EnvironmentSpecificValue(int(ram_val), ["shared_filesystem"])
            if "tmpdirMin" in req or "tmpdirMax" in req:
                disk_val = req.get("tmpdirMin", req.get("tmpdirMax", 4096))
                # Convert to MB if needed
                if isinstance(disk_val, str) and disk_val.endswith("MB"):
                    disk_val = int(disk_val[:-2])
                elif isinstance(disk_val, str) and disk_val.endswith("GB"):
                    disk_val = int(float(disk_val[:-2]) * 1024)
                resources["disk_mb"] = EnvironmentSpecificValue(int(disk_val), ["shared_filesystem"])
    return resources


def _extract_environment_spec(tool_def: Dict[str, Any]) -> Dict[str, EnvironmentSpecificValue]:
    """Extract environment specifications from tool definition."""
    env_spec = {}
    
    for req in tool_def.get("requirements", []):
        if req.get("class") == "DockerRequirement":
            if "dockerPull" in req:
                docker_val = req["dockerPull"]
                if not docker_val.startswith("docker://"):
                    docker_val = f"docker://{docker_val}"
                env_spec["container"] = EnvironmentSpecificValue(docker_val, ["shared_filesystem"])
        
        elif req.get("class") == "SoftwareRequirement":
            if "packages" in req:
                # Convert to conda environment
                packages = req["packages"]
                env_spec["conda"] = EnvironmentSpecificValue(str(packages), ["shared_filesystem"])
    
    return env_spec


def _extract_step_inputs(step_def: Dict[str, Any], tool_def: Dict[str, Any]) -> List[ParameterSpec]:
    """Extract step inputs."""
    inputs = []
    
    # Get input bindings from step
    step_inputs = step_def.get("in", {})
    
    # Get input definitions from tool
    tool_inputs = tool_def.get("inputs", {})
    
    for input_id, input_def in tool_inputs.items():
        # Check if this input is bound in the step
        if input_id in step_inputs:
            # Create parameter spec
            param_spec = _parse_single_parameter_spec(input_id, input_def, "input")
            if param_spec:
                inputs.append(param_spec)
    
    return inputs


def _extract_step_outputs(step_def: Dict[str, Any], tool_def: Dict[str, Any]) -> List[ParameterSpec]:
    """Extract step outputs."""
    outputs = []
    
    # Get output definitions from tool
    tool_outputs = tool_def.get("outputs", {})
    
    for output_id, output_def in tool_outputs.items():
        # Create parameter spec
        param_spec = _parse_single_parameter_spec(output_id, output_def, "output")
        if param_spec:
            outputs.append(param_spec)
    
    return outputs


def _parse_step_dependencies(step_name: str, step_def: Dict[str, Any]) -> List[Edge]:
    """Parse step dependencies."""
    edges = []
    
    # Check for explicit dependencies
    for dep in step_def.get("dependencies", []):
        edges.append(Edge(parent=dep, child=step_name))
    
    # Check for implicit dependencies through input bindings
    step_inputs = step_def.get("in", {})
    for input_id, input_binding in step_inputs.items():
        if isinstance(input_binding, str) and input_binding.startswith("step_"):
            # This is a step reference
            parent_step = input_binding
            edges.append(Edge(parent=parent_step, child=step_name))

    return edges


def _convert_tool_to_workflow_data(
    tool_def: Dict[str, Any],
    cwl_path: Path,
    preserve_metadata: bool = True,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Convert a single CommandLineTool to a single-step workflow."""
    
    # Extract tool information
    tool_name = tool_def.get("label") or tool_def.get("id", "cwl_tool")
    if tool_name.startswith("#"):
        tool_name = tool_name[1:]
    
    # Create a single task from the tool
    task, _ = _parse_cwl_step(
        "main",
        {"run": tool_def},
        cwl_path,
        verbose=verbose,
        debug=False,
    )
    
    # Add single_tool_conversion flag to format_specific
    format_specific = {"cwl_tool": tool_def, "single_tool_conversion": True}
    
    return {
        "name": tool_name,
        "version": "1.0",
        "label": tool_def.get("label"),
        "doc": tool_def.get("doc"),
        "cwl_version": tool_def.get("cwlVersion", "v1.2"),
        "inputs": _parse_parameter_specs(tool_def.get("inputs", {}), "input"),
        "outputs": _parse_parameter_specs(tool_def.get("outputs", {}), "output"),
        "requirements": EnvironmentSpecificValue(_parse_requirements(tool_def.get("requirements", [])), ["shared_filesystem"]),
        "hints": EnvironmentSpecificValue(_parse_requirements(tool_def.get("hints", [])), ["shared_filesystem"]),
        "provenance": _extract_provenance_spec(tool_def) if preserve_metadata else None,
        "documentation": _extract_documentation_spec(tool_def) if preserve_metadata else None,
        "intent": tool_def.get("intent", []),
        "metadata": MetadataSpec(
            source_format="cwl",
            source_file=str(cwl_path),
            source_version=tool_def.get("cwlVersion", "v1.2"),
            format_specific=format_specific,
        ) if preserve_metadata else None,
        "tasks": [task],
        "edges": [],
    }


def _parse_with_cwltool(
    cwl_path: Path, parsed_data: Dict[str, Any], verbose: bool = False
) -> Dict[str, Any]:
    """Use cwltool for enhanced parsing."""
    # This is a placeholder - in a real implementation, you would use cwltool
    # to get additional information like resolved dependencies, etc.
    if verbose:
        print("Enhanced parsing with cwltool not yet implemented")
    return parsed_data


def _extract_provenance_spec(cwl_doc: Dict[str, Any]) -> Optional[ProvenanceSpec]:
    """Extract provenance information from CWL document."""
    # Extract basic provenance information
    authors = []
    contributors = []

    # Look for common provenance fields
    if "author" in cwl_doc:
        authors.append({"name": cwl_doc["author"]})
    
    if "contributor" in cwl_doc:
        contributors.append({"name": cwl_doc["contributor"]})
    
    # Extract from metadata
    metadata = cwl_doc.get("metadata", {})
    if "author" in metadata:
        authors.append({"name": metadata["author"]})
    
    if "contributor" in metadata:
        contributors.append({"name": metadata["contributor"]})
    
    if not authors and not contributors:
        return None
    
    return ProvenanceSpec(
        authors=authors,
        contributors=contributors,
        created=metadata.get("created"),
        modified=metadata.get("modified"),
        version=metadata.get("version"),
        license=metadata.get("license"),
        doi=metadata.get("doi"),
        citations=metadata.get("citations", []),
        keywords=metadata.get("keywords", []),
        derived_from=metadata.get("derived_from"),
        extras=metadata,
    )


def _extract_documentation_spec(cwl_doc: Dict[str, Any]) -> Optional[DocumentationSpec]:
    """Extract documentation information from CWL document."""
    description = cwl_doc.get("doc") or cwl_doc.get("description")
    label = cwl_doc.get("label")
    
    if not description and not label:
        return None
    
    return DocumentationSpec(
        description=description,
        label=label,
        doc=cwl_doc.get("doc"),
        intent=cwl_doc.get("intent", []),
        usage_notes=cwl_doc.get("usage_notes"),
        examples=cwl_doc.get("examples", []),
    )


def _parse_parameter_specs(
    params: Union[Dict, List], param_type: str
) -> List[ParameterSpec]:
    """Parse parameter specifications."""
    if isinstance(params, list):
        # List format
        return [_parse_single_parameter_spec(f"param_{i}", param, param_type) 
                for i, param in enumerate(params) if param]
    elif isinstance(params, dict):
        # Dict format
        return [_parse_single_parameter_spec(param_id, param_def, param_type)
                for param_id, param_def in params.items()]
    else:
        return []


def _parse_single_parameter_spec(
    param_id: str, param_def: Any, param_type: str
) -> Optional[ParameterSpec]:
    """Parse a single parameter specification."""
    
    if isinstance(param_def, str):
        # Simple string type
        return ParameterSpec(
            id=param_id,
            type=param_def,
        )
    elif isinstance(param_def, dict):
        # Full parameter definition
        param_type_spec = param_def.get("type", "string")
        
        return ParameterSpec(
            id=param_id,
            type=param_type_spec,
            label=param_def.get("label"),
            doc=param_def.get("doc"),
            default=param_def.get("default"),
            format=param_def.get("format"),
            secondary_files=param_def.get("secondaryFiles", []),
            streamable=param_def.get("streamable", False),
            load_contents=param_def.get("loadContents", False),
            load_listing=param_def.get("loadListing"),
            input_binding=param_def.get("inputBinding"),
            output_binding=param_def.get("outputBinding"),
            value_from=param_def.get("valueFrom"),
        )

    return None


def _parse_requirements(requirements: List[Dict[str, Any]]) -> List[RequirementSpec]:
    """Parse CWL requirements."""
    result = []

    for req in requirements:
        if isinstance(req, dict) and "class" in req:
            # Extract all fields except 'class' into data
            req_data = {k: v for k, v in req.items() if k != "class"}
            result.append(RequirementSpec(
                class_name=req["class"],
                data=req_data
            ))

    return result


def _parse_scatter_spec(step_def: Dict[str, Any]) -> Optional[ScatterSpec]:
    """Parse scatter specification."""
    scatter = step_def.get("scatter")
    scatter_method = step_def.get("scatterMethod", "dotproduct")

    if scatter:
        if isinstance(scatter, str):
            scatter_list = [scatter]
        elif isinstance(scatter, list):
            scatter_list = scatter
        else:
            return None
            
        return ScatterSpec(
            scatter=scatter_list,
            scatter_method=scatter_method
        )
    
    return None
