"""wf2wf.importers.nextflow – Nextflow DSL2 ➜ Workflow IR

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


class NextflowImporter(BaseImporter):
    """Nextflow importer using shared base infrastructure."""
    
    def _parse_source(self, path: Path, **opts: Any) -> Dict[str, Any]:
        """Parse Nextflow workflow and extract all information."""
        debug = opts.get("debug", False)
        verbose = self.verbose

        if verbose:
            print(f"Parsing Nextflow workflow: {path}")

        # Handle directory vs file input
        if path.is_dir():
            main_nf = path / "main.nf"
            config_file = path / "nextflow.config"
            workflow_dir = path
        else:
            main_nf = path
            workflow_dir = path.parent
            # Look for config files in order of preference
            config_file = None
            for config_name in ["nextflow.config", "test.config", "config.nf"]:
                potential_config = workflow_dir / config_name
                if potential_config.exists():
                    config_file = potential_config
                    break

        if not main_nf.exists():
            raise FileNotFoundError(f"Nextflow main file not found: {main_nf}")

        # Parse configuration first (for defaults)
        config = (
            _parse_nextflow_config(config_file, debug=debug)
            if config_file and config_file.exists()
            else {}
        )

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
                mod_processes = _parse_module_file(module_path, debug=debug)
                module_processes.update(mod_processes)
            elif debug:
                print(f"DEBUG: Module file not found: {module_path}")

        # Combine all processes
        all_processes = {**processes, **module_processes}

        # Extract dependencies from workflow definition
        dependencies = _extract_dependencies(workflow_def, debug=debug)

        # Get workflow name
        workflow_name = (
            workflow_dir.name if workflow_dir.name != "." else "nextflow_workflow"
        )

        return {
            "workflow_name": workflow_name,
            "config": config,
            "processes": all_processes,
            "dependencies": dependencies,
            "workflow_def": workflow_def,
            "includes": includes,
            "workflow_dir": workflow_dir,
        }
    
    def _create_basic_workflow(self, parsed_data: Dict[str, Any]) -> Workflow:
        """Create basic workflow from parsed Nextflow data."""
        workflow_name = parsed_data["workflow_name"]
        config = parsed_data["config"]
        
        # Create workflow with Nextflow-specific execution model
        workflow = Workflow(
            name=workflow_name,
            version="1.0",
            execution_model=EnvironmentSpecificValue("shared_filesystem", ["shared_filesystem"]),
        )
        
        # Add metadata
        workflow.metadata = MetadataSpec(
            source_format="nextflow",
            source_file=str(parsed_data.get("workflow_dir", "")),
            format_specific={"nextflow_config": config},
        )
        
        return workflow
    
    def _extract_tasks(self, parsed_data: Dict[str, Any]) -> List[Task]:
        """Extract tasks from parsed Nextflow data."""
        processes = parsed_data["processes"]
        config = parsed_data["config"]
        debug = parsed_data.get("debug", False)
        
        tasks = []
        for proc_name, proc_info in processes.items():
            task = _create_task_from_process(proc_name, proc_info, config, debug=debug)
            tasks.append(task)
        
        return tasks
    
    def _extract_edges(self, parsed_data: Dict[str, Any]) -> List[Edge]:
        """Extract edges from parsed Nextflow data."""
        dependencies = parsed_data["dependencies"]
        return [Edge(parent=parent, child=child) for parent, child in dependencies]
    
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
        print(f"DEBUG: Parsing config file: {config_path}")

    config = {"params": {}, "process": {}, "executor": {}, "profiles": {}}

    try:
        content = config_path.read_text()

        # Parse params block
        params_match = re.search(r"params\s*\{([^}]*)\}", content, re.DOTALL)
        if params_match:
            params_content = params_match.group(1)
            config["params"] = _parse_config_block(params_content)

        # Parse process block
        process_match = re.search(r"process\s*\{([^}]*)\}", content, re.DOTALL)
        if process_match:
            process_content = process_match.group(1)
            config["process"] = _parse_process_config(process_content)

        # Parse executor block
        executor_match = re.search(r"executor\s*\{([^}]*)\}", content, re.DOTALL)
        if executor_match:
            executor_content = executor_match.group(1)
            config["executor"] = _parse_config_block(executor_content)

        if debug:
            print(f"DEBUG: Parsed config with {len(config['params'])} params")

    except Exception as e:
        if debug:
            print(f"DEBUG: Error parsing config: {e}")

    return config


def _parse_config_block(content: str) -> Dict[str, Any]:
    """Parse a configuration block (params, executor, etc.)."""
    config = {}

    # Simple key-value parsing
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("//"):
            continue

        # Match key = value
        match = re.match(r"(\w+)\s*=\s*(.+)", line)
        if match:
            key = match.group(1)
            value = match.group(2).strip()

            # Remove quotes and parse basic types
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            elif value.lower() in ["true", "false"]:
                value = value.lower() == "true"
            elif value.isdigit():
                value = int(value)
            elif re.match(r"^\d+\.\d+$", value):
                value = float(value)

            config[key] = value

    return config


def _parse_process_config(content: str) -> Dict[str, Any]:
    """Parse process configuration block with withName directives."""
    config = {"defaults": {}, "withName": {}}

    lines = content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if not line or line.startswith("//"):
            i += 1
            continue

        # Parse withName directive
        with_name_match = re.match(r'withName\s*:\s*["\']?([^"\']+)["\']?\s*\{', line)
        if with_name_match:
            process_name = with_name_match.group(1)
            # Find the closing brace
            brace_count = 1
            j = i + 1
            process_config = []
            while j < len(lines) and brace_count > 0:
                if "{" in lines[j]:
                    brace_count += lines[j].count("{")
                if "}" in lines[j]:
                    brace_count -= lines[j].count("}")
                if brace_count > 0:
                    process_config.append(lines[j])
                j += 1
            config["withName"][process_name] = _parse_config_block("\n".join(process_config))
            i = j
        else:
            # Parse default configuration
            match = re.match(r"(\w+)\s*=\s*(.+)", line)
            if match:
                key = match.group(1)
                value = match.group(2).strip()
                config["defaults"][key] = value
            i += 1

    return config


def _parse_main_nf(main_path: Path, debug: bool = False) -> Tuple[Dict, str, List[str]]:
    """Parse main.nf file."""
    if debug:
        print(f"DEBUG: Parsing main file: {main_path}")

    content = main_path.read_text()
    
    # Extract includes
    includes = []
    include_matches = re.finditer(r'include\s+["\']([^"\']+)["\']', content)
    for match in include_matches:
        includes.append(match.group(1))

    # Extract processes
    processes = _extract_processes(content, debug=debug)

    # Extract workflow definition
    workflow_match = re.search(r"workflow\s*\{([^}]*)\}", content, re.DOTALL)
    workflow_def = workflow_match.group(1) if workflow_match else ""

    return processes, workflow_def, includes


def _parse_module_file(module_path: Path, debug: bool = False) -> Dict[str, Dict]:
    """Parse a module file."""
    if debug:
        print(f"DEBUG: Parsing module: {module_path}")
    
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

    return processes


def _parse_process_definition(process_body: str, debug: bool = False) -> Dict[str, Any]:
    """Parse a process definition."""
    process = {
        "inputs": {},
        "outputs": {},
        "script": "",
        "publishDir": "",
        "publishDirMode": "copy",
        "validExitStatus": [0],
        "errorStrategy": "terminate",
        "maxRetries": 3,
        "maxErrors": -1,
        "memory": None,
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
        process["inputs"] = _parse_process_inputs(input_content)

    # Extract output section
    output_match = re.search(r"output\s*:\s*\{([^}]*)\}", process_body, re.DOTALL)
    if output_match:
        output_content = output_match.group(1)
        process["outputs"] = _parse_process_outputs(output_content)

    # Extract script section
    script_match = re.search(r"script\s*:\s*['\"`]([^'\"`]*)['\"`]", process_body, re.DOTALL)
    if script_match:
        process["script"] = script_match.group(1)
    else:
        # Try shell script block
        shell_match = re.search(r"shell\s*:\s*['\"`]([^'\"`]*)['\"`]", process_body, re.DOTALL)
        if shell_match:
            process["script"] = shell_match.group(1)

    # Extract publishDir
    publish_match = re.search(r'publishDir\s*["\']([^"\']+)["\']', process_body)
    if publish_match:
        process["publishDir"] = publish_match.group(1)

    # Extract resource specifications
    resource_patterns = {
        "memory": r"memory\s*=\s*['\"`]([^'\"`]+)['\"`]",
        "cpus": r"cpus\s*=\s*(\d+)",
        "disk": r"disk\s*=\s*['\"`]([^'\"`]+)['\"`]",
        "time": r"time\s*=\s*['\"`]([^'\"`]+)['\"`]",
        "container": r'container\s*["\']([^"\']+)["\']',
        "conda": r'conda\s*["\']([^"\']+)["\']',
        "module": r'module\s*["\']([^"\']+)["\']',
        "tag": r'tag\s*["\']([^"\']+)["\']',
        "label": r'label\s*["\']([^"\']+)["\']',
    }

    for key, pattern in resource_patterns.items():
        match = re.search(pattern, process_body)
        if match:
            process[key] = match.group(1)

    return process


def _parse_process_inputs(input_content: str) -> Dict[str, Any]:
    """Parse process input section."""
    inputs = {}
    
    for line in input_content.split("\n"):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        
        # Match input declarations
        match = re.match(r"(\w+)\s*(\w+)\s*(\w+)", line)
        if match:
            qualifier = match.group(1)  # val, path, env, etc.
            type_name = match.group(2)  # file, string, int, etc.
            var_name = match.group(3)   # variable name
            inputs[var_name] = {"qualifier": qualifier, "type": type_name}
    
    return inputs


def _parse_process_outputs(output_content: str) -> Dict[str, Any]:
    """Parse process output section."""
    outputs = {}
    
    for line in output_content.split("\n"):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        
        # Match output declarations
        match = re.match(r"(\w+)\s*(\w+)\s*(\w+)", line)
        if match:
            qualifier = match.group(1)  # val, path, env, etc.
            type_name = match.group(2)  # file, string, int, etc.
            var_name = match.group(3)   # variable name
            outputs[var_name] = {"qualifier": qualifier, "type": type_name}
    
    return outputs


def _parse_resource_value(value_str: str) -> Any:
    """Parse resource value string."""
    if not value_str:
        return None
    
    # Remove quotes
    value_str = value_str.strip('"\'')
    
    # Parse memory values
    if value_str.endswith("GB"):
        return int(float(value_str[:-2]) * 1024)  # Convert to MB
    elif value_str.endswith("MB"):
        return int(value_str[:-2])
    elif value_str.endswith("KB"):
        return int(value_str[:-2]) // 1024  # Convert to MB
    
    # Parse time values
    if value_str.endswith("h"):
        return int(float(value_str[:-1]) * 3600)  # Convert to seconds
    elif value_str.endswith("m"):
        return int(float(value_str[:-1]) * 60)  # Convert to seconds
    elif value_str.endswith("s"):
        return int(value_str[:-1])
    
    # Parse numeric values
    try:
        if "." in value_str:
            return float(value_str)
        else:
            return int(value_str)
    except ValueError:
        return value_str


def _extract_dependencies(
    workflow_def: str, debug: bool = False
) -> List[Tuple[str, str]]:
    """Extract dependencies from workflow definition."""
    dependencies = []
    
    # Look for collect operations which indicate dependencies
    collect_matches = re.finditer(r"(\w+)\s*\.\s*collect\s*\(\s*\)", workflow_def)
    for match in collect_matches:
        channel_name = match.group(1)
        # This is a simplified dependency extraction
        # In a real implementation, you'd need to track channel definitions
        if debug:
            print(f"DEBUG: Found collect operation on channel: {channel_name}")
    
    return dependencies


def _create_task_from_process(
    process_name: str, process_info: Dict, config: Dict, debug: bool = False
) -> Task:
    """Create a Task from a Nextflow process definition."""
    
    # Get default configuration
    default_config = config.get("process", {}).get("defaults", {})
    process_config = config.get("process", {}).get("withName", {}).get(process_name, {})
    
    # Merge configurations (process-specific overrides defaults)
    merged_config = {**default_config, **process_config}
    
    # Extract script
    script = process_info.get("script", "")
    if not script:
        script = merged_config.get("script", "")
    
    # Extract resources
    memory = process_info.get("memory") or merged_config.get("memory")
    cpus = process_info.get("cpus") or merged_config.get("cpus")
    disk = process_info.get("disk") or merged_config.get("disk")
    time = process_info.get("time") or merged_config.get("time")
    
    # Convert memory to MB
    mem_mb = _convert_memory_to_mb(memory) if memory else 4096
    
    # Convert time to seconds
    time_s = _convert_time_to_seconds(time) if time else 3600
    
    # Extract environment
    container = process_info.get("container") or merged_config.get("container")
    conda = process_info.get("conda") or merged_config.get("conda")
    module = process_info.get("module") or merged_config.get("module")
    
    # Convert inputs and outputs to ParameterSpec
    inputs = []
    for var_name, var_info in process_info.get("inputs", {}).items():
        inputs.append(ParameterSpec(
            id=var_name,
            type=var_info.get("type", "string"),
            label=var_name,
        ))
    
    outputs = []
    for var_name, var_info in process_info.get("outputs", {}).items():
        outputs.append(ParameterSpec(
            id=var_name,
            type=var_info.get("type", "string"),
            label=var_name,
        ))
    
    # Create task with environment-specific values
    task = Task(
        id=process_name,
        label=process_info.get("label", process_name),
        doc=process_info.get("tag", ""),
        script=EnvironmentSpecificValue(script, ["shared_filesystem"]) if script else EnvironmentSpecificValue(None, ["shared_filesystem"]),
        inputs=inputs,
        outputs=outputs,
        cpu=EnvironmentSpecificValue(int(cpus) if cpus else 1, ["shared_filesystem"]),
        mem_mb=EnvironmentSpecificValue(mem_mb, ["shared_filesystem"]),
        disk_mb=EnvironmentSpecificValue(_convert_memory_to_mb(disk) if disk else 4096, ["shared_filesystem"]),
        time_s=EnvironmentSpecificValue(time_s, ["shared_filesystem"]),
        container=EnvironmentSpecificValue(container, ["shared_filesystem"]) if container else EnvironmentSpecificValue(None, ["shared_filesystem"]),
        conda=EnvironmentSpecificValue(conda, ["shared_filesystem"]) if conda else EnvironmentSpecificValue(None, ["shared_filesystem"]),
        modules=EnvironmentSpecificValue([module] if module else [], ["shared_filesystem"]),
        retry_count=EnvironmentSpecificValue(process_info.get("maxRetries", 3), ["shared_filesystem"]),
        on_failure=EnvironmentSpecificValue(process_info.get("errorStrategy", "terminate"), ["shared_filesystem"]),
    )
    
    return task


def _convert_memory_to_mb(memory_str: str) -> Optional[int]:
    """Convert memory string to MB."""
    if not memory_str:
        return None
    
    memory_str = memory_str.strip()
    
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


def _convert_time_to_seconds(time_str: str) -> Optional[int]:
    """Convert time string to seconds."""
    if not time_str:
        return None
    
    time_str = time_str.strip()
    
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
