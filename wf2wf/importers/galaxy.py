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
import logging
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
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger("wf2wf.importers.galaxy")
    
    def _parse_source(self, path: Path, **opts: Any) -> Dict[str, Any]:
        """Parse a Galaxy workflow file (.ga) and return a dict."""
        with open(path, "r") as f:
            galaxy_doc = json.load(f)

        # Validate required fields
        if "steps" not in galaxy_doc or not galaxy_doc["steps"]:
            raise ValueError("Invalid Galaxy workflow: missing or empty 'steps' field.")

        return galaxy_doc
    
    def _get_source_format(self) -> str:
        """Get the source format name."""
        return "galaxy"

    def _create_basic_workflow(self, parsed_data: Dict[str, Any]) -> Workflow:
        """Create a Workflow object from parsed Galaxy data."""
        name = parsed_data.get("name", "galaxy_workflow")
        version = parsed_data.get("version", "1.0")
        doc = parsed_data.get("annotation", None)
        label = parsed_data.get("label", name)

        # Extract tasks and edges
        tasks = {t.id: t for t in self._extract_tasks(parsed_data)}
        edges = self._extract_edges(parsed_data)

        # Extract workflow-level inputs and outputs
        inputs = []
        outputs = []
        for step_id, step_data in parsed_data["steps"].items():
            if step_data.get("type") == "data_input":
                param = _convert_galaxy_input_step(step_id, step_data)
                inputs.append(param)
            # Workflow outputs
            for output in step_data.get("workflow_outputs", []):
                outputs.append(ParameterSpec(
                    id=output.get("label", f"output_{step_id}_{output.get('output_name', 'unknown')}"),
                    type="File",
                    label=output.get("label", f"output_{step_id}_{output.get('output_name', 'unknown')}"),
                    doc=f"Workflow output from step {step_id}",
                ))

        # Build workflow
        wf = Workflow(
            name=name,
            version=version,
            label=label,
            doc=doc,
            tasks=tasks,
            edges=edges,
            inputs=inputs,
            outputs=outputs,
        )
        return wf

    def _extract_tasks(self, parsed_data: Dict[str, Any]) -> List[Task]:
        """Extract Task objects from Galaxy steps."""
        tasks = []
        for step_id, step_data in parsed_data["steps"].items():
            if step_data.get("type") == "data_input":
                # Data input step is not a task
                continue
            # Tool step
            task_dict = _convert_galaxy_tool_step_to_dict(step_id, step_data)
            task = Task(id=task_dict["id"], label=task_dict["label"], doc=task_dict["doc"],
                        command=EnvironmentSpecificValue(task_dict["command"]),
                        inputs=task_dict["inputs"], outputs=task_dict["outputs"],
                        cpu=EnvironmentSpecificValue(task_dict["cpu"]),
                        mem_mb=EnvironmentSpecificValue(task_dict["mem_mb"]),
                        disk_mb=EnvironmentSpecificValue(task_dict["disk_mb"]),
                        time_s=EnvironmentSpecificValue(task_dict["time_s"]))
            tasks.append(task)
        return tasks

    def _extract_edges(self, parsed_data: Dict[str, Any]) -> List[Edge]:
        """Extract Edge objects from Galaxy step connections, only between tool steps."""
        edges = []
        steps = parsed_data["steps"]
        # Only include tool steps as tasks
        tool_task_ids = {f"step_{step_id}" for step_id, step_data in steps.items() if step_data.get("type") != "data_input"}
        for step_id, step_data in steps.items():
            for edge_dict in _extract_galaxy_connections(step_id, step_data, steps):
                # Only add edge if both parent and child are tool steps
                if edge_dict["parent"] in tool_task_ids and edge_dict["child"] in tool_task_ids:
                    edges.append(Edge(parent=edge_dict["parent"], child=edge_dict["child"]))
        return edges


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

    # Try to get the input name from the step's 'inputs' field
    input_name = None
    inputs_list = step_data.get("inputs", [])
    if inputs_list and isinstance(inputs_list, list) and len(inputs_list) > 0:
        # Use the first input's name if available
        input_name = inputs_list[0].get("name")

    # Determine input type from tool_state
    tool_state = step_data.get("tool_state", {})
    if isinstance(tool_state, str):
        try:
            tool_state = json.loads(tool_state)
        except json.JSONDecodeError:
            tool_state = {}

    # Galaxy data inputs are typically files
    input_type = "File"

    # Use input_name if available, else fallback to input_{step_id}
    param_id = f"{input_name}_{step_id}" if input_name else f"input_{step_id}"

    # Create parameter spec
    param_spec = ParameterSpec(
        id=param_id,
        type=input_type,
        label=label,
        doc=annotation,
    )

    return param_spec


def _convert_galaxy_tool_step_to_dict(
    step_id: str,
    step_data: Dict[str, Any],
    preserve_metadata: bool = True,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Convert Galaxy tool step to dictionary for base importer."""

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

    # Create task dictionary
    task_dict = {
        "id": f"step_{step_id}",
        "label": label,
        "doc": annotation,
        "command": f"galaxy_tool:{tool_id}@{tool_version}",
        "inputs": inputs,
        "outputs": outputs,
        "cpu": 1,
        "mem_mb": 4096,
        "disk_mb": 4096,
        "time_s": 3600,
    }

    return task_dict


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
            doc=f"Input parameter: {param_name}",
        )
        inputs.append(param_spec)

    return inputs


def _extract_galaxy_tool_outputs(step_data: Dict[str, Any]) -> List[ParameterSpec]:
    """Extract tool outputs from Galaxy step data."""
    outputs = []

    # Extract outputs from step data
    step_outputs = step_data.get("outputs", [])
    for output in step_outputs:
        output_name = output.get("name", "unknown")
        output_type = output.get("type", "data")

        # Map Galaxy types to IR types
        ir_type = _map_galaxy_type_to_ir(output_type)

        output_spec = ParameterSpec(
            id=output_name,
            type=ir_type,
            label=output_name,
            doc=f"Output: {output_name}",
        )
        outputs.append(output_spec)

    return outputs


def _extract_galaxy_connections(
    step_id: str, step_data: Dict[str, Any], all_steps: Dict[str, Any]
) -> List[dict]:
    """Extract connections from Galaxy step data."""
    edges = []

    # Extract input connections
    input_connections = step_data.get("input_connections", {})
    for input_name, connection in input_connections.items():
        if isinstance(connection, dict) and "id" in connection:
            parent_step_id = connection["id"]
            parent_task_id = f"step_{parent_step_id}"
            child_task_id = f"step_{step_id}"
            # Return as dict, not Edge object
            edge = {"parent": parent_task_id, "child": child_task_id}
            edges.append(edge)

    return edges


def _extract_galaxy_outputs(
    steps: Dict[str, Any], tasks: Dict[str, Task]
) -> List[ParameterSpec]:
    """Extract workflow outputs from Galaxy steps."""
    outputs = []

    for step_id, step_data in steps.items():
        workflow_outputs = step_data.get("workflow_outputs", [])
        for output in workflow_outputs:
            output_spec = ParameterSpec(
                id=output.get("label", f"output_{step_id}_{output.get('output_name', 'unknown')}"),
                type="File",  # Galaxy outputs are typically files
                label=output.get("label", f"output_{step_id}_{output.get('output_name', 'unknown')}"),
                doc=f"Workflow output from step {step_id}",
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
        # Check for file-like patterns
        if param_value.endswith(('.txt', '.fastq', '.fasta', '.bam', '.sam', '.vcf')):
            return "File"
        elif param_value.startswith('http://') or param_value.startswith('https://'):
            return "string"
        else:
            return "string"
    elif isinstance(param_value, list):
        # For lists, use "Any" instead of "array" to avoid validation issues
        return "Any"
    elif isinstance(param_value, dict):
        # For dictionaries, use "Any" instead of "record" to avoid validation issues
        return "Any"
    else:
        return "string"


def _map_galaxy_type_to_ir(galaxy_type: str) -> str:
    """Map Galaxy data types to IR types."""
    type_mapping = {
        "data": "File",
        "fasta": "File",
        "fastq": "File",
        "fastqsanger": "File",
        "bam": "File",
        "sam": "File",
        "vcf": "File",
        "txt": "File",
        "csv": "File",
        "tsv": "File",
        "json": "File",
        "xml": "File",
        "html": "File",
        "pdf": "File",
        "png": "File",
        "jpg": "File",
        "jpeg": "File",
        "gif": "File",
        "svg": "File",
        "bed": "File",
        "gtf": "File",
        "gff": "File",
        "wig": "File",
        "bigwig": "File",
        "bigbed": "File",
        "tabular": "File",
        "interval": "File",
        "peaks": "File",
        "matrix": "File",
        "h5": "File",
        "hdf5": "File",
        "zip": "File",
        "tar": "File",
        "gz": "File",
        "bz2": "File",
        "collection": "Directory",
        "list": "array",
        "boolean": "boolean",
        "integer": "int",
        "float": "float",
        "text": "string",
        "color": "string",
        "genomebuild": "string",
        "select": "string",
        "drill_down": "string",
    }
    
    return type_mapping.get(galaxy_type, "File")


def _extract_galaxy_provenance(galaxy_doc: Dict[str, Any]) -> Optional[ProvenanceSpec]:
    """Extract provenance information from Galaxy workflow."""
    if not galaxy_doc:
        return None

    # Extract basic provenance information
    extras = {}
    if "uuid" in galaxy_doc:
        extras["galaxy_uuid"] = galaxy_doc["uuid"]

    return ProvenanceSpec(
        version=galaxy_doc.get("version", "1.0"),
        extras=extras
    )


def _extract_galaxy_documentation(
    galaxy_doc: Dict[str, Any],
) -> Optional[DocumentationSpec]:
    """Extract documentation information from Galaxy workflow."""
    if not galaxy_doc:
        return None

    description = galaxy_doc.get("annotation", "")
    intent = galaxy_doc.get("tags", [])

    return DocumentationSpec(
        description=description,
        doc=description,
        intent=intent
    )
