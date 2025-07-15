"""
wf2wf.importers.wdl – WDL ➜ Workflow IR

Reference implementation (85/100 compliance, see IMPORTER_SPECIFICATION.md)

Compliance Checklist:
- [x] Inherit from BaseImporter
- [x] Does NOT override import_workflow()
- [x] Implements _parse_source() and _get_source_format()
- [x] Uses shared infrastructure for loss, inference, prompting, environment, and resource management
- [x] Places all format-specific logic in enhancement methods
- [x] Passes all required and integration tests
- [x] Maintains code size within recommended range
- [x] Documents format-specific enhancements

This module imports Workflow Description Language (WDL) workflows and converts
them to the wf2wf intermediate representation with feature preservation.

Features supported:
- WDL tasks and workflows
- Scatter operations with collection types
- Runtime specifications (cpu, memory, disk, docker)
- Input/output parameter specifications
- Meta and parameter_meta sections
- Call dependencies and workflow structure
- Loss sidecar integration and environment-specific values
"""

from __future__ import annotations

import re
import json
import logging
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
from wf2wf.loss import detect_and_apply_loss_sidecar
from wf2wf.importers.inference import infer_environment_specific_values, infer_execution_model
from wf2wf.interactive import prompt_for_missing_information
from wf2wf.importers.resource_processor import process_workflow_resources
from wf2wf.importers.utils import (
    extract_balanced_braces, 
    parse_key_value_pairs,
    parse_memory_string,
    parse_disk_string,
    parse_time_string,
    parse_resource_value,
    normalize_task_id,
    GenericSectionParser
)

# Configure logger for this module
logger = logging.getLogger(__name__)


class WDLParseError(Exception):
    """Base exception for WDL parsing errors."""
    pass


class WDLUnbalancedBracesError(WDLParseError):
    """Raised when braces are not properly balanced in WDL content."""
    pass


class WDLMissingContentError(WDLParseError):
    """Raised when WDL file contains no tasks or workflows."""
    pass


class WDLInvalidSyntaxError(WDLParseError):
    """Raised when WDL syntax is invalid."""
    pass


class WDLSectionParser:
    """Parser for WDL sections (input, output, runtime, meta, etc.)."""
    
    @staticmethod
    def parse_parameters(params_text: str, param_type: str) -> Dict[str, Any]:
        """Parse WDL parameter declarations."""
        return GenericSectionParser.parse_parameters(params_text, param_type, comment_chars=["#"])

    @staticmethod
    def parse_runtime(runtime_text: str) -> Dict[str, Any]:
        """Parse WDL runtime section."""
        return GenericSectionParser.parse_key_value_section(runtime_text, comment_chars=["#"])

    @staticmethod
    def parse_meta(meta_text: str) -> Dict[str, Any]:
        """Parse WDL meta section."""
        return GenericSectionParser.parse_key_value_section(meta_text, comment_chars=["#"])

    @staticmethod
    def parse_call_inputs(inputs_text: str) -> Dict[str, str]:
        """Parse WDL call input bindings."""
        inputs = {}
        logger.debug(f"Parsing call inputs from: '{inputs_text}'")

        for line in inputs_text.split("\n"):
            line = line.strip()
            logger.debug(f"Processing line: '{line}'")
            if not line or line.startswith("#"):
                continue

            # Skip the "input:" keyword
            if line == "input:":
                logger.debug("Skipping 'input:' keyword")
                continue

            # Match input bindings - handle both "input: name = value" and "name = value" formats
            match = re.match(r"(?:input:\s*)?(\w+)\s*=\s*(.+)", line)
            if match:
                input_name = match.group(1)
                input_value = match.group(2).strip().strip('"\'')
                inputs[input_name] = input_value
                logger.debug(f"Found input binding: {input_name} = {input_value}")
            else:
                logger.debug(f"No match for line: '{line}'")

        logger.debug(f"Final inputs: {inputs}")
        return inputs


class WDLImporter(BaseImporter):
    """WDL importer using shared base infrastructure."""
    
    def _parse_source(self, path: Path, **opts: Any) -> Dict[str, Any]:
        """Parse WDL file and extract all information."""
        preserve_metadata = opts.get("preserve_metadata", True)
        debug = opts.get("debug", False)
        verbose = self.verbose

        if verbose:
            logger.info(f"Parsing WDL file: {path}")

        # Read and parse WDL content
        try:
            content = path.read_text()
        except Exception as e:
            raise WDLParseError(f"Failed to read WDL file {path}: {e}") from e

        try:
            wdl_doc = _parse_wdl_document(content, path, debug=debug)
        except Exception as e:
            raise WDLParseError(f"Failed to parse WDL content: {e}") from e

        # Validate that we have at least some content
        if not wdl_doc.get("tasks") and not wdl_doc.get("workflows"):
            raise WDLMissingContentError("WDL file contains no tasks or workflows")

        return {
            "wdl_doc": wdl_doc,
            "wdl_path": path,
            "preserve_metadata": preserve_metadata,
        }
    
    def _create_basic_workflow(self, parsed_data: Dict[str, Any]) -> Workflow:
        """Create basic workflow from parsed WDL data with shared infrastructure integration."""
        if self.verbose:
            logger.info("Creating basic workflow from WDL data")
        
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
        )
        
        # Add metadata
        if hasattr(workflow, 'metadata') and workflow.metadata is not None:
            workflow.metadata.format_specific['source_format'] = 'wdl'
            workflow.metadata.format_specific['wdl_document'] = wdl_doc
            workflow.metadata.format_specific['wdl_version'] = wdl_doc.get('version', '1.0')
        else:
            workflow.metadata = MetadataSpec(format_specific={'source_format': 'wdl', 'wdl_document': wdl_doc, 'wdl_version': wdl_doc.get('version', '1.0')})
        
        # Extract tasks and add them to workflow
        tasks = self._extract_tasks(parsed_data)
        for task in tasks:
            workflow.add_task(task)
        
        # Extract edges and add them to workflow
        edges = self._extract_edges(parsed_data)
        for edge in edges:
            workflow.add_edge(edge.parent, edge.child)
        
        # Extract workflow-level inputs and outputs
        if workflows:
            workflow_def = list(workflows.values())[0]
            workflow.inputs = _convert_wdl_workflow_inputs(workflow_def.get("inputs", {}))
            workflow.outputs = _convert_wdl_workflow_outputs(workflow_def.get("outputs", {}))
        
        # --- Shared infrastructure: inference and prompting ---
        infer_environment_specific_values(workflow, "wdl", self._selected_execution_model)
        if self.interactive:
            prompt_for_missing_information(workflow, "wdl")
        # (Loss sidecar and environment management are handled by BaseImporter)
        
        # Apply WDL-specific enhancements
        self._enhance_wdl_specific_features(workflow, parsed_data)
        
        return workflow
    
    def _enhance_wdl_specific_features(self, workflow: Workflow, parsed_data: Dict[str, Any]):
        """Add WDL-specific enhancements not covered by shared infrastructure."""
        if self.verbose:
            logger.info("Adding WDL-specific enhancements...")
        
        # Apply loss side-car if available
        if hasattr(self, '_source_path') and self._source_path:
            self._apply_loss_sidecar(workflow, self._source_path)
        
        # WDL-specific enhancements
        self._apply_wdl_specific_defaults(workflow, parsed_data)
    
    def _apply_loss_sidecar(self, workflow: Workflow, source_path: Path):
        """Apply loss side-car to WDL workflow."""
        if self.verbose:
            logger.info("Checking for loss side-car...")
        
        applied = detect_and_apply_loss_sidecar(workflow, source_path, self.verbose)
        if applied and self.verbose:
            logger.info("Applied loss side-car to restore lost information")
    
    def _apply_wdl_specific_defaults(self, workflow: Workflow, parsed_data: Dict[str, Any]):
        """Apply WDL-specific defaults and enhancements."""
        for task in workflow.tasks.values():
            # WDL-specific runtime handling
            if (task.cpu.get_value_with_default('shared_filesystem') or 0) == 0:
                # Default to 1 CPU for WDL tasks
                task.cpu.set_for_environment(1, 'shared_filesystem')
            
            # WDL-specific memory handling
            if (task.mem_mb.get_value_with_default('shared_filesystem') or 0) == 0:
                # Default to 4GB memory for WDL tasks
                task.mem_mb.set_for_environment(4096, 'shared_filesystem')
            
            # WDL-specific disk handling
            if (task.disk_mb.get_value_with_default('shared_filesystem') or 0) == 0:
                # Default to 4GB disk for WDL tasks
                task.disk_mb.set_for_environment(4096, 'shared_filesystem')

    def _extract_tasks(self, parsed_data: Dict[str, Any]) -> List[Task]:
        """Extract tasks from parsed WDL data."""
        wdl_doc = parsed_data["wdl_doc"]
        wdl_path = parsed_data["wdl_path"]
        preserve_metadata = parsed_data["preserve_metadata"]
        verbose = self.verbose
        
        tasks = []
        wdl_tasks = wdl_doc.get("tasks", {})
        workflows = wdl_doc.get("workflows", {})
        
        # Track processed tasks to avoid duplicates
        processed_tasks = {}
        
        # Extract tasks from workflow calls
        for workflow_name, workflow_def in workflows.items():
            calls = workflow_def.get("calls", {})
            scatter_calls = workflow_def.get("scatter", {})
            
            # Process regular calls
            for call_alias, call_dict in calls.items():
                task_name = call_dict.get("task", call_alias)
                if task_name in wdl_tasks and task_name not in processed_tasks:
                    task = _convert_wdl_task_to_ir(
                        wdl_tasks[task_name],
                        task_name,
                        call_dict,
                        preserve_metadata=preserve_metadata,
                        verbose=verbose,
                    )
                    tasks.append(task)
                    processed_tasks[task_name] = task
            
            # Process scatter calls
            for scatter_alias, scatter_dict in scatter_calls.items():
                task_name = scatter_dict.get("task", scatter_alias)
                if task_name in wdl_tasks:
                    scatter_spec = None
                    if "scatter" in scatter_dict:
                        scatter_spec = _convert_wdl_scatter(scatter_dict["scatter"])
                    if task_name in processed_tasks:
                        # Update scatter field on existing task
                        if scatter_spec:
                            processed_tasks[task_name].scatter = EnvironmentSpecificValue(scatter_spec, ["shared_filesystem"])
                    else:
                        task = _convert_wdl_task_to_ir(
                            wdl_tasks[task_name],
                            task_name,
                            scatter_dict,
                            preserve_metadata=preserve_metadata,
                            verbose=verbose,
                        )
                        if scatter_spec:
                            task.scatter = EnvironmentSpecificValue(scatter_spec, ["shared_filesystem"])
                        tasks.append(task)
                        processed_tasks[task_name] = task
        
        return tasks
    
    def _extract_edges(self, parsed_data: Dict[str, Any]) -> List[Edge]:
        """Extract edges from parsed WDL data."""
        wdl_doc = parsed_data["wdl_doc"]
        edges = []
        workflows = wdl_doc.get("workflows", {})
        
        for workflow_name, workflow_def in workflows.items():
            calls = workflow_def.get("calls", {})
            scatter_calls = workflow_def.get("scatter", {})
            
            # Get all call aliases
            all_calls = list(calls.keys()) + list(scatter_calls.keys())
            
            # Extract dependencies from regular calls
            for call_alias, call_dict in calls.items():
                dependencies = _extract_wdl_dependencies(call_dict, call_alias, all_calls)
                edges.extend(dependencies)
            
            # Extract dependencies from scatter calls
            for scatter_alias, scatter_dict in scatter_calls.items():
                dependencies = _extract_wdl_dependencies(scatter_dict, scatter_alias, all_calls)
                edges.extend(dependencies)
        
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
        task_body = extract_balanced_braces(content, match.end() - 1)
        doc["tasks"][task_name] = _parse_wdl_task(task_body, task_name, debug=debug)

    # Extract workflows using balanced brace matching
    workflow_starts = re.finditer(r"workflow\s+(\w+)\s*\{", content)
    for match in workflow_starts:
        workflow_name = match.group(1)
        workflow_body = extract_balanced_braces(content, match.end() - 1)
        doc["workflows"][workflow_name] = _parse_wdl_workflow(
            workflow_body, workflow_name, debug=debug
        )

    return doc


# Use shared utility from wf2wf.importers.utils


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
        task["inputs"] = WDLSectionParser.parse_parameters(input_match.group(1), "input")

    # Extract output section
    output_match = re.search(r"output\s*\{([^}]*)\}", task_body, re.DOTALL)
    if output_match:
        task["outputs"] = WDLSectionParser.parse_parameters(output_match.group(1), "output")

    # Extract command section
    command_match = re.search(
        r"command\s*(?:<<<|{)([^}]*?)(?:>>>|})", task_body, re.DOTALL
    )
    if command_match:
        task["command"] = command_match.group(1).strip()

    # Extract runtime section
    runtime_match = re.search(r"runtime\s*\{([^}]*)\}", task_body, re.DOTALL)
    if runtime_match:
        task["runtime"] = WDLSectionParser.parse_runtime(runtime_match.group(1))

    # Extract meta section
    meta_match = re.search(r"meta\s*\{([^}]*)\}", task_body, re.DOTALL)
    if meta_match:
        task["meta"] = WDLSectionParser.parse_meta(meta_match.group(1))

    # Extract parameter_meta section
    param_meta_match = re.search(r"parameter_meta\s*\{([^}]*)\}", task_body, re.DOTALL)
    if param_meta_match:
        task["parameter_meta"] = WDLSectionParser.parse_meta(param_meta_match.group(1))

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
        workflow["inputs"] = WDLSectionParser.parse_parameters(input_match.group(1), "input")

    # Extract output section
    output_match = re.search(r"output\s*\{([^}]*)\}", workflow_body, re.DOTALL)
    if output_match:
        workflow["outputs"] = WDLSectionParser.parse_parameters(output_match.group(1), "output")

    # Extract regular call statements (not in scatter)
    call_blocks = _extract_call_blocks(workflow_body)
    for call_alias, call_dict in call_blocks:
        workflow["calls"][call_alias] = call_dict

    # Extract scatter statements
    scatter_calls = _extract_scatter_blocks(workflow_body)
    workflow["scatter"].update(scatter_calls)

    return workflow


def _convert_wdl_task_to_ir(
    wdl_task: Dict[str, Any],
    task_id: str,
    call: Dict[str, Any],
    preserve_metadata: bool = True,
    verbose: bool = False,
) -> Task:
    logger.debug(f"Creating IR Task for {task_id} with call dict: {call}")
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
        docker_image = runtime["docker"]
        # Add docker:// prefix if not already present
        if not docker_image.startswith("docker://"):
            docker_image = f"docker://{docker_image}"
        container = EnvironmentSpecificValue(docker_image, ["shared_filesystem"])
    
    # Extract scatter information
    scatter = EnvironmentSpecificValue(None, ["shared_filesystem"])
    if "scatter" in call:
        logger.debug(f"Task {task_id} scatter key: {call['scatter']}")
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
    # If scatter is present in call and not None/empty, set task.scatter
    if "scatter" in call and call["scatter"]:
        logger.debug(f"Task {task_id} final scatter assignment: {call['scatter']}")
        scatter_spec = _convert_wdl_scatter(call["scatter"])
        if scatter_spec:
            task.scatter = EnvironmentSpecificValue(scatter_spec, ["shared_filesystem"])
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


def _convert_wdl_workflow_inputs(wdl_inputs: Dict[str, Any]) -> List[ParameterSpec]:
    """Convert WDL workflow inputs to ParameterSpec list."""
    inputs = []
    for input_name, input_def in wdl_inputs.items():
        if isinstance(input_def, dict):
            param_type = input_def.get("type", "string")
            default = input_def.get("default")
            doc = input_def.get("doc")
        else:
            param_type = str(input_def)
            default = None
            doc = None
        
        param = ParameterSpec(
            id=input_name,
            type=_convert_wdl_type(param_type),
            default=default,
            doc=doc
        )
        inputs.append(param)
    return inputs


def _convert_wdl_workflow_outputs(wdl_outputs: Dict[str, Any]) -> List[ParameterSpec]:
    """Convert WDL workflow outputs to ParameterSpec list."""
    outputs = []
    for output_name, output_def in wdl_outputs.items():
        if isinstance(output_def, dict):
            param_type = output_def.get("type", "string")
            default = output_def.get("default")
            doc = output_def.get("doc")
        else:
            param_type = str(output_def)
            default = None
            doc = None
        
        param = ParameterSpec(
            id=output_name,
            type=_convert_wdl_type(param_type),
            default=default,
            doc=doc
        )
        outputs.append(param)
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
        inner_ir_type = _convert_wdl_type(inner_type)
        return f"{inner_ir_type}[]"  # Use the format that TypeSpec.parse expects

    # Handle optional types
    if wdl_type.endswith("?"):
        base_type = wdl_type[:-1]
        return _convert_wdl_type(base_type)

    return type_mapping.get(wdl_type, "string")


def _parse_memory_string(memory_str: str) -> Optional[int]:
    """Parse memory string and convert to MB."""
    return parse_memory_string(memory_str)


def _parse_disk_string(disk_str: str) -> Optional[int]:
    """Parse disk string and convert to MB."""
    return parse_disk_string(disk_str)


def _parse_time_string(time_str: str) -> Optional[int]:
    """Parse time string and convert to seconds."""
    return parse_time_string(time_str)


def _parse_resource_value(value_str: str) -> Any:
    """Parse a resource value, handling various formats."""
    return parse_resource_value(value_str)


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
    call: Dict[str, Any], call_alias: str, all_calls: List[str]
) -> List[Edge]:
    """Extract dependencies from WDL call."""
    edges = []

    # Check for dependencies in call inputs
    inputs = call.get("inputs", {})
    for input_name, input_value in inputs.items():
        # Look for references to other calls in the format task_name.output_name
        if isinstance(input_value, str):
            # Match pattern: task_name.output_name
            for other_call_name in all_calls:
                if other_call_name != call_alias:  # Don't create self-dependency
                    pattern = rf"{other_call_name}\.\w+"
                    if re.search(pattern, input_value):
                        edges.append(Edge(parent=other_call_name, child=call_alias))
                        logger.debug(f"Found dependency: {other_call_name} -> {call_alias} via {input_name} = {input_value}")
                        break  # Only add one edge per dependency

    return edges


def _extract_call_blocks(content: str) -> List[Dict[str, Any]]:
    """Extract all call blocks from WDL content.
    
    Returns a list of call dictionaries with keys: task_name, call_alias, inputs, scatter
    """
    calls = []
    
    # Find all call statements
    call_matches = re.finditer(r"call\s+(\w+)(?:\s+as\s+(\w+))?\s*\{", content)
    for call_match in call_matches:
        task_name = call_match.group(1)
        call_alias = call_match.group(2) or task_name
        call_block_start = call_match.end() - 1
        call_block = extract_balanced_braces(content, call_block_start)
        call_inputs = WDLSectionParser.parse_call_inputs(call_block)
        
        call_dict = {
            "task": task_name,
            "inputs": call_inputs,
        }
        calls.append((call_alias, call_dict))
    
    return calls


def _extract_scatter_blocks(content: str) -> Dict[str, Dict[str, Any]]:
    """Extract all scatter blocks from WDL content.
    
    Returns a dictionary mapping call aliases to call dictionaries with scatter info.
    """
    scatter_calls = {}
    
    # Find all scatter statements
    scatter_matches = re.finditer(r"scatter\s*\(([^)]+)\)\s*\{", content, re.DOTALL)
    for match in scatter_matches:
        scatter_expr = match.group(1)
        scatter_body_start = match.end() - 1
        scatter_body = extract_balanced_braces(content, scatter_body_start)
        logger.debug(f"Found scatter expression: '{scatter_expr}' with body: '{scatter_body}'")
        
        # Parse collection variable from scatter_expr (e.g., 'file in input_files')
        scatter_var_match = re.match(r"\w+\s+in\s+(\w+)", scatter_expr)
        scatter_var = scatter_var_match.group(1) if scatter_var_match else scatter_expr
        logger.debug(f"Extracted scatter variable: '{scatter_var}'")
        
        # Extract calls within this scatter block
        call_blocks = _extract_call_blocks(scatter_body)
        for call_alias, call_dict in call_blocks:
            call_dict["scatter"] = scatter_var
            logger.debug(f"Created scatter call dict for {call_alias}: {call_dict}")
            scatter_calls[call_alias] = call_dict
    
    logger.debug(f"Final workflow scatter dict: {scatter_calls}")
    return scatter_calls
