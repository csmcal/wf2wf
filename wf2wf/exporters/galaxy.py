"""wf2wf.exporters.galaxy – Workflow IR ➜ Galaxy

This module exports wf2wf intermediate representation workflows to
Galaxy workflow JSON format (.ga files).

Features supported:
- Galaxy workflow JSON format
- Tool steps and data input steps
- Workflow connections and dependencies
- Tool parameters and configurations
- Workflow annotations and metadata
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, Union

from wf2wf.core import Workflow, Task, ParameterSpec

from wf2wf.loss import (
    reset as loss_reset,
    write as loss_write,
    record as loss_record,
    prepare as loss_prepare,
    as_list as loss_as_list,
    compute_checksum,
)


def from_workflow(wf: Workflow, out_file: Union[str, Path], **opts: Any) -> None:
    """Export a wf2wf workflow to Galaxy workflow format.

    Args:
        wf: The workflow to export
        out_file: Path for the output Galaxy workflow file (.ga)
        **opts: Additional options:
            - galaxy_version: str = "21.09" - Galaxy version compatibility
            - preserve_metadata: bool = True - Preserve metadata
            - verbose: bool = False - Enable verbose output

    Raises:
        RuntimeError: If the workflow cannot be exported
    """
    # Prepare loss handling
    loss_prepare(wf.loss_map)
    loss_reset()

    output_path = Path(out_file).resolve()
    galaxy_version = opts.get("galaxy_version", "21.09")
    preserve_metadata = opts.get("preserve_metadata", True)
    verbose = opts.get("verbose", False)

    if verbose:
        print(f"Exporting workflow '{wf.name}' to Galaxy format")

    try:
        # Record unsupported features

        if wf.intent:
            loss_record(
                "/intent",
                "intent",
                wf.intent,
                "Galaxy workflow schema lacks intent field",
                "user",
            )

        for task in wf.tasks.values():
            if task.scatter:
                loss_record(
                    f"/tasks/{task.id}/scatter",
                    "scatter",
                    task.scatter.scatter,
                    "Galaxy lacks scatter construct",
                    "user",
                )
            if task.when:
                loss_record(
                    f"/tasks/{task.id}/when",
                    "when",
                    task.when,
                    "Conditional execution not preserved in Galaxy",
                    "user",
                )

        # Create output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate Galaxy workflow JSON
        galaxy_doc = _generate_galaxy_workflow(
            wf, galaxy_version, preserve_metadata=preserve_metadata, verbose=verbose
        )

        # Write Galaxy workflow file
        with open(output_path, "w") as f:
            json.dump(galaxy_doc, f, indent=2, sort_keys=True)

        if verbose:
            print(f"Galaxy workflow exported to: {output_path}")

        try:
            from wf2wf import report as _rpt

            _rpt.add_artefact(output_path)
            _rpt.add_action("Exported Galaxy workflow")
        except ImportError:
            pass

        loss_write(
            output_path.with_suffix(".loss.json"),
            target_engine="galaxy",
            source_checksum=compute_checksum(wf),
        )
        wf.loss_map = loss_as_list()

    except Exception as e:
        raise RuntimeError(f"Failed to export Galaxy workflow: {e}")


def _generate_galaxy_workflow(
    wf: Workflow,
    galaxy_version: str,
    preserve_metadata: bool = True,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Generate Galaxy workflow JSON document."""

    galaxy_doc = {
        "a_galaxy_workflow": "true",
        "annotation": wf.doc or wf.label or "",
        "format-version": "0.1",
        "name": wf.name,
        "steps": {},
        "tags": [],
        "uuid": str(uuid.uuid4()),
        "version": wf.version or "1.0",
    }

    # Add creator information if available
    if preserve_metadata and wf.provenance and wf.provenance.authors:
        galaxy_doc["creator"] = [
            author.get("name", "Unknown") for author in wf.provenance.authors
        ]

    # Add license if available
    if preserve_metadata and wf.provenance and wf.provenance.license:
        galaxy_doc["license"] = wf.provenance.license

    # Add tags from keywords if available
    if preserve_metadata and wf.provenance and wf.provenance.keywords:
        galaxy_doc["tags"] = wf.provenance.keywords

    step_id = 0

    # Add input steps
    for input_param in wf.inputs:
        input_step = _generate_galaxy_input_step(input_param, step_id)
        galaxy_doc["steps"][str(step_id)] = input_step
        step_id += 1

    # Add tool steps
    task_to_step_id = {}
    for task in wf.tasks.values():
        tool_step = _generate_galaxy_tool_step(
            task, step_id, wf, task_to_step_id, preserve_metadata=preserve_metadata
        )
        galaxy_doc["steps"][str(step_id)] = tool_step
        task_to_step_id[task.id] = step_id
        step_id += 1

    return galaxy_doc


def _generate_galaxy_input_step(
    input_param: ParameterSpec, step_id: int
) -> Dict[str, Any]:
    """Generate Galaxy data input step."""

    step = {
        "annotation": input_param.doc or "",
        "content_id": None,
        "errors": None,
        "id": step_id,
        "input_connections": {},
        "inputs": [
            {
                "description": input_param.doc or input_param.label or "",
                "name": input_param.id,
            }
        ],
        "label": input_param.label or input_param.id,
        "name": "Input dataset",
        "outputs": [
            {"name": "output", "type": _convert_ir_type_to_galaxy(input_param.type)}
        ],
        "position": {"left": 10, "top": 10 + (step_id * 100)},
        "tool_id": None,
        "tool_state": json.dumps({"optional": False, "tag": ""}),
        "tool_version": None,
        "type": "data_input",
        "uuid": str(uuid.uuid4()),
        "workflow_outputs": [],
    }

    return step


def _generate_galaxy_tool_step(
    task: Task,
    step_id: int,
    workflow: Workflow,
    task_to_step_id: Dict[str, int],
    preserve_metadata: bool = True,
) -> Dict[str, Any]:
    """Generate Galaxy tool step."""

    # Extract tool information
    tool_id = task.meta.get("galaxy_tool_id", task.id) if task.meta else task.id
    tool_version = task.meta.get("galaxy_tool_version", "1.0") if task.meta else "1.0"

    # Generate tool state from task inputs
    tool_state = {}
    for input_param in task.inputs:
        if input_param.default is not None:
            tool_state[input_param.id] = input_param.default
        else:
            tool_state[input_param.id] = ""

    # Add Galaxy-specific parameters
    tool_state["__page__"] = None
    tool_state["__rerun_remap_job_id__"] = None

    # Generate input connections
    input_connections = _generate_galaxy_input_connections(
        task, workflow, task_to_step_id
    )

    # Generate outputs
    outputs = []
    for output_param in task.outputs:
        outputs.append(
            {
                "name": output_param.id,
                "type": _convert_ir_type_to_galaxy(output_param.type),
            }
        )

    # Determine workflow outputs
    workflow_outputs = []
    for output_param in workflow.outputs:
        if any(out.id == output_param.id for out in task.outputs):
            workflow_outputs.append(
                {
                    "output_name": output_param.id,
                    "label": output_param.label or output_param.id,
                    "uuid": str(uuid.uuid4()),
                }
            )

    step = {
        "annotation": task.doc or "",
        "content_id": tool_id,
        "errors": None,
        "id": step_id,
        "input_connections": input_connections,
        "inputs": [],
        "label": task.label or task.id,
        "name": tool_id,
        "outputs": outputs,
        "position": {"left": 200 + (step_id * 50), "top": 10 + (step_id * 100)},
        "tool_id": tool_id,
        "tool_state": json.dumps(tool_state),
        "tool_version": tool_version,
        "type": "tool",
        "uuid": str(uuid.uuid4()),
        "workflow_outputs": workflow_outputs,
    }

    # ------------------------------------------------------------------
    # Container reference (digest or SIF path)
    # ------------------------------------------------------------------

    if task.environment and task.environment.container:
        step["container"] = task.environment.container

    # ------------------------------------------------------------------
    # SBOM / SIF provenance for reproducibility
    # ------------------------------------------------------------------

    if task.environment and task.environment.env_vars:
        sbom_path = task.environment.env_vars.get("WF2WF_SBOM")
        sif_path = task.environment.env_vars.get("WF2WF_SIF")

        if sbom_path:
            step["wf2wf_sbom"] = str(sbom_path)
        if sif_path:
            step["wf2wf_sif"] = str(sif_path)

    # Add original Galaxy metadata if available
    if preserve_metadata and task.meta:
        if "galaxy_uuid" in task.meta:
            step["uuid"] = task.meta["galaxy_uuid"]
        if "galaxy_errors" in task.meta:
            step["errors"] = task.meta["galaxy_errors"]

    return step


def _generate_galaxy_input_connections(
    task: Task, workflow: Workflow, task_to_step_id: Dict[str, int]
) -> Dict[str, Any]:
    """Generate input connections for Galaxy tool step."""

    input_connections = {}

    # Find dependencies through workflow edges
    for edge in workflow.edges:
        if edge.child == task.id:
            parent_step_id = task_to_step_id.get(edge.parent)
            if parent_step_id is not None:
                # Simple connection mapping - could be enhanced
                # For now, connect first output of parent to first input of child
                if task.inputs:
                    input_name = task.inputs[0].id
                    input_connections[input_name] = {
                        "id": parent_step_id,
                        "output_name": "output",
                    }

    # Also check for input connections from workflow inputs
    input_step_id = 0
    for input_param in workflow.inputs:
        # Check if any task input matches workflow input
        for task_input in task.inputs:
            if task_input.id == input_param.id or task_input.id.endswith(
                input_param.id
            ):
                input_connections[task_input.id] = {
                    "id": input_step_id,
                    "output_name": "output",
                }
        input_step_id += 1

    return input_connections


def _convert_ir_type_to_galaxy(ir_type: str) -> str:
    """Convert IR type to Galaxy data type."""

    # Handle union types
    if isinstance(ir_type, dict):
        ir_type = str(ir_type)

    ir_type = str(ir_type)

    # Basic type mapping
    type_mapping = {
        "File": "data",
        "Directory": "data_collection",
        "string": "text",
        "int": "integer",
        "float": "float",
        "boolean": "boolean",
    }

    # Handle optional types
    if ir_type.endswith("?"):
        base_type = ir_type[:-1]
        return type_mapping.get(base_type, "data")

    # Handle array types
    if ir_type.startswith("array<") and ir_type.endswith(">"):
        return "data_collection"

    return type_mapping.get(ir_type, "data")
