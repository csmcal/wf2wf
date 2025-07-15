"""
wf2wf.importers.nextflow – Nextflow DSL2 ➜ Workflow IR

Reference implementation (90/100 compliance, see IMPORTER_SPECIFICATION.md)

Compliance Checklist:
- [x] Inherit from BaseImporter
- [x] Does NOT override import_workflow()
- [x] Implements _parse_source() and _get_source_format()
- [x] Uses shared infrastructure for loss, inference, prompting, environment, and resource management
- [x] Places all format-specific logic in enhancement methods
- [x] Passes all required and integration tests
- [x] Maintains code size within recommended range
- [x] Documents format-specific enhancements

This module converts Nextflow DSL2 workflows to the wf2wf intermediate representation.
It parses main.nf files, module files, and nextflow.config files to extract:
- Process definitions
- Resource specifications
- Container/conda environments
- Dependencies and data flow
- Configuration parameters
"""

from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, Union

from wf2wf.core import (
    Workflow, 
    Task, 
    Edge, 
    EnvironmentSpecificValue,
    ParameterSpec,
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
    parse_memory_string,
    parse_disk_string,
    parse_time_string,
    parse_resource_value,
    normalize_task_id,
    extract_resource_specifications,
    extract_environment_specifications,
    extract_error_handling_specifications,
    GenericSectionParser
)

# Configure logger for this module
logger = logging.getLogger(__name__)


class NextflowParseError(Exception):
    """Base exception for Nextflow parsing errors."""
    pass


class NextflowFileNotFoundError(NextflowParseError):
    """Raised when required Nextflow files are not found."""
    pass


class NextflowInvalidSyntaxError(NextflowParseError):
    """Raised when Nextflow syntax is invalid."""
    pass


class NextflowConfigError(NextflowParseError):
    """Raised when Nextflow configuration is invalid."""
    pass


class NextflowImporter(BaseImporter):
    """Nextflow importer that converts Nextflow DSL2 workflows to the IR."""

    def _parse_source(self, path: Path, **opts: Any) -> Dict[str, Any]:
        """Parse Nextflow workflow source."""
        debug = opts.get("debug", False)
        workflow_dir = path if path.is_dir() else path.parent
        main_nf = path if path.suffix == ".nf" else workflow_dir / "main.nf"

        if not main_nf.exists():
            raise NextflowFileNotFoundError(f"Nextflow file not found: {main_nf}")

        if debug:
            logger.debug(f"DEBUG: Parsing Nextflow workflow from {workflow_dir}")
            logger.debug(f"DEBUG: Main file: {main_nf}")

        # Parse nextflow.config if it exists
        config_path = workflow_dir / "nextflow.config"
        config = {}
        if config_path.exists():
            config = _parse_nextflow_config(config_path, debug=debug)

        if debug:
            logger.debug(f"Parsed config: {config}")

        # Parse main workflow file
        processes, workflow_def, includes = _parse_main_nf(main_nf, debug=debug)

        # Parse included modules
        module_processes = {}
        for include_path in includes:
            module_path = workflow_dir / include_path
            # Try with .nf extension if file doesn't exist
            if not module_path.exists() and not include_path.endswith(".nf"):
                module_path = workflow_dir / (include_path + ".nf")

            if module_path.exists():
                if debug:
                    logger.debug(f"Parsing module file: {module_path}")
                mod_processes = _parse_module_file(module_path, debug=debug)
                if debug:
                    logger.debug(f"Found {len(mod_processes)} processes in module: {list(mod_processes.keys())}")
                module_processes.update(mod_processes)
            elif debug:
                logger.debug(f"Module file not found: {module_path}")

        # Combine all processes
        all_processes = {**processes, **module_processes}
        if debug:
            logger.debug(f"Total processes found: {len(all_processes)}")
            logger.debug(f"Process names: {list(all_processes.keys())}")
            logger.debug(f"Main processes: {list(processes.keys())}")
            logger.debug(f"Module processes: {list(module_processes.keys())}")
            logger.debug(f"Includes found: {includes}")

        # Extract dependencies from workflow definition
        dependencies = _extract_dependencies(workflow_def, debug=debug)

        # Get workflow name
        workflow_name = (
            workflow_dir.name if workflow_dir.name != "." else "nextflow_workflow"
        )

        # Convert processes to tasks format expected by base importer
        tasks = {}
        for proc_name, proc_info in all_processes.items():
            task_data = _convert_process_to_task_data(proc_name, proc_info, config, debug=debug)
            tasks[proc_name] = task_data

        # Convert dependencies to edges format expected by base importer
        edges = []
        for parent, child in dependencies:
            edges.append({"parent": parent, "child": child})

        result = {
            "name": workflow_name,
            "version": "1.0",
            "tasks": tasks,
            "edges": edges,
            "inputs": [],  # Nextflow inputs are handled at process level
            "outputs": [],  # Nextflow outputs are handled at process level
            "config": config,
            "workflow_dir": workflow_dir,
            "debug": debug,
        }
        
        if debug:
            logger.debug(f"Parsed {len(tasks)} tasks: {list(tasks.keys())}")
            logger.debug(f"Parsed {len(edges)} edges")
        
        return result

    def _create_basic_workflow(self, parsed_data: Dict[str, Any]) -> Workflow:
        """Create basic workflow from parsed Nextflow data with shared infrastructure integration."""
        if self.verbose:
            logger.info("Creating basic workflow from Nextflow data")
        
        # Create basic workflow using parent method
        workflow = super()._create_basic_workflow(parsed_data)
        
        # Add Nextflow-specific metadata
        workflow.metadata = MetadataSpec(
            source_format="nextflow",
            source_file=str(parsed_data.get("workflow_dir", "")),
            format_specific={
                "nextflow_config": parsed_data.get("config", {}),
                "workflow_dir": str(parsed_data.get("workflow_dir", "")),
            }
        )
        
        # --- Shared infrastructure: prompting ---
        if self.interactive:
            prompt_for_missing_information(workflow, "nextflow")
        # (Inference, loss sidecar and environment management are handled by BaseImporter)
        
        # Apply Nextflow-specific enhancements
        self._enhance_nextflow_specific_features(workflow, parsed_data)
        
        return workflow
    
    def _enhance_nextflow_specific_features(self, workflow: Workflow, parsed_data: Dict[str, Any]):
        """Add Nextflow-specific enhancements not covered by shared infrastructure."""
        if self.verbose:
            logger.info("Adding Nextflow-specific enhancements...")
        
        # Nextflow-specific logic: ensure environment-specific values are set for multiple environments
        # since Nextflow workflows can run in various environments
        environments = ["shared_filesystem", "distributed_computing", "cloud_native"]
        
        for task in workflow.tasks.values():
            # Ensure critical fields are set for all applicable environments
            for field_name in ['cpu', 'mem_mb', 'disk_mb', 'time_s', 'gpu', 'container', 'conda']:
                field_value = getattr(task, field_name)
                if isinstance(field_value, EnvironmentSpecificValue):
                    # If value is only set for shared_filesystem, extend to other environments
                    shared_value = field_value.get_value_for("shared_filesystem")
                    if shared_value is not None:
                        for env in environments:
                            if not field_value.is_applicable_to(env):
                                field_value.set_for_environment(shared_value, env)

    def _create_task_from_data(self, task_id: str, task_data: Dict[str, Any]) -> Task:
        """
        Create a Task object from task data.
        
        Use base implementation but ensure values are set for multiple environments.
        
        Args:
            task_id: ID of the task
            task_data: Dictionary containing task data
            
        Returns:
            Task object
        """
        # Use base implementation to create the task
        task = super()._create_task_from_data(task_id, task_data)
        
        # Nextflow workflows can run in various environments, so ensure values
        # are set for multiple environments if they're only set for shared_filesystem
        environments = ["shared_filesystem", "distributed_computing", "cloud_native"]
        
        # Check each environment-specific field and extend to other environments if needed
        for field_name in ['cpu', 'mem_mb', 'disk_mb', 'time_s', 'gpu', 'container', 'conda']:
            field_value = getattr(task, field_name)
            if isinstance(field_value, EnvironmentSpecificValue):
                # If value is only set for shared_filesystem, extend to other environments
                shared_value = field_value.get_value_for("shared_filesystem")
                if shared_value is not None:
                    for env in environments:
                        if not field_value.is_applicable_to(env):
                            field_value.set_for_environment(shared_value, env)
        
        return task

    def _get_source_format(self) -> str:
        """Get the source format name."""
        return "nextflow"


def to_workflow(path: Union[str, Path], **opts: Any) -> Workflow:
    """Convert Nextflow workflow at *path* into a Workflow IR object using shared infrastructure.

    Parameters
    ----------
    path : Union[str, Path]
        Path to the main.nf file or directory containing it.
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
    importer = NextflowImporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False)
    )
    return importer.import_workflow(path, **opts)


def _parse_nextflow_config(config_path: Path, debug: bool = False) -> Dict[str, Any]:
    """Parse nextflow.config file."""
    if debug:
        logger.debug(f"Parsing config file: {config_path}")

    config = {"params": {}, "process": {"defaults": {}, "withName": {}}, "executor": {}, "profiles": {}}

    try:
        content = config_path.read_text()
        if debug:
            logger.debug(f"Config content: {content}")

        # Parse params block
        params_match = re.search(r"params\s*\{([^}]*)\}", content, re.DOTALL)
        if params_match:
            params_content = params_match.group(1)
            if debug:
                logger.debug(f"Params content: {params_content}")
            config["params"] = NextflowSectionParser.parse_config_block(params_content)
            if debug:
                logger.debug(f"Parsed params: {config['params']}")

        # Parse process block with special handling for withName
        process_match = re.search(r"process\s*\{([^}]*)\}", content, re.DOTALL)
        if process_match:
            process_content = process_match.group(1)
            
            # Parse withName blocks first
            with_name_matches = re.finditer(r"withName:\s*['\"]?(\w+)['\"]?\s*\{([^}]*)\}", process_content, re.DOTALL)
            for match in with_name_matches:
                process_name = match.group(1)
                with_name_content = match.group(2)
                config["process"]["withName"][process_name] = NextflowSectionParser.parse_config_block(with_name_content)
            
            # Parse the rest of the process block (defaults)
            # Remove withName blocks from content to avoid double parsing
            process_content_clean = re.sub(r"withName:\s*['\"]?\w+['\"]?\s*\{[^}]*\}", "", process_content, flags=re.DOTALL)
            config["process"]["defaults"] = NextflowSectionParser.parse_config_block(process_content_clean)

        # Parse executor block
        executor_match = re.search(r"executor\s*\{([^}]*)\}", content, re.DOTALL)
        if executor_match:
            executor_content = executor_match.group(1)
            config["executor"] = NextflowSectionParser.parse_config_block(executor_content)

        if debug:
            logger.debug(f"Parsed config with {len(config['params'])} params")
            logger.debug(f"Process config: {config['process']}")

    except Exception as e:
        if debug:
            logger.debug(f"Error parsing config: {e}")

    return config


class NextflowSectionParser:
    """Parser for Nextflow sections using shared utilities."""
    
    @staticmethod
    def parse_config_block(content: str) -> Dict[str, Any]:
        """Parse Nextflow config block."""
        return GenericSectionParser.parse_key_value_section(content, comment_chars=["//", "#"])

    @staticmethod
    def parse_process_config(content: str) -> Dict[str, Any]:
        """Parse Nextflow process config section."""
        return GenericSectionParser.parse_key_value_section(content, comment_chars=["//", "#"])

    @staticmethod
    def parse_process_inputs(input_content: str) -> List[ParameterSpec]:
        """Parse Nextflow process inputs."""
        inputs = []
        params = GenericSectionParser.parse_parameters(input_content, "input", comment_chars=["//", "#"])
        
        for param_name, param_info in params.items():
            param = ParameterSpec(
                id=param_name,
                type=param_info.get("type", "string"),
                default=param_info.get("default"),
            )
            inputs.append(param)
        
        return inputs

    @staticmethod
    def parse_process_outputs(output_content: str) -> List[ParameterSpec]:
        """Parse Nextflow process outputs."""
        outputs = []
        params = GenericSectionParser.parse_parameters(output_content, "output", comment_chars=["//", "#"])
        
        for param_name, param_info in params.items():
            param = ParameterSpec(
                id=param_name,
                type=param_info.get("type", "string"),
                default=param_info.get("default"),
            )
            outputs.append(param)
        
        return outputs

    @staticmethod
    def parse_resource_value(value_str: Any) -> Any:
        """Parse a resource value using shared utility."""
        return parse_resource_value(value_str)


def _parse_main_nf(main_path: Path, debug: bool = False) -> Tuple[Dict, str, List[str]]:
    """Parse main.nf file."""
    if debug:
        logger.debug(f"DEBUG: Parsing main file: {main_path}")

    content = main_path.read_text()
    
    # Extract includes
    includes = []
    include_matches = re.finditer(r'include\s*\{\s*(\w+)\s*\}\s*from\s*["\']([^"\']+)["\']', content)
    for match in include_matches:
        process_name = match.group(1)
        module_path = match.group(2)
        includes.append(module_path)
        if debug:
            logger.debug(f"DEBUG: Found include: {process_name} from {module_path}")

    # Extract processes from main file
    processes = _extract_processes(content, debug=debug)

    # Extract workflow definition
    workflow_match = re.search(r"workflow\s*\{([^}]*)\}", content, re.DOTALL)
    workflow_def = workflow_match.group(1) if workflow_match else ""

    return processes, workflow_def, includes


def _parse_module_file(module_path: Path, debug: bool = False) -> Dict[str, Dict]:
    """Parse a module file."""
    if debug:
        logger.debug(f"DEBUG: Parsing module: {module_path}")
    
    content = module_path.read_text()
    return _extract_processes(content, debug=debug)


def _extract_processes(content: str, debug: bool = False) -> Dict[str, Dict]:
    """Extract process definitions from content."""
    processes = {}

    # Find process definitions
    process_matches = re.finditer(r"process\s+(\w+)\s*\{", content)
    
    for match in process_matches:
        process_name = match.group(1)
        start_pos = match.end() - 1
        
        # Extract process body
        brace_count = 0
        i = start_pos
        process_body = ""
        
        while i < len(content):
            if content[i] == "{":
                brace_count += 1
            elif content[i] == "}":
                brace_count -= 1
                if brace_count == 0:
                    process_body = content[start_pos + 1:i]
                    break
            i += 1
        
        if process_body:
            process_info = _parse_process_definition(process_body, debug=debug)
            processes[process_name] = process_info
            if debug:
                logger.debug(f"DEBUG: Extracted process: {process_name}")

    return processes


def _parse_process_definition(process_body: str, debug: bool = False) -> Dict[str, Any]:
    """Parse a process definition."""
    process = {
        "inputs": [],
        "outputs": [],
        "script": "",
        "publishDir": "",
        "publishDirMode": "copy",
        "validExitStatus": [0],
        "errorStrategy": "terminate",
        "maxRetries": 3,
        "maxErrors": -1,
        "memory": None,
        "mem_mb": None,
        "cpus": None,
        "disk": None,
        "time": None,
        "container": None,
        "conda": None,
        "module": None,
        "tag": None,
        "label": None,
    }

    # Extract input section
    input_match = re.search(r"input\s*:\s*\{([^}]*)\}", process_body, re.DOTALL)
    if input_match:
        input_content = input_match.group(1)
        process["inputs"] = NextflowSectionParser.parse_process_inputs(input_content)

    # Extract output section
    output_match = re.search(r"output\s*:\s*\{([^}]*)\}", process_body, re.DOTALL)
    if output_match:
        output_content = output_match.group(1)
        process["outputs"] = NextflowSectionParser.parse_process_outputs(output_content)

    # Extract script section - handle both single and triple quotes
    script_match = re.search(r"script\s*:\s*['\"`]([^'\"`]*)['\"`]", process_body, re.DOTALL)
    if script_match:
        script_content = script_match.group(1)
        process["script"] = script_content
        process["command"] = script_content  # Also set command for compatibility
    else:
        # Try triple-quoted script block
        script_match = re.search(r"script\s*:\s*'''([^']*)'''", process_body, re.DOTALL)
        if script_match:
            script_content = script_match.group(1)
            process["script"] = script_content
            process["command"] = script_content  # Also set command for compatibility
        else:
            # Try shell script block
            shell_match = re.search(r"shell\s*:\s*['\"`]([^'\"`]*)['\"`]", process_body, re.DOTALL)
            if shell_match:
                script_content = shell_match.group(1)
                process["script"] = script_content
                process["command"] = script_content  # Also set command for compatibility

    # Extract publishDir
    publish_match = re.search(r'publishDir\s*["\']([^"\']+)["\']', process_body)
    if publish_match:
        process["publishDir"] = publish_match.group(1)

    # Extract resource specifications - handle different formats
    # CPU can be specified as "cpus 4" or "cpus = 4"
    cpus_match = re.search(r"cpus\s+(?:=\s*)?(\d+)", process_body)
    if cpus_match:
        process["cpus"] = int(cpus_match.group(1))
    
    # Memory
    mem_match = re.search(r"memory\s+(?:=\s*)?(.+)", process_body)
    if mem_match:
        mem_val = mem_match.group(1).strip().strip("'\"` ")
        process["memory"] = mem_val
        process["mem_mb"] = parse_memory_string(mem_val)

    # Disk
    disk_match = re.search(r"disk\s+(?:=\s*)?(.+)", process_body)
    if disk_match:
        disk_val = disk_match.group(1).strip().strip("'\"` ")
        process["disk_mb"] = parse_disk_string(disk_val)

    # Time
    time_match = re.search(r"time\s+(?:=\s*)?(.+)", process_body)
    if time_match:
        time_val = time_match.group(1).strip().strip("'\"` ")
        process["time_s"] = parse_time_string(time_val)
    
    # Container can be specified as "container 'image:tag'" or "container = 'image:tag'"
    container_match = re.search(r"container\s+(?:=\s*)?['\"`]([^'\"`]+)['\"`]", process_body)
    if container_match:
        process["container"] = container_match.group(1)
    
    # Conda
    conda_match = re.search(r"conda\s+['\"]([^'\"]+)['\"]", process_body)
    if conda_match:
        process["conda"] = conda_match.group(1)
    
    # Tag can be specified as "tag 'tag_name'" or "tag = 'tag_name'"
    tag_match = re.search(r"tag\s+(?:=\s*)?['\"`]([^'\"`]+)['\"`]", process_body)
    if tag_match:
        process["tag"] = tag_match.group(1)
    
    # Label can be specified as "label 'label_name'" or "label = 'label_name'"
    label_match = re.search(r"label\s+(?:=\s*)?['\"`]([^'\"`]+)['\"`]", process_body)
    if label_match:
        process["label"] = label_match.group(1)

    # Accelerator can be specified as "accelerator 2, type: 'nvidia-tesla-v100'"
    accelerator_match = re.search(r"accelerator\s+(\d+)(?:,\s*type:\s*['\"`]([^'\"`]+)['\"`])?", process_body)
    if accelerator_match:
        process["gpu"] = int(accelerator_match.group(1))
        if accelerator_match.group(2):
            process["gpu_type"] = accelerator_match.group(2)

    # maxRetries
    max_retries_match = re.search(r"maxRetries\s+(\d+)", process_body)
    if max_retries_match:
        process["retry_count"] = int(max_retries_match.group(1))

    return process


def _extract_dependencies(
    workflow_def: str, debug: bool = False
) -> List[Tuple[str, str]]:
    """Extract dependencies from workflow definition."""
    dependencies = []
    
    if not workflow_def.strip():
        return dependencies
    
    if debug:
        logger.debug(f"DEBUG: Analyzing workflow definition: {workflow_def}")
    
    # Track process invocations and their outputs
    process_invocations = []
    
    # Find process invocations in the workflow block
    # Pattern: process_name(input_channel) or process_name()
    process_calls = re.finditer(r'(\w+)\s*\(\s*([^)]*)\s*\)', workflow_def)
    
    for match in process_calls:
        process_name = match.group(1)
        input_args = match.group(2).strip()
        
        # Skip if it's not a process call (could be function calls)
        if process_name.lower() in ['channel', 'frompath', 'fromlist', 'from', 'collect', 'map', 'filter']:
            continue
            
        process_invocations.append((process_name, input_args))
        if debug:
            logger.debug(f"DEBUG: Found process call: {process_name}({input_args})")
    
    # Extract dependencies based on process invocation order and input/output relationships
    for i, (process_name, input_args) in enumerate(process_invocations):
        if not input_args:
            continue
            
        # Look for channel variables that might be outputs from previous processes
        # This is a simplified approach - in a real implementation, you'd track channel definitions
        for j, (prev_process, prev_args) in enumerate(process_invocations[:i]):
            # If this process uses output from a previous process, create dependency
            if prev_process in input_args or f"{prev_process}_ch" in input_args:
                dependencies.append((prev_process, process_name))
                if debug:
                    logger.debug(f"DEBUG: Found dependency: {prev_process} -> {process_name}")
    
    # If no explicit dependencies found, create linear dependencies based on invocation order
    if not dependencies and len(process_invocations) > 1:
        for i in range(len(process_invocations) - 1):
            prev_process = process_invocations[i][0]
            next_process = process_invocations[i + 1][0]
            dependencies.append((prev_process, next_process))
            if debug:
                logger.debug(f"DEBUG: Created linear dependency: {prev_process} -> {next_process}")
    
    return dependencies


def _convert_process_to_task_data(process_name: str, process_info: Dict, config: Dict, debug: bool = False) -> Dict[str, Any]:
    """Convert Nextflow process data to task data format expected by base importer."""
    task_data = {
        "label": process_name,
        "doc": process_info.get("doc", ""),
        "inputs": process_info.get("inputs", []),
        "outputs": process_info.get("outputs", []),  # Ensure this is a list, not dict
    }
    
    # CPU
    if "cpus" in process_info:
        cpu_value = NextflowSectionParser.parse_resource_value(process_info["cpus"])
        if cpu_value is not None:
            task_data["cpu"] = cpu_value
    # Memory
    if "mem_mb" in process_info:
        mem_value = process_info["mem_mb"]
        mem_value = parse_memory_string(mem_value) if not isinstance(mem_value, int) else mem_value
        if mem_value is not None:
            task_data["mem_mb"] = mem_value
    # Disk
    if "disk_mb" in process_info:
        disk_value = process_info["disk_mb"]
        disk_value = parse_disk_string(disk_value) if not isinstance(disk_value, int) else disk_value
        if disk_value is not None:
            task_data["disk_mb"] = disk_value
    # Time
    if "time_s" in process_info:
        time_value = process_info["time_s"]
        time_value = parse_time_string(time_value) if not isinstance(time_value, int) else time_value
        if time_value is not None:
            task_data["time_s"] = time_value
    # Container
    if "container" in process_info:
        task_data["container"] = process_info["container"]
    # Command/script
    if "script" in process_info:
        task_data["script"] = process_info["script"]
        task_data["command"] = process_info["script"]  # Also set command
    elif "command" in process_info:
        task_data["command"] = process_info["command"]
    # GPU
    if "gpu" in process_info:
        gpu_value = NextflowSectionParser.parse_resource_value(process_info["gpu"])
        if gpu_value is not None:
            task_data["gpu"] = gpu_value
    # Conda
    if "conda" in process_info:
        conda_value = process_info["conda"]
        if conda_value:
            task_data["conda"] = conda_value
    # Retry count
    if "retry_count" in process_info:
        retry_value = NextflowSectionParser.parse_resource_value(process_info["retry_count"])
        if retry_value is not None:
            task_data["retry_count"] = retry_value
    # Apply config defaults if not specified
    process_config = config.get("process", {})
    defaults = process_config.get("defaults", {})
    with_name = process_config.get("withName", {})
    # Apply withName specific config
    if process_name in with_name:
        specific_config = with_name[process_name]
        if "cpus" in specific_config and "cpu" not in task_data:
            cpu_value = NextflowSectionParser.parse_resource_value(specific_config["cpus"])
            if cpu_value is not None:
                task_data["cpu"] = cpu_value
        if "memory" in specific_config and "mem_mb" not in task_data:
            mem_value = parse_memory_string(specific_config["memory"])
            if mem_value is not None:
                task_data["mem_mb"] = mem_value
        if "disk" in specific_config and "disk_mb" not in task_data:
            disk_value = parse_disk_string(specific_config["disk"])
            if disk_value is not None:
                task_data["disk_mb"] = disk_value
        if "container" in specific_config and "container" not in task_data:
            task_data["container"] = specific_config["container"]
    # Apply defaults if still not specified
    if "cpu" not in task_data and "cpus" in defaults:
        cpu_value = NextflowSectionParser.parse_resource_value(defaults["cpus"])
        if cpu_value is not None:
            task_data["cpu"] = cpu_value
    if "mem_mb" not in task_data and "memory" in defaults:
        mem_value = parse_memory_string(defaults["memory"])
        if mem_value is not None:
            task_data["mem_mb"] = mem_value
    if "disk_mb" not in task_data and "disk" in defaults:
        disk_value = parse_disk_string(defaults["disk"])
        if disk_value is not None:
            task_data["disk_mb"] = disk_value
    if "container" not in task_data and "container" in defaults:
        task_data["container"] = defaults["container"]
    return task_data





def _convert_memory_to_mb(memory_str: str) -> Optional[int]:
    """Convert memory string to MB using shared utility."""
    return parse_memory_string(memory_str)


def _convert_time_to_seconds(time_str: str) -> Optional[int]:
    """Convert time string to seconds using shared utility."""
    return parse_time_string(time_str)
