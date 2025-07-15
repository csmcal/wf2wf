"""wf2wf.importers.dagman – Condor DAGMan ➜ Workflow IR

This module converts HTCondor DAGMan files (.dag) to the wf2wf intermediate representation.

Public API:
    to_workflow(path, **opts)   -> returns `wf2wf.core.Workflow` object
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union
import logging

from wf2wf.core import Workflow, Task, EnvironmentSpecificValue, MetadataSpec
from wf2wf.importers.base import BaseImporter


class DAGManImporter(BaseImporter):
    """DAGMan importer using shared base infrastructure."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger("wf2wf.importers.dagman")

    def _parse_source(self, path: Path, **opts: Any) -> Dict[str, Any]:
        verbose = opts.get("verbose", False)
        debug = opts.get("debug", False)
        if not path.exists():
            self.logger.error(f"DAG file not found: {path}")
            raise FileNotFoundError(f"DAG file not found: {path}")
        if verbose:
            self.logger.info(f"Parsing DAGMan file: {path}")
        dag_content = path.read_text()
        jobs, dependencies, variables, metadata = _parse_dag_file(dag_content, debug=debug)
        if not jobs:
            self.logger.error("No jobs found in DAG file")
            raise ValueError("No jobs found in DAG file")
        return {
            "jobs": jobs,
            "dependencies": dependencies,
            "variables": variables,
            "metadata": metadata,
            "dag_path": path,
            "dag_dir": path.parent
        }

    def _create_basic_workflow(self, parsed_data: Dict[str, Any]) -> Workflow:
        metadata = parsed_data.get("metadata", {})
        name = metadata.get("original_workflow_name") or parsed_data.get("name")
        
        # Fallback to DAG file stem if no name is found
        if not name and parsed_data.get("dag_path"):
            name = Path(parsed_data["dag_path"]).stem
        
        # Final fallback to a default name
        if not name:
            name = "imported_dagman_workflow"
            
        version = metadata.get("original_workflow_version") or parsed_data.get("version") or "1.0"
        wf = Workflow(
            name=name,
            version=version,
            tasks={},
            edges=[],
        )
        # Always create metadata
        if wf.metadata is None:
            wf.metadata = MetadataSpec()
        if metadata.get("workflow_metadata"):
            wf.metadata.add_format_specific("workflow_metadata", metadata["workflow_metadata"])
        # Add dag_variables if present
        dag_variables = parsed_data.get("variables")
        if dag_variables:
            wf.metadata.add_format_specific("dag_variables", dag_variables)
        # Extract and add tasks
        tasks = self._extract_tasks(parsed_data)
        for task in tasks:
            wf.add_task(task)
        # Extract and add edges
        edges = self._extract_edges(parsed_data)
        for parent, child in edges:
            wf.add_edge(parent, child)
        return wf

    def _extract_tasks(self, parsed_data: Dict[str, Any]) -> List[Task]:
        jobs = parsed_data["jobs"]
        dag_dir = parsed_data["dag_dir"]
        verbose = self.verbose
        tasks = []
        submit_files = {}
        for job_name, job_info in jobs.items():
            submit_info = {}
            if job_info.get("inline_submit"):
                submit_info = _parse_submit_content(job_info["inline_submit"], debug=False)
                if verbose:
                    self.logger.info(f"Parsed inline submit for {job_name}")
            elif job_info.get("submit_file"):
                submit_file = Path(dag_dir / job_info["submit_file"])
                if str(submit_file) not in submit_files:
                    if submit_file.exists():
                        submit_files[str(submit_file)] = _parse_submit_file(submit_file, debug=False)
                    else:
                        if verbose:
                            self.logger.warning(f"Submit file not found: {submit_file}")
                        submit_files[str(submit_file)] = {}
                submit_info = submit_files[str(submit_file)]
            else:
                if verbose:
                    self.logger.warning(f"No submit information found for job {job_name}")
            task = _create_task_from_job(job_name, job_info, submit_info, dag_dir)
            tasks.append(task)
            if verbose:
                self.logger.info(f"Added task: {task.id}")
        return tasks

    def _extract_edges(self, parsed_data: Dict[str, Any]) -> List[Tuple[str, str]]:
        edges = parsed_data["dependencies"]
        if self.verbose:
            self.logger.info(f"Extracted {len(edges)} edges from DAGMan file")
            for parent, child in edges:
                self.logger.debug(f"Edge: {parent} -> {child}")
        return edges

    def _get_source_format(self) -> str:
        return "dagman"


def to_workflow(path: Union[str, Path], **opts: Any) -> Workflow:
    """Convert DAGMan file at *path* into a Workflow IR object using shared infrastructure.

    Parameters
    ----------
    path : Union[str, Path]
        Path to the .dag file.
    name : str, optional
        Override workflow name (defaults to DAG filename stem).
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
    importer = DAGManImporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False)
    )
    return importer.import_workflow(path, **opts)


def _parse_dag_file(
    content: str, debug: bool = False
) -> Tuple[Dict[str, Dict], List[Tuple[str, str]], Dict[str, str], Dict[str, Any]]:
    """Parse DAG file content and extract jobs, dependencies, variables, and metadata."""

    jobs = {}
    dependencies = []
    variables = {}
    metadata = {}

    lines = content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        i += 1

        if not line:
            continue

        # Extract metadata from comments
        if line.startswith("#"):
            # Look for workflow metadata in comments
            if "Original workflow name:" in line:
                name = line.split("Original workflow name:", 1)[1].strip()
                metadata["original_workflow_name"] = name
                if debug:
                    print(f"DEBUG: Found original workflow name: {name}")
            elif "Original workflow version:" in line:
                version = line.split("Original workflow version:", 1)[1].strip()
                metadata["original_workflow_version"] = version
                if debug:
                    print(f"DEBUG: Found original workflow version: {version}")
            elif "Workflow metadata:" in line:
                try:
                    import json

                    metadata_str = line.split("Workflow metadata:", 1)[1].strip()
                    workflow_metadata = json.loads(metadata_str)
                    metadata["workflow_metadata"] = workflow_metadata
                    if debug:
                        print(f"DEBUG: Found workflow metadata: {workflow_metadata}")
                except (json.JSONDecodeError, ValueError) as e:
                    if debug:
                        print(f"DEBUG: Could not parse workflow metadata: {e}")
            continue

        try:
            # JOB jobname submit_file OR JOB jobname { ... }
            job_match = re.match(r"^JOB\s+(\S+)\s+(.*)$", line)
            if job_match:
                job_name = job_match.group(1)
                job_spec = job_match.group(2).strip()

                if job_spec.startswith("{"):
                    # Inline submit description
                    if debug:
                        print(f"DEBUG: Found inline JOB {job_name}")

                    # Parse inline submit description
                    inline_content = []
                    if job_spec == "{":
                        # Opening brace on separate line, collect until closing brace
                        while i < len(lines):
                            inline_line = lines[i].strip()
                            i += 1
                            if inline_line == "}":
                                break
                            if inline_line and not inline_line.startswith("#"):
                                # Remove leading indentation
                                inline_content.append(inline_line.lstrip())
                    else:
                        # Single line inline (shouldn't happen with our format but handle it)
                        inline_content = (
                            [job_spec[1:-1].strip()] if job_spec.endswith("}") else []
                        )

                    jobs[job_name] = {
                        "submit_file": None,  # No external file
                        "inline_submit": "\n".join(inline_content),
                        "extra_args": "",
                        "retry": 0,
                        "priority": 0,
                        "vars": {},
                    }
                    if debug:
                        print(
                            f"DEBUG: Parsed inline submit for {job_name}: {len(inline_content)} lines"
                        )
                else:
                    # External submit file
                    parts = job_spec.split()
                    submit_file = parts[0]
                    extra_args = " ".join(parts[1:]) if len(parts) > 1 else ""

                    jobs[job_name] = {
                        "submit_file": submit_file,
                        "inline_submit": None,
                        "extra_args": extra_args,
                        "retry": 0,
                        "priority": 0,
                        "vars": {},
                    }
                    if debug:
                        print(f"DEBUG: Found external JOB {job_name} -> {submit_file}")
                continue

            # PARENT child1 child2 ... CHILD parent1 parent2 ...
            parent_match = re.match(r"^PARENT\s+(.*?)\s+CHILD\s+(.*)$", line)
            if parent_match:
                parents = parent_match.group(1).split()
                children = parent_match.group(2).split()

                for parent in parents:
                    for child in children:
                        dependencies.append((parent, child))
                        if debug:
                            print(f"DEBUG: Found dependency {parent} -> {child}")
                continue

            # RETRY jobname count
            retry_match = re.match(r"^RETRY\s+(\S+)\s+(\d+)$", line)
            if retry_match:
                job_name = retry_match.group(1)
                retry_count = int(retry_match.group(2))
                if job_name in jobs:
                    jobs[job_name]["retry"] = retry_count
                if debug:
                    print(f"DEBUG: Set retry for {job_name}: {retry_count}")
                continue

            # PRIORITY jobname priority_value
            priority_match = re.match(r"^PRIORITY\s+(\S+)\s+([-+]?\d+)$", line)
            if priority_match:
                job_name = priority_match.group(1)
                priority = int(priority_match.group(2))
                if job_name in jobs:
                    jobs[job_name]["priority"] = priority
                if debug:
                    print(f"DEBUG: Set priority for {job_name}: {priority}")
                continue

            # VARS jobname var1="value1" var2="value2" ...
            vars_match = re.match(r"^VARS\s+(\S+)\s+(.*)$", line)
            if vars_match:
                job_name = vars_match.group(1)
                vars_string = vars_match.group(2)

                # Parse variables (simple implementation)
                job_vars = {}
                var_pairs = re.findall(r'(\w+)="([^"]*)"', vars_string)
                for var_name, var_value in var_pairs:
                    job_vars[var_name] = var_value

                if job_name in jobs:
                    jobs[job_name]["vars"] = job_vars
                if debug:
                    print(f"DEBUG: Set variables for {job_name}: {job_vars}")
                continue

            # SET_ENV name=value
            env_match = re.match(r"^SET_ENV\s+(\w+)=(.*)$", line)
            if env_match:
                var_name = env_match.group(1)
                var_value = env_match.group(2)
                variables[var_name] = var_value
                if debug:
                    print(f"DEBUG: Set environment variable {var_name}={var_value}")
                continue

            # Skip other DAGMan commands for now
            if debug and not line.startswith(("CONFIG", "DOT", "NODE_STATUS_FILE")):
                print(f"DEBUG: Skipping line {i}: {line}")

        except Exception as e:
            if debug:
                print(f"DEBUG: Error parsing line {i}: {e}")

    return jobs, dependencies, variables, metadata


def _parse_submit_content(content: str, debug: bool = False) -> Dict[str, Any]:
    """Parse inline submit description content and extract job information."""

    submit_info = {
        "executable": None,
        "arguments": None,
        "input": [],
        "output": [],
        "error": None,
        "log": None,
        "resources": {},
        "environment": {},
        "universe": "vanilla",
        "requirements": None,
        "raw_submit": {},
    }

    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Split on = but handle quoted values
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip().lower()
        value = value.strip()

        # Remove quotes
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]

        submit_info["raw_submit"][key] = value

        # Parse key submit directives
        if key == "executable":
            submit_info["executable"] = value
        elif key == "arguments":
            submit_info["arguments"] = value
        elif key == "universe":
            submit_info["universe"] = value
        elif key == "output":
            # Always append as ParameterSpec, not string
            from wf2wf.core import ParameterSpec, EnvironmentSpecificValue
            submit_info["output"].append(
                ParameterSpec(id=value, type="File", transfer_mode=EnvironmentSpecificValue("always"))
            )
        elif key == "error":
            submit_info["error"] = value
        elif key == "log":
            submit_info["log"] = value
        elif key == "requirements":
            submit_info["requirements"] = value
        elif key == "docker_image":
            submit_info["environment"]["container"] = f"docker://{value}"
        elif key.startswith("+singularityimage"):
            submit_info["environment"]["container"] = value
        elif key.startswith("request_"):
            # Resource requests
            if key == "request_cpus":
                try:
                    submit_info["resources"]["cpu"] = int(value)
                except ValueError:
                    if debug:
                        print(f"DEBUG: Could not parse CPU value: {value}")
            elif key == "request_memory":
                try:
                    submit_info["resources"]["mem_mb"] = _parse_memory_value(value)
                except ValueError:
                    if debug:
                        print(f"DEBUG: Could not parse memory value: {value}")
            elif key == "request_disk":
                try:
                    submit_info["resources"]["disk_mb"] = _parse_memory_value(value)
                except ValueError:
                    if debug:
                        print(f"DEBUG: Could not parse disk value: {value}")
            elif key == "request_gpus":
                try:
                    submit_info["resources"]["gpu"] = int(value)
                except ValueError:
                    if debug:
                        print(f"DEBUG: Could not parse GPU value: {value}")
        else:
            # Store other attributes in resources.extra
            if not submit_info["resources"]:
                submit_info["resources"] = {}
            submit_info["resources"][key] = value

    return submit_info


def _parse_submit_file(submit_path: Path, debug: bool = False) -> Dict[str, Any]:
    """Parse HTCondor submit file and extract job information."""

    submit_info = {
        "executable": None,
        "arguments": None,
        "input": [],
        "output": [],
        "error": None,
        "log": None,
        "resources": {},
        "environment": {},
        "universe": "vanilla",
        "requirements": None,
        "raw_submit": {},
    }

    if not submit_path.exists():
        return submit_info

    content = submit_path.read_text()

    for line in content.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Split on = but handle quoted values
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip().lower()
        value = value.strip()

        # Remove quotes
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]

        submit_info["raw_submit"][key] = value

        # Parse key submit directives
        if key == "executable":
            submit_info["executable"] = value
        elif key == "arguments":
            submit_info["arguments"] = value
        elif key == "universe":
            submit_info["universe"] = value
        elif key == "error":
            submit_info["error"] = value
        elif key == "output":
            # Don't confuse with output files - this is stdout redirection
            pass
        elif key == "log":
            submit_info["log"] = value
        elif key == "requirements":
            submit_info["requirements"] = value

        # Resource requests
        elif key == "request_cpus":
            submit_info["resources"]["cpu"] = int(float(value))
        elif key == "request_memory":
            # Handle memory units (MB, GB, etc.)
            submit_info["resources"]["mem_mb"] = _parse_memory_value(value)
        elif key == "request_disk":
            submit_info["resources"]["disk_mb"] = _parse_memory_value(value)
        elif key == "request_gpus":
            submit_info["resources"]["gpu"] = int(float(value))

        # Container universe
        elif key == "container_image":
            submit_info["environment"]["container"] = value
        elif key == "docker_image":
            submit_info["environment"]["container"] = f"docker://{value}"

        # Transfer files (approximate input/output detection)
        elif key == "transfer_input_files":
            # Create ParameterSpec objects with explicit transfer mode
            from wf2wf.core import ParameterSpec, EnvironmentSpecificValue
            submit_info["input"] = [
                ParameterSpec(id=f.strip(), type="File", transfer_mode=EnvironmentSpecificValue("always"))
                for f in value.split(",") if f.strip()
            ]
        elif key == "transfer_output_files":
            # Create ParameterSpec objects with explicit transfer mode
            from wf2wf.core import ParameterSpec, EnvironmentSpecificValue
            submit_info["output"] = [
                ParameterSpec(id=f.strip(), type="File", transfer_mode=EnvironmentSpecificValue("always"))
                for f in value.split(",") if f.strip()
            ]

        # Environment variables
        elif key == "environment":
            # Parse environment string: "VAR1=value1 VAR2=value2"
            env_vars = {}
            for env_pair in value.split():
                if "=" in env_pair:
                    env_key, env_val = env_pair.split("=", 1)
                    env_vars[env_key] = env_val
            submit_info["environment"]["env_vars"] = env_vars

    if debug:
        print(f"DEBUG: Parsed submit file {submit_path}:")
        print(f"  executable: {submit_info['executable']}")
        print(f"  arguments: {submit_info['arguments']}")
        print(
            f"  resources: cpu={submit_info['resources'].get('cpu')}, mem={submit_info['resources'].get('mem_mb')}MB"
        )

    return submit_info


def _create_task_from_job(
    job_name: str, job_info: Dict, submit_info: Dict, dag_dir: Path
) -> Task:
    """Create a Task object from DAG job and submit file information."""

    # Build command
    command = None
    script = None

    if submit_info.get("executable"):
        executable = submit_info["executable"]
        arguments = submit_info.get("arguments") or ""

        # Check if executable is a wrapper script generated by wf2wf
        exec_path = dag_dir / executable
        if exec_path.exists() and exec_path.suffix == ".sh":
            # Try to extract the original command from the wrapper script
            try:
                script_content = exec_path.read_text()
                # Look for the actual command after the wf2wf comment
                lines = script_content.split("\n")
                for line in lines:
                    line = line.strip()
                    # Skip shebang, set commands, and comments
                    if (
                        line.startswith("#")
                        or line.startswith("set ")
                        or not line
                        or line.startswith("#!/")
                    ):
                        continue
                    # This should be the actual command
                    if line != "echo 'No command defined'":
                        command = line
                        break

                # If we couldn't extract a meaningful command, use the script path
                if not command or command == "echo 'No command defined'":
                    script = executable
                    if arguments:
                        command = f"{executable} {arguments}"
                    else:
                        command = executable

            except Exception:
                # Fallback to using the script as-is
                script = executable
                command = (
                    f"{executable} {arguments}".strip() if arguments else executable
                )
        else:
            # Regular executable
            command = f"{executable} {arguments}".strip()

    # Fallback if no command found
    if not command:
        command = "echo 'No command specified'"

    # Create task with environment-specific values
    task = Task(id=job_name)
    
    # Set command and script
    if command:
        task.command.set_for_environment(command, "distributed_computing")
    if script:
        task.script.set_for_environment(script, "distributed_computing")
    
    # Set inputs and outputs
    task.inputs = submit_info.get("input", [])
    task.outputs = submit_info.get("output", [])
    
    # Set resource values from submit info, or use defaults for distributed_computing
    resources = submit_info.get("resources", {})
    
    # Always set CPU value for distributed_computing (use default if not specified)
    cpu_value = resources.get("cpu", 1)
    task.cpu.set_for_environment(cpu_value, "distributed_computing")
    
    # Always set memory value for distributed_computing (use default if not specified)
    mem_value = resources.get("mem_mb", 4096)
    task.mem_mb.set_for_environment(mem_value, "distributed_computing")
    
    # Always set disk value for distributed_computing (use default if not specified)
    disk_value = resources.get("disk_mb", 4096)
    task.disk_mb.set_for_environment(disk_value, "distributed_computing")
    
    # Always set GPU value for distributed_computing (use default if not specified)
    gpu_value = resources.get("gpu", 0)
    task.gpu.set_for_environment(gpu_value, "distributed_computing")
    
    # Set environment values
    if submit_info.get("environment"):
        env = submit_info["environment"]
        if "container" in env:
            task.container.set_for_environment(env["container"], "distributed_computing")
        if "env_vars" in env:
            task.env_vars.set_for_environment(env["env_vars"], "distributed_computing")
    
    # Set retry and priority
    retry_count = job_info.get("retry", 0)
    if retry_count > 0:
        task.retry_count.set_for_environment(retry_count, "distributed_computing")
    
    priority = job_info.get("priority", 0)
    if priority != 0:
        task.priority.set_for_environment(priority, "distributed_computing")

    # Add DAGMan-specific metadata
    if task.metadata is None:
        task.metadata = MetadataSpec()
    
    task.metadata.add_format_specific("submit_file", job_info.get("submit_file"))
    task.metadata.add_format_specific("universe", submit_info.get("universe", "vanilla"))
    task.metadata.add_format_specific("dag_vars", job_info.get("vars", {}))
    task.metadata.add_format_specific("requirements", submit_info.get("requirements"))
    task.metadata.add_format_specific("condor_log", submit_info.get("log"))
    task.metadata.add_format_specific("condor_error", submit_info.get("error"))

    # Add any extra submit file attributes
    if submit_info.get("raw_submit"):
        task.metadata.add_format_specific("raw_condor_submit", submit_info["raw_submit"])
        # Store custom attributes (e.g., +wantgpulab) in task.extra
        for k, v in submit_info["raw_submit"].items():
            if k.startswith("+"):
                task.extra[k] = EnvironmentSpecificValue(v, ["distributed_computing"])

    return task


def _parse_memory_value(value: str) -> int:
    """Parse memory value with units (MB, GB, etc.) and return MB."""

    value = value.upper().strip()

    # Extract number and unit
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([A-Z]*)$", value)
    if not match:
        # Assume MB if no unit
        try:
            return int(float(value))
        except ValueError:
            return 0

    number = float(match.group(1))
    unit = match.group(2)

    # Convert to MB
    if unit in ["", "MB", "M"]:
        return int(number)
    elif unit in ["GB", "G"]:
        return int(number * 1024)
    elif unit in ["KB", "K"]:
        return int(number / 1024)
    elif unit in ["TB", "T"]:
        return int(number * 1024 * 1024)
    else:
        # Unknown unit, assume MB
        return int(number)
