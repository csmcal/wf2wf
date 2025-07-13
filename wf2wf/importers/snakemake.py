"""
Snakemake workflow importer.

This module provides functionality to import Snakemake workflows
into the workflow IR format.
"""

import json
import re
import shutil
import subprocess
import textwrap
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from wf2wf.core import (
    CheckpointSpec,
    Edge,
    EnvironmentSpecificValue,
    LoggingSpec,
    MetadataSpec,
    NetworkingSpec,
    ParameterSpec,
    ScatterSpec,
    SecuritySpec,
    Task,
    Workflow,
    TypeSpec,
)
from wf2wf.importers.base import BaseImporter
from wf2wf.importers.utils import parse_memory_string, parse_disk_string, parse_time_string, parse_resource_value
from wf2wf.importers.inference import infer_execution_model, infer_environment_specific_values
from wf2wf.interactive import prompt_for_execution_model_confirmation, prompt_for_missing_information
from wf2wf.loss import detect_and_apply_loss_sidecar, record

import logging

logger = logging.getLogger(__name__)


class SnakemakeImporter(BaseImporter):
    """Snakemake importer using shared base infrastructure with enhanced features."""
    
    def _create_basic_workflow(self, parsed_data: Dict[str, Any]) -> Workflow:
        """Create basic workflow from Snakemake data with format-specific enhancements."""
        if self.verbose:
            logger.info("Creating basic workflow from Snakemake data")
        
        # Create basic workflow using internal method
        workflow = self._create_basic_workflow_internal(parsed_data)
        
        # Apply Snakemake-specific enhancements
        self._enhance_snakemake_specific_features(workflow, parsed_data)
        
        return workflow
    
    def _create_basic_workflow_internal(self, parsed_data: Dict[str, Any]) -> Workflow:
        """Internal method to create the basic workflow structure."""
        workflow_name = parsed_data["workflow_name"]
        # Create workflow object
        wf = Workflow(
            name=workflow_name,
            version="1.0",
            execution_model=EnvironmentSpecificValue("shared_filesystem", ["shared_filesystem"]),
        )
        # Extract and add tasks
        tasks = self._extract_tasks(parsed_data)
        
        # Check for empty workflow
        # In parse_only mode, only check if tasks were extracted from rule templates
        # In normal mode, also check DAG output and jobs
        parse_only = parsed_data.get("parse_only", False)
        
        if parse_only:
            # In parse_only mode, only check if tasks were extracted
            if not tasks:
                raise RuntimeError("No jobs found")
        else:
            # In normal mode, check DAG output and jobs as well
            dag_output = parsed_data.get("dag_output", "")
            jobs = parsed_data.get("jobs", {})
            is_empty_dag = not dag_output.strip() or dag_output.strip() == "digraph snakemake_dag {}"
            has_no_jobs = not jobs or (isinstance(jobs, list) and len(jobs) == 0) or (isinstance(jobs, dict) and len(jobs) == 0)
            
            if not tasks or (is_empty_dag and has_no_jobs):
                raise RuntimeError("No jobs found")
            
        for task in tasks:
            wf.add_task(task)
        # Build a mapping from rule name/job label to task ID
        task_id_map = {task.id: task.id for task in tasks}
        # Extract and add edges, ensuring all endpoints exist
        edges = self._extract_edges(parsed_data)
        for edge in edges:
            if edge.parent not in task_id_map:
                raise ValueError(f"Parent task '{edge.parent}' not found in workflow. Available tasks: {list(task_id_map.keys())}")
            if edge.child not in task_id_map:
                raise ValueError(f"Child task '{edge.child}' not found in workflow. Available tasks: {list(task_id_map.keys())}")
            wf.add_edge(edge.parent, edge.child)
        
        # Extract workflow outputs from the "all" rule
        workflow_outputs = self._extract_workflow_outputs_from_all_rule(parsed_data)
        wf.outputs.extend(workflow_outputs)
        
        return wf
    
    def _enhance_snakemake_specific_features(self, workflow: Workflow, parsed_data: Dict[str, Any]):
        """Add Snakemake-specific enhancements not covered by shared infrastructure."""
        if self.verbose:
            logger.info("Adding Snakemake-specific enhancements...")
        
        # Apply loss side-car if available
        if hasattr(self, '_source_path') and self._source_path:
            self._apply_loss_sidecar(workflow, self._source_path)
        
        # Infer Snakemake-specific missing information using shared infrastructure
        self._infer_snakemake_specific_information(workflow, parsed_data)
        
        # Interactive prompting for Snakemake-specific configurations
        if self.interactive:
            self._prompt_for_snakemake_specific_information(workflow, parsed_data)
        
        # Environment management
        self._handle_environment_management(workflow, self._source_path, self._opts)
    
    def _infer_snakemake_specific_information(self, workflow: Workflow, parsed_data: Dict[str, Any]):
        """Infer Snakemake-specific missing information using shared infrastructure."""
        if self.verbose:
            logger.info("Inferring Snakemake-specific information using shared infrastructure...")
        
        # Use shared inference for execution model detection
        execution_model = infer_execution_model(workflow, "snakemake")
        workflow.execution_model.set_for_environment(execution_model, 'shared_filesystem')
        
        # Use shared inference for environment-specific values
        infer_environment_specific_values(workflow, "snakemake")
        
        # Snakemake-specific enhancements that aren't covered by shared infrastructure
        self._apply_snakemake_specific_defaults(workflow, parsed_data)
    
    def _apply_snakemake_specific_defaults(self, workflow: Workflow, parsed_data: Dict[str, Any]):
        """Apply Snakemake-specific defaults and enhancements."""
        for task in workflow.tasks.values():
            # Snakemake-specific threads handling
            if (task.threads.get_value_with_default('shared_filesystem') or 0) == 0:
                # Default to 1 thread for Snakemake tasks
                task.threads.set_for_environment(1, 'shared_filesystem')
            
            # Snakemake-specific wildcard processing (if available in parsed_data)
            if "wildcards" in parsed_data.get("rule_templates", {}).get(task.id, {}):
                wildcard_data = parsed_data["rule_templates"][task.id]["wildcards"]
                if wildcard_data:
                    # Create scatter specification for wildcard-based parallelization
                    scatter_spec = ScatterSpec(
                        scatter=list(wildcard_data.keys()),
                        scatter_method="dotproduct"
                    )
                    task.scatter.set_for_environment(scatter_spec, 'shared_filesystem')
    
    def _prompt_for_snakemake_specific_information(self, workflow: Workflow, parsed_data: Dict[str, Any]):
        """Interactive prompting for Snakemake-specific configurations."""
        if self.verbose:
            logger.info("Starting interactive prompting for Snakemake configurations...")
        
        # Use shared interactive prompting for execution model confirmation
        prompt_for_execution_model_confirmation(
            workflow, 
            "snakemake",
            content_analysis=parsed_data.get("rule_templates"),
            target_format=getattr(self, '_target_format', None)
        )
        
        # Use shared interactive prompting for common resource types
        prompt_for_missing_information(workflow, "snakemake")
        
        # Snakemake-specific environment prompting (if needed)
        self._prompt_for_snakemake_environments(workflow)
    
    def _prompt_for_snakemake_environments(self, workflow: Workflow):
        """Interactive prompting for Snakemake environment specifications."""
        for task in workflow.tasks.values():
            if not task.conda.get_value_for('shared_filesystem') and not task.container.get_value_for('shared_filesystem'):
                if self.interactive:
                    message = f"Task '{task.id}' has no environment specification. Add conda environment or container?"
                    response = self._prompt_user(message, "n")
                    if response.lower() in ['y', 'yes']:
                        env_type = self._prompt_user("Environment type (conda/container)?", "conda")
                        if env_type.lower() == 'conda':
                            env_spec = self._prompt_user("Conda environment specification?", "python=3.9")
                            task.conda.set_for_environment(env_spec, 'shared_filesystem')
                        elif env_type.lower() == 'container':
                            container_spec = self._prompt_user("Container specification?", "biocontainers/default:latest")
                            task.container.set_for_environment(container_spec, 'shared_filesystem')
    
    def _apply_loss_sidecar(self, workflow: Workflow, source_path: Path):
        """Apply loss side-car to Snakemake workflow."""
        if self.verbose:
            logger.info("Checking for loss side-car...")
        
        applied = detect_and_apply_loss_sidecar(workflow, source_path, self.verbose)
        if applied and self.verbose:
            logger.info("Applied loss side-car to restore lost information")
    
    def _handle_environment_management(self, workflow: Workflow, path: Path, opts: Dict[str, Any]):
        """Handle environment management for Snakemake workflows."""
        # This would integrate with the EnvironmentManager
        # For now, just log that environment management is available
        if self.verbose:
            logger.info("Environment management available for conda/container specifications")
    
    def _parse_source(self, path: Path, **opts: Any) -> Dict[str, Any]:
        """Parse Snakefile and extract all information."""
        # Store source path and opts for later use
        self._source_path = path
        self._opts = opts
        
        # Convert string to Path if needed
        if isinstance(path, str):
            path = Path(path)
        
        preserve_metadata = opts.get("preserve_metadata", True)
        parse_only = opts.get("parse_only", False)
        workdir = opts.get("workdir")
        configfile = opts.get("configfile")
        cores = opts.get("cores", 1)
        snakemake_args = opts.get("snakemake_args", [])
        verbose = self.verbose
        debug = opts.get("debug", False)

        # Check if snakemake executable is available (unless parse_only mode)
        if not parse_only:
            if not shutil.which("snakemake"):
                raise ImportError("snakemake executable not found in PATH")

        if verbose:
            logger.info(f"Step 1: Parsing Snakefile: {path}")

        # Convert workdir to Path if it's a string
        if workdir and isinstance(workdir, str):
            workdir = Path(workdir)

        # Parse the Snakefile for rule templates
        try:
            parsed_rules = _parse_snakefile_for_rules(path, debug=debug)
            if verbose:
                logger.info(f"Found {len(parsed_rules['rules'])} rule templates.")
        except Exception as e:
            raise RuntimeError(f"Failed to read or parse the Snakefile: {e}")

        # Get workflow name from directory or filename
        workflow_name = path.stem if path.stem != "Snakefile" else path.parent.name
        if workflow_name == ".":
            workflow_name = "snakemake_workflow"
        
        result = {
            "rules": parsed_rules["rules"],
            "directives": parsed_rules.get("directives", {}),
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
                logger.info("Step 2: Running `snakemake --dag` to get dependency graph...")

            dag_output = self._run_snakemake_dag(path, workdir, configfile, cores, snakemake_args, verbose)
            result["dag_output"] = dag_output
            
            # Get job details from `snakemake --dry-run`
            if verbose:
                logger.info("Step 3: Running `snakemake --dry-run` to get job details...")
            
            dryrun_output = self._run_snakemake_dryrun(path, workdir, configfile, cores, snakemake_args, verbose)
            result["dryrun_output"] = dryrun_output
            
            # Parse dry-run output to get job information
            if dryrun_output:
                jobs = _parse_dryrun_output(dryrun_output, debug=debug)
                result["jobs"] = jobs
                if debug:
                    logger.debug(f"Parsed {len(jobs)} jobs from dry-run output")

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
                logger.warning(f"`snakemake --dag` failed: {e}")
                logger.warning(f"STDOUT: {e.stdout}")
                logger.warning(f"STDERR: {e.stderr}")
            raise RuntimeError(f"snakemake --dag failed: {e}")
    
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
                logger.warning(f"`snakemake --dry-run` failed: {e}")
                logger.warning(f"STDOUT: {e.stdout}")
                logger.warning(f"STDERR: {e.stderr}")
            return ""
    
    def _extract_tasks(self, parsed_data: Dict[str, Any]) -> List[Task]:
        """Extract tasks from parsed Snakemake data using rule-based approach with wildcard preservation."""
        tasks = []
        rules = parsed_data.get("rules", {})
        jobs = parsed_data.get("jobs", {})
        
        if self.verbose:
            logger.info(f"Extracting tasks from {len(rules)} rules")
        
        # Convert jobs list to dictionary if needed (jobs from _parse_dryrun_output is a list)
        if isinstance(jobs, list):
            jobs_dict = {}
            for job_data in jobs:
                job_id = job_data.get("jobid", f"job_{len(jobs_dict)}")
                jobs_dict[job_id] = job_data
            jobs = jobs_dict
            if self.verbose:
                logger.debug(f"Converted {len(jobs)} jobs from list to dictionary format")
        
        # Group jobs by rule name to collect wildcard instances
        rule_jobs = {}
        for job_id, job_data in jobs.items():
            rule_name = job_data.get("rule_name", job_id)
            if rule_name not in rule_jobs:
                rule_jobs[rule_name] = []
            rule_jobs[rule_name].append((job_id, job_data))
        
        # Create one task per rule, with scatter information if multiple instances
        for rule_name, rule_details in rules.items():
            # For the "all" rule, only include it if it has both input and output specifications
            if rule_name == "all":
                has_input = "input" in rule_details
                has_output = "output" in rule_details
                if not (has_input and has_output):
                    continue  # Skip "all" rule if it only has inputs (target specification)
            
            rule_job_instances = rule_jobs.get(rule_name, [])
            
            if rule_job_instances:
                # Use the enhanced task builder with wildcard preservation
                task = _build_task_from_rule_with_wildcards(rule_name, rule_details, rule_job_instances)
            else:
                # Fallback to basic task creation from rule template
                task = _build_task_from_rule_details(rule_name, rule_details)
            
            tasks.append(task)
            
            if self.verbose:
                logger.info(f"Created task '{task.id}' with {len(task.inputs)} inputs, {len(task.outputs)} outputs")
        
        return tasks
    
    def _extract_edges(self, parsed_data: Dict[str, Any]) -> List[Edge]:
        """Extract edges from parsed Snakemake data using rule-based approach."""
        import re
        edges = []
        dot_output = parsed_data.get("dag_output", "")
        jobs = parsed_data.get("jobs", {})
        rules = parsed_data.get("rules", {})

        if self.verbose:
            logger.info("Extracting edges from DAG output")

        # Check if "all" rule should be included as a task
        all_rule_details = rules.get("all", {})
        include_all_rule = "input" in all_rule_details and "output" in all_rule_details

        # Build mapping from DOT node IDs to base rule names (first line of label)
        id_to_rule = {}
        node_label_pattern = re.compile(r'^(\w+)\s*\[label\s*=\s*"([^"]+)"')
        for line in dot_output.splitlines():
            line = line.strip()
            m = node_label_pattern.match(line)
            if m:
                node_id = m.group(1)
                label = m.group(2)
                # Extract base rule name (first part before any escaped newlines)
                # Handle both literal newlines and escaped \n
                if "\\n" in label:
                    rule_name = label.split("\\n", 1)[0].strip()
                else:
                    rule_name = label.split("\n", 1)[0].strip()
                # Remove "rule " prefix if present
                if rule_name.startswith("rule "):
                    rule_name = rule_name[5:].strip()
                id_to_rule[node_id] = rule_name
                if self.verbose:
                    logger.debug(f"Mapped node {node_id} -> rule '{rule_name}' (from label: '{label}')")

        if self.verbose:
            logger.info(f"Node ID to rule mapping: {id_to_rule}")

        # Parse edges: e.g. 1 -> 0, and deduplicate edges between rule names
        edge_pattern = re.compile(r'^(\w+)\s*->\s*(\w+)')
        seen = set()
        for line in dot_output.splitlines():
            line = line.strip()
            m = edge_pattern.match(line)
            if m:
                parent_id, child_id = m.group(1), m.group(2)
                # Always use id_to_rule mapping for both parent and child
                parent_rule = id_to_rule.get(parent_id)
                child_rule = id_to_rule.get(child_id)
                if parent_rule is None or child_rule is None:
                    if self.verbose:
                        logger.warning(f"Skipping edge {parent_id} -> {child_id}: node IDs not found in mapping")
                    continue
                # Exclude edges involving the 'all' pseudo-task only if it's not a real task
                if (parent_rule == "all" and not include_all_rule) or (child_rule == "all" and not include_all_rule):
                    continue
                key = (parent_rule, child_rule)
                if key not in seen:
                    edge = Edge(parent=parent_rule, child=child_rule)
                    edges.append(edge)
                    seen.add(key)
                    if self.verbose:
                        logger.debug(f"Created edge: {parent_rule} -> {child_rule} (from nodes {parent_id} -> {child_id})")
                else:
                    if self.verbose:
                        logger.debug(f"Skipping duplicate edge: {parent_rule} -> {child_rule}")

        if self.verbose:
            logger.info(f"Extracted {len(edges)} unique edges between rules")
            for edge in edges:
                logger.debug(f"Edge: {edge.parent} -> {edge.child}")

        return edges
    
    def _extract_environment_specific_values(self, parsed_data: Dict[str, Any], workflow: Workflow) -> None:
        """Extract environment-specific values from parsed data."""
        # Snakemake is inherently for shared filesystem, so set execution model
        workflow.execution_model.set_for_environment("shared_filesystem", "shared_filesystem")
        
        # Note: Config handling removed - config should be converted to proper IR parameters
        # rather than stored as opaque data
    
    def _get_source_format(self) -> str:
        """Get the source format name."""
        return "snakemake"

    def _extract_workflow_outputs_from_all_rule(self, parsed_data: Dict[str, Any]) -> List[ParameterSpec]:
        """Extract workflow outputs from the 'all' rule's input specification."""
        outputs = []
        
        # Get rules from parsed data (direct structure from parser)
        rules = parsed_data.get("rules", {})
        
        # Check if there's an "all" rule
        if "all" in rules:
            all_rule = rules["all"]
            if "input" in all_rule:
                # Parse the input specification from the "all" rule
                input_spec = all_rule["input"]
                if isinstance(input_spec, str):
                    # Single input
                    if input_spec.strip():
                        outputs.append(ParameterSpec(id=input_spec.strip(), type=TypeSpec(type="File")))
                elif isinstance(input_spec, list):
                    # Multiple inputs
                    for inp in input_spec:
                        if isinstance(inp, str) and inp.strip():
                            outputs.append(ParameterSpec(id=inp.strip(), type=TypeSpec(type="File")))
        
        return outputs


def _build_task_from_job_data(rule_name: str, job_data: Dict[str, Any], rule_template: Dict[str, Any]) -> Task:
    """Build a task from job data and rule template."""
    task = Task(id=rule_name)

    # Command
    if "shellcmd" in job_data:
        task.command.set_for_environment(job_data["shellcmd"], "shared_filesystem")

    # Resources
    if "resources" in job_data:
        resources = job_data["resources"]
        if "threads" in resources:
            task.threads.set_for_environment(resources["threads"], "shared_filesystem")
        if "mem_mb" in resources:
            task.mem_mb.set_for_environment(resources["mem_mb"], "shared_filesystem")
        if "disk_mb" in resources:
            task.disk_mb.set_for_environment(resources["disk_mb"], "shared_filesystem")
        if "gpu" in resources:
            task.gpu.set_for_environment(resources["gpu"], "shared_filesystem")
        if "gpu_mem_mb" in resources:
            task.gpu_mem_mb.set_for_environment(resources["gpu_mem_mb"], "shared_filesystem")
        if "time_min" in resources:
            task.time_s.set_for_environment(int(resources["time_min"]) * 60, "shared_filesystem")

    # Inputs/outputs
    if "input" in job_data:
        task.inputs = [ParameterSpec(id=f, type="File") for f in job_data["input"]]
    if "output" in job_data:
        task.outputs = [ParameterSpec(id=f, type="File") for f in job_data["output"]]

    # Environment
    if rule_template.get("conda"):
        task.conda.set_for_environment(rule_template["conda"], "shared_filesystem")
    if rule_template.get("container"):
        task.container.set_for_environment(rule_template["container"], "shared_filesystem")

    # Retries
    if rule_template.get("retries") is not None:
        task.retry_count.set_for_environment(int(rule_template["retries"]), "shared_filesystem")

    # Script/run block
    if rule_template.get("script"):
        task.script.set_for_environment(rule_template["script"], "shared_filesystem")
    elif rule_template.get("run"):
        task.script.set_for_environment(rule_template["run"], "shared_filesystem")

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
    if isinstance(path, str):
        path = Path(path)
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
            "retries": task.retry_count.get_value_for('shared_filesystem'),
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
        # Robust, quote-aware parsing for key directives
        directives_to_capture = [
            "input", "output", "log", "conda", "container", "shell", "script", "priority"
        ]
        
        # Process each line and handle indented directives properly
        i = 0
        while i < len(body_lines):
            line = body_lines[i]
            stripped = line.strip()
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                i += 1
                continue
            
            # Check if this line starts a directive (after stripping whitespace)
            directive_found = None
            for directive in directives_to_capture:
                if stripped.startswith(f"{directive}:"):
                    directive_found = directive
                    break
            
            if directive_found:
                # Find the start of the value (after colon)
                colon_pos = stripped.find(":")
                value = stripped[colon_pos + 1:].lstrip()
                
                # If value starts with a quote, capture until matching quote
                if value and value[0] in ('"', "'"):
                    quote_char = value[0]
                    value_body = value[1:]
                    collected = []
                    
                    # If the quote ends on the same line
                    if value_body.endswith(quote_char) and not value_body[:-1].endswith("\\"):
                        collected.append(value_body[:-1])
                    else:
                        collected.append(value_body)
                        i += 1
                        while i < len(body_lines):
                            l = body_lines[i]
                            if l.rstrip().endswith(quote_char) and not l.rstrip()[:-1].endswith("\\"):
                                collected.append(l.rstrip()[:-1])
                                break
                            else:
                                collected.append(l.rstrip("\n"))
                            i += 1
                    value = "\n".join(collected)
                else:
                    # Unquoted value (single line)
                    value = value.strip()
                
                details[directive_found] = value
            
            i += 1

        # Parse retries directive (simple numeric value)
        retries_pattern = re.compile(r"^\s*retries:\s*(\d+)", re.M)
        retries_match = retries_pattern.search(body)
        if retries_match:
            details["retries"] = int(retries_match.group(1))

        # State machine for the 'input:' block
        in_input_block = False
        input_lines = []
        for line in body_lines:
            stripped_line = line.strip()
            if stripped_line.startswith("input:"):
                # Handle single-line input: input: "A.txt"
                after_colon = line.split("input:", 1)[1].strip()
                if after_colon:
                    # Remove quotes and trailing commas
                    after_colon = after_colon.rstrip(",").strip('"\'')
                    if after_colon:
                        input_lines.append(after_colon)
                    in_input_block = False
                else:
                    in_input_block = True
                continue

            if (
                in_input_block
                and line
                and not line.startswith((" ", "\t"))
                and stripped_line
            ):
                # Check if this is the start of a new directive
                if any(stripped_line.startswith(d) for d in ["output:", "shell:", "run:", "script:", "resources:", "conda:", "container:", "threads:", "retries:"]):
                    in_input_block = False

            if in_input_block and (line.startswith(" ") or line.startswith("\t")):
                input_lines.append(line.strip())

        if input_lines:
            # Parse the input specification
            input_items = []
            for line in input_lines:
                if line and not line.startswith("#"):
                    # Split by comma and handle each item
                    items = [item.strip().strip('"\'') for item in line.split(",")]
                    for item in items:
                        item = item.strip()
                        if item and not item.startswith(("shell:", "run:", "script:", "resources:", "conda:", "container:", "threads:", "retries:")):
                            input_items.append(item)
            if input_items:
                if len(input_items) == 1:
                    details["input"] = input_items[0]
                else:
                    details["input"] = input_items

        # State machine for the 'output:' block
        in_output_block = False
        output_lines = []
        for line in body_lines:
            stripped_line = line.strip()
            if stripped_line.startswith("output:"):
                # Handle single-line output: output: "A.txt"
                after_colon = line.split("output:", 1)[1].strip()
                if after_colon:
                    after_colon = after_colon.rstrip(",").strip('"\'')
                    if after_colon:
                        output_lines.append(after_colon)
                    in_output_block = False
                else:
                    in_output_block = True
                continue

            if (
                in_output_block
                and line
                and not line.startswith((" ", "\t"))
                and stripped_line
            ):
                # Check if this is the start of a new directive
                if any(stripped_line.startswith(d) for d in ["input:", "shell:", "run:", "script:", "resources:", "conda:", "container:", "threads:", "retries:"]):
                    in_output_block = False

            if in_output_block and (line.startswith(" ") or line.startswith("\t")):
                output_lines.append(line.strip())

        if output_lines:
            # Parse the output specification
            output_items = []
            for line in output_lines:
                if line and not line.startswith("#"):
                    # Split by comma and handle each item
                    items = [item.strip().strip('"\'') for item in line.split(",")]
                    for item in items:
                        item = item.strip()
                        if item and not item.startswith(("shell:", "run:", "script:", "resources:", "conda:", "container:", "threads:", "retries:")):
                            output_items.append(item)
            if output_items:
                if len(output_items) == 1:
                    details["output"] = output_items[0]
                else:
                    details["output"] = output_items

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
                # Handle both = and : formats for resource assignments
                if "=" in res_line:
                    key, val = res_line.split("=", 1)
                    # Strip comments and clean up the value
                    val = val.split("#")[0].strip().strip(",")
                    # Skip shell commands (they should be parsed separately)
                    if key.strip() != "shell":
                        res_details[key.strip()] = val
                elif ":" in res_line:
                    key, val = res_line.split(":", 1)
                    # Strip comments and clean up the value
                    val = val.split("#")[0].strip().strip(",")
                    # Skip shell commands (they should be parsed separately)
                    if key.strip() != "shell":
                        res_details[key.strip()] = val
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

    # Inputs
    inputs = []
    if rule_details.get("input"):
        input_list = _parse_snakemake_list(rule_details["input"])
        for inp in input_list:
            if inp.strip():
                param = ParameterSpec(id=inp.strip(), type="File")
                inputs.append(param)
    task.inputs = inputs

    # Outputs
    outputs = []
    if rule_details.get("output"):
        output_list = _parse_snakemake_list(rule_details["output"])
        for out in output_list:
            if out.strip():
                param = ParameterSpec(id=out.strip(), type="File")
                outputs.append(param)
    task.outputs = outputs

    # Command/script (environment-specific for shared_filesystem)
    if rule_details.get("shell"):
        task.command.set_for_environment(rule_details["shell"], "shared_filesystem")
    elif rule_details.get("run"):
        task.script.set_for_environment(rule_details["run"], "shared_filesystem")
    elif rule_details.get("script"):
        task.script.set_for_environment(rule_details["script"], "shared_filesystem")

    # Resources (environment-specific for shared_filesystem)
    if rule_details.get("threads"):
        task.threads.set_for_environment(rule_details["threads"], "shared_filesystem")
    if rule_details.get("resources"):
        resources = rule_details["resources"]
        if isinstance(resources, dict):
            if "mem_mb" in resources:
                task.mem_mb.set_for_environment(resources["mem_mb"], "shared_filesystem")
            if "mem_gb" in resources:
                task.mem_mb.set_for_environment(resources["mem_gb"] * 1024, "shared_filesystem")
            if "disk_mb" in resources:
                task.disk_mb.set_for_environment(resources["disk_mb"], "shared_filesystem")
            if "disk_gb" in resources:
                # Convert GB to MB
                task.disk_mb.set_for_environment(int(resources["disk_gb"]) * 1024, "shared_filesystem")
            if "gpu" in resources:
                task.gpu.set_for_environment(resources["gpu"], "shared_filesystem")

    # Environment specifications (environment-specific for shared_filesystem)
    if rule_details.get("conda"):
        task.conda.set_for_environment(rule_details["conda"], "shared_filesystem")
    if rule_details.get("container"):
        task.container.set_for_environment(rule_details["container"], "shared_filesystem")

    # Retry logic (environment-specific for shared_filesystem)
    if rule_details.get("retries"):
        task.retry_count.set_for_environment(rule_details["retries"], "shared_filesystem")

    # Priority (environment-specific for shared_filesystem)
    if rule_details.get("priority"):
        task.priority.set_for_environment(rule_details["priority"], "shared_filesystem")

    # Store original rule details in metadata for potential future use
    if not task.metadata:
        task.metadata = MetadataSpec()
    task.metadata.add_format_specific("snakemake_rule", rule_details)

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
            mem_value = parse_memory_string(resources["mem_mb"])
            if mem_value is not None:
                task.mem_mb.set_for_environment(mem_value, "shared_filesystem")
        if "disk_mb" in resources:
            disk_value = parse_disk_string(resources["disk_mb"])
            if disk_value is not None:
                task.disk_mb.set_for_environment(disk_value, "shared_filesystem")
        if "disk_gb" in resources:
            # Convert GB to MB using utility function
            disk_value = parse_disk_string(f"{resources['disk_gb']}GB")
            if disk_value is not None:
                task.disk_mb.set_for_environment(disk_value, "shared_filesystem")
        if "threads" in resources:
            # Set both threads and cpu for compatibility
            threads_value = parse_resource_value(resources["threads"])
            if threads_value is not None:
                task.threads.set_for_environment(threads_value, "shared_filesystem")
                task.cpu.set_for_environment(threads_value, "shared_filesystem")
        if "cpus" in resources:
            cpu_value = parse_resource_value(resources["cpus"])
            if cpu_value is not None:
                task.cpu.set_for_environment(cpu_value, "shared_filesystem")
        if "time_min" in resources:
            # Convert minutes to seconds
            time_value = parse_resource_value(resources["time_min"])
            if time_value is not None:
                task.time_s.set_for_environment(time_value * 60, "shared_filesystem")
        if "gpu" in resources:
            gpu_value = parse_resource_value(resources["gpu"])
            if gpu_value is not None:
                task.gpu.set_for_environment(gpu_value, "shared_filesystem")
        if "gpu_mem_mb" in resources:
            gpu_mem_value = parse_memory_string(resources["gpu_mem_mb"])
            if gpu_mem_value is not None:
                task.gpu_mem_mb.set_for_environment(gpu_mem_value, "shared_filesystem")
    
    # Set environment
    if rule_details.get("conda"):
        task.conda.set_for_environment(rule_details["conda"], "shared_filesystem")
    if rule_details.get("container"):
        task.container.set_for_environment(rule_details["container"], "shared_filesystem")
    
    # Set retries
    if rule_details.get("retries"):
        task.retry_count.set_for_environment(rule_details["retries"], "shared_filesystem")
    
    # Set priority
    if rule_details.get("priority"):
        priority_value = parse_resource_value(rule_details["priority"])
        if priority_value is not None:
            task.priority.set_for_environment(priority_value, "shared_filesystem")
    
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


def _build_task_from_rule_with_wildcards(rule_name: str, rule_details: Dict[str, Any], rule_job_instances: List[tuple]) -> Task:
    """Build a task from rule details with wildcard pattern preservation and scatter information."""
    task = Task(id=rule_name)
    
    # Extract wildcard patterns and instances
    wildcard_patterns = _extract_wildcard_patterns(rule_details)
    wildcard_instances = _extract_wildcard_instances(rule_job_instances)
    
    # Set up scatter if multiple instances exist
    if len(rule_job_instances) > 1 and wildcard_instances:
        scatter_spec = ScatterSpec(
            scatter=list(wildcard_instances[0].keys()) if wildcard_instances else [],
            wildcard_instances=wildcard_instances
        )
        task.scatter.set_for_environment(scatter_spec, "shared_filesystem")
    
    # Command/script
    if rule_details.get("shell"):
        task.command.set_for_environment(rule_details["shell"], "shared_filesystem")
    elif rule_details.get("script"):
        task.script.set_for_environment(rule_details["script"], "shared_filesystem")
    elif rule_details.get("run"):
        task.script.set_for_environment(rule_details["run"], "shared_filesystem")
    
    # Resources - prioritize job data from dry-run output over rule template
    # First, try to get resources from job instances (dry-run output)
    job_resources = {}
    if rule_job_instances:
        # Use the first job instance's resources as representative
        first_job_data = rule_job_instances[0][1]  # (job_id, job_data)
        if "resources" in first_job_data:
            job_resources = first_job_data["resources"]
    
    # Set resources from job data (dry-run output) if available
    if job_resources:
        if "threads" in job_resources:
            threads_value = parse_resource_value(job_resources["threads"])
            if threads_value is not None:
                task.threads.set_for_environment(threads_value, "shared_filesystem")
        if "mem_mb" in job_resources:
            mem_value = parse_memory_string(job_resources["mem_mb"])
            if mem_value is not None:
                task.mem_mb.set_for_environment(mem_value, "shared_filesystem")
        if "disk_mb" in job_resources:
            disk_value = parse_disk_string(job_resources["disk_mb"])
            if disk_value is not None:
                task.disk_mb.set_for_environment(disk_value, "shared_filesystem")
        if "disk_gb" in job_resources:
            # Convert GB to MB using utility function
            disk_value = parse_disk_string(f"{job_resources['disk_gb']}GB")
            if disk_value is not None:
                task.disk_mb.set_for_environment(disk_value, "shared_filesystem")
        if "gpu" in job_resources:
            gpu_value = parse_resource_value(job_resources["gpu"])
            if gpu_value is not None:
                task.gpu.set_for_environment(gpu_value, "shared_filesystem")
        if "time_min" in job_resources:
            # Convert minutes to seconds
            time_value = parse_resource_value(job_resources["time_min"])
            if time_value is not None:
                task.time_s.set_for_environment(time_value * 60, "shared_filesystem")
    else:
        # Fallback to rule template resources
        if "threads" in rule_details:
            threads_value = parse_resource_value(rule_details["threads"])
            if threads_value is not None:
                task.threads.set_for_environment(threads_value, "shared_filesystem")
                task.cpu.set_for_environment(threads_value, "shared_filesystem")
        if "resources" in rule_details:
            resources = rule_details["resources"]
            if "mem_mb" in resources:
                mem_value = parse_memory_string(resources["mem_mb"])
                if mem_value is not None:
                    task.mem_mb.set_for_environment(mem_value, "shared_filesystem")
            if "disk_mb" in resources:
                disk_value = parse_disk_string(resources["disk_mb"])
                if disk_value is not None:
                    task.disk_mb.set_for_environment(disk_value, "shared_filesystem")
            if "disk_gb" in resources:
                # Convert GB to MB using utility function
                disk_value = parse_disk_string(f"{resources['disk_gb']}GB")
                if disk_value is not None:
                    task.disk_mb.set_for_environment(disk_value, "shared_filesystem")
            if "threads" in resources:
                # Set both threads and cpu for compatibility
                threads_value = parse_resource_value(resources["threads"])
                if threads_value is not None:
                    task.threads.set_for_environment(threads_value, "shared_filesystem")
                    task.cpu.set_for_environment(threads_value, "shared_filesystem")
            if "gpu" in resources:
                gpu_value = parse_resource_value(resources["gpu"])
                if gpu_value is not None:
                    task.gpu.set_for_environment(gpu_value, "shared_filesystem")
            if "time_min" in resources:
                # Convert minutes to seconds
                time_value = parse_resource_value(resources["time_min"])
                if time_value is not None:
                    task.time_s.set_for_environment(time_value * 60, "shared_filesystem")
    
    # Inputs with wildcard patterns
    if "input" in rule_details:
        for i, input_pattern in enumerate(rule_details["input"]):
            param = ParameterSpec(
                id=f"input_{i}",
                type="File",
                wildcard_pattern=input_pattern
            )
            task.inputs.append(param)
    
    # Outputs with wildcard patterns
    if "output" in rule_details:
        for i, output_pattern in enumerate(rule_details["output"]):
            param = ParameterSpec(
                id=f"output_{i}",
                type="File",
                wildcard_pattern=output_pattern
            )
            task.outputs.append(param)
    
    # Environment
    if rule_details.get("conda"):
        task.conda.set_for_environment(rule_details["conda"], "shared_filesystem")
    if rule_details.get("container"):
        task.container.set_for_environment(rule_details["container"], "shared_filesystem")
    
    # Retries
    if rule_details.get("retries") is not None:
        task.retry_count.set_for_environment(int(rule_details["retries"]), "shared_filesystem")
    
    # Priority
    if rule_details.get("priority"):
        priority_value = parse_resource_value(rule_details["priority"])
        if priority_value is not None:
            task.priority.set_for_environment(priority_value, "shared_filesystem")
    
    return task


def _extract_wildcard_patterns(rule_details: Dict[str, Any]) -> Dict[str, str]:
    """Extract wildcard patterns from rule details."""
    patterns = {}
    
    # Extract from input/output patterns
    for io_type in ["input", "output"]:
        if io_type in rule_details:
            for pattern in rule_details[io_type]:
                # Find wildcards in pattern like {wildcard}
                import re
                wildcards = re.findall(r'\{([^}]+)\}', pattern)
                for wildcard in wildcards:
                    patterns[wildcard] = pattern
    
    return patterns


def _extract_wildcard_instances(rule_job_instances: List[tuple]) -> List[Dict[str, str]]:
    """Extract wildcard instances from job instances."""
    instances = []
    
    for job_id, job_data in rule_job_instances:
        if "wildcards" in job_data:
            instances.append(job_data["wildcards"])
        else:
            # Try to extract from job_id if it contains wildcard info
            # This is a fallback for when wildcards aren't explicitly stored
            pass
    
    return instances
