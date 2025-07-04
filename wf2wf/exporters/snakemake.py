"""wf2wf.exporters.snakemake – Workflow IR ➜ Snakemake

This module converts the wf2wf intermediate representation to Snakemake workflows.

Public API:
    from_workflow(wf, out_file, **opts)   -> writes Snakefile
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any, List, Optional, Union

from wf2wf.core import Workflow, Task, ResourceSpec, ParameterSpec
from wf2wf.loss import (
    reset as loss_reset,
    write as loss_write,
    record as loss_record,
    prepare,
    as_list,
    compute_checksum,
)


def from_workflow(wf: Workflow, out_file: Union[str, Path], **opts: Any):
    """Convert Workflow IR to Snakemake format.

    Parameters
    ----------
    wf : Workflow
        In-memory workflow IR.
    out_file : Union[str, Path]
        Target Snakefile path.
    config_file : Union[str, Path], optional
        Write config to separate YAML file (default: embed in Snakefile).
    create_all_rule : bool, optional
        Create 'all' rule that depends on final outputs (default: True).
    include_resources : bool, optional
        Include resource specifications in rules (default: True).
    include_conda : bool, optional
        Include conda environment specifications (default: True).
    include_containers : bool, optional
        Include container specifications (default: True).
    script_dir : Union[str, Path], optional
        Directory for external scripts (default: 'scripts/').
    verbose : bool, optional
        Enable verbose output (default: False).
    debug : bool, optional
        Enable debug output (default: False).
    """
    # Prepare loss detection for repeat losses
    prepare(wf.loss_map)
    loss_reset()

    out_path = Path(out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    config_file = opts.get("config_file")
    create_all_rule = opts.get("create_all_rule", True)
    include_resources = opts.get("include_resources", True)
    include_conda = opts.get("include_conda", True)
    include_containers = opts.get("include_containers", True)
    script_dir = opts.get("script_dir", "scripts")
    verbose = opts.get("verbose", False)
    debug = opts.get("debug", False)

    if verbose:
        print(f"Converting workflow '{wf.name}' to Snakemake format")
        print(f"  Output: {out_path}")
        print(f"  Tasks: {len(wf.tasks)}")
        print(f"  Dependencies: {len(wf.edges)}")

    # Analyze workflow structure
    final_outputs = _find_final_outputs(wf)
    input_files = _find_input_files(wf)

    if debug:
        print(f"DEBUG: Final outputs: {final_outputs}")
        print(f"DEBUG: Input files: {input_files}")

    # ------------------------------------------------------------------
    # Loss recording for unsupported IR features
    # ------------------------------------------------------------------
    # Workflow-level intent not representable in Snakemake
    if wf.intent:
        loss_record(
            "/intent",
            "intent",
            wf.intent,
            "Snakemake has no ontology intent field",
            "user",
        )

    for task in wf.tasks.values():
        if task.scatter:
            loss_record(
                f"/tasks/{task.id}/scatter",
                "scatter",
                task.scatter.scatter,
                "Native scatter not supported in Snakemake",
                "user",
            )
        if task.when:
            loss_record(
                f"/tasks/{task.id}/when",
                "when",
                task.when,
                "Conditional execution not directly supported in Snakemake",
                "user",
            )
        if task.resources.gpu or task.resources.gpu_mem_mb:
            loss_record(
                f"/tasks/{task.id}/resources/gpu",
                "gpu",
                task.resources.gpu,
                "GPU scheduling not expressible in Snakemake",
                "user",
            )

        # Secondary files on outputs lost
        for p in task.outputs:
            if isinstance(p, ParameterSpec) and p.secondary_files:
                loss_record(
                    f"/tasks/{task.id}/outputs/{p.id}/secondary_files",
                    "secondary_files",
                    p.secondary_files,
                    "Secondary files concept missing in Snakemake",
                    "user",
                )

    # Generate Snakefile content
    snakefile_lines = []

    # Header comment
    snakefile_lines.extend(
        [
            f"# Snakefile generated by wf2wf from workflow '{wf.name}'",
            "# Original format: Workflow IR",
            f"# Tasks: {len(wf.tasks)}, Dependencies: {len(wf.edges)}",
            "",
        ]
    )

    # Config handling
    config_lines = _generate_config_section(wf, config_file, out_path)
    snakefile_lines.extend(config_lines)

    # All rule (if requested and we have final outputs)
    if create_all_rule and final_outputs:
        snakefile_lines.extend(
            [
                "rule all:",
                "    input:",
            ]
        )
        for output in sorted(final_outputs):
            snakefile_lines.append(f'        "{output}",')
        snakefile_lines.append("")

    # Generate rules for each task
    script_dir_path = out_path.parent / script_dir if script_dir else None

    for task_id in _topological_sort(wf):
        task = wf.tasks[task_id]
        rule_lines = _generate_rule(
            task,
            include_resources=include_resources,
            include_conda=include_conda,
            include_containers=include_containers,
            script_dir=script_dir_path,
            debug=debug,
        )
        snakefile_lines.extend(rule_lines)
        snakefile_lines.append("")

    # Write Snakefile
    snakefile_content = "\n".join(snakefile_lines)
    out_path.write_text(snakefile_content)

    if verbose:
        print(f"✓ Snakefile written to {out_path}")
        if script_dir_path and any(task.script for task in wf.tasks.values()):
            print(f"  Scripts directory: {script_dir_path}")

    # Report hooks
    try:
        from wf2wf import report as _rpt

        _rpt.add_artefact(out_path)
        _rpt.add_action("Exported Snakemake workflow")
    except ImportError:
        pass

    # Persist loss side-car and update in-memory workflow object
    loss_write(
        out_path.with_suffix(".loss.json"),
        target_engine="snakemake",
        source_checksum=compute_checksum(wf),
    )
    wf.loss_map = as_list()


def _find_final_outputs(wf: Workflow) -> List[str]:
    """Find outputs that are not inputs to any other task."""

    all_inputs = set()
    all_outputs = set()

    for task in wf.tasks.values():
        all_inputs.update(task.inputs)
        all_outputs.update(task.outputs)

    # Final outputs are outputs that are never used as inputs
    final_outputs = []
    for task in wf.tasks.values():
        for output in task.outputs:
            if output not in all_inputs:
                final_outputs.append(output)

    return final_outputs


def _find_input_files(wf: Workflow) -> List[str]:
    """Find inputs that are not outputs of any task."""

    all_inputs = set()
    all_outputs = set()

    for task in wf.tasks.values():
        all_inputs.update(task.inputs)
        all_outputs.update(task.outputs)

    # Input files are inputs that are never produced as outputs
    input_files = []
    for task in wf.tasks.values():
        for input_file in task.inputs:
            if input_file not in all_outputs:
                input_files.append(input_file)

    return list(set(input_files))  # Remove duplicates


def _generate_config_section(
    wf: Workflow, config_file: Optional[Path], out_path: Path
) -> List[str]:
    """Generate config section for Snakefile."""

    lines = []

    if wf.config:
        if config_file:
            # Write config to separate file
            config_path = Path(config_file)
            if not config_path.is_absolute():
                config_path = out_path.parent / config_path

            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w") as f:
                yaml.dump(wf.config, f, default_flow_style=False, indent=2)

            lines.extend([f'configfile: "{config_path.name}"', ""])
        else:
            # Embed config in Snakefile
            lines.append("# Workflow configuration")
            config_yaml = yaml.dump(wf.config, default_flow_style=False, indent=2)
            for line in config_yaml.split("\n"):
                if line.strip():
                    lines.append(f"# {line}")
            lines.extend(
                [
                    "config = {",
                ]
            )

            def format_config_value(value, indent=1):
                """Format config values for Python dict syntax."""
                spaces = "    " * indent
                if isinstance(value, dict):
                    result = [""]
                    for k, v in value.items():
                        if isinstance(v, dict):
                            result.append(f'{spaces}"{k}": {{')
                            result.extend(format_config_value(v, indent + 1))
                            result.append(f"{spaces}}},")
                        else:
                            result.append(f'{spaces}"{k}": {repr(v)},')
                    return result
                else:
                    return [f"{spaces}{repr(value)},"]

            for key, value in wf.config.items():
                if isinstance(value, dict):
                    lines.append(f'    "{key}": {{')
                    lines.extend(format_config_value(value, 2))
                    lines.append("    },")
                else:
                    lines.append(f'    "{key}": {repr(value)},')

            lines.extend(["}", ""])

    return lines


def _generate_rule(
    task: Task,
    include_resources: bool = True,
    include_conda: bool = True,
    include_containers: bool = True,
    script_dir: Optional[Path] = None,
    debug: bool = False,
) -> List[str]:
    """Generate Snakemake rule for a task."""

    lines = []

    # Rule header
    rule_name = _sanitize_rule_name(task.id)
    lines.append(f"rule {rule_name}:")

    # Input files
    if task.inputs:
        if len(task.inputs) == 1:
            lines.append(f'    input: "{task.inputs[0]}"')
        else:
            lines.append("    input:")
            for input_file in task.inputs:
                lines.append(f'        "{input_file}",')

    # Output files
    if task.outputs:
        if len(task.outputs) == 1:
            lines.append(f'    output: "{task.outputs[0]}"')
        else:
            lines.append("    output:")
            for output_file in task.outputs:
                lines.append(f'        "{output_file}",')

    # Parameters (from task params)
    if task.params:
        lines.append("    params:")
        for key, value in task.params.items():
            lines.append(f"        {key}={repr(value)},")

    # Resources
    if include_resources and _has_non_default_resources(task.resources):
        resource_lines = _generate_resource_spec(task.resources)
        if resource_lines:
            lines.extend(resource_lines)

    # Conda environment
    if include_conda and task.environment.conda:
        lines.append(f'    conda: "{task.environment.conda}"')

    # Container
    if include_containers and task.environment.container:
        # Convert different container formats
        container = task.environment.container
        if container.startswith("docker://"):
            container = container[9:]  # Remove docker:// prefix
        lines.append(f'    container: "{container}"')

    # SBOM / SIF provenance comments for reproducibility
    sbom_path = (
        task.environment.env_vars.get("WF2WF_SBOM") if task.environment else None
    )
    sif_path = task.environment.env_vars.get("WF2WF_SIF") if task.environment else None

    if sbom_path:
        lines.append(f'    # wf2wf_sbom: "{sbom_path}"')
    if sif_path:
        lines.append(f'    # wf2wf_sif: "{sif_path}"')

    # Priority (if non-zero)
    if task.priority != 0:
        lines.append(f"    priority: {task.priority}")

    # Retries (if non-zero)
    if task.retry > 0:
        lines.append(f"    retries: {task.retry}")

    # Script or shell command
    if task.script:
        # External script
        script_path = task.script
        if script_dir:
            # Copy script to scripts directory
            script_dir.mkdir(parents=True, exist_ok=True)
            script_dest = script_dir / Path(task.script).name
            # Note: In real implementation, you might want to copy the script file
            # Use forward slashes consistently for cross-platform compatibility
            script_path = str(script_dest.relative_to(script_dir.parent)).replace("\\", "/")

        lines.append(f'    script: "{script_path}"')

    elif task.command:
        # Shell command
        command = task.command

        # Handle multi-line commands
        if "\n" in command or len(command) > 80:
            lines.append('    shell: """')
            for cmd_line in command.split("\n"):
                lines.append(f"    {cmd_line}")
            lines.append('    """')
        else:
            lines.append(f'    shell: "{command}"')

    else:
        # No command specified - create a placeholder
        lines.append('    shell: "echo \\"Task {rule_name} completed\\""')

    return lines


def _has_non_default_resources(resources: ResourceSpec) -> bool:
    """Check if resource spec has non-default values."""

    return (
        resources.cpu != 1
        or resources.mem_mb > 0
        or resources.disk_mb > 0
        or resources.gpu > 0
        or resources.gpu_mem_mb > 0
        or resources.time_s > 0
        or resources.threads != 1
        or resources.extra
    )


def _generate_resource_spec(resources: ResourceSpec) -> List[str]:
    """Generate resources section for a Snakemake rule."""

    lines = ["    resources:"]

    if resources.cpu != 1:
        lines.append(f"        cpus={resources.cpu},")

    if resources.mem_mb > 0:
        # Convert MB to GB for readability if >= 1GB
        if resources.mem_mb >= 1024:
            mem_gb = resources.mem_mb / 1024
            if mem_gb == int(mem_gb):
                lines.append(f"        mem_gb={int(mem_gb)},")
            else:
                lines.append(f"        mem_gb={mem_gb:.1f},")
        else:
            lines.append(f"        mem_mb={resources.mem_mb},")

    if resources.disk_mb > 0:
        # Convert MB to GB for readability if >= 1GB
        if resources.disk_mb >= 1024:
            disk_gb = resources.disk_mb / 1024
            if disk_gb == int(disk_gb):
                lines.append(f"        disk_gb={int(disk_gb)},")
            else:
                lines.append(f"        disk_gb={disk_gb:.1f},")
        else:
            lines.append(f"        disk_mb={resources.disk_mb},")

    if resources.gpu > 0:
        lines.append(f"        gpu={resources.gpu},")

    if resources.time_s > 0:
        # Convert seconds to hours/minutes for readability
        if resources.time_s >= 3600:
            hours = resources.time_s / 3600
            lines.append(
                f"        runtime={int(hours * 60)},"
            )  # Snakemake uses minutes
        else:
            minutes = resources.time_s / 60
            lines.append(f"        runtime={int(minutes)},")

    if resources.threads != 1:
        lines.append(f"        threads={resources.threads},")

    # Add extra resources
    for key, value in resources.extra.items():
        lines.append(f"        {key}={repr(value)},")

    return lines if len(lines) > 1 else []


def _sanitize_rule_name(name: str) -> str:
    """Sanitize task ID to be a valid Snakemake rule name."""

    import re

    # Replace invalid characters with underscores
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)

    # Ensure it starts with a letter or underscore
    if sanitized and sanitized[0].isdigit():
        sanitized = f"rule_{sanitized}"

    # Ensure it's not empty
    if not sanitized:
        sanitized = "rule_unnamed"

    return sanitized


def _topological_sort(wf: Workflow) -> List[str]:
    """Return task IDs in topological order."""

    from collections import defaultdict, deque

    # Build adjacency list and in-degree count
    graph = defaultdict(list)
    in_degree = defaultdict(int)

    # Initialize all tasks with in-degree 0
    for task_id in wf.tasks:
        in_degree[task_id] = 0

    # Build graph from edges
    for edge in wf.edges:
        graph[edge.parent].append(edge.child)
        in_degree[edge.child] += 1

    # Kahn's algorithm
    queue = deque([task_id for task_id in wf.tasks if in_degree[task_id] == 0])
    result = []

    while queue:
        current = queue.popleft()
        result.append(current)

        for neighbor in graph[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Check for cycles
    if len(result) != len(wf.tasks):
        # Fallback to original order if cycle detected
        return list(wf.tasks.keys())

    return result
