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
from typing import Any, Dict, Union, List, Tuple
from collections import defaultdict

from wf2wf.core import Workflow, Task, EnvironmentSpecificValue, ParameterSpec, CheckpointSpec, LoggingSpec, SecuritySpec, NetworkingSpec, MetadataSpec
from wf2wf.importers.base import BaseImporter


class SnakemakeImporter(BaseImporter):
    """Snakemake importer using shared base infrastructure."""
    
    def _parse_source(self, path: Path, **opts: Any) -> Dict[str, Any]:
        """Parse Snakefile and extract all information."""
        configfile = opts.get("configfile")
        workdir = opts.get("workdir")
        cores = opts.get("cores", 1)
        snakemake_args = opts.get("snakemake_args", [])
        parse_only = opts.get("parse_only", False)
        verbose = self.verbose
        debug = opts.get("debug", False)

        if debug:
            print(f"DEBUG: Converting Snakemake workflow from {path}")
        
        # Check for snakemake executable unless parse_only mode is enabled
        if not parse_only and not shutil.which("snakemake"):
            raise RuntimeError("The 'snakemake' executable was not found in your PATH. Please install snakemake: 'pip install snakemake' or 'conda install snakemake'")
        
        # Use the Snakefile's directory as working directory by default
        if workdir is None:
            workdir = path.parent

        # Parse Snakefile for rule templates
        if verbose:
            print("INFO: Step 1: Parsing Snakefile for rule definitions...")

        try:
            rule_templates = _parse_snakefile_for_rules(path, debug=debug)
            if verbose:
                print(f"  Found {len(rule_templates['rules'])} rule templates.")
        except Exception as e:
            raise RuntimeError(f"Failed to read or parse the Snakefile: {e}")

        # Get workflow name from directory or filename
        workflow_name = path.stem if path.stem != "Snakefile" else path.parent.name
        if workflow_name == ".":
            workflow_name = "snakemake_workflow"
        
        result = {
            "rule_templates": rule_templates,
            "workflow_name": workflow_name,
            "workdir": workdir,
            "parse_only": parse_only,
            "configfile": configfile,
            "cores": cores,
            "snakemake_args": snakemake_args
        }
        
        # If not parse-only, get additional information from snakemake
        if not parse_only:
            # Get execution graph from `snakemake --dag`
            if verbose:
                print("INFO: Step 2: Running `snakemake --dag` to get dependency graph...")

            dag_output = self._run_snakemake_dag(path, workdir, configfile, cores, snakemake_args, verbose)
            result["dag_output"] = dag_output
            
            # Get job details from `snakemake --dry-run`
            if verbose:
                print("INFO: Step 3: Running `snakemake --dry-run` to get job details...")
            
            dryrun_output = self._run_snakemake_dryrun(path, workdir, configfile, cores, snakemake_args, verbose)
            result["dryrun_output"] = dryrun_output
        
        return result
    
    def _run_snakemake_dag(self, path: Path, workdir: Path, configfile: str, cores: int, snakemake_args: List[str], verbose: bool) -> str:
        """Run snakemake --dag to get dependency graph."""
        sm_cli_args = [
            "snakemake",
            "--snakefile",
            str(path),
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
            return dag_process.stdout
        except subprocess.CalledProcessError as e:
            if verbose:
                print(f"WARNING: `snakemake --dag` failed: {e}")
                print(f"STDOUT: {e.stdout}")
                print(f"STDERR: {e.stderr}")
            return ""
    
    def _run_snakemake_dryrun(self, path: Path, workdir: Path, configfile: str, cores: int, snakemake_args: List[str], verbose: bool) -> str:
        """Run snakemake --dry-run to get job details."""
        sm_cli_args = [
            "snakemake",
            "--snakefile",
            str(path),
            "--cores",
            str(cores),
            "--quiet",
        ]
        if workdir:
            sm_cli_args.extend(["--directory", str(workdir)])
        if configfile:
            sm_cli_args.extend(["--configfile", str(configfile)])

        dryrun_cmd = sm_cli_args + ["--dry-run", "--forceall"]
        if snakemake_args:
            dryrun_cmd.extend(snakemake_args)

        try:
            dryrun_process = subprocess.run(
                dryrun_cmd, capture_output=True, text=True, check=True
            )
            return dryrun_process.stdout
        except subprocess.CalledProcessError as e:
            if verbose:
                print(f"WARNING: `snakemake --dry-run` failed: {e}")
                print(f"STDOUT: {e.stdout}")
                print(f"STDERR: {e.stderr}")
            return ""
    
    def _create_basic_workflow(self, parsed_data: Dict[str, Any]) -> Workflow:
        """Create basic workflow from parsed Snakemake data."""
        workflow_name = parsed_data["workflow_name"]
        
        # Create workflow object
        wf = Workflow(
            name=workflow_name,
            version="1.0",
            execution_model=EnvironmentSpecificValue("shared_filesystem", ["shared_filesystem"]),
        )
        
        return wf
    
    def _extract_tasks(self, parsed_data: Dict[str, Any]) -> List[Task]:
        """Extract tasks from parsed Snakemake data."""
        rule_templates = parsed_data["rule_templates"]
        parse_only = parsed_data["parse_only"]
        verbose = self.verbose
        debug = parsed_data.get("debug", False)
        
        tasks = []
        
        if parse_only:
            # Create tasks from rule templates only
            if verbose:
                print("INFO: Creating tasks from rule templates...")

            for rule_name, rule_details in rule_templates["rules"].items():
                task = _create_task_from_rule_template(rule_name, rule_details, verbose=verbose, debug=debug)
                tasks.append(task)

            if verbose:
                print(f"  Created {len(tasks)} tasks from rule templates")
        else:
            # Create tasks from dry-run output
            dryrun_output = parsed_data.get("dryrun_output", "")
            if dryrun_output:
                jobs = _parse_dryrun_output(dryrun_output, debug=debug)
                
                for job_data in jobs:
                    rule_name = job_data.get("rule", "unknown")
                    task = _build_task_from_job_data(rule_name, job_data, rule_templates["rules"].get(rule_name, {}))
                    tasks.append(task)
                
                if verbose:
                    print(f"  Created {len(tasks)} tasks from dry-run output")
        
        return tasks
    
    def _extract_edges(self, parsed_data: Dict[str, Any]) -> List[Tuple[str, str]]:
        """Extract edges from parsed Snakemake data."""
        if parsed_data["parse_only"]:
            return []  # No edges in parse-only mode
        
        dag_output = parsed_data.get("dag_output", "")
        if dag_output:
            return _parse_dot_output(dag_output, debug=parsed_data.get("debug", False))
        
        return []
    
    def _extract_environment_specific_values(self, parsed_data: Dict[str, Any], workflow: Workflow) -> None:
        """Extract environment-specific values from parsed data."""
        # Snakemake is inherently for shared filesystem, so set execution model
        workflow.execution_model.set_for_environment("shared_filesystem", "shared_filesystem")
        
        # Note: Config handling removed - config should be converted to proper IR parameters
        # rather than stored as opaque data
    
    def _get_source_format(self) -> str:
        """Get the source format name."""
        return "snakemake"


def _build_task_from_job_data(rule_name: str, job_data: Dict[str, Any], rule_template: Dict[str, Any]) -> Task:
    """Build a task from job data and rule template."""
    # This is a simplified version - the full implementation would be more complex
    task = Task(id=rule_name)
    
    # Set command from job data
    if "shellcmd" in job_data:
        task.command.set_for_environment(job_data["shellcmd"], "shared_filesystem")
    
    # Set resources from job data
    if "resources" in job_data:
        resources = job_data["resources"]
        if "threads" in resources:
            task.threads.set_for_environment(resources["threads"], "shared_filesystem")
        if "mem_mb" in resources:
            task.mem_mb.set_for_environment(resources["mem_mb"], "shared_filesystem")
    
    # Set inputs and outputs from job data
    if "input" in job_data:
        task.inputs = [ParameterSpec(id=f, type="File") for f in job_data["input"]]
    if "output" in job_data:
        task.outputs = [ParameterSpec(id=f, type="File") for f in job_data["output"]]
    
    return task


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def to_workflow(path: Union[str, Path], **opts: Any) -> Workflow:
    """Convert Snakefile at *path* into a Workflow IR object using shared infrastructure.

    Parameters
    ----------
    path : Union[str, Path]
        Path to the Snakefile.
    workdir : Union[str, Path], optional
        Working directory for Snakemake execution.
    cores : int, optional
        Number of cores to use (default: 1).
    configfile : Union[str, Path], optional
        Path to config file.
    snakemake_args : List[str], optional
        Additional arguments to pass to snakemake commands.
    config : Dict[str, Any], optional
        Base configuration dictionary.
    verbose : bool, optional
        Enable verbose output (default: False).
    debug : bool, optional
        Enable debug output (default: False).
    parse_only : bool, optional
        Parse Snakefile without requiring snakemake executable (default: False).
        This mode has limitations: no wildcard expansion, no job instantiation,
        no dependency resolution, and no actual workflow execution plan.
    interactive : bool, optional
        Enable interactive mode (default: False).

    Returns
    -------
    Workflow
        Populated IR instance.
    """
    importer = SnakemakeImporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False)
    )
    return importer.import_workflow(path, **opts)


def to_dag_info(*, snakefile_path: Union[str, Path], **kwargs) -> Dict[str, Any]:
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
            "threads": task.resources.get("threads"),
            "resources": task.resources,
            "conda_env_spec": task.environment.get("conda"),
            "container_img_url": task.environment.get("container"),
            "is_shell": task.meta.get("is_shell", False),
            "is_script": task.meta.get("is_script", False),
            "is_run": task.meta.get("is_run", False),
            "is_containerized": task.meta.get("is_containerized", False),
            "script_file": None, # No longer available in new IR
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


def _detect_transfer_mode(filepath: str, is_input: bool = True) -> str:
    """Detect appropriate transfer mode for a file based on path patterns.
    
    Parameters
    ----------
    filepath : str
        Path to the file
    is_input : bool
        Whether this is an input file (True) or output file (False)
        
    Returns
    -------
    str
        Transfer mode: "auto", "shared", "never", or "always"
    """
    # Convert to lowercase for pattern matching
    path_lower = filepath.lower()
    
    # Patterns indicating shared/networked storage
    shared_patterns = [
        '/nfs/', '/mnt/', '/shared/', '/data/', '/storage/',
        '/lustre/', '/gpfs/', '/beegfs/', '/ceph/',
        'gs://', 's3://', 'azure://', 'http://', 'https://', 'ftp://',
        '/scratch/', '/work/', '/project/', '/group/',
    ]
    
    # Patterns indicating local temporary files that shouldn't be transferred
    local_patterns = [
        '/tmp/', '/var/tmp/', '.tmp', 'temp_', 'tmp_',
        '/dev/', '/proc/', '/sys/',
        '.log', '.err', '.out',  # Log files typically local
    ]
    
    # Patterns indicating reference data that should be on shared storage
    reference_patterns = [
        '.genome', '.fa', '.fasta', '.fna', '.faa',
        '.gtf', '.gff', '.gff3', '.bed', '.sam', '.bam',
        'reference/', 'ref/', 'genome/', 'annotation/',
        '.idx', '.index', '.dict',  # Index files
    ]
    
    # Check for shared storage patterns
    if any(pattern in path_lower for pattern in shared_patterns):
        return "shared"
    
    # Check for local temporary patterns
    if any(pattern in path_lower for pattern in local_patterns):
        return "never"
    
    # For input files: check if it looks like reference data
    if is_input and any(pattern in path_lower for pattern in reference_patterns):
        return "shared"
    
    # For outputs in certain directories, assume they might be on shared storage
    if not is_input:
        output_shared_patterns = [
            'results/', 'output/', 'analysis/', 'processed/',
        ]
        if any(pattern in path_lower for pattern in output_shared_patterns):
            return "shared"
    
    # Default to auto for everything else
    return "auto"


def _create_task_from_rule_template(rule_name: str, rule_details: Dict[str, Any], verbose: bool = False, debug: bool = False) -> Task:
    """Create a task from a rule template in parse-only mode."""
    
    task = Task(id=rule_name, label=rule_name)
    
    # Initialize multi-environment specifications
    # The original code had MultiEnvironmentResourceSpec, MultiEnvironmentFileTransferSpec, MultiEnvironmentErrorHandlingSpec
    # but they are no longer imported. Assuming a simplified Task object for now.
    multi_env_resources = {}
    multi_env_file_transfer = {}
    multi_env_error_handling = {}
    
    # Extract inputs
    inputs = []
    if rule_details.get("input"):
        input_str = rule_details["input"]
        # Parse comma-separated inputs, handling quotes
        input_list = _parse_snakemake_list(input_str)
        for inp in input_list:
            if inp.strip():
                # Detect transfer mode based on file path patterns
                transfer_mode = _detect_transfer_mode(inp.strip(), is_input=True)
                
                # Create multi-environment file transfer specification
                if transfer_mode == "shared":
                    multi_env_file_transfer["mode"] = "shared"
                elif transfer_mode == "never":
                    multi_env_file_transfer["mode"] = "never"
                else:  # auto
                    multi_env_file_transfer["mode"] = "auto"
                
                param = ParameterSpec(id=inp.strip(), type="File", transfer_mode=transfer_mode)
                # Ensure type normalization
                param.type = param.type if hasattr(param.type, 'type') else ParameterSpec(id=param.id, type=param.type).type
                inputs.append(param)
    
    # Extract outputs
    outputs = []
    if rule_details.get("output"):
        output_str = rule_details["output"]
        # Parse comma-separated outputs, handling quotes
        output_list = _parse_snakemake_list(output_str)
        for out in output_list:
            if out.strip():
                # Detect transfer mode based on file path patterns
                transfer_mode = _detect_transfer_mode(out.strip(), is_input=False)
                
                # Create multi-environment file transfer specification for outputs
                if transfer_mode == "shared":
                    multi_env_file_transfer["mode"] = "shared"
                elif transfer_mode == "never":
                    multi_env_file_transfer["mode"] = "never"
                else:  # auto
                    multi_env_file_transfer["mode"] = "auto"
                
                param = ParameterSpec(id=out.strip(), type="File", transfer_mode=transfer_mode)
                # Ensure type normalization
                param.type = param.type if hasattr(param.type, 'type') else ParameterSpec(id=param.id, type=param.type).type
                outputs.append(param)
    
    # Extract command/script
    command = None
    script = None
    
    if rule_details.get("shell"):
        command = rule_details["shell"]
    elif rule_details.get("script"):
        script = rule_details["script"]
    elif rule_details.get("run"):
        # For run blocks, store the code in meta and use a placeholder command
        command = f"# run block for rule {rule_name}"
        task.meta = {"run_block": rule_details["run"]}
    else:
        command = f"echo 'No command defined for rule {rule_name}'"
    
    task.command = command
    if script:
        task.script = script
    
    # Extract resources and populate multi-environment specifications
    if rule_details.get("resources"):
        resources = {}
        for key, value in rule_details["resources"].items():
            if key == "mem_mb":
                resources["mem_mb"] = int(value)
                # Multi-environment: shared filesystem typically needs less explicit memory
                multi_env_resources["mem_mb"] = int(value)
                multi_env_resources["mem_mb"] = int(value) # This line seems redundant, should be multi_env_resources["mem_mb"] = int(value)
                multi_env_resources["mem_mb"] = 0 # Shared systems often don't need explicit memory
            elif key == "disk_mb":
                resources["disk_mb"] = int(value)
                # Multi-environment: shared filesystem typically needs less explicit disk
                multi_env_resources["disk_mb"] = int(value)
                multi_env_resources["disk_mb"] = int(value) # This line seems redundant, should be multi_env_resources["disk_mb"] = int(value)
                multi_env_resources["disk_mb"] = 0 # Shared systems often don't need explicit disk
            elif key == "cpus":
                resources["cpu"] = int(value)
                # Multi-environment: CPU requirements apply to all environments
                multi_env_resources["cpu"] = int(value)
                multi_env_resources["cpu"] = int(value) # This line seems redundant, should be multi_env_resources["cpu"] = int(value)
                multi_env_resources["cpu"] = int(value)
            elif key == "time_min":
                resources["time_s"] = int(value)
                # Multi-environment: time limits apply to distributed and cloud environments
                multi_env_resources["time_s"] = int(value)
                multi_env_resources["time_s"] = int(value) # This line seems redundant, should be multi_env_resources["time_s"] = int(value)
                multi_env_resources["time_s"] = int(value)
            elif key == "gpu":
                resources["gpu"] = int(value)
                # Multi-environment: GPU requirements apply to distributed and cloud environments
                multi_env_resources["gpu"] = int(value)
                multi_env_resources["gpu"] = int(value) # This line seems redundant, should be multi_env_resources["gpu"] = int(value)
                multi_env_resources["gpu"] = int(value)
            elif key == "gpu_mem_mb":
                resources["gpu_mem_mb"] = int(value)
                # Multi-environment: GPU memory requirements apply to distributed and cloud environments
                multi_env_resources["gpu_mem_mb"] = int(value)
                multi_env_resources["gpu_mem_mb"] = int(value) # This line seems redundant, should be multi_env_resources["gpu_mem_mb"] = int(value)
                multi_env_resources["gpu_mem_mb"] = int(value)
            else:
                # Store other resources in metadata
                if task.metadata is None:
                    task.metadata = MetadataSpec()
                if "resources" not in task.metadata.format_specific:
                    task.metadata.format_specific["resources"] = {}
                task.metadata.format_specific["resources"][key] = value
        
        if any([resources.get("mem_mb"), resources.get("disk_mb"), resources.get("cpu"), resources.get("time_s"), resources.get("gpu"), resources.get("gpu_mem_mb")]):
            task.resources = resources
    
    # Extract environment
    if rule_details.get("conda"):
        environment = {"conda": rule_details["conda"]}
        if not task.environment:
            task.environment = {}
        task.environment.update(environment)
    
    if rule_details.get("container"):
        environment = {"container": rule_details["container"]}
        if not task.environment:
            task.environment = {}
        task.environment.update(environment)
    
    # Extract retries and populate multi-environment error handling
    if rule_details.get("retries"):
        task.retry = rule_details["retries"]
        # Multi-environment: retry logic is more important for distributed and cloud environments
        multi_env_error_handling["retry_count"] = rule_details["retries"]
        multi_env_error_handling["retry_count"] = rule_details["retries"] # This line seems redundant, should be multi_env_error_handling["retry_count"] = rule_details["retries"]
        multi_env_error_handling["retry_count"] = 0 # Shared systems often don't need explicit retries
    
    # Set multi-environment specifications on the task
    task.multi_env_resources = multi_env_resources
    task.multi_env_file_transfer = multi_env_file_transfer
    task.multi_env_error_handling = multi_env_error_handling
    
    # Store rule details in meta
    task.meta.update({
        "rule_name": rule_name,
        "rule_details": rule_details,
        "parse_only_mode": True,
        "limitations": [
            "No wildcard expansion",
            "No job instantiation", 
            "No dependency resolution",
            "Limited resource detection"
        ]
    })
    
    # Set inputs and outputs
    task.inputs = inputs
    task.outputs = outputs
    
    if debug:
        print(f"DEBUG: Created task '{rule_name}' with {len(inputs)} inputs, {len(outputs)} outputs")
    
    return task


def _parse_snakemake_list(list_str: str) -> List[str]:
    """Parse a Snakemake list string (comma-separated, possibly quoted)."""
    if not list_str:
        return []
    
    # Simple parsing - split by comma and strip whitespace
    # This is a basic implementation that could be enhanced for complex cases
    items = []
    current_item = ""
    in_quotes = False
    quote_char = None
    
    for char in list_str:
        if char in ['"', "'"] and not in_quotes:
            in_quotes = True
            quote_char = char
        elif char == quote_char and in_quotes:
            in_quotes = False
            quote_char = None
        elif char == ',' and not in_quotes:
            items.append(current_item.strip())
            current_item = ""
        else:
            current_item += char
    
    # Add the last item
    if current_item.strip():
        items.append(current_item.strip())
    
    return items


def _build_task_from_rule_details(rule_name: str, rule_details: Dict[str, Any]) -> Task:
    """Build a Task from parsed rule details."""
    
    task = Task(id=rule_name)
    
    # Set command or script
    if rule_details.get("shell"):
        task.command.set_for_environment(rule_details["shell"], "shared_filesystem")
    elif rule_details.get("script"):
        task.script.set_for_environment(rule_details["script"], "shared_filesystem")
    
    # Set resources
    if rule_details.get("resources"):
        resources = rule_details["resources"]
        if "mem_mb" in resources:
            task.mem_mb.set_for_environment(int(resources["mem_mb"]), "shared_filesystem")
        if "disk_mb" in resources:
            task.disk_mb.set_for_environment(int(resources["disk_mb"]), "shared_filesystem")
        if "cpus" in resources:
            task.cpu.set_for_environment(int(resources["cpus"]), "shared_filesystem")
        if "time_min" in resources:
            task.time_s.set_for_environment(int(resources["time_min"]), "shared_filesystem")
        if "gpu" in resources:
            task.gpu.set_for_environment(int(resources["gpu"]), "shared_filesystem")
        if "gpu_mem_mb" in resources:
            task.gpu_mem_mb.set_for_environment(int(resources["gpu_mem_mb"]), "shared_filesystem")
    
    # Set environment
    if rule_details.get("conda"):
        task.conda.set_for_environment(rule_details["conda"], "shared_filesystem")
    if rule_details.get("container"):
        task.container.set_for_environment(rule_details["container"], "shared_filesystem")
    
    # Set retries
    if rule_details.get("retries"):
        task.retry_count.set_for_environment(rule_details["retries"], "shared_filesystem")
    
    # Set inputs and outputs
    if rule_details.get("inputs"):
        for inp in rule_details["inputs"]:
            param = ParameterSpec(id=inp.strip(), type="File")
            task.inputs.append(param)
    
    if rule_details.get("outputs"):
        for out in rule_details["outputs"]:
            param = ParameterSpec(id=out.strip(), type="File")
            task.outputs.append(param)
    
    # Set checkpointing if present
    if rule_details.get("checkpointing"):
        cp = rule_details["checkpointing"]
        spec = CheckpointSpec(
            strategy=cp.get("strategy"),
            interval=cp.get("interval"),
            storage_location=cp.get("storage_location"),
            enabled=cp.get("enabled"),
            notes=cp.get("notes"),
        )
        task.checkpointing.set_for_environment(spec, "shared_filesystem")
    # Set logging if present
    if rule_details.get("logging"):
        lg = rule_details["logging"]
        spec = LoggingSpec(
            log_level=lg.get("log_level"),
            log_format=lg.get("log_format"),
            log_destination=lg.get("log_destination"),
            aggregation=lg.get("aggregation"),
            notes=lg.get("notes"),
        )
        task.logging.set_for_environment(spec, "shared_filesystem")
    # Set security if present
    if rule_details.get("security"):
        sec = rule_details["security"]
        spec = SecuritySpec(
            encryption=sec.get("encryption"),
            access_policies=sec.get("access_policies"),
            secrets=sec.get("secrets", {}),
            authentication=sec.get("authentication"),
            notes=sec.get("notes"),
        )
        task.security.set_for_environment(spec, "shared_filesystem")
    # Set networking if present
    if rule_details.get("networking"):
        net = rule_details["networking"]
        spec = NetworkingSpec(
            network_mode=net.get("network_mode"),
            allowed_ports=net.get("allowed_ports", []),
            egress_rules=net.get("egress_rules", []),
            ingress_rules=net.get("ingress_rules", []),
            notes=net.get("notes"),
        )
        task.networking.set_for_environment(spec, "shared_filesystem")
    
    return task
