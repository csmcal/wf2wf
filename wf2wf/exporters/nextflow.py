"""wf2wf.exporters.nextflow – Workflow IR ➜ Nextflow DSL2

This module converts wf2wf intermediate representation to Nextflow DSL2 workflows.
It generates main.nf files, module files, and nextflow.config files with:
- Process definitions with proper DSL2 syntax
- Resource specifications
- Container/conda environments
- Channel operations and dependencies
- Configuration parameters
"""

import re
from pathlib import Path
from typing import Any, List, Union

from wf2wf.core import Workflow, Task, ParameterSpec
from wf2wf.loss import (
    reset as loss_reset,
    write as loss_write,
    record as loss_record,
    prepare,
    as_list,
    compute_checksum,
)


# Helper to extract identifier/filename from ParameterSpec or raw string
def _param_identifier(param: Any) -> str:
    """Return a filename / identifier string from a ParameterSpec or raw value."""
    if isinstance(param, ParameterSpec):
        return str(param.id)
    return str(param)


def from_workflow(wf: Workflow, out_file: Union[str, Path], **opts: Any):
    """Convert a wf2wf Workflow to Nextflow DSL2.

    Args:
        wf: Workflow object to convert
        out_file: Path to output main.nf file
        **opts: Additional options (modular, config_file, verbose, etc.)
    """
    prepare(wf.loss_map)
    loss_reset()
    out_path = Path(out_file)
    verbose = opts.get("verbose", False)
    modular = opts.get("modular", True)  # Create separate module files
    config_file = opts.get("config_file", None)  # Separate config file

    if verbose:
        print(f"Exporting Nextflow workflow to: {out_path}")

    # Create output directory if needed
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------------
    # Record unsupported features BEFORE writing files / loss side-car
    # --------------------------------------------------------------

    # Workflow-level intent
    if wf.intent:
        loss_record(
            "/intent",
            "intent",
            wf.intent,
            "Nextflow lacks explicit intent metadata",
            "user",
        )

    # Task-level unsupported attributes
    for task in wf.tasks.values():
        # Secondary files unsupported
        for io_name in ("inputs", "outputs"):
            params = getattr(task, io_name)
            for p in params:
                if isinstance(p, ParameterSpec) and getattr(p, "secondary_files", None):
                    loss_record(
                        f"/tasks/{task.id}/{io_name}/{p.id}/secondary_files",
                        "secondary_files",
                        p.secondary_files,
                        "Nextflow has no native secondary_files",
                        "user",
                    )

        # GPU memory / capability unsupported
        if getattr(task.resources, "gpu_mem_mb", None):
            loss_record(
                f"/tasks/{task.id}/resources/gpu_mem_mb",
                "gpu_mem_mb",
                task.resources.gpu_mem_mb,
                "Nextflow resource model lacks GPU memory field",
                "user",
            )
        if getattr(task.resources, "gpu_capability", None):
            loss_record(
                f"/tasks/{task.id}/resources/gpu_capability",
                "gpu_capability",
                task.resources.gpu_capability,
                "No gpu_capability mapping in Nextflow",
                "user",
            )

    # Generate main.nf content
    main_content = _generate_main_nf(wf, modular=modular, verbose=verbose)

    # Write main.nf
    out_path.write_text(main_content)

    if verbose:
        print(f"✓ Nextflow script written to {out_path}")

    try:
        from wf2wf import report as _rpt

        _rpt.add_artefact(out_path)
        _rpt.add_action("Exported Nextflow workflow")
    except ImportError:
        pass

    # ------------------------------------------------------------------
    # Persist loss map side-car and attach to workflow object
    # ------------------------------------------------------------------

    loss_write(
        out_path.with_suffix(".loss.json"),
        target_engine="nextflow",
        source_checksum=compute_checksum(wf),
    )
    wf.loss_map = as_list()

    if modular:
        # Create modules directory and individual module files
        modules_dir = out_path.parent / "modules"
        modules_dir.mkdir(exist_ok=True)

        for task_id, task in wf.tasks.items():
            module_content = _generate_module_file(task)
            module_file = modules_dir / f"{_sanitize_process_name(task_id)}.nf"
            module_file.write_text(module_content)

    # Generate configuration file
    config_content = _generate_nextflow_config(wf)

    if config_file:
        # Write to separate config file
        config_path = Path(config_file)
        config_path.write_text(config_content)
    else:
        # Write to nextflow.config in same directory
        config_path = out_path.parent / "nextflow.config"
        config_path.write_text(config_content)

    if verbose:
        print(f"Generated Nextflow workflow with {len(wf.tasks)} processes")
        if modular:
            print(f"Created {len(wf.tasks)} module files in {modules_dir}")
        print(f"Configuration written to: {config_path}")

    # (Intent already recorded above)


def _generate_main_nf(wf: Workflow, modular: bool = True, verbose: bool = False) -> str:
    """Generate main.nf content."""
    lines = [
        "#!/usr/bin/env nextflow",
        "",
        "/*",
        f" * {wf.name} - Generated by wf2wf",
        f" * Original format: {wf.meta.get('source_format', 'Workflow IR')}",
        f" * Tasks: {len(wf.tasks)}, Dependencies: {len(wf.edges)}",
        " */",
        "",
        "nextflow.enable.dsl=2",
        "",
    ]

    # Add includes for modular workflows
    if modular:
        lines.append("// Process modules")
        for task_id in wf.tasks.keys():
            process_name = _sanitize_process_name(task_id).upper()
            module_path = f"./modules/{_sanitize_process_name(task_id)}"
            lines.append(f"include {{ {process_name} }} from '{module_path}'")
        lines.append("")
    else:
        # Embed process definitions directly
        lines.append("// Process definitions")
        for task in wf.tasks.values():
            process_def = _generate_process_definition(task)
            lines.extend(process_def.split("\n"))
            lines.append("")

    # Generate workflow definition
    lines.extend(_generate_workflow_definition(wf).split("\n"))

    # Add workflow completion handler
    lines.extend(
        [
            "",
            "workflow.onComplete {",
            '    println "Pipeline completed at: $workflow.complete"',
            "    println \"Execution status: ${ workflow.success ? 'OK' : 'failed' }\"",
            "}",
        ]
    )

    return "\n".join(lines)


def _generate_module_file(task: Task) -> str:
    """Generate a separate module file for a task."""
    lines = [
        "/*",
        f" * {task.id} process module",
        " * Generated by wf2wf",
        " */",
        "",
    ]

    process_def = _generate_process_definition(task)
    lines.extend(process_def.split("\n"))

    return "\n".join(lines)


def _generate_process_definition(task: Task) -> str:
    """Generate Nextflow process definition from Task."""
    from wf2wf.environ import format_container_for_target_format, get_environment_metadata
    
    process_name = _sanitize_process_name(task.id).upper()

    lines = [
        f"process {process_name} {{",
    ]

    # Add tag if available
    if task.meta.get("tag"):
        lines.append(f"    tag \"{task.meta['tag']}\"")
    elif task.inputs:
        # Auto-generate tag from first input
        first_input = _param_identifier(task.inputs[0])
        # Use variable 'input_file' if single input; otherwise use sanitized name
        if len(task.inputs) == 1:
            lines.append('    tag "${input_file.baseName}"')
        else:
            lines.append(f'    tag "{Path(first_input).stem}"')

    # Add resource specifications
    if task.resources.cpu:
        lines.append(f"    cpus {task.resources.cpu}")

    if task.resources.mem_mb:
        memory_gb = task.resources.mem_mb / 1024
        if memory_gb >= 1:
            lines.append(f"    memory '{memory_gb:.1f}.GB'")
        else:
            lines.append(f"    memory '{task.resources.mem_mb}.MB'")

    if task.resources.disk_mb:
        disk_gb = task.resources.disk_mb / 1024
        if disk_gb >= 1:
            lines.append(f"    disk '{disk_gb:.1f}.GB'")
        else:
            lines.append(f"    disk '{task.resources.disk_mb}.MB'")

    if task.resources.time_s:
        time_hours = task.resources.time_s / 3600
        if time_hours >= 1:
            lines.append(f"    time '{time_hours:.1f}h'")
        else:
            time_minutes = task.resources.time_s / 60
            lines.append(f"    time '{time_minutes:.0f}m'")

    if task.resources.gpu:
        lines.append(f"    accelerator {task.resources.gpu}")

    # Add container or conda environment
    if task.environment.container:
        container = format_container_for_target_format(task.environment.container, "nextflow")
        lines.append(f"    container '{container}'")

    if task.environment.conda:
        lines.append(f"    conda '{task.environment.conda}'")

    # SBOM / SIF provenance comments
    if task.environment:
        metadata = get_environment_metadata(task.environment.env_vars)
        if metadata["sbom_path"]:
            lines.append(f"    // wf2wf_sbom: {metadata['sbom_path']}")
        if metadata["sif_path"]:
            lines.append(f"    // wf2wf_sif: {metadata['sif_path']}")

    # Add error handling
    if task.retry > 0:
        lines.append("    errorStrategy 'retry'")
        lines.append(f"    maxRetries {task.retry}")

    # Add publishDir if specified
    publish_dir = task.meta.get("publishDir")
    if publish_dir:
        lines.append(f"    publishDir \"{publish_dir}\", mode: 'copy'")
    elif task.outputs:
        # Auto-generate publishDir
        lines.append(f"    publishDir \"results/{task.id}\", mode: 'copy'")

    # Priority
    if task.priority:
        lines.append(f"    priority {task.priority}")

    # Conditional execution
    if task.when:
        # Wrap the expression into Nextflow 'when { ... }' block
        expr = task.when.strip()
        # Remove leading '$(...)' if present so it becomes plain Groovy/JS
        if expr.startswith("$(") and expr.endswith(")"):
            expr = expr[2:-1]
        lines.append(f"    when {{ {expr} }}")

    lines.append("")

    # Add input specification
    if task.inputs:
        lines.append("    input:")
        for i, input_param in enumerate(task.inputs):
            input_name = _param_identifier(input_param)
            if i == 0 and len(task.inputs) == 1:
                # Single input; use canonical 'input_file'
                lines.append("    path input_file")
            else:
                var_name = _sanitize_variable_name(Path(input_name).stem)
                lines.append(f"    path {var_name}")
        lines.append("")

    # Add output specification
    if task.outputs:
        lines.append("    output:")
        for output_param in task.outputs:
            output_name_full = _param_identifier(output_param)
            output_name = Path(output_name_full).name
            emit_name = _sanitize_variable_name(Path(output_name).stem)
            lines.append(f'    path "{output_name}", emit: {emit_name}')
        lines.append("")

    # Add script section
    lines.append("    script:")
    lines.append('    """')

    # Generate script content
    if task.script:
        # Use external script
        script_path = task.script
        if task.command:
            # Script with arguments
            lines.append(f"    {task.command}")
        else:
            # Just the script
            lines.append(f"    {script_path}")
    elif task.command:
        # Inline command
        command = task.command

        # Handle multi-line commands
        if "\n" in command:
            for cmd_line in command.split("\n"):
                if cmd_line.strip():
                    lines.append(f"    {cmd_line}")
        else:
            lines.append(f"    {command}")
    else:
        # Default command
        lines.append(f'    echo "Processing {task.id}"')

    lines.append('    """')
    lines.append("}")

    return "\n".join(lines)


def _generate_workflow_definition(wf: Workflow) -> str:
    """Generate the main workflow definition."""
    lines = [
        "workflow {",
    ]

    # Find input tasks (tasks with no dependencies)
    input_tasks = _find_input_tasks(wf)

    # Create input channels
    if input_tasks:
        lines.append("    // Input channels")
        for task_id in input_tasks:
            task = wf.tasks[task_id]
            if task.inputs:
                # Create channel from input files
                input_files = ", ".join(
                    f'"{_param_identifier(f)}"' for f in task.inputs
                )
                lines.append(f"    {task_id}_ch = Channel.fromPath([{input_files}])")
            else:
                # Create empty channel or value channel
                lines.append(f"    {task_id}_ch = Channel.value('start')")
        lines.append("")

    # Generate process calls in topological order
    ordered_tasks = _topological_sort(wf)

    lines.append("    // Process execution")
    for task_id in ordered_tasks:
        task = wf.tasks[task_id]
        process_name = _sanitize_process_name(task_id).upper()

        # Find input channels for this task
        input_channels = []

        # Check if this is an input task
        if task_id in input_tasks:
            input_channels.append(f"{task_id}_ch")
        else:
            # Find parent tasks
            parents = [edge.parent for edge in wf.edges if edge.child == task_id]
            for parent in parents:
                parent_name = _sanitize_process_name(parent).upper()
                input_channels.append(f"{parent_name}.out")

        # Generate process call
        if input_channels:
            input_str = ", ".join(input_channels)
            lines.append(f"    {process_name}({input_str})")
        else:
            lines.append(f"    {process_name}()")

    # Find final outputs
    final_tasks = _find_final_tasks(wf)
    if final_tasks:
        lines.append("")
        lines.append("    // Final outputs")
        for task_id in final_tasks:
            process_name = _sanitize_process_name(task_id).upper()
            lines.append(f"    {process_name}.out.view()")

    lines.append("}")

    return "\n".join(lines)


def _generate_nextflow_config(wf: Workflow) -> str:
    """Generate nextflow.config content."""
    lines = [
        "// Nextflow configuration file",
        "// Generated by wf2wf",
        "",
        "// Enable DSL2",
        "nextflow.enable.dsl = 2",
        "",
    ]

    # Add parameters from workflow config
    if wf.config:
        lines.append("// Pipeline parameters")
        lines.append("params {")
        for key, value in wf.config.items():
            if isinstance(value, str):
                lines.append(f'    {key} = "{value}"')
            elif isinstance(value, bool):
                lines.append(f"    {key} = {str(value).lower()}")
            else:
                lines.append(f"    {key} = {value}")
        lines.append("}")
        lines.append("")

    # Add process configuration
    lines.extend(
        [
            "// Process configuration",
            "process {",
            "    // Default settings",
            "    cpus = 1",
            "    memory = '2.GB'",
            "    time = '1h'",
            "",
            "    // Error handling",
            "    errorStrategy = 'retry'",
            "    maxRetries = 1",
            "",
            "    // Container settings",
            "    container = 'ubuntu:20.04'",
            "",
        ]
    )

    # Add process-specific configurations
    for task_id, task in wf.tasks.items():
        process_name = _sanitize_process_name(task_id).upper()

        config_lines = []

        if task.resources.cpu:
            config_lines.append(f"        cpus = {task.resources.cpu}")

        if task.resources.mem_mb:
            memory_gb = task.resources.mem_mb / 1024
            if memory_gb >= 1:
                config_lines.append(f"        memory = '{memory_gb:.1f}.GB'")
            else:
                config_lines.append(f"        memory = '{task.resources.mem_mb}.MB'")

        if task.resources.time_s:
            time_hours = task.resources.time_s / 3600
            if time_hours >= 1:
                config_lines.append(f"        time = '{time_hours:.1f}h'")
            else:
                time_minutes = task.resources.time_s / 60
                config_lines.append(f"        time = '{time_minutes:.0f}m'")

        if task.environment.container:
            container = task.environment.container
            if container.startswith("docker://"):
                container = container[9:]
            config_lines.append(f"        container = '{container}'")

        if task.retry > 0:
            config_lines.append(f"        maxRetries = {task.retry}")

        if config_lines:
            lines.append(f"    withName: '{process_name}' {{")
            lines.extend(config_lines)
            lines.append("    }")
            lines.append("")

    lines.append("}")
    lines.append("")

    # Add executor configuration
    lines.extend(
        [
            "// Executor configuration",
            "executor {",
            "    name = 'local'",
            "    cpus = 8",
            "    memory = '32.GB'",
            "}",
            "",
            "// Container configuration",
            "docker {",
            "    enabled = true",
            "    runOptions = '-u $(id -u):$(id -g)'",
            "}",
            "",
            "singularity {",
            "    enabled = false",
            "    autoMounts = true",
            "}",
            "",
            "// Conda configuration",
            "conda {",
            "    enabled = true",
            "    useMamba = true",
            "}",
            "",
            "// Resource monitoring",
            "timeline {",
            "    enabled = true",
            "    file = 'results/timeline.html'",
            "}",
            "",
            "report {",
            "    enabled = true",
            "    file = 'results/report.html'",
            "}",
            "",
            "trace {",
            "    enabled = true",
            "    file = 'results/trace.txt'",
            "}",
            "",
            "dag {",
            "    enabled = true",
            "    file = 'results/dag.svg'",
            "}",
        ]
    )

    return "\n".join(lines)


def _find_input_tasks(wf: Workflow) -> List[str]:
    """Find tasks that have no incoming dependencies."""
    has_parents = {edge.child for edge in wf.edges}
    return [task_id for task_id in wf.tasks.keys() if task_id not in has_parents]


def _find_final_tasks(wf: Workflow) -> List[str]:
    """Find tasks that have no outgoing dependencies."""
    has_children = {edge.parent for edge in wf.edges}
    return [task_id for task_id in wf.tasks.keys() if task_id not in has_children]


def _topological_sort(wf: Workflow) -> List[str]:
    """Perform topological sort of tasks."""
    # Build adjacency list
    graph = {task_id: [] for task_id in wf.tasks.keys()}
    in_degree = {task_id: 0 for task_id in wf.tasks.keys()}

    for edge in wf.edges:
        graph[edge.parent].append(edge.child)
        in_degree[edge.child] += 1

    # Kahn's algorithm
    queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
    result = []

    while queue:
        current = queue.pop(0)
        result.append(current)

        for neighbor in graph[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return result


def _sanitize_process_name(name: str) -> str:
    """Sanitize process name for Nextflow."""
    # Replace invalid characters with underscores
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)

    # Ensure it starts with a letter or underscore
    if sanitized and sanitized[0].isdigit():
        sanitized = f"process_{sanitized}"

    return sanitized


def _sanitize_variable_name(name: str) -> str:
    """Sanitize variable name for Nextflow."""
    # Replace invalid characters with underscores
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)

    # Ensure it starts with a letter or underscore
    if sanitized and sanitized[0].isdigit():
        sanitized = f"var_{sanitized}"

    # Convert to lowercase for variable names
    return sanitized.lower()
