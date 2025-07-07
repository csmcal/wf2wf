"""wf2wf.exporters.wdl – Workflow IR ➜ WDL

This module exports wf2wf intermediate representation workflows to
Workflow Description Language (WDL) format with enhanced features.
"""

from __future__ import annotations

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


class WDLExporter(BaseExporter):
    """WDL exporter using shared infrastructure."""
    
    def _get_target_format(self) -> str:
        """Get the target format name."""
        return "wdl"
    
    def _generate_output(self, workflow: Workflow, output_path: Path, **opts: Any) -> None:
        """Generate WDL output."""
        tasks_dir = opts.get("tasks_dir", "tasks")
        preserve_metadata = opts.get("preserve_metadata", True)
        wdl_version = opts.get("wdl_version", "1.0")
        add_runtime = opts.get("add_runtime", True)
        add_meta = opts.get("add_meta", True)
        target_env = self.target_environment

        if self.verbose:
            print(f"Exporting workflow '{workflow.name}' to WDL {wdl_version}")

        try:
            # Create output directory
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate main workflow file
            main_wdl_content = _generate_main_wdl_enhanced(
                workflow,
                wdl_version=wdl_version,
                preserve_metadata=preserve_metadata,
                add_runtime=add_runtime,
                add_meta=add_meta,
                verbose=self.verbose,
                target_environment=target_env,
            )

            with output_path.open('w') as f:
                f.write(main_wdl_content)

            # Generate task files if requested
            if tasks_dir and workflow.tasks:
                tasks_path = output_path.parent / tasks_dir
                tasks_path.mkdir(parents=True, exist_ok=True)
                
                for task in workflow.tasks.values():
                    task_content = _generate_task_wdl_enhanced(
                        task,
                        preserve_metadata=preserve_metadata,
                        add_runtime=add_runtime,
                        add_meta=add_meta,
                        verbose=self.verbose,
                        target_environment=target_env,
                    )
                    
                    task_file = tasks_path / f"{task.id}.wdl"
                    with task_file.open('w') as f:
                        f.write(task_content)
                    
                    if self.verbose:
                        print(f"  wrote task {task.id} → {task_file}")

            if self.verbose:
                print(f"✓ WDL workflow exported to {output_path}")

        except Exception as e:
            raise RuntimeError(f"Failed to export WDL workflow: {e}")


# Legacy function for backward compatibility
def from_workflow(wf: Workflow, out_file: Union[str, Path], **opts: Any) -> None:
    """Export a wf2wf workflow to WDL format (legacy function)."""
    exporter = WDLExporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False)
    )
    exporter.export_workflow(wf, out_file, **opts)


# Helper functions
def _generate_main_wdl_enhanced(
    workflow: Workflow,
    wdl_version: str = "1.0",
    preserve_metadata: bool = True,
    add_runtime: bool = True,
    add_meta: bool = True,
    verbose: bool = False,
    target_environment: str = "shared_filesystem",
) -> str:
    """Generate enhanced main WDL file."""
    lines = []
    
    # Add version and metadata
    lines.append(f"version {wdl_version}")
    lines.append("")
    
    if preserve_metadata:
        if workflow.label:
            lines.append(f"# Workflow: {workflow.label}")
        if workflow.doc:
            lines.append(f"# Description: {workflow.doc}")
        if workflow.version:
            lines.append(f"# Version: {workflow.version}")
        lines.append("")
    
    # Add imports if tasks are in separate files
    if workflow.tasks:
        lines.append("import \"tasks/*.wdl\"")
        lines.append("")
    
    # Add workflow definition
    lines.append("workflow " + (workflow.name or "main") + " {")
    
    # Add workflow inputs
    if workflow.inputs:
        lines.append("    input {")
        for param in workflow.inputs:
            if isinstance(param, ParameterSpec):
                wdl_type = _convert_type_to_wdl(param.type)
                default_value = _get_wdl_default_value(param)
                if default_value:
                    lines.append(f"        {wdl_type} {param.id} = {default_value}")
                else:
                    lines.append(f"        {wdl_type} {param.id}")
            else:
                lines.append(f"        String {param}")
        lines.append("    }")
        lines.append("")
    
    # Add task calls
    lines.append("    # Task calls")
    for task in workflow.tasks.values():
        task_call = _generate_task_call_enhanced(task, workflow)
        lines.append(f"    {task_call}")
    
    # Add workflow outputs
    if workflow.outputs:
        lines.append("")
        lines.append("    output {")
        for param in workflow.outputs:
            if isinstance(param, ParameterSpec):
                wdl_type = _convert_type_to_wdl(param.type)
                lines.append(f"        {wdl_type} {param.id} = {task.id}.{param.id}")
            else:
                lines.append(f"        String {param} = {task.id}.{param}")
        lines.append("    }")
    
    lines.append("}")
    
    return "\n".join(lines)


def _generate_task_call_enhanced(task: Task, workflow: Workflow) -> str:
    """Generate enhanced task call."""
    # Get input dependencies
    parent_tasks = [edge.parent for edge in workflow.edges if edge.child == task.id]
    
    # Build input arguments
    inputs = []
    
    # Add dependencies
    for parent in parent_tasks:
        inputs.append(f"{parent}.output")
    
    # Add workflow-level inputs
    for param in task.inputs:
        if isinstance(param, ParameterSpec):
            inputs.append(f"{param.id} = {param.id}")
        else:
            inputs.append(f"{param} = {param}")
    
    if inputs:
        return f"call {task.id} {{ input: {', '.join(inputs)} }}"
    else:
        return f"call {task.id}"


def _generate_task_wdl_enhanced(
    task: Task,
    preserve_metadata: bool = True,
    add_runtime: bool = True,
    add_meta: bool = True,
    verbose: bool = False,
    target_environment: str = "shared_filesystem",
) -> str:
    """Generate enhanced task WDL file."""
    lines = []
    
    # Add metadata
    if preserve_metadata:
        if task.label:
            lines.append(f"# Task: {task.label}")
        if task.doc:
            lines.append(f"# Description: {task.doc}")
        lines.append("")
    
    # Add task definition
    lines.append(f"task {task.id} {{")
    
    # Add inputs
    if task.inputs:
        lines.append("    input {")
        for param in task.inputs:
            if isinstance(param, ParameterSpec):
                wdl_type = _convert_type_to_wdl(param.type)
                default_value = _get_wdl_default_value(param)
                if default_value:
                    lines.append(f"        {wdl_type} {param.id} = {default_value}")
                else:
                    lines.append(f"        {wdl_type} {param.id}")
            else:
                lines.append(f"        String {param}")
        lines.append("    }")
        lines.append("")
    
    # Add command
    command = task.command.get_value_for(target_environment)
    if command:
        lines.append("    command {")
        if isinstance(command, str):
            # Parse command for WDL
            command_lines = _parse_command_for_wdl(command)
            for line in command_lines:
                lines.append(f"        {line}")
        else:
            lines.append(f"        {command}")
        lines.append("    }")
        lines.append("")
    
    # Add runtime
    if add_runtime:
        runtime_lines = _generate_runtime_section(task)
        if runtime_lines:
            lines.append("    runtime {")
            for line in runtime_lines:
                lines.append(f"        {line}")
            lines.append("    }")
            lines.append("")
    
    # Add outputs
    if task.outputs:
        lines.append("    output {")
        for param in task.outputs:
            if isinstance(param, ParameterSpec):
                wdl_type = _convert_type_to_wdl(param.type)
                if param.type.type == "File":
                    lines.append(f"        {wdl_type} {param.id} = \"{param.id}.*\"")
                else:
                    lines.append(f"        {wdl_type} {param.id} = read_string(stdout())")
            else:
                lines.append(f"        String {param} = \"{param}.*\"")
        lines.append("    }")
    
    lines.append("}")
    
    return "\n".join(lines)


def _generate_runtime_section(task: Task) -> List[str]:
    """Generate WDL runtime section."""
    lines = []
    environment = "shared_filesystem"
    
    # CPU
    cpu = task.cpu.get_value_for(environment)
    if cpu:
        lines.append(f"cpu: {cpu}")
    
    # Memory
    mem_mb = task.mem_mb.get_value_for(environment)
    if mem_mb:
        lines.append(f"memory: \"{mem_mb} MB\"")
    
    # Disk
    disk_mb = task.disk_mb.get_value_for(environment)
    if disk_mb:
        lines.append(f"disks: \"local-disk {disk_mb} LOCAL\"")
    
    # GPU
    gpu = task.gpu.get_value_for(environment)
    if gpu:
        lines.append(f"gpu: {gpu}")
    
    # Docker container
    container = task.container.get_value_for(environment)
    if container:
        lines.append(f"docker: \"{container}\"")
    
    # Time limit
    time_s = task.time_s.get_value_for(environment)
    if time_s:
        lines.append(f"maxRetries: {time_s // 3600}")  # Convert to hours
    
    return lines


def _convert_type_to_wdl(type_spec) -> str:
    """Convert TypeSpec to WDL type."""
    if isinstance(type_spec, str):
        return type_spec
    
    if type_spec.type == "File":
        return "File"
    elif type_spec.type == "Directory":
        return "Directory"
    elif type_spec.type == "string":
        return "String"
    elif type_spec.type == "int":
        return "Int"
    elif type_spec.type == "long":
        return "Int"
    elif type_spec.type == "float":
        return "Float"
    elif type_spec.type == "double":
        return "Float"
    elif type_spec.type == "boolean":
        return "Boolean"
    elif type_spec.type == "array":
        item_type = _convert_type_to_wdl(type_spec.items)
        return f"Array[{item_type}]"
    elif type_spec.type == "record":
        return "Object"  # WDL doesn't have record types, use Object
    elif type_spec.type == "enum":
        return "String"  # WDL doesn't have enum types, use String
    else:
        return "String"  # Default fallback


def _get_wdl_default_value(param: ParameterSpec) -> Optional[str]:
    """Get WDL default value for parameter."""
    if param.default is not None:
        if isinstance(param.default, str):
            return f"\"{param.default}\""
        elif isinstance(param.default, bool):
            return str(param.default).lower()
        else:
            return str(param.default)
    
    # Provide sensible defaults based on type
    if param.type.type == "File":
        return "\"input.txt\""
    elif param.type.type == "string":
        return "\"default\""
    elif param.type.type == "int":
        return "0"
    elif param.type.type == "float":
        return "0.0"
    elif param.type.type == "boolean":
        return "false"
    else:
        return None


def _parse_command_for_wdl(command: str) -> List[str]:
    """Parse command string into WDL command lines."""
    import shlex
    
    if not command or command.startswith("#"):
        return ["echo 'No command specified'"]
    
    # Simple command parsing
    parts = shlex.split(command)
    if not parts:
        return ["echo 'Empty command'"]
    
    # Convert to WDL command format
    command_lines = []
    
    # Handle simple commands
    if len(parts) == 1:
        command_lines.append(parts[0])
    else:
        # Multi-part command
        command_lines.append(" ".join(parts))
    
    return command_lines
