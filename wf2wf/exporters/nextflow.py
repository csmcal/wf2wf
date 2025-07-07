"""wf2wf.exporters.nextflow – Workflow IR ➜ Nextflow DSL2

This module exports wf2wf intermediate representation workflows to
Nextflow DSL2 format with enhanced features and channel management.
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


class NextflowExporter(BaseExporter):
    """Nextflow exporter using shared infrastructure."""
    
    def _get_target_format(self) -> str:
        """Get the target format name."""
        return "nextflow"
    
    def _generate_output(self, workflow: Workflow, output_path: Path, **opts: Any) -> None:
        """Generate Nextflow output."""
        config_file = opts.get("config_file", "nextflow.config")
        modules_dir = opts.get("modules_dir", "modules")
        use_dsl2 = opts.get("use_dsl2", True)
        add_channels = opts.get("add_channels", True)
        preserve_metadata = opts.get("preserve_metadata", True)
        container_mode = opts.get("container_mode", "docker")
        target_env = self.target_environment

        if self.verbose:
            print(f"Exporting workflow '{workflow.name}' to Nextflow DSL2")

        try:
            # Create output directory
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate main.nf file
            main_nf_content = _generate_main_nf_enhanced(
                workflow,
                use_dsl2=use_dsl2,
                add_channels=add_channels,
                preserve_metadata=preserve_metadata,
                container_mode=container_mode,
                verbose=self.verbose,
                target_environment=target_env,
            )

            with output_path.open('w') as f:
                f.write(main_nf_content)

            # Generate modules if requested
            if modules_dir and workflow.tasks:
                modules_path = output_path.parent / modules_dir
                modules_path.mkdir(parents=True, exist_ok=True)
                
                for task in workflow.tasks.values():
                    module_content = _generate_module_nf_enhanced(
                        task,
                        preserve_metadata=preserve_metadata,
                        container_mode=container_mode,
                        verbose=self.verbose,
                        target_environment=target_env,
                    )
                    
                    module_file = modules_path / f"{task.id}.nf"
                    with module_file.open('w') as f:
                        f.write(module_content)
                    
                    if self.verbose:
                        print(f"  wrote module {task.id} → {module_file}")

            # Generate nextflow.config if requested
            if config_file:
                config_content = _generate_nextflow_config_enhanced(
                    workflow,
                    container_mode=container_mode,
                    verbose=self.verbose,
                    target_environment=target_env,
                )
                
                config_path = output_path.parent / config_file
                with config_path.open('w') as f:
                    f.write(config_content)
                
                if self.verbose:
                    print(f"  wrote config → {config_path}")

            if self.verbose:
                print(f"✓ Nextflow workflow exported to {output_path}")

        except Exception as e:
            raise RuntimeError(f"Failed to export Nextflow workflow: {e}")


# Legacy function for backward compatibility
def from_workflow(wf: Workflow, out_file: Union[str, Path], **opts: Any) -> None:
    """Export a wf2wf workflow to Nextflow DSL2 format (legacy function)."""
    exporter = NextflowExporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False)
    )
    exporter.export_workflow(wf, out_file, **opts)


# Helper functions
def _generate_main_nf_enhanced(
    workflow: Workflow,
    use_dsl2: bool = True,
    add_channels: bool = True,
    preserve_metadata: bool = True,
    container_mode: str = "docker",
    verbose: bool = False,
    target_environment: str = "shared_filesystem",
) -> str:
    """Generate enhanced main.nf file."""
    lines = []
    
    # Add shebang and metadata
    lines.append("#!/usr/bin/env nextflow")
    lines.append("")
    
    if preserve_metadata:
        if workflow.label:
            lines.append(f"// Workflow: {workflow.label}")
        if workflow.doc:
            lines.append(f"// Description: {workflow.doc}")
        if workflow.version:
            lines.append(f"// Version: {workflow.version}")
        lines.append("")
    
    # Add DSL2 directive
    if use_dsl2:
        lines.append("nextflow.enable.dsl = 2")
        lines.append("")
    
    # Add workflow inputs
    if workflow.inputs:
        lines.append("// Workflow inputs")
        for param in workflow.inputs:
            if isinstance(param, ParameterSpec):
                lines.append(f"params.{param.id} = {_get_default_value(param)}")
            else:
                lines.append(f"params.{param} = null")
        lines.append("")
    
    # Add channel definitions
    if add_channels:
        lines.extend(_generate_channel_definitions(workflow))
        lines.append("")
    
    # Add workflow definition
    lines.append("workflow {")
    
    # Add workflow inputs
    if workflow.inputs:
        lines.append("    // Workflow inputs")
        for param in workflow.inputs:
            if isinstance(param, ParameterSpec):
                lines.append(f"    take: {param.id}")
            else:
                lines.append(f"    take: {param}")
        lines.append("")
    
    # Add process calls
    lines.append("    // Process calls")
    for task in workflow.tasks.values():
        process_call = _generate_process_call_enhanced(task, workflow)
        lines.append(f"    {process_call}")
    
    # Add workflow outputs
    if workflow.outputs:
        lines.append("")
        lines.append("    // Workflow outputs")
        for param in workflow.outputs:
            if isinstance(param, ParameterSpec):
                lines.append(f"    emit: {param.id}")
            else:
                lines.append(f"    emit: {param}")
    
    lines.append("}")
    lines.append("")
    
    return "\n".join(lines)


def _generate_channel_definitions(workflow: Workflow) -> List[str]:
    """Generate channel definitions for workflow inputs."""
    lines = []
    
    for param in workflow.inputs:
        if isinstance(param, ParameterSpec):
            if param.type.type == "File":
                lines.append(f"// Input file channel")
                lines.append(f"Channel.fromPath(params.{param.id})")
            elif param.type.type == "array":
                lines.append(f"// Input array channel")
                lines.append(f"Channel.of(params.{param.id})")
            else:
                lines.append(f"// Input value channel")
                lines.append(f"Channel.of(params.{param.id})")
        else:
            lines.append(f"Channel.of(params.{param})")
    
    return lines


def _generate_process_call_enhanced(task: Task, workflow: Workflow) -> str:
    """Generate enhanced process call."""
    # Get input dependencies
    parent_tasks = [edge.parent for edge in workflow.edges if edge.child == task.id]
    
    if parent_tasks:
        # Task has dependencies
        inputs = []
        for parent in parent_tasks:
            inputs.append(f"{parent}.out")
        
        # Add workflow-level inputs
        for param in task.inputs:
            if isinstance(param, ParameterSpec):
                inputs.append(f"params.{param.id}")
            else:
                inputs.append(f"params.{param}")
        
        return f"{task.id}({', '.join(inputs)})"
    else:
        # Task has no dependencies
        inputs = []
        for param in task.inputs:
            if isinstance(param, ParameterSpec):
                inputs.append(f"params.{param.id}")
            else:
                inputs.append(f"params.{param}")
        
        if inputs:
            return f"{task.id}({', '.join(inputs)})"
        else:
            return f"{task.id}()"


def _generate_module_nf_enhanced(
    task: Task,
    preserve_metadata: bool = True,
    container_mode: str = "docker",
    verbose: bool = False,
    target_environment: str = "shared_filesystem",
) -> str:
    """Generate enhanced module.nf file."""
    lines = []
    
    # Add process definition
    lines.append(f"process {task.id} {{")
    
    # Add metadata
    if preserve_metadata:
        if task.label:
            lines.append(f"    tag '{task.label}'")
        if task.doc:
            lines.append(f"    publishDir 'results/{task.id}', mode: 'copy'")
        lines.append("")
    
    # Add resource requirements
    cpu = task.cpu.get_value_for(target_environment)
    mem_mb = task.mem_mb.get_value_for(target_environment)
    disk_mb = task.disk_mb.get_value_for(target_environment)
    
    if cpu or mem_mb or disk_mb:
        lines.append("    // Resource requirements")
        if cpu:
            lines.append(f"    cpus {cpu}")
        if mem_mb:
            lines.append(f"    memory '{mem_mb} MB'")
        if disk_mb:
            lines.append(f"    disk '{disk_mb} MB'")
        lines.append("")
    
    # Add container specification
    container = task.container.get_value_for(target_environment)
    if container:
        lines.append("    // Container specification")
        if container_mode == "docker":
            lines.append(f"    container '{container}'")
        elif container_mode == "singularity":
            lines.append(f"    container '{container}'")
        lines.append("")
    
    # Add conda environment
    conda = task.conda.get_value_for(target_environment)
    if conda:
        lines.append("    // Conda environment")
        lines.append(f"    conda '{conda}'")
        lines.append("")
    
    # Add error handling
    retry_count = task.retry_count.get_value_for(target_environment)
    if retry_count:
        lines.append("    // Error handling")
        lines.append(f"    maxRetries {retry_count}")
        lines.append("")
    
    # Add inputs
    if task.inputs:
        lines.append("    input:")
        for param in task.inputs:
            if isinstance(param, ParameterSpec):
                if param.type.type == "File":
                    lines.append(f"        path {param.id}")
                elif param.type.type == "array":
                    lines.append(f"        each {param.id}")
                else:
                    lines.append(f"        val {param.id}")
            else:
                lines.append(f"        val {param}")
        lines.append("")
    
    # Add outputs
    if task.outputs:
        lines.append("    output:")
        for param in task.outputs:
            if isinstance(param, ParameterSpec):
                if param.type.type == "File":
                    lines.append(f"        path \"{param.id}.*\", emit: {param.id}")
                else:
                    lines.append(f"        val {param.id}, emit: {param.id}")
            else:
                lines.append(f"        path \"{param}.*\", emit: {param}")
        lines.append("")
    
    # Add script
    command = task.command.get_value_for(target_environment)
    if command:
        lines.append("    script:")
        if isinstance(command, str):
            # Parse command into script lines
            script_lines = _parse_command_for_nextflow(command)
            for line in script_lines:
                lines.append(f"        {line}")
        else:
            lines.append(f"        {command}")
    else:
        lines.append("    script:")
        lines.append(f"        echo 'No command specified for {task.id}'")
    
    lines.append("}")
    
    return "\n".join(lines)


def _generate_nextflow_config_enhanced(
    workflow: Workflow,
    container_mode: str = "docker",
    verbose: bool = False,
    target_environment: str = "shared_filesystem",
) -> str:
    """Generate enhanced nextflow.config file."""
    lines = []
    
    lines.append("// Nextflow configuration file")
    lines.append("// Generated by wf2wf")
    lines.append("")
    
    # Add process configuration
    lines.append("process {")
    lines.append("    // Default resource requirements")
    lines.append("    cpus = 1")
    lines.append("    memory = '4 GB'")
    lines.append("    disk = '4 GB'")
    lines.append("")
    
    # Add container configuration
    if container_mode == "docker":
        lines.append("    // Docker configuration")
        lines.append("    container = 'default-runtime:latest'")
    elif container_mode == "singularity":
        lines.append("    // Singularity configuration")
        lines.append("    container = 'default-runtime.sif'")
    
    lines.append("")
    lines.append("    // Error handling")
    lines.append("    maxRetries = 2")
    lines.append("    errorStrategy = 'retry'")
    lines.append("}")
    lines.append("")
    
    # Add executor configuration
    lines.append("executor {")
    lines.append("    name = 'local'")
    lines.append("    queueSize = 100")
    lines.append("}")
    lines.append("")
    
    # Add reporting configuration
    lines.append("report {")
    lines.append("    enabled = true")
    lines.append("    file = 'pipeline_report.html'")
    lines.append("}")
    lines.append("")
    
    # Add timeline configuration
    lines.append("timeline {")
    lines.append("    enabled = true")
    lines.append("    file = 'timeline_report.html'")
    lines.append("}")
    lines.append("")
    
    # Add trace configuration
    lines.append("trace {")
    lines.append("    enabled = true")
    lines.append("    file = 'trace.txt'")
    lines.append("}")
    
    return "\n".join(lines)


def _get_default_value(param: ParameterSpec) -> str:
    """Get default value for parameter."""
    if param.default is not None:
        if isinstance(param.default, str):
            return f"'{param.default}'"
        else:
            return str(param.default)
    
    # Provide sensible defaults based on type
    if param.type.type == "File":
        return "'input.txt'"
    elif param.type.type == "string":
        return "'default'"
    elif param.type.type == "int":
        return "0"
    elif param.type.type == "float":
        return "0.0"
    elif param.type.type == "boolean":
        return "false"
    else:
        return "null"


def _parse_command_for_nextflow(command: str) -> List[str]:
    """Parse command string into Nextflow script lines."""
    import shlex
    
    if not command or command.startswith("#"):
        return ["echo 'No command specified'"]
    
    # Simple command parsing
    parts = shlex.split(command)
    if not parts:
        return ["echo 'Empty command'"]
    
    # Convert to Nextflow script format
    script_lines = []
    
    # Handle simple commands
    if len(parts) == 1:
        script_lines.append(parts[0])
    else:
        # Multi-part command
        script_lines.append(" ".join(parts))
    
    return script_lines
