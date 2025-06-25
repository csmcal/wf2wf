"""wf2wf.importers.nextflow – Nextflow DSL2 ➜ Workflow IR

This module converts Nextflow DSL2 workflows to the wf2wf intermediate representation.
It parses main.nf files, module files, and nextflow.config files to extract:
- Process definitions
- Resource specifications  
- Container/conda environments
- Dependencies and data flow
- Configuration parameters
"""

import re
import subprocess
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from wf2wf.core import Workflow, Task, Edge, ResourceSpec, EnvironmentSpec


def to_workflow(path: str | Path, **opts: Any) -> Workflow:
    """Convert a Nextflow workflow to wf2wf IR.
    
    Args:
        path: Path to main.nf file or directory containing it
        **opts: Additional options (verbose, debug, etc.)
        
    Returns:
        Workflow object representing the Nextflow pipeline
    """
    nf_path = Path(path)
    verbose = opts.get('verbose', False)
    debug = opts.get('debug', False)
    
    if verbose:
        print(f"Parsing Nextflow workflow: {nf_path}")
    
    # Handle directory vs file input
    if nf_path.is_dir():
        main_nf = nf_path / "main.nf"
        config_file = nf_path / "nextflow.config"
        workflow_dir = nf_path
    else:
        main_nf = nf_path
        workflow_dir = nf_path.parent
        # Look for config files in order of preference
        config_file = None
        for config_name in ["nextflow.config", "test.config", "config.nf"]:
            potential_config = workflow_dir / config_name
            if potential_config.exists():
                config_file = potential_config
                break
    
    if not main_nf.exists():
        raise FileNotFoundError(f"Nextflow main file not found: {main_nf}")
    
    try:
        # Parse configuration first (for defaults)
        config = _parse_nextflow_config(config_file, debug=debug) if config_file and config_file.exists() else {}
        
        # Parse main workflow file
        processes, workflow_def, includes = _parse_main_nf(main_nf, debug=debug)
        
        # Parse included modules
        module_processes = {}
        for include_path in includes:
            module_path = workflow_dir / include_path
            # Try with .nf extension if file doesn't exist
            if not module_path.exists() and not include_path.endswith('.nf'):
                module_path = workflow_dir / (include_path + '.nf')
            
            if module_path.exists():
                mod_processes = _parse_module_file(module_path, debug=debug)
                module_processes.update(mod_processes)
            elif debug:
                print(f"DEBUG: Module file not found: {module_path}")
        
        # Combine all processes
        all_processes = {**processes, **module_processes}
        
        # Extract dependencies from workflow definition
        dependencies = _extract_dependencies(workflow_def, debug=debug)
        
        # Create workflow object
        workflow_name = workflow_dir.name if workflow_dir.name != "." else "nextflow_workflow"
        wf = Workflow(
            name=workflow_name,
            config=config.get('params', {}),
            meta={
                'source_format': 'nextflow',
                'nextflow_config': config
            }
        )
        
        # Convert processes to tasks
        for proc_name, proc_info in all_processes.items():
            task = _create_task_from_process(proc_name, proc_info, config, debug=debug)
            wf.add_task(task)
        
        # Add dependencies
        for parent, child in dependencies:
            if parent in wf.tasks and child in wf.tasks:
                wf.add_edge(parent, child)
            elif debug:
                print(f"DEBUG: Skipping edge {parent} -> {child} (missing tasks)")
        
        if verbose:
            print(f"Converted Nextflow workflow: {len(wf.tasks)} processes, {len(wf.edges)} dependencies")
        
        return wf
        
    except Exception as e:
        raise RuntimeError(f"Failed to parse Nextflow workflow: {e}")


def _parse_nextflow_config(config_path: Path, debug: bool = False) -> Dict[str, Any]:
    """Parse nextflow.config file."""
    if debug:
        print(f"DEBUG: Parsing config file: {config_path}")
    
    config = {
        'params': {},
        'process': {},
        'executor': {},
        'profiles': {}
    }
    
    try:
        content = config_path.read_text()
        
        # Parse params block
        params_match = re.search(r'params\s*\{([^}]*)\}', content, re.DOTALL)
        if params_match:
            params_content = params_match.group(1)
            config['params'] = _parse_config_block(params_content)
        
        # Parse process block
        process_match = re.search(r'process\s*\{([^}]*)\}', content, re.DOTALL)
        if process_match:
            process_content = process_match.group(1)
            config['process'] = _parse_process_config(process_content)
        
        # Parse executor block
        executor_match = re.search(r'executor\s*\{([^}]*)\}', content, re.DOTALL)
        if executor_match:
            executor_content = executor_match.group(1)
            config['executor'] = _parse_config_block(executor_content)
        
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
    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('//'):
            continue
        
        # Match key = value
        match = re.match(r'(\w+)\s*=\s*(.+)', line)
        if match:
            key = match.group(1)
            value = match.group(2).strip()
            
            # Remove quotes and parse basic types
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            elif value.lower() in ['true', 'false']:
                value = value.lower() == 'true'
            elif value.isdigit():
                value = int(value)
            elif re.match(r'^\d+\.\d+$', value):
                value = float(value)
            
            config[key] = value
    
    return config


def _parse_process_config(content: str) -> Dict[str, Any]:
    """Parse process configuration block with withName directives."""
    config = {
        'defaults': {},
        'withName': {}
    }
    
    lines = content.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        if not line or line.startswith('//'):
            i += 1
            continue
        
        # Handle withName blocks
        with_name_match = re.match(r"withName:\s*['\"]?(\w+)['\"]?\s*\{", line)
        if with_name_match:
            process_name = with_name_match.group(1)
            i += 1
            
            # Parse the withName block
            block_content = []
            brace_count = 1
            
            while i < len(lines) and brace_count > 0:
                block_line = lines[i].strip()
                if '{' in block_line:
                    brace_count += block_line.count('{')
                if '}' in block_line:
                    brace_count -= block_line.count('}')
                
                if brace_count > 0:
                    block_content.append(block_line)
                i += 1
            
            config['withName'][process_name] = _parse_config_block('\n'.join(block_content))
        
        # Handle default process settings
        elif '=' in line:
            key_value = line.split('=', 1)
            if len(key_value) == 2:
                key = key_value[0].strip()
                value = key_value[1].strip()
                config['defaults'][key] = value
        
        i += 1
    
    return config


def _parse_main_nf(main_path: Path, debug: bool = False) -> Tuple[Dict, str, List[str]]:
    """Parse main.nf file and extract processes, workflow, and includes."""
    if debug:
        print(f"DEBUG: Parsing main.nf: {main_path}")
    
    content = main_path.read_text()
    
    # Extract include statements
    includes = []
    include_pattern = r"include\s*\{\s*(\w+)\s*\}\s*from\s*['\"]([^'\"]+)['\"]"
    for match in re.finditer(include_pattern, content):
        include_file = match.group(2)
        includes.append(include_file)
    
    # Extract workflow block
    workflow_match = re.search(r'workflow\s*\{([^}]*)\}', content, re.DOTALL)
    workflow_def = workflow_match.group(1) if workflow_match else ""
    
    # Extract process definitions (if any in main.nf)
    processes = _extract_processes(content, debug=debug)
    
    if debug:
        print(f"DEBUG: Found {len(processes)} processes, {len(includes)} includes")
    
    return processes, workflow_def, includes


def _parse_module_file(module_path: Path, debug: bool = False) -> Dict[str, Dict]:
    """Parse a Nextflow module file."""
    if debug:
        print(f"DEBUG: Parsing module: {module_path}")
    
    content = module_path.read_text()
    return _extract_processes(content, debug=debug)


def _extract_processes(content: str, debug: bool = False) -> Dict[str, Dict]:
    """Extract process definitions from Nextflow content."""
    processes = {}
    
    # Find all process blocks - use a more robust approach that handles nested braces
    lines = content.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Look for process definition start
        process_match = re.match(r'process\s+(\w+)\s*\{', line)
        if process_match:
            process_name = process_match.group(1)
            
            # Find the matching closing brace
            brace_count = 1
            process_lines = []
            i += 1
            
            while i < len(lines) and brace_count > 0:
                current_line = lines[i]
                
                # Count braces, but ignore those inside triple quotes
                in_triple_quotes = False
                j = 0
                while j < len(current_line):
                    if current_line[j:j+3] in ['"""', "'''"]:
                        in_triple_quotes = not in_triple_quotes
                        j += 3
                    elif not in_triple_quotes:
                        if current_line[j] == '{':
                            brace_count += 1
                        elif current_line[j] == '}':
                            brace_count -= 1
                        j += 1
                    else:
                        j += 1
                
                if brace_count > 0:
                    process_lines.append(current_line)
                
                i += 1
            
            # Parse the process body
            process_body = '\n'.join(process_lines)
            process_info = _parse_process_definition(process_body, debug=debug)
            processes[process_name] = process_info
            
            if debug:
                print(f"DEBUG: Extracted process {process_name}")
        else:
            i += 1
    
    return processes


def _parse_process_definition(process_body: str, debug: bool = False) -> Dict[str, Any]:
    """Parse a single process definition body (content between braces)."""
    process_info = {
        'name': '',
        'script': '',
        'inputs': [],
        'outputs': [],
        'resources': {},
        'container': None,
        'conda': None,
        'tag': None,
        'publishDir': None,
        'errorStrategy': None,
        'maxRetries': 0,
        'directives': {}
    }
    
    lines = process_body.split('\n')
    current_section = None
    script_lines = []
    in_script = False
    
    for line in lines:
        line = line.strip()
        
        if not line or line.startswith('//'):
            continue
        
        # Script section
        if line.startswith('script:') or line == '"""' or line == "'''":
            in_script = True
            current_section = 'script'
            continue
        
        if in_script:
            if line == '"""' or line == "'''":
                in_script = False
                process_info['script'] = '\n'.join(script_lines)
                script_lines = []
            else:
                script_lines.append(line)
            continue
        
        # Input section
        if line.startswith('input:'):
            current_section = 'input'
            continue
        
        # Output section  
        if line.startswith('output:'):
            current_section = 'output'
            continue
        
        # Process current section
        if current_section == 'input':
            input_match = re.match(r'(path|val|file|tuple|each)\s+(.+)', line)
            if input_match:
                input_type = input_match.group(1)
                input_spec = input_match.group(2)
                process_info['inputs'].append({'type': input_type, 'spec': input_spec})
        
        elif current_section == 'output':
            # Handle outputs with optional emit names
            if ', emit:' in line:
                output_match = re.match(r'(path|val|file|tuple)\s+(.+?),\s*emit:\s*(\w+)', line)
                if output_match:
                    output_type = output_match.group(1)
                    output_spec = output_match.group(2).strip()
                    emit_name = output_match.group(3)
                    process_info['outputs'].append({
                        'type': output_type, 
                        'spec': output_spec,
                        'emit': emit_name
                    })
            else:
                output_match = re.match(r'(path|val|file|tuple)\s+(.+)', line)
                if output_match:
                    output_type = output_match.group(1)
                    output_spec = output_match.group(2).strip()
                    process_info['outputs'].append({
                        'type': output_type, 
                        'spec': output_spec,
                        'emit': None
                    })
        
        # Resource directives
        elif line.startswith('cpus '):
            process_info['resources']['cpus'] = _parse_resource_value(line.split()[1])
        elif line.startswith('memory '):
            process_info['resources']['memory'] = _parse_resource_value(line.split()[1])
        elif line.startswith('disk '):
            process_info['resources']['disk'] = _parse_resource_value(line.split()[1])
        elif line.startswith('time '):
            process_info['resources']['time'] = _parse_resource_value(line.split()[1])
        elif line.startswith('accelerator '):
            # Parse accelerator directive: accelerator 1, type: 'nvidia-tesla-k80'
            accel_match = re.match(r'accelerator\s+(\d+)(?:,\s*type:\s*[\'"]([^\'"]+)[\'"])?', line)
            if accel_match:
                process_info['resources']['accelerator'] = {
                    'count': int(accel_match.group(1)),
                    'type': accel_match.group(2) if accel_match.group(2) else 'gpu'
                }
        
        # Container and environment
        elif line.startswith('container '):
            container_match = re.match(r"container\s+['\"]([^'\"]+)['\"]", line)
            if container_match:
                process_info['container'] = container_match.group(1)
        elif line.startswith('conda '):
            conda_match = re.match(r"conda\s+['\"]([^'\"]+)['\"]", line)
            if conda_match:
                process_info['conda'] = conda_match.group(1)
        
        # Other directives
        elif line.startswith('tag '):
            tag_match = re.match(r"tag\s+['\"]([^'\"]+)['\"]", line)
            if tag_match:
                process_info['tag'] = tag_match.group(1)
        elif line.startswith('publishDir '):
            publish_match = re.match(r"publishDir\s+['\"]([^'\"]+)['\"]", line)
            if publish_match:
                process_info['publishDir'] = publish_match.group(1)
        elif line.startswith('errorStrategy '):
            error_match = re.match(r"errorStrategy\s+['\"]([^'\"]+)['\"]", line)
            if error_match:
                process_info['errorStrategy'] = error_match.group(1)
        elif line.startswith('maxRetries '):
            retry_match = re.match(r"maxRetries\s+(\d+)", line)
            if retry_match:
                process_info['maxRetries'] = int(retry_match.group(1))
    
    return process_info


def _parse_resource_value(value_str: str) -> Any:
    """Parse resource value (e.g., '4', '8.GB', '2h')."""
    value_str = value_str.strip('\'"')
    
    # Handle memory units
    memory_match = re.match(r'(\d+(?:\.\d+)?)\s*\.?(GB|MB|KB|TB)', value_str, re.IGNORECASE)
    if memory_match:
        number = float(memory_match.group(1))
        unit = memory_match.group(2).upper()
        
        if unit == 'GB':
            return f"{number}GB"
        elif unit == 'MB':
            return f"{number}MB"
        elif unit == 'TB':
            return f"{number}TB"
        elif unit == 'KB':
            return f"{number}KB"
    
    # Handle time units
    time_match = re.match(r'(\d+(?:\.\d+)?)\s*([hms])', value_str)
    if time_match:
        number = float(time_match.group(1))
        unit = time_match.group(2)
        return f"{number}{unit}"
    
    # Handle plain numbers
    if value_str.isdigit():
        return int(value_str)
    
    try:
        return float(value_str)
    except ValueError:
        return value_str


def _extract_dependencies(workflow_def: str, debug: bool = False) -> List[Tuple[str, str]]:
    """Extract process dependencies from workflow definition."""
    dependencies = []
    
    # Look for process calls and .out references
    # Pattern: PROCESS_NAME(input) followed by OTHER_PROCESS(PROCESS_NAME.out)
    lines = workflow_def.split('\n')
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Find process calls with .out references
        # Example: ANALYZE_DATA(PREPARE_DATA.out)
        call_match = re.match(r'(\w+)\(([^)]*)\)', line)
        if call_match:
            process_name = call_match.group(1)
            inputs = call_match.group(2)
            
            # Look for .out references in inputs
            out_refs = re.findall(r'(\w+)\.out', inputs)
            for parent_process in out_refs:
                dependencies.append((parent_process, process_name))
                if debug:
                    print(f"DEBUG: Found dependency: {parent_process} -> {process_name}")
    
    return dependencies


def _create_task_from_process(process_name: str, process_info: Dict, config: Dict, debug: bool = False) -> Task:
    """Convert a Nextflow process to a wf2wf Task."""
    
    # Extract inputs and outputs
    inputs = []
    outputs = []
    
    for input_spec in process_info.get('inputs', []):
        if input_spec['type'] in ['path', 'val']:
            # Extract variable names from input specifications
            spec = input_spec['spec']
            # Remove quotes if present
            if spec.startswith('"') and spec.endswith('"'):
                spec = spec[1:-1]
            elif spec.startswith("'") and spec.endswith("'"):
                spec = spec[1:-1]
            inputs.append(spec)
    
    for output_spec in process_info.get('outputs', []):
        if output_spec['type'] == 'path':
            # Extract file names from path specifications
            spec = output_spec['spec']
            # Remove quotes if present
            if spec.startswith('"') and spec.endswith('"'):
                spec = spec[1:-1]
            elif spec.startswith("'") and spec.endswith("'"):
                spec = spec[1:-1]
            outputs.append(spec)
    
    # Create resource specification
    resources = ResourceSpec()
    proc_resources = process_info.get('resources', {})
    
    if 'cpus' in proc_resources:
        resources.cpu = int(proc_resources['cpus'])
    
    if 'memory' in proc_resources:
        memory_str = str(proc_resources['memory'])
        memory_mb = _convert_memory_to_mb(memory_str)
        if memory_mb:
            resources.mem_mb = memory_mb
    
    if 'disk' in proc_resources:
        disk_str = str(proc_resources['disk'])
        disk_mb = _convert_memory_to_mb(disk_str)  # Same conversion logic
        if disk_mb:
            resources.disk_mb = disk_mb
    
    if 'time' in proc_resources:
        time_str = str(proc_resources['time'])
        time_seconds = _convert_time_to_seconds(time_str)
        if time_seconds:
            resources.time_s = time_seconds
    
    if 'accelerator' in proc_resources:
        accel_info = proc_resources['accelerator']
        if isinstance(accel_info, dict):
            resources.gpu = accel_info.get('count', 1)
        else:
            resources.gpu = 1
    
    # Apply config defaults and overrides
    process_config = config.get('process', {})
    
    # Apply withName configuration (process-specific settings take precedence)
    with_name_config = process_config.get('withName', {}).get(process_name, {})
    if with_name_config:
        # Only apply config if not already set in process definition
        if 'cpus' in with_name_config and not resources.cpu:
            resources.cpu = int(with_name_config['cpus'])
        if 'memory' in with_name_config and not resources.mem_mb:
            memory_mb = _convert_memory_to_mb(str(with_name_config['memory']))
            if memory_mb:
                resources.mem_mb = memory_mb
    
    # Create environment specification
    environment = EnvironmentSpec()
    
    if process_info.get('container'):
        environment.container = process_info['container']
    elif with_name_config.get('container'):
        environment.container = with_name_config['container']
    
    if process_info.get('conda'):
        environment.conda = process_info['conda']
    
    # Create task
    task = Task(
        id=process_name,
        command=process_info.get('script', ''),
        inputs=inputs,
        outputs=outputs,
        resources=resources,
        environment=environment,
        retry=process_info.get('maxRetries', 0),
        priority=0  # Nextflow doesn't have explicit priorities
    )
    
    # Add Nextflow-specific metadata
    task.meta.update({
        'nextflow_process': process_name,
        'tag': process_info.get('tag'),
        'publishDir': process_info.get('publishDir'),
        'errorStrategy': process_info.get('errorStrategy'),
        'directives': process_info.get('directives', {})
    })
    
    return task


def _convert_memory_to_mb(memory_str: str) -> Optional[int]:
    """Convert memory string to MB."""
    if not memory_str:
        return None
    
    # Handle Nextflow memory format (e.g., "8.GB", "4GB", "1024MB")
    match = re.match(r'(\d+(?:\.\d+)?)\s*\.?(GB|MB|KB|TB)', memory_str, re.IGNORECASE)
    if match:
        number = float(match.group(1))
        unit = match.group(2).upper()
        
        if unit == 'GB':
            return int(number * 1024)
        elif unit == 'MB':
            return int(number)
        elif unit == 'TB':
            return int(number * 1024 * 1024)
        elif unit == 'KB':
            return int(number / 1024)
    
    # Try to parse as plain number (assume MB)
    try:
        return int(float(memory_str))
    except ValueError:
        return None


def _convert_time_to_seconds(time_str: str) -> Optional[int]:
    """Convert time string to seconds."""
    if not time_str:
        return None
    
    # Handle time formats (e.g., "2h", "30m", "120s")
    match = re.match(r'(\d+(?:\.\d+)?)\s*([hms])', time_str)
    if match:
        number = float(match.group(1))
        unit = match.group(2)
        
        if unit == 'h':
            return int(number * 3600)
        elif unit == 'm':
            return int(number * 60)
        elif unit == 's':
            return int(number)
    
    # Try to parse as plain number (assume seconds)
    try:
        return int(float(time_str))
    except ValueError:
        return None 