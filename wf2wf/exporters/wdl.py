"""wf2wf.exporters.wdl – Workflow IR ➜ WDL

This module exports wf2wf intermediate representation workflows to
Workflow Description Language (WDL) format with feature preservation.

Features supported:
- WDL tasks and workflows
- Scatter operations
- Runtime specifications (cpu, memory, disk, docker)
- Input/output parameter specifications
- Meta and parameter_meta sections
"""

from pathlib import Path
from typing import Any, Dict

from wf2wf.core import Workflow, Task, ResourceSpec, EnvironmentSpec

# Loss mapping helpers
from wf2wf.loss import (
    reset as loss_reset,
    write as loss_write,
    record as loss_record,
    prepare as loss_prepare,
    as_list as loss_as_list,
    compute_checksum,
)


def from_workflow(wf: Workflow, out_file: str | Path, **opts: Any) -> None:
    """Export a wf2wf workflow to WDL format.

    Args:
        wf: The workflow to export
        out_file: Path for the output WDL workflow file
        **opts: Additional options:
            - wdl_version: str = "1.0" - WDL version to target
            - preserve_metadata: bool = True - Preserve metadata in meta sections
            - verbose: bool = False - Enable verbose output

    Raises:
        RuntimeError: If the workflow cannot be exported
    """
    # ------------------------------------------------------------------
    # Prepare loss handling
    # ------------------------------------------------------------------

    loss_prepare(wf.loss_map)
    loss_reset()

    output_path = Path(out_file).resolve()

    wdl_version = opts.get("wdl_version", "1.0")
    preserve_metadata = opts.get("preserve_metadata", True)
    verbose = opts.get("verbose", False)

    if verbose:
        print(f"Exporting workflow '{wf.name}' to WDL {wdl_version}")

    try:
        # Record unsupported features before generation

        if wf.intent:
            loss_record(
                "/intent", "intent", wf.intent, "WDL spec has no intent field", "user"
            )

        for task in wf.tasks.values():
            if task.when:
                loss_record(
                    f"/tasks/{task.id}/when",
                    "when",
                    task.when,
                    "Conditional when unsupported in WDL 1.0",
                    "user",
                )
            if task.resources.gpu or getattr(task.resources, "gpu_mem_mb", None):
                loss_record(
                    f"/tasks/{task.id}/resources/gpu",
                    "gpu",
                    task.resources.gpu,
                    "GPU resources not first-class in WDL runtime",
                    "user",
                )

        # Create output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate WDL content
        wdl_content = _generate_wdl_workflow(
            wf, wdl_version, preserve_metadata=preserve_metadata, verbose=verbose
        )

        # Write WDL file
        output_path.write_text(wdl_content)

        if verbose:
            print(f"WDL workflow exported to: {output_path}")

        try:
            from wf2wf import report as _rpt

            _rpt.add_artefact(output_path)
            _rpt.add_action("Exported WDL workflow")
        except ImportError:
            pass

        # Persist loss side-car and update workflow object
        loss_write(
            output_path.with_suffix(".loss.json"),
            target_engine="wdl",
            source_checksum=compute_checksum(wf),
        )
        wf.loss_map = loss_as_list()

    except Exception as e:
        raise RuntimeError(f"Failed to export WDL workflow: {e}")


def _generate_wdl_workflow(
    wf: Workflow,
    wdl_version: str,
    preserve_metadata: bool = True,
    verbose: bool = False,
) -> str:
    """Generate complete WDL workflow content."""

    lines = []

    # Add version declaration
    lines.append(f"version {wdl_version}")
    lines.append("")

    # Generate tasks
    for task in wf.tasks.values():
        task_wdl = _generate_wdl_task(task, preserve_metadata=preserve_metadata)
        lines.append(task_wdl)
        lines.append("")

    # Generate main workflow
    workflow_wdl = _generate_wdl_workflow_definition(
        wf, preserve_metadata=preserve_metadata
    )
    lines.append(workflow_wdl)

    return "\n".join(lines)


def _generate_wdl_task(task: Task, preserve_metadata: bool = True) -> str:
    """Generate WDL task definition."""

    lines = []
    lines.append(f"task {task.id} {{")

    # Add meta section if metadata preservation is enabled
    if preserve_metadata and (task.meta or task.label or task.doc):
        lines.append("    meta {")

        if task.label:
            lines.append(f'        description: "{task.label}"')
        elif task.doc:
            lines.append(f'        description: "{task.doc}"')

        # Add original WDL metadata if available
        if task.meta and "wdl_meta" in task.meta:
            for key, value in task.meta["wdl_meta"].items():
                if key != "description":  # Already handled above
                    lines.append(f'        {key}: "{value}"')

        lines.append("    }")
        lines.append("")

    # Add parameter_meta section if available
    if preserve_metadata and task.meta and "wdl_parameter_meta" in task.meta:
        param_meta = task.meta["wdl_parameter_meta"]
        if param_meta:
            lines.append("    parameter_meta {")
            for key, value in param_meta.items():
                lines.append(f'        {key}: "{value}"')
            lines.append("    }")
            lines.append("")

    # Add input section
    if task.inputs:
        lines.append("    input {")
        for param in task.inputs:
            wdl_type = _convert_ir_type_to_wdl(param.type)
            if param.default is not None:
                lines.append(
                    f"        {wdl_type} {param.id} = {_format_wdl_value(param.default)}"
                )
            else:
                lines.append(f"        {wdl_type} {param.id}")
        lines.append("    }")
        lines.append("")

    # Add command section
    if task.command:
        lines.append("    command <<<")
        # Simple command formatting - could be enhanced for variable substitution
        command_lines = task.command.strip().split("\n")
        for cmd_line in command_lines:
            lines.append(f"        {cmd_line}")
        lines.append("    >>>")
        lines.append("")

    # Add output section
    if task.outputs:
        lines.append("    output {")
        for param in task.outputs:
            wdl_type = _convert_ir_type_to_wdl(param.type)
            # Simple output mapping - could be enhanced
            lines.append(f"        {wdl_type} {param.id} = stdout()")
        lines.append("    }")
        lines.append("")

    # Add runtime section
    runtime_spec = _generate_wdl_runtime(task.resources, task.environment)
    if runtime_spec:
        lines.append("    runtime {")
        for key, value in runtime_spec.items():
            lines.append(f'        {key}: "{value}"')
        lines.append("    }")

    lines.append("}")

    return "\n".join(lines)


def _generate_wdl_workflow_definition(
    wf: Workflow, preserve_metadata: bool = True
) -> str:
    """Generate WDL workflow definition."""

    lines = []
    lines.append(f"workflow {wf.name} {{")

    # Add meta section
    if preserve_metadata and (wf.meta or wf.label or wf.doc):
        lines.append("    meta {")

        if wf.label:
            lines.append(f'        description: "{wf.label}"')
        elif wf.doc:
            lines.append(f'        description: "{wf.doc}"')

        if wf.version:
            lines.append(f'        version: "{wf.version}"')

        # Add original WDL metadata if available
        if wf.meta and "original_wdl_doc" in wf.meta:
            original_meta = wf.meta["original_wdl_doc"].get("workflows", {})
            if original_meta:
                first_workflow = list(original_meta.values())[0]
                for key, value in first_workflow.get("meta", {}).items():
                    if key not in ["description", "version"]:
                        lines.append(f'        {key}: "{value}"')

        lines.append("    }")
        lines.append("")

    # Add input section
    if wf.inputs:
        lines.append("    input {")
        for param in wf.inputs:
            wdl_type = _convert_ir_type_to_wdl(param.type)
            if param.default is not None:
                lines.append(
                    f"        {wdl_type} {param.id} = {_format_wdl_value(param.default)}"
                )
            else:
                lines.append(f"        {wdl_type} {param.id}")
        lines.append("    }")
        lines.append("")

    # Add call statements
    for task in wf.tasks.values():
        if task.scatter:
            # Generate scatter call
            scatter_var = task.scatter.scatter[0] if task.scatter.scatter else "items"
            lines.append(f"    scatter ({task.id}_item in {scatter_var}) {{")
            lines.append(f"        call {task.id} {{")
            lines.append("            input:")
            # Add input mappings - simplified
            for param in task.inputs:
                lines.append(f"                {param.id} = {task.id}_item")
            lines.append("        }")
            lines.append("    }")
        else:
            # Generate regular call
            lines.append(f"    call {task.id}")
            if task.inputs and any(param.default is None for param in task.inputs):
                lines.append("    {")
                lines.append("        input:")
                # Add input mappings - simplified
                for param in task.inputs:
                    if param.default is None:
                        lines.append(f"            {param.id} = {param.id}")
                lines.append("    }")
        lines.append("")

    # Add output section
    if wf.outputs:
        lines.append("    output {")
        for param in wf.outputs:
            wdl_type = _convert_ir_type_to_wdl(param.type)
            # Simple output mapping - find task that produces this output
            producing_task = None
            for task in wf.tasks.values():
                if any(out.id == param.id for out in task.outputs):
                    producing_task = task.id
                    break

            if producing_task:
                lines.append(
                    f"        {wdl_type} {param.id} = {producing_task}.{param.id}"
                )
            else:
                lines.append(f"        {wdl_type} {param.id} = {param.id}")
        lines.append("    }")

    lines.append("}")

    return "\n".join(lines)


def _convert_ir_type_to_wdl(ir_type: str) -> str:
    """Convert IR type to WDL type."""

    # Handle union types (remove from IR type)
    if isinstance(ir_type, dict):
        # Complex type spec - use string representation
        ir_type = str(ir_type)

    ir_type = str(ir_type)

    # Basic type mapping
    type_mapping = {
        "string": "String",
        "int": "Int",
        "float": "Float",
        "boolean": "Boolean",
        "File": "File",
        "Directory": "Directory",
    }

    # Handle optional types (type?)
    if ir_type.endswith("?"):
        base_type = ir_type[:-1]
        mapped_type = type_mapping.get(base_type, base_type)
        return f"{mapped_type}?"

    # Handle array types
    if ir_type.startswith("array<") and ir_type.endswith(">"):
        item_type = ir_type[6:-1]  # Remove 'array<' and '>'
        mapped_item_type = _convert_ir_type_to_wdl(item_type)
        return f"Array[{mapped_item_type}]"

    return type_mapping.get(ir_type, "String")


def _generate_wdl_runtime(
    resources: ResourceSpec, environment: EnvironmentSpec
) -> Dict[str, str]:
    """Generate WDL runtime specification."""

    runtime = {}

    # Add CPU specification
    if resources.cpu > 1:
        runtime["cpu"] = str(resources.cpu)

    # Add memory specification
    if resources.mem_mb > 0:
        if resources.mem_mb >= 1024:
            memory_gb = resources.mem_mb / 1024
            runtime["memory"] = f"{memory_gb:.1f} GB"
        else:
            runtime["memory"] = f"{resources.mem_mb} MB"

    # Add disk specification
    if resources.disk_mb > 0:
        disk_gb = resources.disk_mb / 1024
        runtime["disks"] = f"local-disk {disk_gb:.0f} HDD"

    # Add GPU specification (if supported)
    if resources.gpu > 0:
        runtime["gpu"] = str(resources.gpu)

    # Add Docker/SIF container
    if environment.container:
        container = environment.container
        if container.startswith("docker://"):
            container = container[9:]  # Remove 'docker://' prefix
        runtime["docker"] = container

    # SBOM/SIF extra
    sbom_path = environment.env_vars.get("WF2WF_SBOM") if environment else None
    sif_path = environment.env_vars.get("WF2WF_SIF") if environment else None
    if sbom_path:
        runtime["wf2wf_sbom"] = sbom_path
    if sif_path:
        runtime["wf2wf_sif"] = sif_path

    return runtime


def _format_wdl_value(value: Any) -> str:
    """Format a value for WDL syntax."""

    if isinstance(value, str):
        return f'"{value}"'
    elif isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, list):
        formatted_items = [_format_wdl_value(item) for item in value]
        return f"[{', '.join(formatted_items)}]"
    elif isinstance(value, dict):
        # WDL doesn't have native dict syntax, convert to string
        return f'"{str(value)}"'
    else:
        return f'"{str(value)}"'
