"""wf2wf.importers.galaxy – Galaxy ➜ Workflow IR

This module imports Galaxy workflow files and converts them to the wf2wf
intermediate representation with feature preservation.

Features supported:
- Galaxy workflow JSON format (.ga files)
- Tool steps and data input steps
- Workflow connections and dependencies
- Tool parameters and configurations
- Workflow annotations and metadata
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from wf2wf.core import (
    Workflow,
    Task,
    Edge,
    EnvironmentSpecificValue,
    ParameterSpec,
    ProvenanceSpec,
    DocumentationSpec,
    CheckpointSpec,
    LoggingSpec,
    SecuritySpec,
    NetworkingSpec,
    MetadataSpec,
)
from wf2wf.importers.base import BaseImporter


class GalaxyImporter(BaseImporter):
    """Galaxy importer using shared base infrastructure."""
    
    def _parse_source(self, path: Path, **opts: Any) -> Dict[str, Any]:
        """Parse Galaxy workflow file and extract all information."""
        preserve_metadata = opts.get("preserve_metadata", True)
        debug = opts.get("debug", False)
        verbose = self.verbose

        if verbose:
            print(f"Parsing Galaxy workflow file: {path}")

        # Load Galaxy workflow JSON
        with open(path, "r") as f:
            galaxy_doc = json.load(f)

        return {
            "galaxy_doc": galaxy_doc,
            "galaxy_path": path,
            "preserve_metadata": preserve_metadata,
            "debug": debug,
        }
    
    def _create_basic_workflow(self, parsed_data: Dict[str, Any]) -> Workflow:
        """Create basic workflow from parsed Galaxy data."""
        galaxy_doc = parsed_data["galaxy_doc"]
        galaxy_path = parsed_data["galaxy_path"]
        preserve_metadata = parsed_data["preserve_metadata"]
        
        # Extract workflow metadata
        workflow_name = galaxy_doc.get("name", galaxy_path.stem)
        workflow_version = str(galaxy_doc.get("version", "1.0"))

        # Create workflow with Galaxy-specific execution model
        workflow = Workflow(
            name=workflow_name,
            version=workflow_version,
            label=workflow_name,
            doc=galaxy_doc.get("annotation", ""),
            execution_model=EnvironmentSpecificValue("shared_filesystem", ["shared_filesystem"]),
        )

        # Store Galaxy metadata
        if preserve_metadata:
            workflow.metadata = MetadataSpec(
                source_format="galaxy",
                source_file=str(galaxy_path),
                source_version=galaxy_doc.get("format-version", "0.1"),
                format_specific={
                    "galaxy_uuid": galaxy_doc.get("uuid"),
                    "original_galaxy_doc": galaxy_doc if preserve_metadata else {},
                },
            )

            # Extract provenance
            workflow.provenance = _extract_galaxy_provenance(galaxy_doc)

            # Extract documentation
            workflow.documentation = _extract_galaxy_documentation(galaxy_doc)

        return workflow
    
    def _extract_tasks(self, parsed_data: Dict[str, Any]) -> List[Task]:
        """Extract tasks from parsed Galaxy data."""
        galaxy_doc = parsed_data["galaxy_doc"]
        preserve_metadata = parsed_data["preserve_metadata"]
        verbose = self.verbose
        
        tasks = []
        steps = galaxy_doc.get("steps", {})
        input_steps = {}

        # First pass: create tasks for all steps
        for step_id, step_data in steps.items():
            step_type = step_data.get("type", "tool")

            if step_type == "data_input":
                # Handle data input steps
                input_step = _convert_galaxy_input_step(
                    step_id, step_data, preserve_metadata
                )
                input_steps[step_id] = input_step
                workflow.inputs.append(input_step)

                # Create a placeholder Task so dependency edges referencing this input are valid
                placeholder_task = Task(
                    id=f"step_{step_id}",
                    label=step_data.get("label", f"input_{step_id}"),
                    doc=step_data.get("annotation", ""),
                    command=EnvironmentSpecificValue("# data input placeholder", ["shared_filesystem"]),
                )
                tasks.append(placeholder_task)

            elif step_type == "tool":
                # Handle tool steps
                task = _convert_galaxy_tool_step(
                    step_id, step_data, preserve_metadata=preserve_metadata, verbose=verbose
                )
                tasks.append(task)

        return tasks
    
    def _extract_edges(self, parsed_data: Dict[str, Any]) -> List[Edge]:
        """Extract edges from parsed Galaxy data."""
        galaxy_doc = parsed_data["galaxy_doc"]
        edges = []
        steps = galaxy_doc.get("steps", {})

        # Second pass: extract connections and dependencies
        for step_id, step_data in steps.items():
            if step_data.get("type") == "tool":
                step_edges = _extract_galaxy_connections(step_id, step_data, steps)
                edges.extend(step_edges)

        return edges
    
    def _get_source_format(self) -> str:
        """Get the source format name."""
        return "galaxy"


def to_workflow(path: Union[str, Path], **opts: Any) -> Workflow:
    """Convert Galaxy workflow file at *path* into a Workflow IR object using shared infrastructure.

    Parameters
    ----------
    path : Union[str, Path]
        Path to the .ga file.
    preserve_metadata : bool, optional
        Preserve Galaxy metadata (default: True).
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
    importer = GalaxyImporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False)
    )
    return importer.import_workflow(path, **opts)


def _convert_galaxy_input_step(
    step_id: str, step_data: Dict[str, Any], preserve_metadata: bool = True
) -> ParameterSpec:
    """Convert Galaxy data input step to IR parameter spec."""

    # Extract input information
    label = step_data.get("label", f"input_{step_id}")
    annotation = step_data.get("annotation", "")

    # Determine input type from tool_state
    tool_state = step_data.get("tool_state", {})
    if isinstance(tool_state, str):
        try:
            tool_state = json.loads(tool_state)
        except json.JSONDecodeError:
            tool_state = {}

    # Galaxy data inputs are typically files
    input_type = "File"

    # Create parameter spec
    param_spec = ParameterSpec(
        id=f"input_{step_id}",
        type=input_type,
        label=label,
        doc=annotation,
    )

    return param_spec


def _convert_galaxy_tool_step(
    step_id: str,
    step_data: Dict[str, Any],
    preserve_metadata: bool = True,
    verbose: bool = False,
) -> Task:
    """Convert Galaxy tool step to IR Task."""

    # Extract basic information
    tool_id = step_data.get("tool_id", "unknown_tool")
    tool_version = step_data.get("tool_version", "1.0")
    label = step_data.get("label", f"step_{step_id}")
    annotation = step_data.get("annotation", "")

    # Extract tool state
    tool_state = step_data.get("tool_state", {})
    if isinstance(tool_state, str):
        try:
            tool_state = json.loads(tool_state)
        except json.JSONDecodeError:
            tool_state = {}

    # Convert inputs and outputs
    inputs = _extract_galaxy_tool_inputs(tool_state, step_data)
    outputs = _extract_galaxy_tool_outputs(step_data)

    # Create task with environment-specific values
    task = Task(
        id=f"step_{step_id}",
        label=label,
        doc=annotation,
        command=EnvironmentSpecificValue(f"galaxy_tool:{tool_id}@{tool_version}", ["shared_filesystem"]),
        inputs=inputs,
        outputs=outputs,
        cpu=EnvironmentSpecificValue(1, ["shared_filesystem"]),
        mem_mb=EnvironmentSpecificValue(4096, ["shared_filesystem"]),
        disk_mb=EnvironmentSpecificValue(4096, ["shared_filesystem"]),
        time_s=EnvironmentSpecificValue(3600, ["shared_filesystem"]),
    )

    return task


def _extract_galaxy_tool_inputs(
    tool_state: Dict[str, Any], step_data: Dict[str, Any]
) -> List[ParameterSpec]:
    """Extract tool inputs from Galaxy tool state."""
    inputs = []

    # Extract input parameters from tool state
    for param_name, param_value in tool_state.items():
        if param_name.startswith("__"):
            continue  # Skip internal Galaxy parameters

        # Determine parameter type
        param_type = _infer_galaxy_parameter_type(param_value)

        # Create parameter spec
        param_spec = ParameterSpec(
            id=param_name,
            type=param_type,
            label=param_name,
            default=param_value,
        )
        inputs.append(param_spec)

    return inputs


def _extract_galaxy_tool_outputs(step_data: Dict[str, Any]) -> List[ParameterSpec]:
    """Extract tool outputs from Galaxy step data."""
    outputs = []

    # Galaxy tools typically produce files
    output_files = step_data.get("outputs", [])
    for output_file in output_files:
        output_spec = ParameterSpec(
            id=f"output_{output_file}",
            type="File",
            label=f"Output {output_file}",
        )
        outputs.append(output_spec)

    return outputs


def _extract_galaxy_connections(
    step_id: str, step_data: Dict[str, Any], all_steps: Dict[str, Any]
) -> List[Edge]:
    """Extract connections from Galaxy step."""
    edges = []

    # Extract input connections
    input_connections = step_data.get("input_connections", {})
    for input_name, connection_data in input_connections.items():
        if isinstance(connection_data, dict):
            source_step = connection_data.get("id")
            source_output = connection_data.get("output_name", "output")
            
            if source_step and source_step in all_steps:
                # Create edge from source step to current step
                parent_id = f"step_{source_step}"
                child_id = f"step_{step_id}"
                edges.append(Edge(parent=parent_id, child=child_id))

    return edges


def _extract_galaxy_outputs(
    steps: Dict[str, Any], tasks: Dict[str, Task]
) -> List[ParameterSpec]:
    """Extract workflow outputs from Galaxy steps."""
    outputs = []

    # Find steps that are marked as workflow outputs
    for step_id, step_data in steps.items():
        if step_data.get("workflow_outputs"):
            # This step produces workflow outputs
            step_outputs = step_data.get("outputs", [])
            for output_file in step_outputs:
                output_spec = ParameterSpec(
                    id=f"workflow_output_{step_id}_{output_file}",
                    type="File",
                    label=f"Workflow output from step {step_id}",
                )
                outputs.append(output_spec)

    return outputs


def _infer_galaxy_parameter_type(param_value: Any) -> str:
    """Infer parameter type from Galaxy parameter value."""
    if isinstance(param_value, bool):
        return "boolean"
    elif isinstance(param_value, int):
        return "int"
    elif isinstance(param_value, float):
        return "float"
    elif isinstance(param_value, str):
        # Check if it looks like a file path
        if param_value.startswith("/") or param_value.startswith("./"):
            return "File"
        else:
            return "string"
    elif isinstance(param_value, list):
        return "array"
    elif isinstance(param_value, dict):
        return "record"
    else:
        return "string"


def _extract_galaxy_provenance(galaxy_doc: Dict[str, Any]) -> Optional[ProvenanceSpec]:
    """Extract provenance information from Galaxy workflow."""
    provenance = ProvenanceSpec()

    # Extract basic provenance information
    if "creator" in galaxy_doc:
        provenance.authors = [{"name": galaxy_doc["creator"]}]

    if "version" in galaxy_doc:
        provenance.version = str(galaxy_doc["version"])

    if "uuid" in galaxy_doc:
        provenance.extras["galaxy_uuid"] = galaxy_doc["uuid"]

    # Return None if no provenance data found
    if not any([provenance.authors, provenance.version, provenance.extras]):
        return None

    return provenance


def _extract_galaxy_documentation(
    galaxy_doc: Dict[str, Any],
) -> Optional[DocumentationSpec]:
    """Extract documentation from Galaxy workflow."""
    doc = DocumentationSpec()

    if "annotation" in galaxy_doc:
        doc.description = galaxy_doc["annotation"]
        doc.doc = galaxy_doc["annotation"]

    if "tags" in galaxy_doc:
        doc.intent = galaxy_doc["tags"]

    # Return None if no documentation found
    if not any([doc.description, doc.doc, doc.intent]):
        return None

    return doc
