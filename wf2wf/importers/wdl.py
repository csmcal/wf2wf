"""wf2wf.importers.wdl – WDL ➜ Workflow IR

This module imports Workflow Description Language (WDL) workflows and converts
them to the wf2wf intermediate representation with feature preservation.

Features supported:
- WDL tasks and workflows
- Scatter operations with collection types
- Runtime specifications (cpu, memory, disk, docker)
- Input/output parameter specifications
- Meta and parameter_meta sections
- Call dependencies and workflow structure
"""

import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from wf2wf.core import (
    Workflow,
    Task,
    Edge,
    ResourceSpec,
    EnvironmentSpec,
    ParameterSpec,
    ScatterSpec,
    ProvenanceSpec,
    DocumentationSpec,
)


def to_workflow(path: str | Path, **opts: Any) -> Workflow:
    """Import a WDL workflow file and convert to wf2wf IR.

    Args:
        path: Path to the WDL workflow file (.wdl)
        **opts: Additional options:
            - preserve_metadata: bool = True - Preserve WDL metadata
            - verbose: bool = False - Enable verbose output
            - debug: bool = False - Enable debug output

    Returns:
        Workflow: The converted workflow in wf2wf IR format

    Raises:
        RuntimeError: If the WDL file cannot be parsed or converted
        FileNotFoundError: If the WDL file doesn't exist
    """
    wdl_path = Path(path).resolve()
    if not wdl_path.exists():
        raise FileNotFoundError(f"WDL file not found: {wdl_path}")

    preserve_metadata = opts.get("preserve_metadata", True)
    verbose = opts.get("verbose", False)
    debug = opts.get("debug", False)

    if verbose:
        print(f"Importing WDL workflow: {wdl_path}")

    try:
        # Parse WDL document
        wdl_content = wdl_path.read_text()
        wdl_doc = _parse_wdl_document(wdl_content, wdl_path, debug=debug)

        # Basic sanity check: must contain at least one workflow or task
        if not wdl_doc.get("workflows"):
            raise RuntimeError("Invalid or unsupported WDL content")

        # Convert to workflow IR
        workflow = _convert_wdl_to_workflow(
            wdl_doc,
            wdl_path,
            preserve_metadata=preserve_metadata,
            verbose=verbose,
            debug=debug,
        )

        if verbose:
            print(
                f"Successfully imported WDL workflow with {len(workflow.tasks)} tasks"
            )

        return workflow

    except Exception as e:
        if debug:
            import traceback

            traceback.print_exc()
        raise RuntimeError(f"Failed to import WDL workflow: {e}")


def _parse_wdl_document(
    content: str, wdl_path: Path, debug: bool = False
) -> Dict[str, Any]:
    """Parse WDL document content into structured data."""

    # Simple WDL parser - this could be enhanced with a proper WDL parser library
    doc = {"version": None, "imports": [], "tasks": {}, "workflows": {}, "structs": {}}

    # Extract version
    version_match = re.search(r"version\s+([\d.]+)", content, re.IGNORECASE)
    if version_match:
        doc["version"] = version_match.group(1)

    # Extract imports
    import_matches = re.finditer(
        r'import\s+"([^"]+)"(?:\s+as\s+(\w+))?', content, re.IGNORECASE
    )
    for match in import_matches:
        doc["imports"].append({"path": match.group(1), "alias": match.group(2)})

    # Extract tasks using balanced brace matching
    task_starts = re.finditer(r"task\s+(\w+)\s*\{", content)
    for match in task_starts:
        task_name = match.group(1)
        task_body = _extract_balanced_braces(content, match.end() - 1)
        doc["tasks"][task_name] = _parse_wdl_task(task_body, task_name, debug=debug)

    # Extract workflows using balanced brace matching
    workflow_starts = re.finditer(r"workflow\s+(\w+)\s*\{", content)
    for match in workflow_starts:
        workflow_name = match.group(1)
        workflow_body = _extract_balanced_braces(content, match.end() - 1)
        doc["workflows"][workflow_name] = _parse_wdl_workflow(
            workflow_body, workflow_name, debug=debug
        )

    return doc


def _extract_balanced_braces(text: str, start_pos: int) -> str:
    """Extract content within balanced braces starting from start_pos."""
    brace_count = 0
    i = start_pos
    while i < len(text):
        if text[i] == "{":
            brace_count += 1
        elif text[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                return text[start_pos + 1 : i]
        i += 1
    return ""


def _parse_wdl_task(
    task_body: str, task_name: str, debug: bool = False
) -> Dict[str, Any]:
    """Parse a WDL task definition."""

    task = {
        "name": task_name,
        "inputs": {},
        "outputs": {},
        "command": "",
        "runtime": {},
        "meta": {},
        "parameter_meta": {},
    }

    # Extract input section
    input_match = re.search(r"input\s*\{([^}]*)\}", task_body, re.DOTALL)
    if input_match:
        task["inputs"] = _parse_wdl_parameters(input_match.group(1), "input")

    # Extract output section
    output_match = re.search(r"output\s*\{([^}]*)\}", task_body, re.DOTALL)
    if output_match:
        task["outputs"] = _parse_wdl_parameters(output_match.group(1), "output")

    # Extract command section
    command_match = re.search(
        r"command\s*(?:<<<|{)([^}]*?)(?:>>>|})", task_body, re.DOTALL
    )
    if command_match:
        task["command"] = command_match.group(1).strip()

    # Extract runtime section
    runtime_match = re.search(r"runtime\s*\{([^}]*)\}", task_body, re.DOTALL)
    if runtime_match:
        task["runtime"] = _parse_wdl_runtime(runtime_match.group(1))

    # Extract meta section
    meta_match = re.search(r"meta\s*\{([^}]*)\}", task_body, re.DOTALL)
    if meta_match:
        task["meta"] = _parse_wdl_meta(meta_match.group(1))

    # Extract parameter_meta section
    param_meta_match = re.search(r"parameter_meta\s*\{([^}]*)\}", task_body, re.DOTALL)
    if param_meta_match:
        task["parameter_meta"] = _parse_wdl_meta(param_meta_match.group(1))

    return task


def _parse_wdl_workflow(
    workflow_body: str, workflow_name: str, debug: bool = False
) -> Dict[str, Any]:
    """Parse a WDL workflow definition."""

    workflow = {
        "name": workflow_name,
        "inputs": {},
        "outputs": {},
        "calls": [],
        "meta": {},
        "parameter_meta": {},
    }

    # Extract input section
    input_match = re.search(r"input\s*\{([^}]*)\}", workflow_body, re.DOTALL)
    if input_match:
        workflow["inputs"] = _parse_wdl_parameters(input_match.group(1), "input")

    # Extract output section
    output_match = re.search(r"output\s*\{([^}]*)\}", workflow_body, re.DOTALL)
    if output_match:
        workflow["outputs"] = _parse_wdl_parameters(output_match.group(1), "output")

    # Extract call statements
    call_pattern = r"call\s+(\w+)(?:\s+as\s+(\w+))?(?:\s*\{([^}]*)\})?"
    call_matches = re.finditer(call_pattern, workflow_body, re.DOTALL)

    for match in call_matches:
        call = {
            "task": match.group(1),
            "alias": match.group(2) or match.group(1),
            "inputs": {},
        }

        if match.group(3):  # Call has input block
            call["inputs"] = _parse_wdl_call_inputs(match.group(3))

        workflow["calls"].append(call)

    # Extract scatter statements
    scatter_pattern = r"scatter\s*\(([^)]+)\)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}"
    scatter_matches = re.finditer(scatter_pattern, workflow_body, re.DOTALL)

    for match in scatter_matches:
        scatter_expr = match.group(1).strip()
        scatter_body = match.group(2)

        # Parse scatter calls within the scatter block
        scatter_calls = []
        scatter_call_matches = re.finditer(call_pattern, scatter_body, re.DOTALL)

        for call_match in scatter_call_matches:
            call = {
                "task": call_match.group(1),
                "alias": call_match.group(2) or call_match.group(1),
                "inputs": {},
                "scatter": scatter_expr,
            }

            if call_match.group(3):
                call["inputs"] = _parse_wdl_call_inputs(call_match.group(3))

            scatter_calls.append(call)

        workflow["calls"].extend(scatter_calls)

    # Extract meta sections
    meta_match = re.search(r"meta\s*\{([^}]*)\}", workflow_body, re.DOTALL)
    if meta_match:
        workflow["meta"] = _parse_wdl_meta(meta_match.group(1))

    param_meta_match = re.search(
        r"parameter_meta\s*\{([^}]*)\}", workflow_body, re.DOTALL
    )
    if param_meta_match:
        workflow["parameter_meta"] = _parse_wdl_meta(param_meta_match.group(1))

    return workflow


def _parse_wdl_parameters(params_text: str, param_type: str) -> Dict[str, Any]:
    """Parse WDL input/output parameter declarations."""

    parameters = {}

    # Simple parameter parsing - could be enhanced for complex types
    param_lines = [line.strip() for line in params_text.split("\n") if line.strip()]

    for line in param_lines:
        # Skip comments
        if line.startswith("#"):
            continue

        # Parse parameter declaration: Type name = default_value
        param_match = re.match(
            r"(\w+(?:\[.*?\])?(?:\?)?)\s+(\w+)(?:\s*=\s*(.+))?", line
        )
        if param_match:
            param_type_str = param_match.group(1)
            param_name = param_match.group(2)
            param_default = param_match.group(3)

            parameters[param_name] = {
                "type": param_type_str,
                "default": param_default.strip() if param_default else None,
            }

    return parameters


def _parse_wdl_runtime(runtime_text: str) -> Dict[str, Any]:
    """Parse WDL runtime section."""

    runtime = {}

    # Parse key-value pairs in runtime section
    runtime_lines = [line.strip() for line in runtime_text.split("\n") if line.strip()]

    for line in runtime_lines:
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            runtime[key] = value

    return runtime


def _parse_wdl_meta(meta_text: str) -> Dict[str, Any]:
    """Parse WDL meta or parameter_meta section."""

    meta = {}

    # Parse key-value pairs in meta section
    meta_lines = [line.strip() for line in meta_text.split("\n") if line.strip()]

    for line in meta_lines:
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip("\"'")

            # Try to parse as JSON if it looks like structured data
            try:
                if value.startswith("{") or value.startswith("["):
                    value = json.loads(value)
            except json.JSONDecodeError:
                pass  # Keep as string

            meta[key] = value

    return meta


def _parse_wdl_call_inputs(inputs_text: str) -> Dict[str, str]:
    """Parse WDL call input assignments."""

    inputs = {}

    # Remove the "input:" prefix if present and split by commas
    cleaned_text = inputs_text.strip()
    if cleaned_text.startswith("input:"):
        cleaned_text = cleaned_text[6:].strip()

    # Split by commas and parse each assignment
    input_assignments = [
        line.strip()
        for line in cleaned_text.replace("\n", ",").split(",")
        if line.strip()
    ]

    for assignment in input_assignments:
        if "=" in assignment:
            key, value = assignment.split("=", 1)
            inputs[key.strip()] = value.strip()

    return inputs


def _convert_wdl_to_workflow(
    wdl_doc: Dict[str, Any],
    wdl_path: Path,
    preserve_metadata: bool = True,
    verbose: bool = False,
    debug: bool = False,
) -> Workflow:
    """Convert parsed WDL document to wf2wf Workflow IR."""

    # Find the main workflow (use first workflow if multiple exist)
    main_workflow = None
    if wdl_doc["workflows"]:
        main_workflow_name = list(wdl_doc["workflows"].keys())[0]
        main_workflow = wdl_doc["workflows"][main_workflow_name]
    else:
        # If no workflow, create one from tasks
        main_workflow_name = wdl_path.stem
        main_workflow = {
            "name": main_workflow_name,
            "inputs": {},
            "outputs": {},
            "calls": [],
            "meta": {},
            "parameter_meta": {},
        }

        # Add all tasks as calls
        for task_name in wdl_doc["tasks"].keys():
            main_workflow["calls"].append(
                {"task": task_name, "alias": task_name, "inputs": {}}
            )

    # Create workflow IR
    workflow = Workflow(
        name=main_workflow["name"],
        version="1.0",
        label=main_workflow["name"],
        doc=main_workflow.get("meta", {}).get("description", ""),
    )

    # Store WDL metadata
    if preserve_metadata:
        workflow.meta = {
            "source_format": "wdl",
            "wdl_version": wdl_doc.get("version", "1.0"),
            "original_wdl_doc": wdl_doc if preserve_metadata else {},
        }

        # Extract provenance from meta
        if main_workflow.get("meta"):
            workflow.provenance = _extract_wdl_provenance(main_workflow["meta"])

        # Extract documentation
        if main_workflow.get("meta") or main_workflow.get("parameter_meta"):
            workflow.documentation = _extract_wdl_documentation(
                main_workflow.get("meta", {}), main_workflow.get("parameter_meta", {})
            )

    # Convert workflow inputs
    workflow.inputs = _convert_wdl_inputs(main_workflow.get("inputs", {}))

    # Convert workflow outputs
    workflow.outputs = _convert_wdl_outputs(main_workflow.get("outputs", {}))

    # Convert calls to tasks and edges
    tasks = {}
    edges = []

    for call in main_workflow.get("calls", []):
        task_name = call["task"]
        call_alias = call["alias"]

        if task_name not in wdl_doc["tasks"]:
            if verbose:
                print(f"Warning: Task '{task_name}' not found in WDL document")
            continue

        wdl_task = wdl_doc["tasks"][task_name]

        # Convert WDL task to IR task
        task = _convert_wdl_task_to_ir(
            wdl_task,
            call_alias,
            call,
            preserve_metadata=preserve_metadata,
            verbose=verbose,
        )

        tasks[call_alias] = task

        # Extract dependencies from call inputs
        task_edges = _extract_wdl_dependencies(call, call_alias, main_workflow["calls"])
        edges.extend(task_edges)

    # Add tasks and edges to workflow
    for task in tasks.values():
        workflow.add_task(task)

    for edge in edges:
        try:
            workflow.add_edge(edge.parent, edge.child)
        except KeyError as e:
            if verbose:
                print(f"Warning: Could not add edge {edge.parent} -> {edge.child}: {e}")

    return workflow


def _convert_wdl_task_to_ir(
    wdl_task: Dict[str, Any],
    task_id: str,
    call: Dict[str, Any],
    preserve_metadata: bool = True,
    verbose: bool = False,
) -> Task:
    """Convert a WDL task to IR Task."""

    task = Task(
        id=task_id,
        label=wdl_task.get("meta", {}).get("description", task_id),
        doc=wdl_task.get("meta", {}).get("description", ""),
        command=wdl_task.get("command", ""),
    )

    # Convert inputs
    task.inputs = _convert_wdl_task_inputs(wdl_task.get("inputs", {}))

    # Convert outputs
    task.outputs = _convert_wdl_task_outputs(wdl_task.get("outputs", {}))

    # Convert runtime to resources
    task.resources = _convert_wdl_runtime_to_resources(wdl_task.get("runtime", {}))

    # Convert runtime to environment
    task.environment = _convert_wdl_runtime_to_environment(wdl_task.get("runtime", {}))

    # Handle scatter operations
    if call.get("scatter"):
        task.scatter = _convert_wdl_scatter(call["scatter"])

    # Store WDL metadata
    if preserve_metadata:
        task.meta = {
            "wdl_task": wdl_task.get("name", task_id),
            "wdl_meta": wdl_task.get("meta", {}),
            "wdl_parameter_meta": wdl_task.get("parameter_meta", {}),
            "wdl_runtime": wdl_task.get("runtime", {}),
            "call_inputs": call.get("inputs", {}),
        }

        # Extract provenance
        if wdl_task.get("meta"):
            task.provenance = _extract_wdl_provenance(wdl_task["meta"])

        # Extract documentation
        if wdl_task.get("meta") or wdl_task.get("parameter_meta"):
            task.documentation = _extract_wdl_documentation(
                wdl_task.get("meta", {}), wdl_task.get("parameter_meta", {})
            )

    return task


def _convert_wdl_inputs(wdl_inputs: Dict[str, Any]) -> List[ParameterSpec]:
    """Convert WDL workflow inputs to IR parameter specs."""

    inputs = []

    for param_name, param_def in wdl_inputs.items():
        default_val = param_def.get("default")
        if (
            isinstance(default_val, str)
            and len(default_val) >= 2
            and (
                (default_val.startswith('"') and default_val.endswith('"'))
                or (default_val.startswith("'") and default_val.endswith("'"))
            )
        ):
            default_val = default_val[1:-1]
        param_spec = ParameterSpec(
            id=param_name,
            type=_convert_wdl_type(param_def.get("type", "String")),
            default=default_val,
        )
        inputs.append(param_spec)

    return inputs


def _convert_wdl_outputs(wdl_outputs: Dict[str, Any]) -> List[ParameterSpec]:
    """Convert WDL workflow outputs to IR parameter specs."""

    outputs = []

    for param_name, param_def in wdl_outputs.items():
        param_spec = ParameterSpec(
            id=param_name, type=_convert_wdl_type(param_def.get("type", "String"))
        )
        outputs.append(param_spec)

    return outputs


def _convert_wdl_task_inputs(wdl_inputs: Dict[str, Any]) -> List[ParameterSpec]:
    """Convert WDL task inputs to IR parameter specs."""

    inputs = []

    for param_name, param_def in wdl_inputs.items():
        default_val = param_def.get("default")
        if (
            isinstance(default_val, str)
            and len(default_val) >= 2
            and (
                (default_val.startswith('"') and default_val.endswith('"'))
                or (default_val.startswith("'") and default_val.endswith("'"))
            )
        ):
            default_val = default_val[1:-1]
        param_spec = ParameterSpec(
            id=param_name,
            type=_convert_wdl_type(param_def.get("type", "String")),
            default=default_val,
        )
        inputs.append(param_spec)

    return inputs


def _convert_wdl_task_outputs(wdl_outputs: Dict[str, Any]) -> List[ParameterSpec]:
    """Convert WDL task outputs to IR parameter specs."""

    outputs = []

    for param_name, param_def in wdl_outputs.items():
        param_spec = ParameterSpec(
            id=param_name, type=_convert_wdl_type(param_def.get("type", "String"))
        )
        outputs.append(param_spec)

    return outputs


def _convert_wdl_type(wdl_type: str) -> str:
    """Convert WDL type to IR type."""

    # Basic type mapping
    type_mapping = {
        "String": "string",
        "Int": "int",
        "Float": "float",
        "Boolean": "boolean",
        "File": "File",
        "Directory": "Directory",
    }

    # Handle optional types (Type?)
    if wdl_type.endswith("?"):
        base_type = wdl_type[:-1]
        mapped_type = type_mapping.get(base_type, base_type)
        return f"{mapped_type}?"

    # Handle array types (Array[Type])
    array_match = re.match(r"Array\[(.+)\]", wdl_type)
    if array_match:
        item_type = _convert_wdl_type(array_match.group(1))
        return f"array<{item_type}>"

    return type_mapping.get(wdl_type, wdl_type)


def _convert_wdl_runtime_to_resources(runtime: Dict[str, Any]) -> ResourceSpec:
    """Convert WDL runtime to IR resource spec."""

    resources = ResourceSpec()

    # Parse CPU
    if "cpu" in runtime:
        try:
            resources.cpu = int(runtime["cpu"])
        except (ValueError, TypeError):
            pass

    # Parse memory
    if "memory" in runtime:
        memory_str = str(runtime["memory"])
        memory_mb = _parse_memory_string(memory_str)
        if memory_mb:
            resources.mem_mb = memory_mb

    # Parse disk
    if "disks" in runtime:
        disk_str = str(runtime["disks"])
        disk_mb = _parse_disk_string(disk_str)
        if disk_mb:
            resources.disk_mb = disk_mb

    # Parse GPU (if specified)
    if "gpu" in runtime:
        try:
            resources.gpu = int(runtime["gpu"])
        except (ValueError, TypeError):
            pass

    return resources


def _convert_wdl_runtime_to_environment(runtime: Dict[str, Any]) -> EnvironmentSpec:
    """Convert WDL runtime to IR environment spec."""

    env = EnvironmentSpec()

    # Parse Docker container
    if "docker" in runtime:
        env.container = f"docker://{runtime['docker']}"

    # Parse environment variables (if any)
    if "env" in runtime:
        if isinstance(runtime["env"], dict):
            env.env_vars = runtime["env"]

    return env


def _convert_wdl_scatter(scatter_expr: str) -> ScatterSpec:
    """Convert WDL scatter expression to IR scatter spec."""

    # Parse scatter expression: "item in collection"
    scatter_match = re.match(r"(\w+)\s+in\s+(\w+)", scatter_expr.strip())
    if scatter_match:
        scatter_match.group(1)
        collection_var = scatter_match.group(2)

        return ScatterSpec(scatter=[collection_var], scatter_method="dotproduct")

    # Fallback for more complex expressions
    return ScatterSpec(scatter=[scatter_expr], scatter_method="dotproduct")


def _parse_memory_string(memory_str: str) -> Optional[int]:
    """Parse memory string like '4 GB' to MB."""

    memory_str = memory_str.strip().replace('"', "").replace("'", "")

    # Extract number and unit
    match = re.match(r"(\d+(?:\.\d+)?)\s*([KMGT]?B?)", memory_str, re.IGNORECASE)
    if not match:
        return None

    amount = float(match.group(1))
    unit = match.group(2).upper()

    # Convert to MB
    if unit in ["", "B"]:
        return int(amount / (1024 * 1024))
    elif unit in ["KB", "K"]:
        return int(amount / 1024)
    elif unit in ["MB", "M"]:
        return int(amount)
    elif unit in ["GB", "G"]:
        return int(amount * 1024)
    elif unit in ["TB", "T"]:
        return int(amount * 1024 * 1024)

    return None


def _parse_disk_string(disk_str: str) -> Optional[int]:
    """Parse disk string like 'local-disk 100 HDD' to MB."""

    # WDL disk format: "local-disk size_gb disk_type"
    disk_parts = disk_str.strip().split()
    if len(disk_parts) >= 2:
        try:
            size_gb = float(disk_parts[1])
            return int(size_gb * 1024)  # Convert GB to MB
        except (ValueError, IndexError):
            pass

    return None


def _extract_wdl_dependencies(
    call: Dict[str, Any], call_alias: str, all_calls: List[Dict[str, Any]]
) -> List[Edge]:
    """Extract dependencies from WDL call inputs."""

    edges = []

    # Look for references to other call outputs in inputs
    for input_name, input_value in call.get("inputs", {}).items():
        # Check if input references another call's output
        for other_call in all_calls:
            other_alias = other_call["alias"]
            if other_alias != call_alias and other_alias in input_value:
                edges.append(Edge(parent=other_alias, child=call_alias))

    return edges


def _extract_wdl_provenance(meta: Dict[str, Any]) -> Optional[ProvenanceSpec]:
    """Extract provenance information from WDL meta section."""

    provenance = ProvenanceSpec()

    if "author" in meta:
        provenance.authors = [{"name": meta["author"]}]

    if "version" in meta:
        provenance.version = str(meta["version"])

    if "description" in meta:
        provenance.keywords = [meta["description"]]

    # Return None if no provenance data found
    if not any([provenance.authors, provenance.version, provenance.keywords]):
        return None

    return provenance


def _extract_wdl_documentation(
    meta: Dict[str, Any], parameter_meta: Dict[str, Any]
) -> Optional[DocumentationSpec]:
    """Extract documentation from WDL meta sections."""

    doc = DocumentationSpec()

    if "description" in meta:
        doc.description = meta["description"]
        doc.doc = meta["description"]

    if "usage" in meta:
        doc.usage_notes = meta["usage"]

    # Return None if no documentation found
    if not any([doc.description, doc.doc, doc.usage_notes]):
        return None

    return doc
