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
from wf2wf.importers.inference import infer_environment_specific_values
from wf2wf.interactive import prompt_for_missing_information
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
        
        # Use shared inference for environment-specific values with the selected execution model
        infer_environment_specific_values(workflow, "snakemake", self._selected_execution_model)
        
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
    
    def _detect_missing_input_files(self, path: Path, workdir: Path, configfile: str, cores: int, snakemake_args: List[str], verbose: bool) -> List[str]:
        """
        Detect missing input files by parsing the Snakefile and checking file existence.
        Only files that are not produced by any rule (i.e., true workflow inputs) are checked.
        Returns:
            List of missing input file paths
        """
        import re
        from pathlib import Path
        
        missing_files = []
        all_input_files = set()
        all_output_files = set()
        
        # Parse the Snakefile to extract input and output files from rules
        try:
            with open(path, 'r') as f:
                content = f.read()
            
            # Find all rule definitions
            rule_pattern = re.compile(r'rule\s+(\w+):\s*\n(.*?)(?=\nrule|\n$)', re.DOTALL)
            for rule_match in rule_pattern.finditer(content):
                rule_name = rule_match.group(1)
                rule_body = rule_match.group(2)
                
                # Skip the 'all' rule as it's a target rule, not a processing rule
                if rule_name == 'all':
                    continue
                
                # Find input specification
                input_match = re.search(r'input:\s*\n(.*?)(?=\n\s*(?:output|params|resources|threads|conda|container|shell|script|run|benchmark|log|priority|group|local|restartable|shadow|wrapper|conda|container|envmodules|singularity|apptainer|notebook|script|shell|run|benchmark|log|priority|group|local|restartable|shadow|wrapper|conda|container|envmodules|singularity|apptainer|notebook|rule|$))', rule_body, re.DOTALL | re.IGNORECASE)
                if input_match:
                    input_spec = input_match.group(1).strip()
                    input_files = []
                    named_pattern = re.compile(r'(\w+)\s*=\s*["\']([^"\']+)["\']')
                    named_matches = named_pattern.findall(input_spec)
                    for name, file_path in named_matches:
                        input_files.append(file_path)
                    simple_pattern = re.compile(r'["\']([^"\']+)["\']')
                    simple_matches = simple_pattern.findall(input_spec)
                    for file_path in simple_matches:
                        if file_path not in [f for _, f in named_matches]:
                            input_files.append(file_path)
                    lines = input_spec.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line and not line.startswith('#') and not '=' in line:
                            unquoted_pattern = re.compile(r'([a-zA-Z0-9_/.-]+\.(?:txt|fastq|fq|bam|sam|vcf|bed|gtf|gff|fa|fasta|fna|faa|json|yaml|yml|html|png|jpg|jpeg|pdf|csv|tsv))')
                            unquoted_matches = unquoted_pattern.findall(line)
                            for file_path in unquoted_matches:
                                if file_path not in input_files:
                                    input_files.append(file_path)
                    for input_file in input_files:
                        if input_file and not input_file.startswith('{') and not input_file.startswith('*'):
                            all_input_files.add(input_file)
                # Find output specification
                output_match = re.search(r'output:\s*\n(.*?)(?=\n\s*(?:input|params|resources|threads|conda|container|shell|script|run|benchmark|log|priority|group|local|restartable|shadow|wrapper|conda|container|envmodules|singularity|apptainer|notebook|script|shell|run|benchmark|log|priority|group|local|restartable|shadow|wrapper|conda|container|envmodules|singularity|apptainer|notebook|rule|$))', rule_body, re.DOTALL | re.IGNORECASE)
                if output_match:
                    output_spec = output_match.group(1).strip()
                    output_files = []
                    named_pattern = re.compile(r'(\w+)\s*=\s*["\']([^"\']+)["\']')
                    named_matches = named_pattern.findall(output_spec)
                    for name, file_path in named_matches:
                        output_files.append(file_path)
                    simple_pattern = re.compile(r'["\']([^"\']+)["\']')
                    simple_matches = simple_pattern.findall(output_spec)
                    for file_path in simple_matches:
                        if file_path not in [f for _, f in named_matches]:
                            output_files.append(file_path)
                    lines = output_spec.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line and not line.startswith('#') and not '=' in line:
                            unquoted_pattern = re.compile(r'([a-zA-Z0-9_/.-]+\.(?:txt|fastq|fq|bam|sam|vcf|bed|gtf|gff|fa|fasta|fna|faa|json|yaml|yml|html|png|jpg|jpeg|pdf|csv|tsv))')
                            unquoted_matches = unquoted_pattern.findall(line)
                            for file_path in unquoted_matches:
                                if file_path not in output_files:
                                    output_files.append(file_path)
                    for output_file in output_files:
                        if output_file and not output_file.startswith('{') and not output_file.startswith('*'):
                            all_output_files.add(output_file)
        except Exception as e:
            if verbose:
                logger.warning(f"Error parsing Snakefile for input/output files: {e}")
        # Only check for input files that are not produced by any rule
        true_inputs = all_input_files - all_output_files
        for input_file in true_inputs:
            file_path = Path(input_file)
            if workdir:
                file_path = workdir / file_path
            if not file_path.exists():
                missing_files.append(input_file)
                if verbose:
                    logger.debug(f"Missing true input file: {input_file}")
        if verbose:
            logger.debug(f"Detected missing input files: {missing_files}")
        return missing_files

    def _handle_missing_input_files(self, missing_files: List[str], path: Path, verbose: bool) -> bool:
        """
        Handle missing input files by warning the user and optionally switching to parse-only mode.
        
        Returns:
            True if should continue with parse-only mode, False if should terminate
        """
        if not missing_files:
            return True  # No missing files, continue normally
        
        # Create warning message
        warning_msg = f"\n⚠️  Missing input files detected in {path.name}:\n"
        for file_path in missing_files:
            warning_msg += f"   - {file_path}\n"
        warning_msg += "\nThis will prevent Snakemake from building the DAG and extracting job details.\n"
        warning_msg += "You can:\n"
        warning_msg += "1. Create the missing input files and try again\n"
        warning_msg += "2. Use parse-only mode (limited functionality, no DAG/job details)\n"
        warning_msg += "3. Cancel the import\n"
        
        print(warning_msg)
        
        if self.interactive:
            # Interactive mode: ask user what to do
            while True:
                response = input("Choose option (1/2/3) or press Enter for parse-only mode: ").strip().lower()
                if response in ['', '2']:
                    if verbose:
                        logger.info("Switching to parse-only mode due to missing input files")
                    return True  # Continue with parse-only mode
                elif response == '1':
                    print("Please create the missing input files and run the import again.")
                    return False  # Terminate
                elif response == '3':
                    print("Import cancelled by user.")
                    return False  # Terminate
                else:
                    print("Invalid option. Please choose 1, 2, or 3.")
        else:
            # Non-interactive mode: default to parse-only mode
            if verbose:
                logger.info("Non-interactive mode: defaulting to parse-only mode due to missing input files")
            return True  # Continue with parse-only mode

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
        
        # --- ENVIRONMENT DEPENDENCY CHECK: EARLY EXIT IF NEEDED ---
        if not parse_only:
            if verbose:
                logger.info("Step 1.5: Checking environment dependencies...")
            dependencies = self._detect_environment_dependencies(path)
            
            # Check if we need to handle missing dependencies
            if (dependencies['conda']['required'] and not dependencies['conda']['available']) or \
                (dependencies['docker']['required'] and not dependencies['docker']['available']):
                
                if not self._handle_environment_dependencies(dependencies, path, verbose):
                    raise RuntimeError("Import terminated due to missing environment dependencies")
                
                # Switch to parse-only mode and skip all Snakemake subprocess calls
                parse_only = True
                result["parse_only"] = True
                if verbose:
                    logger.info("Continuing with parse-only mode due to missing environment dependencies")
        
        # --- MISSING INPUT FILE CHECK: EARLY EXIT IF NEEDED ---
        if not parse_only:
            if verbose:
                logger.info("Step 1.6: Checking for missing input files...")
            missing_files = self._detect_missing_input_files(path, workdir, configfile, cores, snakemake_args, verbose)
            if missing_files:
                should_continue = self._handle_missing_input_files(missing_files, path, verbose)
                if not should_continue:
                    raise RuntimeError("Import terminated due to missing input files")
                # Switch to parse-only mode and skip all Snakemake subprocess calls
                parse_only = True
                result["parse_only"] = True
                if verbose:
                    logger.info("Continuing with parse-only mode due to missing input files")
        
        # --- END CHECKS ---

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
        else:
            # In parse-only mode, use enhanced static parsing
            if verbose:
                logger.info("Parse-only mode: using enhanced static parsing...")
            
            static_data = self._extract_dependencies_static(path)
            result.update(static_data)
            
            # Set empty DAG and jobs for compatibility
            result["dag_output"] = ""
            result["dryrun_output"] = ""
            result["jobs"] = {}
            
            if verbose:
                logger.info("Parse-only mode: skipping Snakemake execution")

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
            # For the "all" rule, only include it as a task if it has both input and output specifications
            # If it only has inputs, it's a target specification and should be handled as workflow outputs, not a task
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

        # If DAG output is incomplete (only shows some rules), fall back to rule-based edge extraction
        if self._is_dag_output_incomplete(dot_output, rules):
            if self.verbose:
                logger.info("DAG output is incomplete, using rule-based edge extraction")
            return self._extract_edges_from_rules(rules, include_all_rule)

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

    def _is_dag_output_incomplete(self, dot_output: str, rules: Dict[str, Any]) -> bool:
        """Check if the DAG output is incomplete (doesn't show all rules)."""
        if not dot_output.strip():
            return True
        
        # Count rules in DAG output
        dag_rules = set()
        node_label_pattern = re.compile(r'label\s*=\s*"([^"]+)"')
        for line in dot_output.splitlines():
            m = node_label_pattern.search(line)
            if m:
                label = m.group(1)
                # Extract rule name from label
                if "\\n" in label:
                    rule_name = label.split("\\n", 1)[0].strip()
                else:
                    rule_name = label.split("\n", 1)[0].strip()
                if rule_name.startswith("rule "):
                    rule_name = rule_name[5:].strip()
                dag_rules.add(rule_name)
        
        # Count rules in parsed data
        parsed_rules = set(rules.keys())
        
        # DAG is incomplete if it shows fewer rules than parsed data
        is_incomplete = len(dag_rules) < len(parsed_rules)
        
        if self.verbose:
            logger.info(f"DAG rules: {dag_rules}")
            logger.info(f"Parsed rules: {parsed_rules}")
            logger.info(f"DAG incomplete: {is_incomplete}")
        
        return is_incomplete

    def _extract_edges_from_rules(self, rules: Dict[str, Any], include_all_rule: bool) -> List[Edge]:
        """Extract edges from rule input/output specifications."""
        edges = []
        seen = set()
        
        # Build mapping from output files to rule names
        output_to_rule = {}
        for rule_name, rule_data in rules.items():
            if "output" in rule_data:
                output_spec = rule_data["output"]
                # Handle both string and list outputs from parser
                if isinstance(output_spec, str):
                    outputs = [output_spec]
                else:
                    outputs = output_spec
                for output in outputs:
                    output_to_rule[output] = rule_name
        
        if self.verbose:
            logger.info(f"Output to rule mapping: {output_to_rule}")
        
        # Find edges by matching inputs to outputs
        for rule_name, rule_data in rules.items():
            if "input" in rule_data:
                input_spec = rule_data["input"]
                # Handle both string and list inputs from parser
                if isinstance(input_spec, str):
                    inputs = [input_spec]
                else:
                    inputs = input_spec
                for input_file in inputs:
                    if input_file in output_to_rule:
                        parent_rule = output_to_rule[input_file]
                        # Exclude edges involving the 'all' pseudo-task only if it's not a real task
                        if (parent_rule == "all" and not include_all_rule) or (rule_name == "all" and not include_all_rule):
                            continue
                        key = (parent_rule, rule_name)
                        if key not in seen:
                            edge = Edge(parent=parent_rule, child=rule_name)
                            edges.append(edge)
                            seen.add(key)
                            if self.verbose:
                                logger.debug(f"Created edge from I/O: {parent_rule} -> {rule_name} (via {input_file})")
        
        if self.verbose:
            logger.info(f"Extracted {len(edges)} edges from rule I/O specifications")
            for edge in edges:
                logger.debug(f"Edge: {edge.parent} -> {edge.child}")
        
        return edges
    
    # def _extract_environment_specific_values(self, parsed_data: Dict[str, Any], workflow: Workflow) -> None:
    #     """Extract environment-specific values from parsed data."""
    #     # Note: Config handling removed - config should be converted to proper IR parameters
    #     # rather than stored as opaque data
    
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

    def _detect_environment_dependencies(self, path: Path) -> Dict[str, Any]:
        """
        Detect environment dependencies (conda, docker) from Snakefile and check availability.
        
        Returns:
            Dictionary with dependency information and availability status
        """
        import subprocess
        import shutil
        
        dependencies = {
            'conda': {'required': False, 'available': False, 'environments': []},
            'docker': {'required': False, 'available': False, 'containers': []}
        }
        
        # Parse Snakefile for dependencies
        try:
            with open(path, 'r') as f:
                content = f.read()
            
            # Check for conda directives
            import re
            conda_pattern = r'conda:\s*["\']([^"\']+)["\']'
            conda_matches = re.findall(conda_pattern, content)
            if conda_matches:
                dependencies['conda']['required'] = True
                dependencies['conda']['environments'] = conda_matches
            
            # Check for container directives
            container_pattern = r'container:\s*["\']([^"\']+)["\']'
            container_matches = re.findall(container_pattern, content)
            if container_matches:
                dependencies['docker']['required'] = True
                dependencies['docker']['containers'] = container_matches
            
        except Exception as e:
            if self.verbose:
                logger.warning(f"Error parsing Snakefile for dependencies: {e}")
        
        # Check conda availability
        if dependencies['conda']['required']:
            conda_available = shutil.which('conda') is not None or shutil.which('mamba') is not None
            dependencies['conda']['available'] = conda_available
            
            if not conda_available and self.verbose:
                logger.warning("Conda environments required but conda/mamba not found in PATH")
        
        # Check Docker availability
        if dependencies['docker']['required']:
            try:
                # Check if docker command exists
                docker_exists = shutil.which('docker') is not None
                if docker_exists:
                    # Check if docker daemon is running
                    result = subprocess.run(['docker', 'info'], 
                                          capture_output=True, text=True, timeout=5)
                    docker_running = result.returncode == 0
                    dependencies['docker']['available'] = docker_running
                    
                    if not docker_running and self.verbose:
                        logger.warning("Docker containers required but Docker daemon not running")
                else:
                    dependencies['docker']['available'] = False
                    if self.verbose:
                        logger.warning("Docker containers required but docker command not found")
            except Exception as e:
                dependencies['docker']['available'] = False
                if self.verbose:
                    logger.warning(f"Error checking Docker availability: {e}")
        
        return dependencies

    def _handle_environment_dependencies(self, dependencies: Dict[str, Any], path: Path, verbose: bool) -> bool:
        """
        Handle environment dependency issues with interactive prompting.
        
        Args:
            dependencies: Dependency information from _detect_environment_dependencies
            path: Path to Snakefile
            verbose: Verbose logging flag
            
        Returns:
            True if import should proceed, False if cancelled
        """
        missing_deps = []
        
        if dependencies['conda']['required'] and not dependencies['conda']['available']:
            missing_deps.append(('conda', dependencies['conda']['environments']))
        
        if dependencies['docker']['required'] and not dependencies['docker']['available']:
            missing_deps.append(('docker', dependencies['docker']['containers']))
        
        if not missing_deps:
            return True  # All dependencies available
        
        # Show warning about missing dependencies
        print(f"\n⚠️  Environment dependencies missing for {path.name}:")
        for dep_type, items in missing_deps:
            print(f"   • {dep_type.upper()}: {', '.join(items)}")
        
        if self.interactive:
            print("\nOptions:")
            print("1. Use parse-only mode (static parsing, limited functionality)")
            print("2. Try to create missing conda environments (if conda available)")
            print("3. Skip container usage (if docker unavailable)")
            print("4. Cancel import")
            
            while True:
                try:
                    choice = input("\nSelect option (1-4): ").strip()
                    if choice == '1':
                        if verbose:
                            logger.info("User selected parse-only mode")
                        return True  # Will use parse-only mode
                    elif choice == '2':
                        if dependencies['conda']['required'] and not dependencies['conda']['available']:
                            print("❌ Conda not available, cannot create environments")
                            continue
                        if verbose:
                            logger.info("User selected to create conda environments")
                        return True  # Will try to create environments
                    elif choice == '3':
                        if dependencies['docker']['required'] and not dependencies['docker']['available']:
                            if verbose:
                                logger.info("User selected to skip container usage")
                            return True  # Will skip containers
                        else:
                            print("❌ No docker dependencies to skip")
                            continue
                    elif choice == '4':
                        if verbose:
                            logger.info("User cancelled import")
                        return False
                    else:
                        print("❌ Invalid choice, please enter 1-4")
                except KeyboardInterrupt:
                    print("\n❌ Import cancelled by user")
                    return False
        else:
            # Non-interactive mode: default to parse-only
            if verbose:
                logger.info("Non-interactive mode: defaulting to parse-only mode")
            return True

    def _extract_dependencies_static(self, path: Path) -> Dict[str, Any]:
        """
        Extract dependencies and workflow structure using static parsing.
        
        This method analyzes the Snakefile to infer:
        - Input/output file patterns
        - Wildcard relationships
        - Rule dependencies
        - Resource specifications
        
        Args:
            path: Path to Snakefile
            
        Returns:
            Dictionary with extracted information
        """
        import re
        from collections import defaultdict
        
        result = {
            'rules': {},
            'dependencies': defaultdict(set),
            'file_patterns': {},
            'wildcards': {}
        }
        
        try:
            # Parse rules using existing function
            parsed_rules = _parse_snakefile_for_rules(path, debug=getattr(self, 'debug', False))
            # Extract the actual rules from the parsed data
            result['rules'] = parsed_rules.get('rules', {})
            result['directives'] = parsed_rules.get('directives', {})
            
            # Extract file patterns and infer dependencies
            for rule_name, rule_details in rules.items():
                if rule_name == 'all':
                    continue  # Skip the 'all' rule for dependency analysis
                
                inputs = rule_details.get('input', [])
                outputs = rule_details.get('output', [])
                
                # Convert to lists if they're strings
                if isinstance(inputs, str):
                    inputs = [inputs]
                if isinstance(outputs, str):
                    outputs = [outputs]
                
                # Store file patterns
                result['file_patterns'][rule_name] = {
                    'inputs': inputs,
                    'outputs': outputs
                }
                
                # Extract wildcard patterns
                wildcards = self._extract_wildcard_patterns_from_rule(rule_name, inputs, outputs)
                if wildcards:
                    result['wildcards'][rule_name] = wildcards
                
                # Infer dependencies based on file patterns
                for output_pattern in outputs:
                    for other_rule, other_patterns in result['file_patterns'].items():
                        if other_rule == rule_name:
                            continue
                        
                        # Check if this rule's outputs are inputs to other rules
                        for other_input in other_patterns['inputs']:
                            if self._patterns_match(output_pattern, other_input):
                                result['dependencies'][other_rule].add(rule_name)
            
            if self.verbose:
                logger.info(f"Extracted {len(result['rules'])} rules with static parsing")
                logger.info(f"Inferred {len(result['dependencies'])} dependency relationships")
                
        except Exception as e:
            if self.verbose:
                logger.warning(f"Error in static dependency extraction: {e}")
        
        return result
    
    def _extract_wildcard_patterns_from_rule(self, rule_name: str, inputs: List[str], outputs: List[str]) -> Dict[str, str]:
        """
        Extract wildcard patterns from rule inputs and outputs.
        
        Args:
            rule_name: Name of the rule
            inputs: List of input patterns
            outputs: List of output patterns
            
        Returns:
            Dictionary mapping wildcard names to patterns
        """
        import re
        
        wildcards = {}
        
        # Look for wildcard patterns like {wildcard} or {wildcard,}
        wildcard_pattern = r'\{([^}]+)\}'
        
        # Check outputs first (they usually define the wildcard patterns)
        for output in outputs:
            matches = re.findall(wildcard_pattern, output)
            for match in matches:
                # Handle comma-separated wildcards
                for wc in match.split(','):
                    wc = wc.strip()
                    if wc and wc not in wildcards:
                        wildcards[wc] = output
        
        # Check inputs for additional wildcards
        for input_pattern in inputs:
            matches = re.findall(wildcard_pattern, input_pattern)
            for match in matches:
                for wc in match.split(','):
                    wc = wc.strip()
                    if wc and wc not in wildcards:
                        wildcards[wc] = input_pattern
        
        return wildcards
    
    def _patterns_match(self, pattern1: str, pattern2: str) -> bool:
        """
        Check if two file patterns could match (basic pattern matching).
        
        Args:
            pattern1: First file pattern
            pattern2: Second file pattern
            
        Returns:
            True if patterns could match
        """
        import re
        
        # Simple heuristic: check if patterns share common elements
        # This is a basic implementation - could be enhanced with more sophisticated matching
        
        # Remove wildcards for comparison
        clean1 = re.sub(r'\{[^}]+\}', '*', pattern1)
        clean2 = re.sub(r'\{[^}]+\}', '*', pattern2)
        
        # Check if one pattern is a subset of the other
        if clean1 == clean2:
            return True
        
        # Check if patterns share common path elements
        parts1 = clean1.split('/')
        parts2 = clean2.split('/')
        
        # Find common prefix
        common_length = 0
        for p1, p2 in zip(parts1, parts2):
            if p1 == p2 or p1 == '*' or p2 == '*':
                common_length += 1
            else:
                break
        
        # If they share most of their path, consider them matching
        return common_length >= min(len(parts1), len(parts2)) - 1


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


# def _workflow_to_dag_info(wf: Workflow) -> Dict[str, Any]:
#     """Convert a Workflow back to the legacy dag_info structure for compatibility."""

#     jobs = {}
#     job_dependencies = {}

#     for task in wf.tasks.values():
#         # Extract rule name and index from task_id (format: rule_name_index)
#         rule_name = task.meta.get("rule_name", task.id)

#         job_dict = {
#             "rule_name": rule_name,
#             "condor_job_name": _sanitize_condor_job_name(task.id),
#             "wildcards_dict": task.meta.get("wildcards_dict", {}),
#             "inputs": task.inputs,
#             "outputs": task.outputs,
#             "log_files": task.meta.get("log_files", []),
#             "shell_command": task.command,
#             "threads": task.resources.get("threads"),
#             "resources": task.resources,
#             "conda_env_spec": task.environment.get("conda"),
#             "container_img_url": task.environment.get("container"),
#             "is_shell": task.meta.get("is_shell", False),
#             "is_script": task.meta.get("is_script", False),
#             "is_run": task.meta.get("is_run", False),
#             "is_containerized": task.meta.get("is_containerized", False),
#             "script_file": None, # No longer available in new IR
#             "run_block_code": task.meta.get("run_block_code"),
#             "retries": task.retry_count.get_value_for('shared_filesystem'),
#             "params_dict": task.params,
#             "benchmark_file": None,
#             "container_img_path": None,
#         }

#         jobs[task.id] = job_dict

#     # Build job dependencies (child -> [parents])
#     for edge in wf.edges:
#         if edge.child not in job_dependencies:
#             job_dependencies[edge.child] = []
#         job_dependencies[edge.child].append(edge.parent)

#     return {
#         "jobs": jobs,
#         "job_dependencies": job_dependencies,
#         "snakefile": wf.name,
#         "config": wf.config,
#     }


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
    rule_name_pattern = re.compile(r"^\s*(rule|checkpoint)\s+(\w+):")
    configfile_pattern = re.compile(r"^\s*configfile:\s*['\"](.*?)['\"]")

    # 1. Find the starting line of all rules and top-level directives
    for i, line in enumerate(lines):
        match = rule_name_pattern.match(line)
        if match:
            rule_type = match.group(1)  # 'rule' or 'checkpoint'
            rule_name = match.group(2)
            rule_starts.append({"name": rule_name, "start": i, "type": rule_type})
            continue  # It's a rule, not a top-level directive

        config_match = configfile_pattern.match(line)
        if config_match:
            top_level_directives["configfile"] = config_match.group(1)

    if not rule_starts:
        templates["directives"] = top_level_directives
        return templates

    # Track non-Snakemake directives for warnings (persistent across all rules)
    non_snakemake_directives = set()
    
    # 2. The body of each rule is the text between its start and the next rule's start
    for i, rule_info in enumerate(rule_starts):
        rule_name = rule_info["name"]
        rule_type = rule_info["type"]  # 'rule' or 'checkpoint'
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
        
        # Store the rule type
        if rule_type == "checkpoint":
            details["checkpoint"] = True

        # 3. Parse directives from the extracted rule body
        # Robust, quote-aware parsing for key directives
        directives_to_capture = [
            "input", "output", "log", "conda", "container", "shell", "script", "priority"
        ]
        
        # Valid Snakemake directives (for warning about invalid ones)
        valid_snakemake_directives = {
            "input", "output", "log", "conda", "container", "shell", "script", "priority",
            "threads", "retries", "resources", "run", "params", "benchmark", "checkpoint",
            "group", "localrule", "shadow", "wrapper", "notebook", "envmodules"
        }
        
        # Track context to avoid flagging directives inside other directive blocks
        current_block = None
        block_start_patterns = ["resources:", "input:", "output:", "shell:", "run:", "script:", "conda:", "container:", "threads:", "retries:", "params:", "log:", "benchmark:"]
        
        # Process each line and handle indented directives properly
        i = 0
        while i < len(body_lines):
            line = body_lines[i]
            stripped = line.strip()
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                i += 1
                continue
            
            # FIRST: Check for any directive-like pattern to detect non-Snakemake directives
            # Check for directives that are not inside other directive blocks
            if ":" in stripped and not stripped.startswith("#"):
                # Check if we're inside a directive block by looking at indentation
                # If the line is indented, it's inside a block
                is_indented = line.startswith((" ", "\t"))
                
                # Check for unknown directives if we're not inside a block (not indented) OR if it's a potential directive
                # But skip if we're inside a resources block (resource keys are valid)
                if (not is_indented or (is_indented and ":" in stripped and not any(stripped.startswith(block) for block in block_start_patterns))) and current_block != "resources":
                    if debug:
                        logger.debug(f"Processing line '{stripped}' as potential directive")
                    potential_directive = stripped.split(":")[0].strip()
                    if debug:
                        logger.debug(f"Checking potential directive '{potential_directive}' in rule '{rule_name}'")
                    if (potential_directive and 
                        potential_directive not in valid_snakemake_directives and
                        not potential_directive.startswith(("shell:", "run:", "script:", "resources:", "conda:", "container:", "threads:", "retries:", "params:", "log:", "benchmark:")) and
                        not any(char in potential_directive for char in ['"', "'", "=", "/", "\\"]) and
                        (potential_directive.isalnum() or "_" in potential_directive)):
                        if debug:
                            logger.debug(f"Adding '{potential_directive}' to non-Snakemake directives")
                        non_snakemake_directives.add(potential_directive)
            
            # SECOND: Handle block context for known directives
            # Check if we're starting a new directive block
            for pattern in block_start_patterns:
                if stripped.startswith(pattern):
                    current_block = pattern.rstrip(":")
                    break
            
            # Check if we're ending a directive block (non-indented line that's not a directive)
            if current_block and not line.startswith((" ", "\t")) and stripped and ":" not in stripped:
                current_block = None
            
            # THIRD: Check if this line starts a directive (after stripping whitespace)
            directive_found = None
            for directive in directives_to_capture:
                if stripped.startswith(f"{directive}:"):
                    directive_found = directive
                    break
            
            # Parse known directives if found
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
                # Handle single-line input: input: "A.txt" or input: "A.txt", "B.txt"
                after_colon = line.split("input:", 1)[1].strip()
                if after_colon:
                    # Use the robust parser for single-line inputs too
                    items = _parse_snakemake_io_spec(after_colon)
                    for item in items:
                        if item and not item.startswith(("shell:", "run:", "script:", "resources:", "conda:", "container:", "threads:", "retries:", "params:", "log:", "benchmark:")):
                            input_lines.append(item)
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
                if any(stripped_line.startswith(d) for d in ["output:", "shell:", "run:", "script:", "resources:", "conda:", "container:", "threads:", "retries:", "params:", "log:", "benchmark:"]):
                    in_input_block = False

            if in_input_block and (line.startswith(" ") or line.startswith("\t")):
                input_lines.append(line.strip())

        if input_lines:
            # Parse the input specification
            input_items = []
            for line in input_lines:
                if line and not line.startswith("#"):
                    # Use the robust parser for input/output specifications
                    items = _parse_snakemake_io_spec(line)
                    for item in items:
                        if item and not item.startswith(("shell:", "run:", "script:", "resources:", "conda:", "container:", "threads:", "retries:", "params:", "log:", "benchmark:")):
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
                # Handle single-line output: output: "A.txt" or output: "A.txt", "B.txt"
                after_colon = line.split("output:", 1)[1].strip()
                if after_colon:
                    # Use the robust parser for single-line outputs too
                    items = _parse_snakemake_io_spec(after_colon)
                    for item in items:
                        if item and not item.startswith(("shell:", "run:", "script:", "resources:", "conda:", "container:", "threads:", "retries:", "params:", "log:", "benchmark:")):
                            output_lines.append(item)
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
                if any(stripped_line.startswith(d) for d in ["input:", "shell:", "run:", "script:", "resources:", "conda:", "container:", "threads:", "retries:", "params:", "log:", "benchmark:"]):
                    in_output_block = False

            if in_output_block and (line.startswith(" ") or line.startswith("\t")):
                output_lines.append(line.strip())

        if output_lines:
            # Parse the output specification
            output_items = []
            for line in output_lines:
                if line and not line.startswith("#"):
                    # Use the robust parser for input/output specifications
                    items = _parse_snakemake_io_spec(line)
                    for item in items:
                        if item and not item.startswith(("shell:", "run:", "script:", "resources:", "conda:", "container:", "threads:", "retries:", "params:", "log:", "benchmark:")):
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

        # State machine for the 'container:' block
        in_container_block = False
        container_lines = []
        container_directives = ["input:", "output:", "shell:", "run:", "script:", "resources:", "conda:", "threads:", "retries:", "params:"]
        for line in body_lines:
            stripped_line = line.strip()
            if stripped_line.startswith("container:"):
                # Handle single-line container: container: "docker://image:tag"
                after_colon = line.split("container:", 1)[1].strip()
                if after_colon:
                    # Parse container specification
                    container_spec = after_colon.strip().strip('"\'')
                    details["container"] = container_spec
                    in_container_block = False
                else:
                    in_container_block = True
                continue

            if in_container_block:
                # Only include indented lines that are not directives
                if line.startswith((" ", "\t")) and not any(stripped_line.startswith(d) for d in container_directives):
                    container_lines.append(line)
                else:
                    in_container_block = False

        if container_lines:
            # Parse multi-line container specification
            container_spec = "".join(container_lines).strip().strip('"\'')
            details["container"] = container_spec

        # State machine for the 'conda:' block
        in_conda_block = False
        conda_lines = []
        conda_directives = ["input:", "output:", "shell:", "run:", "script:", "resources:", "container:", "threads:", "retries:", "params:"]
        for line in body_lines:
            stripped_line = line.strip()
            if stripped_line.startswith("conda:"):
                # Handle single-line conda: conda: "environment.yaml"
                after_colon = line.split("conda:", 1)[1].strip()
                if after_colon:
                    # Parse conda specification
                    conda_spec = after_colon.split("#")[0].strip().strip('"\'')
                    details["conda"] = conda_spec
                    # Do NOT set in_conda_block = True for single-line
                else:
                    in_conda_block = True
                continue
            if in_conda_block:
                # Only include indented lines that do not start with another directive
                if (line.startswith(" ") or line.startswith("\t")) and not any(line.lstrip().startswith(d) for d in conda_directives):
                    conda_lines.append(line.strip())
                else:
                    # End of conda block
                    if conda_lines:
                        conda_spec = " ".join(conda_lines).split("#")[0].strip().strip('"\'')
                        details["conda"] = conda_spec
                    in_conda_block = False
                continue
        # If still in conda block at the end
        if in_conda_block and conda_lines:
            conda_spec = " ".join(conda_lines).split("#")[0].strip().strip('"\'')
            details["conda"] = conda_spec

        # State machine for the 'script:' block
        in_script_block = False
        script_lines = []
        script_directives = ["input:", "output:", "shell:", "run:", "resources:", "conda:", "container:", "threads:", "retries:", "params:"]
        for line in body_lines:
            stripped_line = line.strip()
            if stripped_line.startswith("script:"):
                # Handle single-line script: script: "script.py"
                after_colon = line.split("script:", 1)[1].strip()
                if after_colon:
                    # Parse script specification
                    script_spec = after_colon.strip().strip('"\'')
                    details["script"] = script_spec
                    # Do NOT set in_script_block = True for single-line
                else:
                    in_script_block = True
                continue

            if in_script_block:
                # Only include indented lines that don't start with other directives
                if line.startswith((" ", "\t")) and not any(stripped_line.startswith(d) for d in script_directives):
                    script_lines.append(line)
                elif not line.startswith((" ", "\t")) and stripped_line:
                    # Non-indented line or new directive - end the script block
                    in_script_block = False

        if script_lines:
            # Parse multi-line script specification
            script_spec = "".join(script_lines).strip().strip('"\'')
            details["script"] = script_spec

        # State machine for the 'shell:' block
        in_shell_block = False
        shell_lines = []
        for line in body_lines:
            stripped_line = line.strip()
            if stripped_line.startswith("shell:"):
                # Handle single-line shell: shell: "echo 'hello'"
                after_colon = line.split("shell:", 1)[1].strip()
                if after_colon:
                    # Parse shell specification
                    shell_spec = after_colon.strip().strip('"\'')
                    details["shell"] = shell_spec
                    in_shell_block = False
                else:
                    in_shell_block = True
                continue

            if (
                in_shell_block
                and line
                and not line.startswith((" ", "\t"))
                and stripped_line
            ):
                if ":" in stripped_line and not stripped_line.startswith("#"):
                    in_shell_block = False

            if in_shell_block:
                shell_lines.append(line)

        if shell_lines:
            # Parse multi-line shell specification
            shell_spec = "".join(shell_lines).strip().strip('"\'')
            details["shell"] = shell_spec

        # State machine for the 'threads:' block
        in_threads_block = False
        threads_lines = []
        for line in body_lines:
            stripped_line = line.strip()
            if stripped_line.startswith("threads:"):
                # Handle single-line threads: threads: 4
                after_colon = line.split("threads:", 1)[1].strip()
                if after_colon:
                    # Parse threads specification
                    threads_spec = after_colon.strip().strip('"\'')
                    try:
                        details["threads"] = int(threads_spec)
                    except ValueError:
                        details["threads"] = threads_spec
                    in_threads_block = False
                else:
                    in_threads_block = True
                continue

            if (
                in_threads_block
                and line
                and not line.startswith((" ", "\t"))
                and stripped_line
            ):
                if ":" in stripped_line and not stripped_line.startswith("#"):
                    in_threads_block = False

            if in_threads_block:
                threads_lines.append(line)

        if threads_lines:
            # Parse multi-line threads specification - strip comments
            threads_spec = "".join(threads_lines).split("#")[0].strip().strip('"\'')
            try:
                details["threads"] = int(threads_spec)
            except ValueError:
                details["threads"] = threads_spec

        # State machine for the 'retries:' block
        in_retries_block = False
        retries_lines = []
        for line in body_lines:
            stripped_line = line.strip()
            if stripped_line.startswith("retries:"):
                # Handle single-line retries: retries: 3
                after_colon = line.split("retries:", 1)[1].strip()
                if after_colon:
                    # Parse retries specification - strip comments
                    retries_spec = after_colon.split("#")[0].strip().strip('"\'')
                    try:
                        details["retries"] = int(retries_spec)
                    except ValueError:
                        details["retries"] = retries_spec
                    in_retries_block = False
                else:
                    in_retries_block = True
                continue

            if (
                in_retries_block
                and line
                and not line.startswith((" ", "\t"))
                and stripped_line
            ):
                if ":" in stripped_line and not stripped_line.startswith("#"):
                    in_retries_block = False

            if in_retries_block:
                retries_lines.append(line)

        if retries_lines:
            # Parse multi-line retries specification - strip comments
            retries_spec = "".join(retries_lines).split("#")[0].strip().strip('"\'')
            try:
                details["retries"] = int(retries_spec)
            except ValueError:
                details["retries"] = retries_spec

        if debug:
            print(f"DEBUG: Parsed rule '{rule_name}' with details: {details}")
        templates["rules"][rule_name] = details

    # Emit warnings for non-Snakemake directives found across all rules
    if non_snakemake_directives:
        import warnings
        warning_msg = f"Snakefile contains non-Snakemake directives that will be ignored: {', '.join(sorted(non_snakemake_directives))}"
        warnings.warn(warning_msg, UserWarning, stacklevel=2)

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
        input_spec = rule_details["input"]
        # Handle both string and list inputs from parser
        if isinstance(input_spec, str):
            input_list = [input_spec]
        else:
            input_list = input_spec
        for inp in input_list:
            if inp.strip():
                param = ParameterSpec(id=inp.strip(), type="File")
                inputs.append(param)
    task.inputs = inputs

    # Outputs
    outputs = []
    if rule_details.get("output"):
        output_spec = rule_details["output"]
        # Handle both string and list outputs from parser
        if isinstance(output_spec, str):
            output_list = [output_spec]
        else:
            output_list = output_spec
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
        task.retry_count.set_for_environment(int(rule_details["retries"]), "shared_filesystem")

    # Priority (environment-specific for shared_filesystem)
    if rule_details.get("priority"):
        task.priority.set_for_environment(rule_details["priority"], "shared_filesystem")

    # Store original rule details in metadata for potential future use
    if not task.metadata:
        task.metadata = MetadataSpec()
    task.metadata.add_format_specific("snakemake_rule", rule_details)

    return task



def _parse_snakemake_io_spec(spec_str: str) -> List[str]:
    """
    Parse a Snakemake input/output specification that can be either:
    1. A single quoted string: "file.txt"
    2. Comma-separated quoted strings: "file1.txt", "file2.txt"
    3. Python list syntax: ["file1.txt", "file2.txt"]
    """
    if not spec_str:
        return []
    
    spec_str = spec_str.strip()
    
    # Handle Python list syntax: ["file1.txt", "file2.txt"]
    if spec_str.startswith('[') and spec_str.endswith(']'):
        # Remove outer brackets
        inner_content = spec_str[1:-1].strip()
        if not inner_content:
            return []
        
        # Parse the inner content as comma-separated quoted strings
        items = []
        current_item = ""
        in_quotes = False
        quote_char = None
        
        for char in inner_content:
            if char in ['"', "'"] and not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
            elif char == ',' and not in_quotes:
                if current_item.strip():
                    items.append(current_item.strip().strip('"\''))
                current_item = ""
            else:
                current_item += char
        
        # Add the last item
        if current_item.strip():
            items.append(current_item.strip().strip('"\''))
        
        return [item for item in items if item]
    
    # Handle comma-separated quoted strings: "file1.txt", "file2.txt"
    items = []
    current_item = ""
    in_quotes = False
    quote_char = None
    
    for char in spec_str:
        if char in ['"', "'"] and not in_quotes:
            in_quotes = True
            quote_char = char
        elif char == quote_char and in_quotes:
            in_quotes = False
            quote_char = None
        elif char == ',' and not in_quotes:
            if current_item.strip():
                items.append(current_item.strip().strip('"\''))
            current_item = ""
        else:
            current_item += char
    
    # Add the last item
    if current_item.strip():
        items.append(current_item.strip().strip('"\''))
    
    return [item for item in items if item]


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
    if rule_details.get("input"):
        inputs = rule_details["input"]
        # Handle both single string and list of strings
        if isinstance(inputs, str):
            inputs = [inputs]
        for inp in inputs:
            param = ParameterSpec(id=inp.strip(), type="File")
            task.inputs.append(param)
    
    if rule_details.get("output"):
        outputs = rule_details["output"]
        # Handle both single string and list of strings
        if isinstance(outputs, str):
            outputs = [outputs]
        for out in outputs:
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
        input_spec = rule_details["input"]
        # Handle both string and list inputs
        if isinstance(input_spec, str):
            input_patterns = [input_spec]
        else:
            input_patterns = input_spec
        
        for i, input_pattern in enumerate(input_patterns):
            param = ParameterSpec(
                id=f"input_{i}",
                type="File",
                wildcard_pattern=input_pattern
            )
            task.inputs.append(param)
    
    # Outputs with wildcard patterns
    if "output" in rule_details:
        output_spec = rule_details["output"]
        # Handle both string and list outputs
        if isinstance(output_spec, str):
            output_patterns = [output_spec]
        else:
            output_patterns = output_spec
        
        for i, output_pattern in enumerate(output_patterns):
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
