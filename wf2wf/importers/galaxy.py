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

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from wf2wf.core import (
    Workflow,
    Task,
    Edge,
    ResourceSpec,
    ParameterSpec,
    ProvenanceSpec,
    DocumentationSpec,
)


def to_workflow(path: str | Path, **opts: Any) -> Workflow:
    """Import a Galaxy workflow file and convert to wf2wf IR.

    Args:
        path: Path to the Galaxy workflow file (.ga)
        **opts: Additional options:
            - preserve_metadata: bool = True - Preserve Galaxy metadata
            - verbose: bool = False - Enable verbose output
            - debug: bool = False - Enable debug output

    Returns:
        Workflow: The converted workflow in wf2wf IR format

    Raises:
        RuntimeError: If the Galaxy file cannot be parsed or converted
        FileNotFoundError: If the Galaxy file doesn't exist
    """
    galaxy_path = Path(path).resolve()
    if not galaxy_path.exists():
        raise FileNotFoundError(f"Galaxy workflow file not found: {galaxy_path}")

    preserve_metadata = opts.get("preserve_metadata", True)
    verbose = opts.get("verbose", False)
    debug = opts.get("debug", False)

    if verbose:
        print(f"Importing Galaxy workflow: {galaxy_path}")

    try:
        # Load Galaxy workflow JSON
        with open(galaxy_path, "r") as f:
            galaxy_doc = json.load(f)

        # Convert to workflow IR
        workflow = _convert_galaxy_to_workflow(
            galaxy_doc,
            galaxy_path,
            preserve_metadata=preserve_metadata,
            verbose=verbose,
            debug=debug,
        )

        if verbose:
            print(
                f"Successfully imported Galaxy workflow with {len(workflow.tasks)} tasks"
            )

        return workflow

    except Exception as e:
        if debug:
            import traceback

            traceback.print_exc()
        raise RuntimeError(f"Failed to import Galaxy workflow: {e}")


def _convert_galaxy_to_workflow(
    galaxy_doc: Dict[str, Any],
    galaxy_path: Path,
    preserve_metadata: bool = True,
    verbose: bool = False,
    debug: bool = False,
) -> Workflow:
    """Convert Galaxy workflow document to wf2wf Workflow IR."""

    # Extract workflow metadata
    workflow_name = galaxy_doc.get("name", galaxy_path.stem)
    workflow_version = str(galaxy_doc.get("version", "1.0"))

    # Create workflow IR
    workflow = Workflow(
        name=workflow_name,
        version=workflow_version,
        label=workflow_name,
        doc=galaxy_doc.get("annotation", ""),
    )

    # Store Galaxy metadata
    if preserve_metadata:
        workflow.meta = {
            "source_format": "galaxy",
            "galaxy_format_version": galaxy_doc.get("format-version", "0.1"),
            "galaxy_uuid": galaxy_doc.get("uuid"),
            "original_galaxy_doc": galaxy_doc if preserve_metadata else {},
        }

        # Extract provenance
        workflow.provenance = _extract_galaxy_provenance(galaxy_doc)

        # Extract documentation
        workflow.documentation = _extract_galaxy_documentation(galaxy_doc)

    # Convert steps to tasks and edges
    steps = galaxy_doc.get("steps", {})
    tasks = {}
    edges = []
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
                command="# data input placeholder",
            )
            tasks[step_id] = placeholder_task

        elif step_type == "tool":
            # Handle tool steps
            task = _convert_galaxy_tool_step(
                step_id, step_data, preserve_metadata=preserve_metadata, verbose=verbose
            )
            tasks[step_id] = task

    # Second pass: extract connections and dependencies
    for step_id, step_data in steps.items():
        if step_data.get("type") == "tool":
            step_edges = _extract_galaxy_connections(step_id, step_data, steps)
            edges.extend(step_edges)

    # Add tasks and edges to workflow
    for task in tasks.values():
        workflow.add_task(task)

    for edge in edges:
        try:
            workflow.add_edge(edge.parent, edge.child)
        except KeyError as e:
            if verbose:
                print(f"Warning: Could not add edge {edge.parent} -> {edge.child}: {e}")

    # Extract workflow outputs
    workflow.outputs = _extract_galaxy_outputs(steps, tasks)

    return workflow


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

    param_spec = ParameterSpec(
        id=f"input_{step_id}", type=input_type, label=label, doc=annotation
    )

    return param_spec


def _convert_galaxy_tool_step(
    step_id: str,
    step_data: Dict[str, Any],
    preserve_metadata: bool = True,
    verbose: bool = False,
) -> Task:
    """Convert Galaxy tool step to IR Task."""

    # Extract step information
    tool_id = step_data.get("tool_id", f"tool_{step_id}")
    tool_version = step_data.get("tool_version", "")
    label = step_data.get("label", tool_id)
    annotation = step_data.get("annotation", "")

    # Create task
    task = Task(
        id=f"step_{step_id}",
        label=label,
        doc=annotation,
        command=f"{tool_id}",  # Simplified command representation
    )

    # Extract tool state (parameters)
    tool_state = step_data.get("tool_state", {})
    if isinstance(tool_state, str):
        try:
            tool_state = json.loads(tool_state)
        except json.JSONDecodeError:
            tool_state = {}

    # Convert tool parameters to inputs
    task.inputs = _extract_galaxy_tool_inputs(tool_state, step_data)

    # Extract outputs
    task.outputs = _extract_galaxy_tool_outputs(step_data)

    # Set basic resources (Galaxy doesn't typically specify resources explicitly)
    task.resources = ResourceSpec(cpu=1, mem_mb=1024)

    # Store Galaxy metadata
    if preserve_metadata:
        task.meta = {
            "galaxy_tool_id": tool_id,
            "galaxy_tool_version": tool_version,
            "galaxy_tool_state": tool_state,
            "galaxy_step_id": step_id,
            "galaxy_errors": step_data.get("errors"),
            "galaxy_uuid": step_data.get("uuid"),
        }

    return task


def _extract_galaxy_tool_inputs(
    tool_state: Dict[str, Any], step_data: Dict[str, Any]
) -> List[ParameterSpec]:
    """Extract tool inputs from Galaxy tool state."""

    inputs = []

    # Process tool state parameters
    for param_name, param_value in tool_state.items():
        # Skip special Galaxy parameters
        if param_name.startswith("__"):
            continue

        # Determine parameter type
        param_type = _infer_galaxy_parameter_type(param_value)

        param_spec = ParameterSpec(
            id=param_name,
            type=param_type,
            default=param_value if not isinstance(param_value, dict) else None,
        )

        inputs.append(param_spec)

    return inputs


def _extract_galaxy_tool_outputs(step_data: Dict[str, Any]) -> List[ParameterSpec]:
    """Extract tool outputs from Galaxy step data."""

    outputs = []

    # Galaxy outputs are defined in the outputs section
    step_outputs = step_data.get("outputs", [])

    for output in step_outputs:
        if isinstance(output, dict):
            output_name = output.get("name", "output")
            output_type = output.get("type", "File")
        else:
            # Simple string output name
            output_name = str(output)
            output_type = "File"

        param_spec = ParameterSpec(id=output_name, type=output_type)

        outputs.append(param_spec)

    return outputs


def _extract_galaxy_connections(
    step_id: str, step_data: Dict[str, Any], all_steps: Dict[str, Any]
) -> List[Edge]:
    """Extract connections from Galaxy workflow step."""

    edges = []

    # Galaxy connections are defined in input_connections
    input_connections = step_data.get("input_connections", {})

    for input_name, connection in input_connections.items():
        if isinstance(connection, dict):
            source_step = str(connection.get("id", ""))
            if source_step and source_step in all_steps:
                edges.append(
                    Edge(parent=f"step_{source_step}", child=f"step_{step_id}")
                )
        elif isinstance(connection, list):
            # Multiple connections
            for conn in connection:
                if isinstance(conn, dict):
                    source_step = str(conn.get("id", ""))
                    if source_step and source_step in all_steps:
                        edges.append(
                            Edge(parent=f"step_{source_step}", child=f"step_{step_id}")
                        )

    return edges


def _extract_galaxy_outputs(
    steps: Dict[str, Any], tasks: Dict[str, Task]
) -> List[ParameterSpec]:
    """Extract workflow outputs from Galaxy steps."""

    outputs = []

    # Look for steps marked as workflow outputs
    for step_id, step_data in steps.items():
        workflow_outputs = step_data.get("workflow_outputs", [])

        for output in workflow_outputs:
            if isinstance(output, dict):
                raw_output_name = output.get("output_name", f"output_{step_id}")
                output_label = output.get("label", raw_output_name)
                output_name = output_label  # Prefer label as identifier
            else:
                output_label = output_name = str(output)

            param_spec = ParameterSpec(id=output_name, type="File", label=output_label)

            outputs.append(param_spec)

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
        return "string"
    elif isinstance(param_value, list):
        return "array<string>"
    elif isinstance(param_value, dict):
        # Complex parameter - might be a file reference
        if "src" in param_value or "id" in param_value:
            return "File"
        else:
            return "string"
    else:
        return "string"


def _extract_galaxy_provenance(galaxy_doc: Dict[str, Any]) -> Optional[ProvenanceSpec]:
    """Extract provenance information from Galaxy workflow."""

    provenance = ProvenanceSpec()

    # Galaxy workflows may have creator information
    creator = galaxy_doc.get("creator")
    if creator:
        if isinstance(creator, list):
            provenance.authors = [{"name": str(c)} for c in creator]
        else:
            provenance.authors = [{"name": str(creator)}]

    # Extract version
    if "version" in galaxy_doc:
        provenance.version = str(galaxy_doc["version"])

    # Extract license if available
    license_info = galaxy_doc.get("license")
    if license_info:
        provenance.license = str(license_info)

    # Return None if no provenance data found
    if not any([provenance.authors, provenance.version, provenance.license]):
        return None

    return provenance


def _extract_galaxy_documentation(
    galaxy_doc: Dict[str, Any],
) -> Optional[DocumentationSpec]:
    """Extract documentation from Galaxy workflow."""

    doc = DocumentationSpec()

    # Extract annotation as description
    if "annotation" in galaxy_doc:
        doc.description = galaxy_doc["annotation"]
        doc.doc = galaxy_doc["annotation"]

    # Extract name as label
    if "name" in galaxy_doc:
        doc.label = galaxy_doc["name"]

    # Extract tags as keywords
    tags = galaxy_doc.get("tags", [])
    if tags:
        # Convert tags to keywords for provenance
        return doc

    # Return None if no documentation found
    if not any([doc.description, doc.doc, doc.label]):
        return None

    return doc
