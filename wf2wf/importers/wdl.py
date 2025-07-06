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

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from wf2wf.core import (
    Workflow,
    Task,
    Edge,
    EnvironmentSpecificValue,
    ParameterSpec,
    ScatterSpec,
    ProvenanceSpec,
    DocumentationSpec,
    CheckpointSpec,
    LoggingSpec,
    SecuritySpec,
    NetworkingSpec,
    MetadataSpec,
)
from wf2wf.importers.base import BaseImporter


class WDLImporter(BaseImporter):
    """WDL importer using shared base infrastructure."""
    
    def _parse_source(self, path: Path, **opts: Any) -> Dict[str, Any]:
        """Parse WDL file and extract all information."""
        preserve_metadata = opts.get("preserve_metadata", True)
        debug = opts.get("debug", False)
        verbose = self.verbose

        if verbose:
            print(f"Parsing WDL file: {path}")

        # Parse WDL document
        wdl_content = path.read_text()
        wdl_doc = _parse_wdl_document(wdl_content, path, debug=debug)

        # Basic sanity check: must contain at least one workflow or task
        if not wdl_doc.get("workflows") and not wdl_doc.get("tasks"):
            raise RuntimeError("Invalid or unsupported WDL content")

        return {
            "wdl_doc": wdl_doc,
            "wdl_path": path,
            "preserve_metadata": preserve_metadata,
            "debug": debug,
        }
    
    def _create_basic_workflow(self, parsed_data: Dict[str, Any]) -> Workflow:
        """Create basic workflow from parsed WDL data."""
        wdl_doc = parsed_data["wdl_doc"]
        wdl_path = parsed_data["wdl_path"]
        preserve_metadata = parsed_data["preserve_metadata"]
        
        # Get workflow name from first workflow or use filename
        workflows = wdl_doc.get("workflows", {})
        if workflows:
            workflow_name = list(workflows.keys())[0]
        else:
            workflow_name = wdl_path.stem
        
        # Create workflow with WDL-specific execution model
        workflow = Workflow(
            name=workflow_name,
            version=wdl_doc.get("version", "1.0"),
            execution_model=EnvironmentSpecificValue("shared_filesystem", ["shared_filesystem"]),
        )
        
        # Add metadata
        if preserve_metadata:
            workflow.metadata = MetadataSpec(
                source_format="wdl",
                source_file=str(wdl_path),
                source_version=wdl_doc.get("version", "1.0"),
                format_specific={"wdl_document": wdl_doc},
            )
        
        return workflow
    
    def _extract_tasks(self, parsed_data: Dict[str, Any]) -> List[Task]:
        """Extract tasks from parsed WDL data."""
        wdl_doc = parsed_data["wdl_doc"]
        wdl_path = parsed_data["wdl_path"]
        preserve_metadata = parsed_data["preserve_metadata"]
        verbose = self.verbose
        
        tasks = []
        
        # Convert WDL tasks to IR tasks
        for task_name, wdl_task in wdl_doc.get("tasks", {}).items():
            task = _convert_wdl_task_to_ir(
                wdl_task, task_name, {}, preserve_metadata=preserve_metadata, verbose=verbose
            )
            tasks.append(task)
        
        # Convert workflow calls to tasks
        workflows = wdl_doc.get("workflows", {})
        for workflow_name, workflow_def in workflows.items():
            calls = workflow_def.get("calls", {})
            for call_name, call_def in calls.items():
                task_id = f"{workflow_name}.{call_name}"
                
                # Find the task definition
                task_def = wdl_doc.get("tasks", {}).get(call_name, {})
                
                task = _convert_wdl_task_to_ir(
                    task_def, task_id, call_def, preserve_metadata=preserve_metadata, verbose=verbose
                )
                tasks.append(task)
        
        return tasks
    
    def _extract_edges(self, parsed_data: Dict[str, Any]) -> List[Edge]:
        """Extract edges from parsed WDL data."""
        wdl_doc = parsed_data["wdl_doc"]
        edges = []
        
        # Extract dependencies from workflow calls
        workflows = wdl_doc.get("workflows", {})
        for workflow_name, workflow_def in workflows.items():
            calls = workflow_def.get("calls", {})
            all_calls = list(calls.items())
            
            for call_name, call_def in calls.items():
                call_edges = _extract_wdl_dependencies(call_def, call_name, all_calls)
                # Update edge parent/child to include workflow name
                for edge in call_edges:
                    edge.parent = f"{workflow_name}.{edge.parent}"
                    edge.child = f"{workflow_name}.{edge.child}"
                edges.extend(call_edges)
        
        return edges
    
    def _get_source_format(self) -> str:
        """Get the source format name."""
        return "wdl"


def to_workflow(path: Union[str, Path], **opts: Any) -> Workflow:
    """Convert WDL file at *path* into a Workflow IR object using shared infrastructure.

    Parameters
    ----------
    path : Union[str, Path]
        Path to the .wdl file.
    preserve_metadata : bool, optional
        Preserve WDL metadata (default: True).
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
    importer = WDLImporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False)
    )
    return importer.import_workflow(path, **opts)


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
        "calls": {},
        "scatter": {},
        "if": {},
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
    call_matches = re.finditer(r"call\s+(\w+)(?:\s+as\s+(\w+))?\s*\{([^}]*)\}", workflow_body, re.DOTALL)
    for match in call_matches:
        task_name = match.group(1)
        call_alias = match.group(2) or task_name
        call_inputs = match.group(3)
        
        workflow["calls"][call_alias] = {
            "task": task_name,
            "inputs": _parse_wdl_call_inputs(call_inputs),
        }

    # Extract scatter statements
    scatter_matches = re.finditer(r"scatter\s*\(([^)]+)\)\s*in\s*\{([^}]*)\}", workflow_body, re.DOTALL)
    for match in scatter_matches:
        scatter_expr = match.group(1)
        scatter_body = match.group(2)
        
        # Parse calls within scatter
        scatter_calls = {}
        call_matches = re.finditer(r"call\s+(\w+)(?:\s+as\s+(\w+))?\s*\{([^}]*)\}", scatter_body, re.DOTALL)
        for call_match in call_matches:
            task_name = call_match.group(1)
            call_alias = call_match.group(2) or task_name
            call_inputs = call_match.group(3)
            
            scatter_calls[call_alias] = {
                "task": task_name,
                "inputs": _parse_wdl_call_inputs(call_inputs),
                "scatter": scatter_expr,
            }
        
        workflow["scatter"].update(scatter_calls)

    return workflow


def _parse_wdl_parameters(params_text: str, param_type: str) -> Dict[str, Any]:
    """Parse WDL parameter declarations."""
    params = {}

    for line in params_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Match parameter declarations
        match = re.match(r"(\w+)\s+(\w+)(?:\s*=\s*(.+))?", line)
        if match:
            param_name = match.group(1)
            param_type_wdl = match.group(2)
            default_value = match.group(3) if match.group(3) else None

            params[param_name] = {
                "type": param_type_wdl,
                "default": default_value,
            }

    return params


def _parse_wdl_runtime(runtime_text: str) -> Dict[str, Any]:
    """Parse WDL runtime section."""
    runtime = {}

    for line in runtime_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Match runtime declarations
        match = re.match(r"(\w+)\s*:\s*(.+)", line)
        if match:
            key = match.group(1)
            value = match.group(2).strip().strip('"\'')
            runtime[key] = value

    return runtime


def _parse_wdl_meta(meta_text: str) -> Dict[str, Any]:
    """Parse WDL meta section."""
    meta = {}

    for line in meta_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Match meta declarations
        match = re.match(r"(\w+)\s*:\s*(.+)", line)
        if match:
            key = match.group(1)
            value = match.group(2).strip().strip('"\'')
            meta[key] = value

    return meta


def _parse_wdl_call_inputs(inputs_text: str) -> Dict[str, str]:
    """Parse WDL call input bindings."""
    inputs = {}

    for line in inputs_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Match input bindings
        match = re.match(r"(\w+)\s*=\s*(.+)", line)
        if match:
            input_name = match.group(1)
            input_value = match.group(2).strip().strip('"\'')
            inputs[input_name] = input_value

    return inputs


def _convert_wdl_task_to_ir(
    wdl_task: Dict[str, Any],
    task_id: str,
    call: Dict[str, Any],
    preserve_metadata: bool = True,
    verbose: bool = False,
) -> Task:
    """Convert a WDL task to IR Task."""
    
    # Extract basic information
    task_name = wdl_task.get("name", task_id)
    command = wdl_task.get("command", "")
    runtime = wdl_task.get("runtime", {})
    meta = wdl_task.get("meta", {})
    
    # Convert inputs and outputs
    inputs = _convert_wdl_task_inputs(wdl_task.get("inputs", {}))
    outputs = _convert_wdl_task_outputs(wdl_task.get("outputs", {}))
    
    # Convert runtime to resources
    cpu = EnvironmentSpecificValue(1, ["shared_filesystem"])
    mem_mb = EnvironmentSpecificValue(4096, ["shared_filesystem"])
    disk_mb = EnvironmentSpecificValue(4096, ["shared_filesystem"])
    time_s = EnvironmentSpecificValue(3600, ["shared_filesystem"])
    
    if "cpu" in runtime:
        cpu_val = _parse_resource_value(runtime["cpu"])
        if cpu_val is not None:
            cpu = EnvironmentSpecificValue(int(cpu_val), ["shared_filesystem"])
    
    if "memory" in runtime:
        mem_val = _parse_memory_string(runtime["memory"])
        if mem_val is not None:
            mem_mb = EnvironmentSpecificValue(mem_val, ["shared_filesystem"])
    
    if "disk" in runtime:
        disk_val = _parse_disk_string(runtime["disk"])
        if disk_val is not None:
            disk_mb = EnvironmentSpecificValue(disk_val, ["shared_filesystem"])
    
    if "time" in runtime:
        time_val = _parse_time_string(runtime["time"])
        if time_val is not None:
            time_s = EnvironmentSpecificValue(time_val, ["shared_filesystem"])
    
    # Extract environment
    container = EnvironmentSpecificValue(None, ["shared_filesystem"])
    if "docker" in runtime:
        container = EnvironmentSpecificValue(runtime["docker"], ["shared_filesystem"])
    
    # Extract scatter information
    scatter = EnvironmentSpecificValue(None, ["shared_filesystem"])
    if "scatter" in call:
        scatter_expr = call["scatter"]
        scatter_spec = _convert_wdl_scatter(scatter_expr)
        if scatter_spec:
            scatter = EnvironmentSpecificValue(scatter_spec, ["shared_filesystem"])
    
    # Create task
    task = Task(
        id=task_id,
        label=task_name,
        doc=meta.get("description", ""),
        command=EnvironmentSpecificValue(command, ["shared_filesystem"]) if command else EnvironmentSpecificValue(None, ["shared_filesystem"]),
        inputs=inputs,
        outputs=outputs,
        scatter=scatter,
        cpu=cpu,
        mem_mb=mem_mb,
        disk_mb=disk_mb,
        time_s=time_s,
        container=container,
    )
    
    return task


def _convert_wdl_task_inputs(wdl_inputs: Dict[str, Any]) -> List[ParameterSpec]:
    """Convert WDL task inputs to ParameterSpec."""
    inputs = []
    
    for input_name, input_def in wdl_inputs.items():
        if isinstance(input_def, dict):
            input_type = _convert_wdl_type(input_def.get("type", "string"))
            inputs.append(ParameterSpec(
                id=input_name,
                type=input_type,
                label=input_name,
                default=input_def.get("default"),
            ))
    
    return inputs


def _convert_wdl_task_outputs(wdl_outputs: Dict[str, Any]) -> List[ParameterSpec]:
    """Convert WDL task outputs to ParameterSpec."""
    outputs = []
    
    for output_name, output_def in wdl_outputs.items():
        if isinstance(output_def, dict):
            output_type = _convert_wdl_type(output_def.get("type", "string"))
            outputs.append(ParameterSpec(
                id=output_name,
                type=output_type,
                label=output_name,
            ))
    
    return outputs


def _convert_wdl_type(wdl_type: str) -> str:
    """Convert WDL type to IR type."""
    type_mapping = {
        "String": "string",
        "Int": "int",
        "Float": "float",
        "Boolean": "boolean",
        "File": "File",
        "Array": "array",
        "Map": "record",
        "Object": "record",
    }
    
    # Handle array types
    if wdl_type.startswith("Array[") and wdl_type.endswith("]"):
        inner_type = wdl_type[6:-1]
        return f"array<{_convert_wdl_type(inner_type)}>"
    
    # Handle optional types
    if wdl_type.endswith("?"):
        base_type = wdl_type[:-1]
        return _convert_wdl_type(base_type)
    
    return type_mapping.get(wdl_type, "string")


def _parse_memory_string(memory_str: str) -> Optional[int]:
    """Parse memory string to MB."""
    if not memory_str:
        return None
    
    memory_str = memory_str.strip()
    
    # Remove quotes
    memory_str = memory_str.strip('"\'')
    
    if memory_str.endswith("GB"):
        return int(float(memory_str[:-2]) * 1024)
    elif memory_str.endswith("MB"):
        return int(memory_str[:-2])
    elif memory_str.endswith("KB"):
        return int(memory_str[:-2]) // 1024
    else:
        # Assume MB if no unit specified
        try:
            return int(memory_str)
        except ValueError:
            return None


def _parse_disk_string(disk_str: str) -> Optional[int]:
    """Parse disk string to MB."""
    if not disk_str:
        return None
    
    disk_str = disk_str.strip()
    
    # Remove quotes
    disk_str = disk_str.strip('"\'')
    
    if disk_str.endswith("GB"):
        return int(float(disk_str[:-2]) * 1024)
    elif disk_str.endswith("MB"):
        return int(disk_str[:-2])
    elif disk_str.endswith("KB"):
        return int(disk_str[:-2]) // 1024
    else:
        # Assume MB if no unit specified
        try:
            return int(disk_str)
        except ValueError:
            return None


def _parse_time_string(time_str: str) -> Optional[int]:
    """Parse time string to seconds."""
    if not time_str:
        return None
    
    time_str = time_str.strip()
    
    # Remove quotes
    time_str = time_str.strip('"\'')
    
    if time_str.endswith("h"):
        return int(float(time_str[:-1]) * 3600)
    elif time_str.endswith("m"):
        return int(float(time_str[:-1]) * 60)
    elif time_str.endswith("s"):
        return int(time_str[:-1])
    else:
        # Assume seconds if no unit specified
        try:
            return int(time_str)
        except ValueError:
            return None


def _parse_resource_value(value_str: str) -> Any:
    """Parse resource value string."""
    if not value_str:
        return None
    
    # Remove quotes
    value_str = value_str.strip('"\'')
    
    try:
        if "." in value_str:
            return float(value_str)
        else:
            return int(value_str)
    except ValueError:
        return value_str


def _convert_wdl_scatter(scatter_expr: str) -> ScatterSpec:
    """Convert WDL scatter expression to ScatterSpec."""
    # Extract variable name from scatter expression
    # WDL scatter syntax: scatter (item in items)
    match = re.match(r"\((\w+)\s+in\s+(\w+)\)", scatter_expr)
    if match:
        item_var = match.group(1)
        items_var = match.group(2)
        return ScatterSpec(
            scatter=[items_var],
            scatter_method="dotproduct"
        )
    
    # Fallback
    return ScatterSpec(
        scatter=[scatter_expr],
        scatter_method="dotproduct"
    )


def _extract_wdl_dependencies(
    call: Dict[str, Any], call_alias: str, all_calls: List[Dict[str, Any]]
) -> List[Edge]:
    """Extract dependencies from WDL call."""
    edges = []
    
    # Check for dependencies in call inputs
    inputs = call.get("inputs", {})
    for input_name, input_value in inputs.items():
        # Look for references to other calls
        if isinstance(input_value, str):
            for other_call_name, other_call in all_calls:
                if other_call_name in input_value:
                    edges.append(Edge(parent=other_call_name, child=call_alias))
    
    return edges
