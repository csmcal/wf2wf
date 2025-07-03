"""
wf2wf.importers.snakemake – Snakefile ➜ Workflow IR

Refactored implementation that directly converts Snakemake workflows to the
Workflow IR without going through the legacy dag_info structure.

Public API:
    to_workflow(...)   -> returns `wf2wf.core.Workflow` object
    to_dag_info(...)   -> legacy function for backward compatibility
"""

from __future__ import annotations

import json
import re
import subprocess
import shutil
import textwrap
import yaml
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict
from collections import defaultdict

from wf2wf.core import Workflow, Task, ResourceSpec, EnvironmentSpec


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def to_workflow(path: str | Path, **opts: Any) -> Workflow:
    """Convert Snakefile at *path* into a Workflow IR object.

    Parameters
    ----------
    path : str | Path
        Path to the Snakefile.
    workdir : str | Path, optional
        Working directory for Snakemake execution.
    cores : int, optional
        Number of cores to use (default: 1).
    configfile : str | Path, optional
        Path to config file.
    snakemake_args : List[str], optional
        Additional arguments to pass to snakemake commands.
    config : Dict[str, Any], optional
        Base configuration dictionary.
    verbose : bool, optional
        Enable verbose output (default: False).
    debug : bool, optional
        Enable debug output (default: False).

    Returns
    -------
    Workflow
        Populated IR instance.
    """
    snakefile_path = Path(path)
    workdir = opts.get("workdir")
    cores = opts.get("cores", 1)
    configfile = opts.get("configfile")
    snakemake_args = opts.get("snakemake_args", [])
    config = opts.get("config", {})
    verbose = opts.get("verbose", False)
    debug = opts.get("debug", False)

    if not shutil.which("snakemake"):
        raise RuntimeError("The 'snakemake' executable was not found in your PATH.")

    # Use the Snakefile's directory as working directory by default so that
    # relative input/output paths resolve even when the caller is in a
    # different CWD (e.g. test harnesses that invoke wf2wf from elsewhere).
    if workdir is None:
        workdir = snakefile_path.parent

    # Create workflow object
    wf = Workflow(name=snakefile_path.stem)

    # --- Step 1: Parse Snakefile for rule templates ---
    if verbose:
        print("INFO: Step 1: Parsing Snakefile for rule definitions...")

    try:
        rule_templates = _parse_snakefile_for_rules(snakefile_path, debug=debug)
        if verbose:
            print(f"  Found {len(rule_templates['rules'])} rule templates.")
    except Exception as e:
        raise RuntimeError(f"Failed to read or parse the Snakefile: {e}")

    # --- Step 2: Get execution graph from `snakemake --dag` ---
    if verbose:
        print("INFO: Step 2: Running `snakemake --dag` to get dependency graph...")

    sm_cli_args = [
        "snakemake",
        "--snakefile",
        str(snakefile_path),
        "--cores",
        str(cores),
        "--quiet",
    ]
    if workdir:
        sm_cli_args.extend(["--directory", str(workdir)])
    if configfile:
        sm_cli_args.extend(["--configfile", str(configfile)])

    dag_cmd = sm_cli_args + ["--dag", "--forceall"]
    if snakemake_args:
        dag_cmd.extend(snakemake_args)

    try:
        dag_process = subprocess.run(
            dag_cmd, capture_output=True, text=True, check=True
        )
        dot_output = dag_process.stdout
        if verbose:
            print("--- `snakemake --dag` STDOUT ---")
            print(dot_output)
            print("--- `snakemake --dag` STDERR ---")
            print(dag_process.stderr)
            print("---------------------------------")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"'snakemake --dag' failed (exit code {e.returncode}). Stderr:\n{e.stderr}"
        )

    dependencies, job_labels = _parse_dot_output(dot_output, debug=debug)
    if not job_labels:
        raise RuntimeError("No jobs found in the Snakemake workflow")

    # --- Step 3: Get job details from `snakemake --dry-run` ---
    if verbose:
        print("INFO: Step 3: Running `snakemake --dry-run` to get job details...")

    dryrun_cmd = sm_cli_args + ["--dry-run", "--forceall"]
    if snakemake_args:
        dryrun_cmd.extend(snakemake_args)

    try:
        dryrun_process = subprocess.run(
            dryrun_cmd, capture_output=True, text=True, check=True
        )
        dryrun_output = dryrun_process.stdout
        if verbose:
            print("--- `snakemake --dry-run` STDOUT ---")
            print(dryrun_output)
            print("--- `snakemake --dry-run` STDERR ---")
            print(dryrun_process.stderr)
            print("------------------------------------")
    except subprocess.CalledProcessError as e:
        # A failed dry-run is not always fatal
        print(
            f"WARNING: 'snakemake --dry-run' failed (exit code {e.returncode}). Parsing may be incomplete."
        )
        print(f"  Stderr: {e.stderr}")
        dryrun_output = e.stdout + e.stderr

    jobs_from_dryrun = _parse_dryrun_output(dryrun_output, debug=debug)
    dryrun_info_map = {job["jobid"]: job for job in jobs_from_dryrun}

    # --- Step 4: Build config ---
    final_config = {}
    if config:
        final_config.update(config)

    # Load config from Snakefile's configfile directive
    parsed_config_path = rule_templates.get("directives", {}).get("configfile")
    if parsed_config_path:
        snakefile_dir = snakefile_path.parent
        full_config_path = snakefile_dir / parsed_config_path
        if full_config_path.exists():
            try:
                with open(full_config_path, "r") as f:
                    final_config.update(yaml.safe_load(f))
                if verbose:
                    print(
                        f"  Loaded config from Snakefile directive: {full_config_path}"
                    )
            except Exception as e:
                print(
                    f"WARNING: Could not load config file from Snakefile directive at {full_config_path}: {e}"
                )
        else:
            if verbose:
                print(
                    f"WARNING: Config file from Snakefile directive not found: {full_config_path}"
                )

    # Load config from CLI --configfile argument
    if configfile and Path(configfile).exists():
        try:
            with open(configfile, "r") as f:
                final_config.update(yaml.safe_load(f))
            if verbose:
                print(f"  Loaded/overwrote config from CLI argument: {configfile}")
        except Exception as e:
            print(f"WARNING: Could not load config file from CLI at {configfile}: {e}")

    wf.config = final_config

    # --- Step 5: Build tasks from job information ---
    if verbose:
        print("INFO: Step 4: Building tasks from job information...")

    jobid_to_task_id = {}

    for i, (jobid, rule_name) in enumerate(job_labels.items()):
        task_id = f"{rule_name}_{i}"
        jobid_to_task_id[jobid] = task_id

        # Get detailed info from dry-run if available
        dryrun_details = dryrun_info_map.get(jobid, {})

        # Get rule template
        template = rule_templates["rules"].get(rule_name, {})

        # Build task inputs/outputs
        inputs = dryrun_details.get("inputs", [])
        outputs = dryrun_details.get("outputs", [])

        # Build command/script
        command = None
        script = None

        if template.get("shell"):
            command = template["shell"]
            # Apply wildcard substitution
            wildcards = dryrun_details.get("wildcards_dict", {})
            if wildcards:
                for k, v in wildcards.items():
                    command = command.replace(f"{{wildcards.{k}}}", v)
        elif template.get("script"):
            script = template["script"]
        elif template.get("run"):
            # For run blocks, we'll store the code in meta and use a placeholder command
            command = f"# run block for rule {rule_name}"
        elif dryrun_details.get("shell_command"):
            command = dryrun_details["shell_command"]
        else:
            command = f"echo 'No command defined for rule {rule_name}'"

        # Build resources
        resources_dict = dryrun_details.get("resources", {})
        template_resources = template.get("resources", {})

        # Merge template and dryrun resources (dryrun takes precedence)
        merged_resources = {**template_resources, **resources_dict}

        # Handle unit conversions
        disk_mb = 0
        if "disk_mb" in merged_resources:
            disk_mb = int(merged_resources["disk_mb"])
        elif "disk_gb" in merged_resources:
            disk_mb = int(merged_resources["disk_gb"]) * 1024

        resources = ResourceSpec(
            cpu=int(merged_resources.get("threads", merged_resources.get("cpu", 1))),
            mem_mb=int(merged_resources.get("mem_mb", merged_resources.get("mem", 0))),
            disk_mb=disk_mb,
            gpu=int(merged_resources.get("gpu", 0)),
            gpu_mem_mb=int(merged_resources.get("gpu_mem_mb", 0)),
            threads=int(merged_resources.get("threads", 1)),
            extra={
                k: v
                for k, v in merged_resources.items()
                if k
                not in {
                    "threads",
                    "cpu",
                    "mem_mb",
                    "mem",
                    "disk_mb",
                    "disk_gb",
                    "gpu",
                    "gpu_mem_mb",
                }
            },
        )

        # Build environment
        environment = EnvironmentSpec(
            conda=template.get("conda"), container=template.get("container")
        )

        # Build params
        params = dryrun_details.get("params", {})

        # Build metadata
        meta = {
            "rule_name": rule_name,
            "wildcards_dict": dryrun_details.get("wildcards_dict", {}),
            "log_files": dryrun_details.get("log_files", []),
            "is_shell": bool(template.get("shell")),
            "is_script": bool(template.get("script")),
            "is_run": bool(template.get("run")),
            "is_containerized": bool(template.get("container")),
            "run_block_code": template.get("run"),
            "reason": dryrun_details.get("reason", ""),
        }

        # Create task
        task = Task(
            id=task_id,
            command=command,
            script=script,
            inputs=inputs,
            outputs=outputs,
            params=params,
            resources=resources,
            environment=environment,
            priority=0,  # Snakemake doesn't have explicit priorities
            retry=int(template.get("retries", 0)),
            meta=meta,
        )

        wf.add_task(task)

    # --- Step 6: Build edges from dependencies ---
    if verbose:
        print("INFO: Step 5: Building dependency edges...")

    for parent_jobid, child_jobids in dependencies.items():
        if parent_jobid in jobid_to_task_id:
            parent_task_id = jobid_to_task_id[parent_jobid]
            for child_jobid in child_jobids:
                if child_jobid in jobid_to_task_id:
                    child_task_id = jobid_to_task_id[child_jobid]
                    wf.add_edge(parent_task_id, child_task_id)

    if verbose:
        print(
            f"INFO: Successfully created workflow with {len(wf.tasks)} tasks and {len(wf.edges)} edges"
        )

    if debug:
        print("\n--- FINAL WORKFLOW ---")
        print(json.dumps(wf.to_dict(), indent=2, default=str))
        print("----------------------\n")

    return wf


def to_dag_info(*, snakefile_path: str | Path, **kwargs) -> Dict[str, Any]:
    """Legacy function for backward compatibility.

    Converts Snakefile to the old dag_info format by first creating a Workflow
    and then converting it back to dag_info structure.
    """
    wf = to_workflow(snakefile_path, **kwargs)
    return _workflow_to_dag_info(wf)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _workflow_to_dag_info(wf: Workflow) -> Dict[str, Any]:
    """Convert a Workflow back to the legacy dag_info structure for compatibility."""

    jobs = {}
    job_dependencies = {}

    for task in wf.tasks.values():
        # Extract rule name and index from task_id (format: rule_name_index)
        rule_name = task.meta.get("rule_name", task.id)

        job_dict = {
            "rule_name": rule_name,
            "condor_job_name": _sanitize_condor_job_name(task.id),
            "wildcards_dict": task.meta.get("wildcards_dict", {}),
            "inputs": task.inputs,
            "outputs": task.outputs,
            "log_files": task.meta.get("log_files", []),
            "shell_command": task.command,
            "threads": task.resources.threads,
            "resources": {**asdict(task.resources), **task.resources.extra},
            "conda_env_spec": task.environment.conda,
            "container_img_url": task.environment.container,
            "is_shell": task.meta.get("is_shell", False),
            "is_script": task.meta.get("is_script", False),
            "is_run": task.meta.get("is_run", False),
            "is_containerized": task.meta.get("is_containerized", False),
            "script_file": task.script,
            "run_block_code": task.meta.get("run_block_code"),
            "retries": task.retry,
            "params_dict": task.params,
            "benchmark_file": None,
            "container_img_path": None,
        }

        jobs[task.id] = job_dict

    # Build job dependencies (child -> [parents])
    for edge in wf.edges:
        if edge.child not in job_dependencies:
            job_dependencies[edge.child] = []
        job_dependencies[edge.child].append(edge.parent)

    return {
        "jobs": jobs,
        "job_dependencies": job_dependencies,
        "snakefile": wf.name,
        "config": wf.config,
    }


def _parse_snakefile_for_rules(snakefile_path, debug=False):
    """
    A robust, line-by-line parser for a Snakefile to extract rule definitions
    and top-level directives like 'configfile'.
    """
    templates = {"rules": {}}
    top_level_directives = {}
    with open(snakefile_path, "r") as f:
        lines = f.readlines()

    rule_starts = []
    rule_name_pattern = re.compile(r"^\s*rule\s+(\w+):")
    configfile_pattern = re.compile(r"^\s*configfile:\s*['\"](.*?)['\"]")

    # 1. Find the starting line of all rules and top-level directives
    for i, line in enumerate(lines):
        match = rule_name_pattern.match(line)
        if match:
            rule_name = match.group(1)
            rule_starts.append({"name": rule_name, "start": i})
            continue  # It's a rule, not a top-level directive

        config_match = configfile_pattern.match(line)
        if config_match:
            top_level_directives["configfile"] = config_match.group(1)

    if not rule_starts:
        templates["directives"] = top_level_directives
        return templates

    # 2. The body of each rule is the text between its start and the next rule's start
    for i, rule_info in enumerate(rule_starts):
        rule_name = rule_info["name"]
        start_line = rule_info["start"]

        # Determine the end line for the current rule's body
        if i + 1 < len(rule_starts):
            end_line = rule_starts[i + 1]["start"]
        else:
            end_line = len(lines)

        # The body is the lines from just after the 'rule ...:' line to the end line
        body_lines = lines[start_line + 1 : end_line]
        body = "".join(body_lines)

        details = {}

        # 3. Parse directives from the extracted rule body

        # Simple key: "value" directives
        for directive in [
            "input",
            "output",
            "log",
            "conda",
            "container",
            "shell",
            "script",
        ]:
            # This regex handles single/double quotes, raw strings, and allows for newlines
            pattern = re.compile(
                rf"^\s*{directive}:\s*(?:['\"](.*?)(?<!\\)['\"]|r['\"](.*?)(?<!\\)['\"])",
                re.S | re.M,
            )
            dir_match = pattern.search(body)
            if dir_match:
                details[directive] = dir_match.group(1) or dir_match.group(2)

        # Parse retries directive (simple numeric value)
        retries_pattern = re.compile(r"^\s*retries:\s*(\d+)", re.M)
        retries_match = retries_pattern.search(body)
        if retries_match:
            details["retries"] = int(retries_match.group(1))

        # State machine for the 'run:' block
        in_run_block = False
        run_block_lines = []
        for line in body_lines:  # Iterate over the lines of the body
            stripped_line = line.strip()
            # Start of the block
            if stripped_line.startswith("run:"):
                in_run_block = True
                continue

            # Detect end of the block (a new, non-indented directive)
            if (
                in_run_block
                and line
                and not line.startswith((" ", "\t"))
                and stripped_line
            ):
                if ":" in stripped_line and not stripped_line.startswith("#"):
                    in_run_block = False  # End of run block

            if in_run_block:
                run_block_lines.append(line)

        if run_block_lines:
            details["run"] = textwrap.dedent("".join(run_block_lines))

        # State machine for the 'resources:' block
        in_resources_block = False
        resources_lines = []
        for line in body_lines:
            stripped_line = line.strip()
            if stripped_line.startswith("resources:"):
                in_resources_block = True
                continue

            if (
                in_resources_block
                and line
                and not line.startswith((" ", "\t"))
                and stripped_line
            ):
                if ":" in stripped_line and not stripped_line.startswith("#"):
                    in_resources_block = False

            if in_resources_block:
                resources_lines.append(line)

        if resources_lines:
            res_body = "".join(resources_lines)
            res_details = {}
            for res_line in res_body.splitlines():
                res_line = res_line.strip()
                if ":" in res_line:
                    key, val = res_line.split(":", 1)
                    res_details[key.strip()] = val.strip().strip(",")
            if res_details:
                details["resources"] = res_details

        if debug:
            print(f"DEBUG: Parsed rule '{rule_name}' with details: {details}")
        templates["rules"][rule_name] = details

    templates["directives"] = top_level_directives
    return templates


def _parse_dryrun_output(dryrun_output, debug=False):
    """Parses the output of `snakemake --dry-run`."""
    jobs = []
    current_job_data = {}

    def format_job(data):
        if not data:
            return None
        # Ensure jobid is present before formatting
        if "jobid" not in data or "rule_name" not in data:
            return None

        # Helper function to parse resource values
        def parse_resource_value(value):
            try:
                # Try to convert to float first
                float_val = float(value)
                # If it's a whole number, return as int
                if float_val.is_integer():
                    return int(float_val)
                return float_val
            except ValueError:
                return value

        # Parse resources with proper type conversion
        resources = {}
        if data.get("resources"):
            for item in data.get("resources", "").split(", "):
                if "=" in item:
                    key, value = item.split("=", 1)
                    resources[key] = parse_resource_value(value)

        job_info = {
            "jobid": data.get("jobid"),
            "rule_name": data.get("rule_name"),
            "inputs": data.get("input", "").split(", ") if data.get("input") else [],
            "outputs": data.get("output", "").split(", ") if data.get("output") else [],
            "log_files": data.get("log", "").split(", ") if data.get("log") else [],
            "wildcards_dict": dict(
                item.split("=", 1) for item in data.get("wildcards", "").split(", ")
            )
            if data.get("wildcards")
            else {},
            "resources": resources,
            "reason": data.get("reason", ""),
        }
        # Only add shell_command if it's explicitly found
        if "shell_command" in data:
            job_info["shell_command"] = data["shell_command"]
        return job_info

    # Check for "Nothing to be done" message
    if "Nothing to be done." in dryrun_output:
        if debug:
            print("DEBUG: Found 'Nothing to be done' message in dry-run output")
        return []

    for line in dryrun_output.splitlines():
        line = line.strip()
        if not line:
            continue

        # A line starting with 'rule' indicates a new job.
        if line.startswith("rule "):
            # If we have data from a previous job, format and save it.
            if current_job_data:
                formatted = format_job(current_job_data)
                if formatted:
                    jobs.append(formatted)

            # Start a new job
            current_job_data = {"rule_name": line.split(" ")[1].replace(":", "")}
            continue

        # Skip timestamps and other non-key-value lines
        if (
            re.match(r"^\[.+\]$", line)
            or "..." in line
            or "Building DAG" in line
            or "Job stats" in line
            or "job count" in line
            or "---" in line
            or "total" in line
            or "host:" in line
        ):
            continue

        # Parse indented key-value pairs
        match = re.match(r"(\S+):\s*(.*)", line)
        if match and current_job_data:  # Ensure we are inside a job block
            key, value = match.groups()
            # Handle multi-line values (like 'reason') by appending
            if key in current_job_data:
                current_job_data[key] += ", " + value.strip()
            else:
                current_job_data[key] = value.strip()

    # Append the last job after the loop finishes
    if current_job_data:
        formatted = format_job(current_job_data)
        if formatted:
            jobs.append(formatted)

    if debug:
        print("\n--- PARSED DRY-RUN JOBS ---")
        print(json.dumps(jobs, indent=4))
        print("---------------------------\n")

    return jobs


def _parse_dot_output(dot_output, debug=False):
    """Parses the DOT output from `snakemake --dag`."""
    dependencies = defaultdict(list)
    job_labels = {}

    # Check for empty DAG output
    if not dot_output.strip() or dot_output.strip() == "digraph snakemake_dag {}":
        if debug:
            print("DEBUG: Empty DAG output detected")
        return dependencies, job_labels

    dep_pattern = re.compile(r"(\d+)\s*->\s*(\d+)")
    label_pattern = re.compile(r"(\d+)\s*\[.*?label\s*=\s*\"([^\"]+)\"")

    for line in dot_output.splitlines():
        # Find all dependency pairs (parent -> child) in the line
        for parent_id, child_id in dep_pattern.findall(line):
            dependencies[parent_id].append(child_id)

        # Find all node labels in the line
        for node_id, label in label_pattern.findall(line):
            job_labels[node_id] = label

    if debug:
        print("\n--- PARSED DOT OUTPUT ---")
        print("Dependencies:", json.dumps(dependencies, indent=4))
        print("Job Labels:", json.dumps(job_labels, indent=4))
        print("-------------------------\n")

    return dependencies, job_labels


def _print_conversion_warnings(dag_info, script_paths, verbose=False, debug=False):
    """Print comprehensive warnings about the conversion process."""
    print("\n" + "=" * 60)
    print("SNAKE2DAGMAN - CONVERSION WARNINGS AND MANUAL STEPS REQUIRED")
    print("=" * 60)

    if not dag_info or not dag_info.get("jobs"):
        print("  No job information available to generate specific warnings.")
        print("=" * 60)
        return

    if verbose:
        print(f"INFO: Analyzing {len(dag_info['jobs'])} jobs for conversion warnings")

    # Gather unique rule properties for warnings
    conda_rules_info = defaultdict(list)
    script_rules_info = defaultdict(list)
    shell_rules_info = defaultdict(list)
    run_block_rules = set()
    notebook_rules = set()
    wrapper_rules = set()
    dynamic_rules = set()
    pipe_rules = set()
    has_auto_conda_setup = "conda_envs" in dag_info and dag_info["conda_envs"]

    for job_uid, job_details in dag_info["jobs"].items():
        rule_name = job_details["rule_name"]
        if job_details.get("conda_env_spec"):
            conda_rules_info[rule_name].append(job_details["conda_env_spec"])
        if job_details.get("script_file"):
            script_rules_info[rule_name].append(job_details["script_file"])
        if job_details.get("shell_command") and job_details.get(
            "is_shell"
        ):  # Ensure it's an actual shell rule
            shell_rules_info[rule_name].append(
                job_uid
            )  # Just note the rule has shell jobs
        if job_details.get("is_run"):
            run_block_rules.add(rule_name)
        if job_details.get("is_notebook"):
            notebook_rules.add(rule_name)
        if job_details.get("is_wrapper"):
            wrapper_rules.add(rule_name)
        if job_details.get("has_dynamic_input") or job_details.get(
            "has_dynamic_output"
        ):
            dynamic_rules.add(rule_name)
        if job_details.get("has_pipe_output"):
            pipe_rules.add(rule_name)

    if debug:
        print("DEBUG: Warning analysis results:")
        print(f"  Conda rules: {len(conda_rules_info)}")
        print(f"  Script rules: {len(script_rules_info)}")
        print(f"  Shell rules: {len(shell_rules_info)}")
        print(f"  Run block rules: {len(run_block_rules)}")
        print(f"  Notebook rules: {len(notebook_rules)}")
        print(f"  Wrapper rules: {len(wrapper_rules)}")
        print(f"  Dynamic rules: {len(dynamic_rules)}")
        print(f"  Pipe rules: {len(pipe_rules)}")

    print("\n1. CONDA ENVIRONMENTS:")
    if has_auto_conda_setup:
        print(
            "   → AUTOMATIC SETUP ENABLED: Conda environments will be created by dedicated setup jobs."
        )
        print(
            "   → The `--conda-prefix` directory MUST be on a shared filesystem accessible to all nodes."
        )
        print(
            "   → Jobs have been made children of their corresponding environment setup job."
        )
        if verbose:
            conda_envs = dag_info.get("conda_envs", {})
            print(
                f"   → {len(conda_envs)} unique conda environments will be automatically set up."
            )
    elif conda_rules_info:
        print("   Rules with Conda environments detected:")
        for rule, env_specs in conda_rules_info.items():
            unique_specs = sorted(list(set(env_specs)))
            print(f"     - Rule '{rule}': uses {', '.join(unique_specs)}")
        print(
            "   → MANUAL SETUP REQUIRED: You must ensure conda environments are activated correctly."
        )
        print("   → To automate this, run again with `--auto-conda-setup`")
    else:
        if verbose:
            print("   → No conda environments detected in this workflow.")


# ---------------------------------------------------------------------------
# Misc utility mirrors (to avoid cross-imports)
# ---------------------------------------------------------------------------


def _sanitize_condor_job_name(name: str) -> str:
    """Return a HTCondor-friendly job name by replacing unsafe characters."""

    return re.sub(r"[^a-zA-Z0-9_.-]", "_", name)
