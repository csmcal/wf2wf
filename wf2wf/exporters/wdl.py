"""wf2wf.exporters.wdl – Workflow IR ➜ WDL

This module exports wf2wf intermediate representation workflows to
Workflow Description Language (WDL) format with enhanced features.
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


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
            logger.info(f"Generating WDL workflow: {output_path}")
            logger.info(f"  Target environment: {target_env}")
            logger.info(f"  WDL version: {wdl_version}")
            logger.info(f"  Tasks: {len(workflow.tasks)}")
            logger.info(f"  Dependencies: {len(workflow.edges)}")

        try:
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

            # Write main workflow file using shared infrastructure
            self._write_file(main_wdl_content, output_path)

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
                    
                    task_file = tasks_path / f"{self._sanitize_name(task.id)}.wdl"
                    self._write_file(task_content, task_file)
                    
                    if self.verbose:
                        logger.info(f"  wrote task {task.id} → {task_file}")

            if self.verbose:
                logger.info(f"✓ WDL workflow exported to {output_path}")

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
    
    # Add workflow-level metadata if requested
    if add_meta and preserve_metadata:
        workflow_meta_lines = _generate_workflow_meta_section(workflow)
        if workflow_meta_lines:
            lines.append("    meta {")
            for line in workflow_meta_lines:
                lines.append(f"        {line}")
            lines.append("    }")
            lines.append("")
    
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
        # Check if task has conditional execution
        when_expr = task.when.get_value_for(target_environment)
        
        # Check if task has scatter operations
        scatter_spec = task.scatter.get_value_for(target_environment)
        if scatter_spec and scatter_spec.scatter:
            task_call = _generate_scatter_task_call(task, workflow, scatter_spec)
        else:
            task_call = _generate_task_call_enhanced(task, workflow)
        
        # Wrap in conditional if needed
        if when_expr:
            task_call = f"if ({when_expr}) {{\n        {task_call}\n    }}"
        
        lines.append(f"    {task_call}")
    
    # Add workflow outputs
    if workflow.outputs:
        lines.append("")
        lines.append("    output {")
        for param in workflow.outputs:
            if isinstance(param, ParameterSpec):
                wdl_type = _convert_type_to_wdl(param.type)
                # Find the task that produces this output
                output_task = _find_output_task(workflow, param.id)
                if output_task:
                    lines.append(f"        {wdl_type} {param.id} = {output_task}.{param.id}")
                else:
                    # Fallback to first task if no specific task found
                    first_task = next(iter(workflow.tasks.values()), None)
                    if first_task:
                        lines.append(f"        {wdl_type} {param.id} = {first_task.id}.{param.id}")
                    else:
                        lines.append(f"        {wdl_type} {param.id}")
            else:
                lines.append(f"        String {param}")
        lines.append("    }")
    
    lines.append("}")
    
    return "\n".join(lines)


def _generate_task_call_enhanced(task: Task, workflow: Workflow) -> str:
    """Generate enhanced task call."""
    # Get input dependencies
    parent_tasks = [edge.parent for edge in workflow.edges if edge.child == task.id]
    
    # Build input arguments
    inputs = []
    
    # Add dependencies from parent tasks
    for parent in parent_tasks:
        # Find the first output from the parent task
        parent_task = workflow.tasks.get(parent)
        if parent_task and parent_task.outputs:
            first_output = parent_task.outputs[0]
            if isinstance(first_output, ParameterSpec):
                inputs.append(f"{parent}.{first_output.id}")
            else:
                inputs.append(f"{parent}.{str(first_output)}")
        else:
            inputs.append(f"{parent}.output")
    
    # Add workflow-level inputs that match task inputs
    for param in task.inputs:
        if isinstance(param, ParameterSpec):
            # Check if this input is available at workflow level
            workflow_input = next((winput for winput in workflow.inputs 
                                 if isinstance(winput, ParameterSpec) and winput.id == param.id), None)
            if workflow_input:
                inputs.append(f"{param.id} = {param.id}")
    
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
    
    # Add command or script
    command = task.command.get_value_for(target_environment)
    script = task.script.get_value_for(target_environment)
    
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
    elif script:
        lines.append("    command {")
        script_lines = _parse_command_for_wdl(script)
        for line in script_lines:
            lines.append(f"        {line}")
        lines.append("    }")
        lines.append("")
    
    # Add runtime
    if add_runtime:
        runtime_lines = _generate_runtime_section(task, target_environment)
        if runtime_lines:
            lines.append("    runtime {")
            for line in runtime_lines:
                lines.append(f"        {line}")
            lines.append("    }")
            lines.append("")
    
    # Add environment variables if present
    env_vars = task.env_vars.get_value_for(target_environment)
    if env_vars and isinstance(env_vars, dict):
        lines.append("    environment {")
        for key, value in env_vars.items():
            if isinstance(value, str):
                lines.append(f"        {key}: \"{value}\"")
            else:
                lines.append(f"        {key}: {value}")
        lines.append("    }")
        lines.append("")
    
    # Add metadata if requested
    if add_meta and preserve_metadata:
        meta_lines = _generate_meta_section(task)
        if meta_lines:
            lines.append("    meta {")
            for line in meta_lines:
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
                    # For file outputs, use the parameter name as the filename pattern
                    lines.append(f"        {wdl_type} {param.id} = \"{param.id}.*\"")
                elif param.type.type == "Directory":
                    # For directory outputs
                    lines.append(f"        {wdl_type} {param.id} = \"{param.id}/\"")
                elif param.type.type in ["string", "int", "float", "boolean"]:
                    # For primitive types, read from stdout
                    lines.append(f"        {wdl_type} {param.id} = read_string(stdout())")
                else:
                    # Default to string output
                    lines.append(f"        String {param.id} = read_string(stdout())")
            else:
                lines.append(f"        String {param} = \"{param}.*\"")
        lines.append("    }")
    
    lines.append("}")
    
    return "\n".join(lines)


def _find_output_task(workflow: Workflow, output_id: str) -> Optional[str]:
    """Find the task that produces a specific output."""
    for task in workflow.tasks.values():
        for output in task.outputs:
            if isinstance(output, ParameterSpec) and output.id == output_id:
                return task.id
            elif str(output) == output_id:
                return task.id
    return None


def _generate_scatter_task_call(task: Task, workflow: Workflow, scatter_spec) -> str:
    """Generate WDL scatter task call."""
    # Get the base task call
    base_call = _generate_task_call_enhanced(task, workflow)
    
    # Extract scatter parameters
    scatter_params = scatter_spec.scatter
    if len(scatter_params) == 1:
        scatter_expr = scatter_params[0]
    else:
        # Multiple scatter parameters - use cross product
        scatter_expr = f"cross({', '.join(scatter_params)})"
    
    # Wrap the call in scatter
    return f"scatter ({scatter_expr}) {{\n        {base_call}\n    }}"


def _generate_meta_section(task: Task) -> List[str]:
    """Generate WDL meta section with task metadata."""
    lines = []
    
    if task.label:
        lines.append(f"description: \"{task.label}\"")
    
    if task.doc:
        lines.append(f"help: \"{task.doc}\"")
    
    # Add author information if available
    if task.provenance and task.provenance.authors:
        authors = [author.get("name", "Unknown") for author in task.provenance.authors]
        lines.append(f"author: \"{', '.join(authors)}\"")
    
    # Add version information
    if task.provenance and task.provenance.version:
        lines.append(f"version: \"{task.provenance.version}\"")
    
    return lines


def _generate_workflow_meta_section(workflow: Workflow) -> List[str]:
    """Generate WDL workflow meta section."""
    lines = []
    
    if workflow.label:
        lines.append(f"description: \"{workflow.label}\"")
    
    if workflow.doc:
        lines.append(f"help: \"{workflow.doc}\"")
    
    # Add author information if available
    if workflow.provenance and workflow.provenance.authors:
        authors = [author.get("name", "Unknown") for author in workflow.provenance.authors]
        lines.append(f"author: \"{', '.join(authors)}\"")
    
    # Add version information
    if workflow.version:
        lines.append(f"version: \"{workflow.version}\"")
    
    # Add license if available
    if workflow.provenance and workflow.provenance.license:
        lines.append(f"license: \"{workflow.provenance.license}\"")
    
    return lines


def _generate_runtime_section(task: Task, target_environment: str = "shared_filesystem") -> List[str]:
    """Generate WDL runtime section using environment-specific values."""
    lines = []
    
    # Get environment-specific values
    cpu = task.cpu.get_value_for(target_environment)
    mem_mb = task.mem_mb.get_value_for(target_environment)
    disk_mb = task.disk_mb.get_value_for(target_environment)
    gpu = task.gpu.get_value_for(target_environment)
    container = task.container.get_value_for(target_environment)
    time_s = task.time_s.get_value_for(target_environment)
    threads = task.threads.get_value_for(target_environment)
    
    # CPU
    if cpu:
        lines.append(f"cpu: {cpu}")
    
    # Memory
    if mem_mb:
        lines.append(f"memory: \"{mem_mb} MB\"")
    
    # Disk
    if disk_mb:
        lines.append(f"disks: \"local-disk {disk_mb} LOCAL\"")
    
    # GPU
    if gpu:
        lines.append(f"gpu: {gpu}")
    
    # Docker container
    if container:
        lines.append(f"docker: \"{container}\"")
    
    # Time limit (convert to hours for WDL)
    if time_s:
        hours = max(1, time_s // 3600)  # Minimum 1 hour
        lines.append(f"maxRetries: {hours}")
    
    # Threads (if different from CPU)
    if threads and threads != cpu:
        lines.append(f"threads: {threads}")
    
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
    
    # Handle multi-line commands
    if "\n" in command:
        lines = command.strip().split("\n")
        command_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                command_lines.append(line)
        return command_lines if command_lines else ["echo 'No valid command found'"]
    
    # Simple command parsing with error handling
    try:
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
    except ValueError:
        # If shlex parsing fails (e.g., unclosed quotes), return the command as-is
        return [command.strip()]
