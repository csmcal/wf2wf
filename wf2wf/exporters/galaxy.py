"""wf2wf.exporters.galaxy – Workflow IR ➜ Galaxy

This module exports wf2wf intermediate representation workflows to
Galaxy workflow format with enhanced features and tool integration.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from wf2wf.core import (
    Workflow,
    Task,
    ParameterSpec,
    EnvironmentSpecificValue,
)
from wf2wf.exporters.base import BaseExporter


class GalaxyExporter(BaseExporter):
    """Galaxy exporter using shared infrastructure."""
    
    def _get_target_format(self) -> str:
        """Get the target format name."""
        return "galaxy"
    
    def _generate_output(self, workflow: Workflow, output_path: Path, **opts: Any) -> None:
        """Generate Galaxy output."""
        preserve_metadata = opts.get("preserve_metadata", True)
        add_tool_configs = opts.get("add_tool_configs", True)
        tool_config_dir = opts.get("tool_config_dir", "tool_configs")
        workflow_format = opts.get("workflow_format", "json")  # json or yaml
        target_env = self.target_environment

        if self.verbose:
            print(f"Exporting workflow '{workflow.name}' to Galaxy format")
            print(f"  Target environment: {target_env}")
            print(f"  Tasks: {len(workflow.tasks)}")
            print(f"  Dependencies: {len(workflow.edges)}")

        try:
            # Generate Galaxy workflow
            galaxy_workflow = _generate_galaxy_workflow_enhanced(
                workflow,
                preserve_metadata=preserve_metadata,
                add_tool_configs=add_tool_configs,
                verbose=self.verbose,
                target_environment=target_env,
            )

            # Write workflow file using shared infrastructure
            if workflow_format.lower() == "yaml":
                import yaml
                workflow_content = yaml.dump(galaxy_workflow, default_flow_style=False, indent=2)
                self._write_file(workflow_content, output_path)
            else:
                self._write_json(galaxy_workflow, output_path)

            # Generate tool configurations if requested
            if add_tool_configs and workflow.tasks:
                tool_config_path = output_path.parent / tool_config_dir
                tool_config_path.mkdir(parents=True, exist_ok=True)
                
                for task in workflow.tasks.values():
                    tool_config = _generate_tool_config_enhanced(
                        task,
                        preserve_metadata=preserve_metadata,
                        verbose=self.verbose,
                        target_environment=target_env,
                    )
                    
                    tool_file = tool_config_path / f"{self._sanitize_name(task.id)}.xml"
                    self._write_file(tool_config, tool_file)
                    
                    if self.verbose:
                        print(f"  wrote tool config {task.id} → {tool_file}")

            if self.verbose:
                print(f"✓ Galaxy workflow exported to {output_path}")

        except Exception as e:
            raise RuntimeError(f"Failed to export Galaxy workflow: {e}")


# Legacy function for backward compatibility
def from_workflow(wf: Workflow, out_file: Union[str, Path], **opts: Any) -> None:
    """Export a wf2wf workflow to Galaxy format (legacy function)."""
    exporter = GalaxyExporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False)
    )
    exporter.export_workflow(wf, out_file, **opts)


# Helper functions
def _generate_galaxy_workflow_enhanced(
    workflow: Workflow,
    preserve_metadata: bool = True,
    add_tool_configs: bool = True,
    verbose: bool = False,
    target_environment: str = "shared_filesystem",
) -> Dict[str, Any]:
    """Generate enhanced Galaxy workflow."""
    galaxy_workflow = {
        "a_galaxy_workflow": "true",
        "format-version": "0.1",
        "name": workflow.name or "wf2wf_workflow",
        "uuid": _generate_uuid(),
        "steps": {},
        "annotation": "",
    }
    
    # Add metadata
    if preserve_metadata:
        if workflow.label:
            galaxy_workflow["name"] = workflow.label
        if workflow.doc:
            galaxy_workflow["annotation"] = workflow.doc
        if workflow.version:
            galaxy_workflow["version"] = workflow.version
    
    # Generate steps
    step_id = 0
    input_steps = {}
    task_steps = {}  # Track task step IDs
    
    # Add input steps
    for param in workflow.inputs:
        if isinstance(param, ParameterSpec):
            step_id += 1
            input_steps[param.id] = step_id
            galaxy_workflow["steps"][str(step_id)] = _generate_input_step(
                step_id, param, galaxy_workflow["name"]
            )
    
    # Add tool steps
    for task in workflow.tasks.values():
        step_id += 1
        task_steps[task.id] = step_id
        galaxy_workflow["steps"][str(step_id)] = _generate_tool_step_enhanced(
            step_id, task, workflow, input_steps, task_steps, verbose, target_environment
        )
    
    return galaxy_workflow


def _generate_input_step(step_id: int, param: ParameterSpec, workflow_name: str) -> Dict[str, Any]:
    """Generate Galaxy input step."""
    return {
        "id": step_id,
        "type": "input",
        "name": param.id,
        "tool_id": None,
        "tool_version": None,
        "tool_state": json.dumps({
            "name": param.id,
            "type": _convert_type_to_galaxy(param.type),
            "optional": param.type.nullable if hasattr(param.type, 'nullable') else False,
        }),
        "input_connections": {},
        "outputs": {},
        "position": {
            "left": step_id * 200,
            "top": 100,
        },
        "workflow_outputs": [],
        "label": param.label or param.id,
        "annotation": param.doc or "",
    }


def _generate_tool_step_enhanced(
    step_id: int,
    task: Task,
    workflow: Workflow,
    input_steps: Dict[str, int],
    task_steps: Dict[str, int],
    verbose: bool = False,
    target_environment: str = "shared_filesystem",
) -> Dict[str, Any]:
    """Generate enhanced Galaxy tool step."""
    # Get input connections
    input_connections = {}
    parent_tasks = [edge.parent for edge in workflow.edges if edge.child == task.id]
    
    # Add parent task connections
    for parent in parent_tasks:
        if parent in task_steps:
            input_connections["input1"] = {
                "id": task_steps[parent],
                "output_name": "output1",
            }
    
    # Add workflow input connections
    for param in task.inputs:
        if isinstance(param, ParameterSpec) and param.id in input_steps:
            input_connections[param.id] = {
                "id": input_steps[param.id],
                "output_name": "output",
            }
    
    # Generate tool state
    tool_state = _generate_tool_state_enhanced(task, target_environment)
    
    return {
        "id": step_id,
        "type": "tool",
        "name": task.id,
        "tool_id": f"toolshed.g2.bx.psu.edu/repos/devteam/{task.id}/custom_tool/1.0.0",
        "tool_version": "1.0.0",
        "tool_state": json.dumps(tool_state),
        "input_connections": input_connections,
        "outputs": _generate_outputs_enhanced(task),
        "position": {
            "left": step_id * 200,
            "top": 200,
        },
        "workflow_outputs": [],
        "label": task.label or task.id,
        "annotation": task.doc or "",
    }


def _generate_tool_state_enhanced(task: Task, target_environment: str) -> Dict[str, Any]:
    """Generate enhanced Galaxy tool state."""
    tool_state = {}
    
    # Add command using environment-specific value handling
    command = task.command.get_value_for(target_environment)
    if command:
        tool_state["command"] = command
    
    # Add script if no command
    if not command:
        script = task.script.get_value_for(target_environment)
        if script:
            tool_state["script"] = script
    
    # Add resource requirements using environment-specific value handling
    cpu = task.cpu.get_value_for(target_environment)
    mem_mb = task.mem_mb.get_value_for(target_environment)
    threads = task.threads.get_value_for(target_environment)
    
    if cpu:
        tool_state["cpu"] = cpu
    if mem_mb:
        tool_state["memory"] = f"{mem_mb}MB"
    if threads:
        tool_state["threads"] = threads
    
    # Add container specification
    container = task.container.get_value_for(target_environment)
    if container:
        tool_state["container"] = container
    
    # Add conda environment
    conda = task.conda.get_value_for(target_environment)
    if conda:
        tool_state["conda_env"] = conda
    
    # Add environment variables
    env_vars = task.env_vars.get_value_for(target_environment)
    if env_vars:
        tool_state["environment_variables"] = env_vars
    
    return tool_state


def _generate_outputs_enhanced(task: Task) -> Dict[str, Any]:
    """Generate enhanced Galaxy outputs."""
    outputs = {}
    
    for param in task.outputs:
        if isinstance(param, ParameterSpec):
            outputs[param.id] = {
                "name": param.id,
                "type": _convert_type_to_galaxy(param.type),
                "label": param.label or param.id,
            }
        else:
            outputs[str(param)] = {
                "name": str(param),
                "type": "data",
                "label": str(param),
            }
    
    return outputs


def _generate_tool_config_enhanced(
    task: Task,
    preserve_metadata: bool = True,
    verbose: bool = False,
    target_environment: str = "shared_filesystem",
) -> str:
    """Generate enhanced Galaxy tool configuration."""
    lines = []
    
    # Add XML header
    lines.append('<?xml version="1.0"?>')
    lines.append('<tool id="' + task.id + '" name="' + (task.label or task.id) + '" version="1.0.0">')
    
    # Add description
    if preserve_metadata and task.doc:
        lines.append('    <description>' + task.doc + '</description>')
    
    # Add command or script
    command = task.command.get_value_for(target_environment)
    script = task.script.get_value_for(target_environment)
    
    if command:
        lines.append('    <command><![CDATA[')
        lines.append('        ' + command)
        lines.append('    ]]></command>')
    elif script:
        lines.append('    <command><![CDATA[')
        lines.append('        ' + script)
        lines.append('    ]]></command>')
    
    # Add requirements
    requirements = []
    container = task.container.get_value_for(target_environment)
    conda = task.conda.get_value_for(target_environment)
    
    if container:
        requirements.append(f'        <container type="docker">{container}</container>')
    if conda:
        requirements.append(f'        <requirement type="package" version="1.0">{conda}</requirement>')
    
    if requirements:
        lines.append('    <requirements>')
        lines.extend(requirements)
        lines.append('    </requirements>')
    
    # Add inputs
    if task.inputs:
        lines.append('    <inputs>')
        for param in task.inputs:
            if isinstance(param, ParameterSpec):
                lines.extend(_generate_tool_input(param))
        lines.append('    </inputs>')
    
    # Add outputs
    if task.outputs:
        lines.append('    <outputs>')
        for param in task.outputs:
            if isinstance(param, ParameterSpec):
                lines.extend(_generate_tool_output(param))
        lines.append('    </outputs>')
    
    # Add help
    if preserve_metadata and task.doc:
        lines.append('    <help><![CDATA[')
        lines.append('        ' + task.doc)
        lines.append('    ]]></help>')
    
    lines.append('</tool>')
    
    return '\n'.join(lines)


def _generate_tool_input(param: ParameterSpec) -> List[str]:
    """Generate Galaxy tool input."""
    lines = []
    
    param_type = _convert_type_to_galaxy(param.type)
    param_id = param.id
    param_label = param.label or param.id
    
    if param_type == "data":
        lines.append(f'        <param name="{param_id}" type="data" format="txt" label="{param_label}" />')
    elif param_type == "text":
        lines.append(f'        <param name="{param_id}" type="text" label="{param_label}" />')
    elif param_type == "integer":
        lines.append(f'        <param name="{param_id}" type="integer" label="{param_label}" />')
    elif param_type == "float":
        lines.append(f'        <param name="{param_id}" type="float" label="{param_label}" />')
    elif param_type == "boolean":
        lines.append(f'        <param name="{param_id}" type="boolean" label="{param_label}" />')
    else:
        lines.append(f'        <param name="{param_id}" type="text" label="{param_label}" />')
    
    return lines


def _generate_tool_output(param: ParameterSpec) -> List[str]:
    """Generate Galaxy tool output."""
    lines = []
    
    param_type = _convert_type_to_galaxy(param.type)
    param_id = param.id
    param_label = param.label or param.id
    
    if param_type == "data":
        lines.append(f'        <data name="{param_id}" format="txt" label="{param_label}" />')
    else:
        lines.append(f'        <data name="{param_id}" format="txt" label="{param_label}" />')
    
    return lines


def _convert_type_to_galaxy(type_spec) -> str:
    """Convert TypeSpec to Galaxy type."""
    if isinstance(type_spec, str):
        return type_spec
    
    if type_spec.type == "File":
        return "data"
    elif type_spec.type == "Directory":
        return "data"
    elif type_spec.type == "string":
        return "text"
    elif type_spec.type == "int":
        return "integer"
    elif type_spec.type == "long":
        return "integer"
    elif type_spec.type == "float":
        return "float"
    elif type_spec.type == "double":
        return "float"
    elif type_spec.type == "boolean":
        return "boolean"
    elif type_spec.type == "array":
        return "data"  # Galaxy arrays are typically data collections
    else:
        return "text"  # Default fallback


def _generate_uuid() -> str:
    """Generate a UUID for Galaxy workflow."""
    import uuid
    return str(uuid.uuid4())
