"""wf2wf.importers.dagman – Condor DAGMan ➜ Workflow IR

This module converts HTCondor DAGMan files (.dag) to the wf2wf intermediate representation.

Public API:
    to_workflow(path, **opts)   -> returns `wf2wf.core.Workflow` object
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from wf2wf.core import Workflow, Task, ResourceSpec, EnvironmentSpec


def to_workflow(path: Union[str, Path], **opts: Any) -> Workflow:
    """Convert DAGMan file at *path* into a Workflow IR object.

    Parameters
    ----------
    path : str | Path
        Path to the .dag file.
    name : str, optional
        Override workflow name (defaults to DAG filename stem).
    verbose : bool, optional
        Enable verbose output (default: False).
    debug : bool, optional
        Enable debug output (default: False).

    Returns
    -------
    Workflow
        Populated IR instance.
    """
    dag_path = Path(path)
    if not dag_path.exists():
        raise FileNotFoundError(f"DAG file not found: {dag_path}")

    verbose = opts.get("verbose", False)
    debug = opts.get("debug", False)
    workflow_name = opts.get("name")  # Don't set default here

    if verbose:
        print(f"Parsing DAGMan file: {dag_path}")

    # Parse the DAG file
    dag_content = dag_path.read_text()
    jobs, dependencies, variables, metadata = _parse_dag_file(dag_content, debug=debug)

    if not jobs:
        raise ValueError("No jobs found in DAG file")

    # Use metadata workflow name if available, otherwise use provided name or filename
    if not workflow_name:
        workflow_name = metadata.get("original_workflow_name", dag_path.stem)

    # Create workflow with metadata
    wf = Workflow(
        name=workflow_name, version=metadata.get("original_workflow_version", "1.0")
    )

    # Restore workflow metadata if available
    if metadata.get("workflow_metadata"):
        wf.meta.update(metadata["workflow_metadata"])

    # Add jobs as tasks
    submit_files = {}  # Cache parsed submit files

    for job_name, job_info in jobs.items():
        submit_info = {}

        if job_info.get("inline_submit"):
            # Parse inline submit description
            submit_info = _parse_submit_content(job_info["inline_submit"], debug=debug)
            if verbose:
                print(f"  Parsed inline submit for {job_name}")
        elif job_info.get("submit_file"):
            # Parse external submit file
            submit_file = Path(dag_path.parent / job_info["submit_file"])

            # Parse submit file if not already cached
            if str(submit_file) not in submit_files:
                if submit_file.exists():
                    submit_files[str(submit_file)] = _parse_submit_file(
                        submit_file, debug=debug
                    )
                else:
                    if verbose:
                        print(f"WARNING: Submit file not found: {submit_file}")
                    submit_files[str(submit_file)] = {}

            submit_info = submit_files[str(submit_file)]
        else:
            if verbose:
                print(f"WARNING: No submit information found for job {job_name}")

        # Create task from job info
        task = _create_task_from_job(job_name, job_info, submit_info, dag_path.parent)
        wf.add_task(task)

        if verbose:
            print(f"  Added task: {task.id}")

    # Add dependencies as edges
    for parent, child in dependencies:
        try:
            wf.add_edge(parent, child)
            if verbose:
                print(f"  Added edge: {parent} -> {child}")
        except KeyError as e:
            if verbose:
                print(f"WARNING: Skipping invalid dependency {parent} -> {child}: {e}")

    # Store DAG variables in workflow meta
    if variables:
        wf.meta["dag_variables"] = variables

    if verbose:
        print(
            f"Created workflow '{wf.name}' with {len(wf.tasks)} tasks and {len(wf.edges)} dependencies"
        )

    return wf


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
        "resources": ResourceSpec(),
        "environment": EnvironmentSpec(),
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
            submit_info["output"].append(value)
        elif key == "error":
            submit_info["error"] = value
        elif key == "log":
            submit_info["log"] = value
        elif key == "requirements":
            submit_info["requirements"] = value
        elif key == "docker_image":
            submit_info["environment"].container = f"docker://{value}"
        elif key.startswith("+singularityimage"):
            submit_info["environment"].container = value
        elif key.startswith("request_"):
            # Resource requests
            if key == "request_cpus":
                try:
                    submit_info["resources"].cpu = int(value)
                except ValueError:
                    if debug:
                        print(f"DEBUG: Could not parse CPU value: {value}")
            elif key == "request_memory":
                try:
                    submit_info["resources"].mem_mb = _parse_memory_value(value)
                except ValueError:
                    if debug:
                        print(f"DEBUG: Could not parse memory value: {value}")
            elif key == "request_disk":
                try:
                    submit_info["resources"].disk_mb = _parse_memory_value(value)
                except ValueError:
                    if debug:
                        print(f"DEBUG: Could not parse disk value: {value}")
            elif key == "request_gpus":
                try:
                    submit_info["resources"].gpu = int(value)
                except ValueError:
                    if debug:
                        print(f"DEBUG: Could not parse GPU value: {value}")
        else:
            # Store other attributes in resources.extra
            if not submit_info["resources"].extra:
                submit_info["resources"].extra = {}
            submit_info["resources"].extra[key] = value

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
        "resources": ResourceSpec(),
        "environment": EnvironmentSpec(),
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
            submit_info["resources"].cpu = int(float(value))
        elif key == "request_memory":
            # Handle memory units (MB, GB, etc.)
            submit_info["resources"].mem_mb = _parse_memory_value(value)
        elif key == "request_disk":
            submit_info["resources"].disk_mb = _parse_memory_value(value)
        elif key == "request_gpus":
            submit_info["resources"].gpu = int(float(value))

        # Container universe
        elif key == "container_image":
            submit_info["environment"].container = value
        elif key == "docker_image":
            submit_info["environment"].container = f"docker://{value}"

        # Transfer files (approximate input/output detection)
        elif key == "transfer_input_files":
            submit_info["input"] = [f.strip() for f in value.split(",") if f.strip()]
        elif key == "transfer_output_files":
            submit_info["output"] = [f.strip() for f in value.split(",") if f.strip()]

        # Environment variables
        elif key == "environment":
            # Parse environment string: "VAR1=value1 VAR2=value2"
            env_vars = {}
            for env_pair in value.split():
                if "=" in env_pair:
                    env_key, env_val = env_pair.split("=", 1)
                    env_vars[env_key] = env_val
            submit_info["environment"].env_vars = env_vars

    if debug:
        print(f"DEBUG: Parsed submit file {submit_path}:")
        print(f"  executable: {submit_info['executable']}")
        print(f"  arguments: {submit_info['arguments']}")
        print(
            f"  resources: cpu={submit_info['resources'].cpu}, mem={submit_info['resources'].mem_mb}MB"
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

    # Create task
    task = Task(
        id=job_name,
        command=command,
        script=script,
        inputs=submit_info.get("input", []),
        outputs=submit_info.get("output", []),
        resources=submit_info.get("resources", ResourceSpec()),
        environment=submit_info.get("environment", EnvironmentSpec()),
        retry=job_info.get("retry", 0),
        priority=job_info.get("priority", 0),
    )

    # Add DAGMan-specific metadata
    task.meta.update(
        {
            "submit_file": job_info.get("submit_file"),
            "universe": submit_info.get("universe", "vanilla"),
            "dag_vars": job_info.get("vars", {}),
            "requirements": submit_info.get("requirements"),
            "condor_log": submit_info.get("log"),
            "condor_error": submit_info.get("error"),
        }
    )

    # Add any extra submit file attributes
    if submit_info.get("raw_submit"):
        task.meta["raw_condor_submit"] = submit_info.get("raw_submit")

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
