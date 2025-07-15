"""wf2wf.exporters.dagman – Workflow IR ➜ HTCondor DAGMan

This module converts the wf2wf intermediate representation to HTCondor DAGMan format.
"""

from __future__ import annotations

import os
import re
import json
import shutil
import hashlib
import subprocess
import tempfile
import textwrap
import sys
import logging
from collections import defaultdict, namedtuple
from pathlib import Path
from typing import Any, Dict, List, Union

from wf2wf.core import Workflow, Task, EnvironmentSpecificValue
from wf2wf.exporters.base import BaseExporter
from wf2wf.exporters.inference import _has_env_value
from wf2wf.importers.inference import infer_condor_attributes
from wf2wf.environ import pack_conda_environment, generate_conda_activation_script

logger = logging.getLogger(__name__)


class DAGManExporter(BaseExporter):
    """DAGMan exporter using shared infrastructure."""
    
    def __init__(self, interactive: bool = False, verbose: bool = False, target_environment: str = "distributed_computing"):
        """Initialize DAGMan exporter with distributed_computing as default target environment."""
        super().__init__(interactive=interactive, verbose=verbose, target_environment=target_environment)
    
    def _get_target_format(self) -> str:
        """Get the target format name."""
        return "dagman"
    
    def _generate_output(self, workflow: Workflow, output_path: Path, **opts: Any) -> None:
        """Generate DAGMan output using shared infrastructure."""
        workdir = opts.get("workdir")
        scripts_dir = opts.get("scripts_dir")
        default_memory = opts.get("default_memory", "2GB")
        default_disk = opts.get("default_disk", "2GB")
        default_cpus = opts.get("default_cpus", 1)
        inline_submit = opts.get("inline_submit", False)
        debug = opts.get("debug", False)
        
        # Apply Condor-specific inference to generate appropriate attributes
        infer_condor_attributes(workflow, target_environment=self.target_environment)
        
        # Resolve paths & directories
        scripts_dir = Path(scripts_dir) if scripts_dir else output_path.with_name("scripts")
        scripts_dir.mkdir(parents=True, exist_ok=True)

        workdir = Path(workdir) if workdir else output_path.parent

        if self.verbose:
            logger.info(f"Writing DAG to {output_path}")
            logger.info(f"  scripts_dir = {scripts_dir}")
            logger.info(f"  workdir     = {workdir}")
            logger.info(f"  target_env  = {self.target_environment}")

        # Write wrapper shell scripts (one per task)
        script_paths: Dict[str, Path] = {}

        for task in workflow.tasks.values():
            script_file = scripts_dir / f"{self._sanitize_name(task.id)}.sh"
            self._write_task_wrapper_script(task, script_file)
            script_paths[task.id] = script_file

        if self.verbose:
            logger.info(f"  wrote {len(script_paths)} wrapper scripts → {scripts_dir}")

        # Report hook action for scripts dir as artefact
        try:
            from wf2wf import report as _rpt
            _rpt.add_artefact(output_path)
            _rpt.add_action("Exported DAGMan workflow")
        except ImportError:
            pass

        # Ensure logs dir
        (workdir / "logs").mkdir(exist_ok=True)

        # Generate DAG & submit-description blocks
        self._write_dag_file(
            workflow,
            output_path,
            script_paths,
            workdir=workdir,
            default_memory=default_memory,
            default_disk=default_disk,
            default_cpus=default_cpus,
            inline_submit=inline_submit,
        )

    def _write_task_wrapper_script(self, task: Task, path: Path):
        """Write wrapper script for a task using shared infrastructure."""
        # Use shared infrastructure for environment-specific value extraction
        # Note: Could use _has_env_value(task.command, self.target_environment) to check existence
        command = task.command.get_value_with_default(self.target_environment)
        script = task.script.get_value_with_default(self.target_environment)
        environment = self._get_task_environment_for_target(task)
        conda_env = environment.get('conda')
        
        # Handle conda environment if specified
        conda_activation_script = None
        if conda_env:
            try:
                # Package the conda environment
                env_tarball_path = pack_conda_environment(conda_env, path.parent)
                if self.verbose:
                    logger.info(f"Packaged conda environment '{conda_env}' to {env_tarball_path}")
                
                # Generate activation script
                conda_activation_script = generate_conda_activation_script(
                    env_tarball_path.name, command or script
                )
            except Exception as e:
                logger.warning(f"Failed to package conda environment '{conda_env}': {e}")
                # Fall back to direct conda activation
                conda_activation_script = f"#!/bin/bash\nset -euo pipefail\nconda activate {conda_env}\n"
        
        if script:
            # Copy script file
            script_path = Path(script)
            if script_path.exists():
                if conda_activation_script:
                    # Create wrapper that activates conda environment first
                    path.write_text(conda_activation_script)
                else:
                    shutil.copy2(script_path, path)
                # Make executable
                path.chmod(0o755)
            else:
                # Create placeholder script with proper format
                script_ext = script_path.suffix
                if conda_activation_script:
                    # Use conda activation script
                    path.write_text(conda_activation_script)
                else:
                    if script_ext in ('.py', '.PY'):
                        script_content = f"#!/bin/bash\nset -euo pipefail\npython {script}\n"
                    elif script_ext in ('.R', '.r'):
                        script_content = f"#!/bin/bash\nset -euo pipefail\nRscript {script}\n"
                    else:
                        script_content = f"#!/bin/bash\nset -euo pipefail\nbash {script}\n"
                    path.write_text(script_content)
                path.chmod(0o755)
        elif command:
            # Create wrapper script with command
            if conda_activation_script:
                # Use conda activation script
                path.write_text(conda_activation_script)
            else:
                path.write_text(f"#!/bin/bash\nset -euo pipefail\n{command}\n")
            path.chmod(0o755)
        else:
            # Create placeholder script
            if conda_activation_script:
                # Use conda activation script
                path.write_text(conda_activation_script)
            else:
                path.write_text(f"#!/bin/bash\nset -euo pipefail\necho 'No command defined'\nexit 1\n")
            path.chmod(0o755)

    def _write_dag_file(
        self,
        wf: Workflow,
        dag_path: Path,
        script_paths: Dict[str, Path],
        *,
        workdir: Path,
        default_memory: str,
        default_disk: str,
        default_cpus: int,
        inline_submit: bool = False,
    ):
        """Write DAG file with job definitions using shared infrastructure."""
        dag_lines = []
        
        # Header comment
        dag_lines.extend([
            f"# DAG file generated by wf2wf from workflow '{wf.name}'",
            "# Original format: Workflow IR",
            f"# Original workflow name: {wf.name}",
            f"# Original workflow version: {wf.version or None}",
            f"# Tasks: {len(wf.tasks)}, Dependencies: {len(wf.edges)}",
            "",
        ])
        
        # Job definitions
        for task in wf.tasks.values():
            script_path = script_paths[task.id]
            relative_script_path = script_path.relative_to(workdir)

            if inline_submit:
                # Inline submit description
                dag_lines.append(f"JOB {task.id} {{")
                submit_lines = self._generate_submit_content(
                    task, script_path, workdir, default_memory, default_disk, default_cpus
                )
                for line in submit_lines:
                    dag_lines.append(f"    {line}")
                dag_lines.append("}")
            else:
                # External submit file
                submit_file = dag_path.parent / f"{task.id}.sub"
                self._write_submit_file(
                    task, submit_file, script_path, workdir, default_memory, default_disk, default_cpus
                )
                dag_lines.append(f"JOB {task.id} {submit_file.name}")
            
            # Emit RETRY and PRIORITY lines using shared infrastructure
            retry = task.retry_count.get_value_with_default(self.target_environment)
            if retry and retry > 0:
                dag_lines.append(f"RETRY {task.id} {retry}")
            priority = task.priority.get_value_with_default(self.target_environment)
            if priority and priority > 0:
                dag_lines.append(f"PRIORITY {task.id} {priority}")
            
            dag_lines.append("")

        # Dependencies
        for edge in wf.edges:
            dag_lines.append(f"PARENT {edge.parent} CHILD {edge.child}")

        # Write DAG file using shared infrastructure
        dag_content = "\n".join(dag_lines)
        self._write_file(dag_content, dag_path)

    def _write_submit_file(
        self,
        task: Task,
        submit_path: Path,
        script_path: Path,
        workdir: Path,
        default_memory: str,
        default_disk: str,
        default_cpus: int,
    ):
        """Write submit file for a task using shared infrastructure."""
        submit_lines = self._generate_submit_content(
            task, script_path, workdir, default_memory, default_disk, default_cpus
        )
        submit_content = "\n".join(submit_lines)
        self._write_file(submit_content, submit_path)

    def _parse_memory_string(self, memory_str: str) -> int:
        """Parse memory string to MB."""
        memory_str = memory_str.upper()
        if memory_str.endswith("GB"):
            return int(float(memory_str[:-2]) * 1024)
        elif memory_str.endswith("MB"):
            return int(float(memory_str[:-2]))
        else:
            return int(float(memory_str))

    def _generate_submit_content(
        self,
        task: Task,
        script_path: Path,
        workdir: Path,
        default_memory: str,
        default_disk: str,
        default_cpus: int,
    ) -> List[str]:
        """Generate submit file content for a task using shared infrastructure."""
        submit_lines = []
        
        # Executable
        relative_script_path = script_path.relative_to(workdir)
        submit_lines.append(f"executable = {relative_script_path}")
        
        # Use BaseExporter helper methods for environment-specific value extraction
        resources = self._get_task_resources_for_target(task)
        environment = self._get_task_environment_for_target(task)
        error_handling = self._get_task_error_handling_for_target(task)
        advanced_features = self._get_task_advanced_features_for_target(task)
        
        # Debug output using logging convention
        if self.verbose:
            logger.debug(f"Task {task.id} resources: {resources}")
            logger.debug(f"Task {task.id} environment: {environment}")
            logger.debug(f"Task {task.id} error_handling: {error_handling}")
            logger.debug(f"Task {task.id} advanced_features: {advanced_features}")
        
        # Resource requirements - use extracted values with defaults
        cpu = resources.get('cpu', default_cpus)
        mem_mb = resources.get('mem_mb', self._parse_memory_string(default_memory))
        disk_mb = resources.get('disk_mb', self._parse_memory_string(default_disk))
        
        if self.verbose:
            logger.debug(f"Task {task.id} final CPU: {cpu} (from resources: {resources.get('cpu')}, default: {default_cpus})")
            logger.debug(f"Task {task.id} final memory: {mem_mb}MB (from resources: {resources.get('mem_mb')}, default: {self._parse_memory_string(default_memory)})")
            logger.debug(f"Task {task.id} final disk: {disk_mb}MB (from resources: {resources.get('disk_mb')}, default: {self._parse_memory_string(default_disk)})")
        
        submit_lines.append(f"request_cpus = {cpu}")
        submit_lines.append(f"request_memory = {mem_mb}MB")
        submit_lines.append(f"request_disk = {disk_mb}MB")
        
        # GPU if specified
        gpu = resources.get('gpu')
        if gpu:
            submit_lines.append(f"request_gpus = {gpu}")
        
        # GPU memory if specified
        gpu_mem = resources.get('gpu_mem_mb')
        if gpu_mem:
            submit_lines.append(f"gpus_minimum_memory = {gpu_mem}")
        
        # Container if specified
        container = environment.get('container')
        if container:
            if container.startswith("docker://"):
                submit_lines.append("universe = docker")
                # Strip docker:// prefix
                container_image = container[len("docker://"):]
                submit_lines.append(f"docker_image = {container_image}")
            elif container.endswith(".sif") or container.startswith("apptainer://"):
                submit_lines.append("universe = vanilla")
                submit_lines.append(f'+SingularityImage = "{container}"')
            else:
                submit_lines.append("universe = vanilla")
                submit_lines.append(f"executable = {container}")
        
        # Conda environment if specified
        conda = environment.get('conda')
        if conda:
            # Only set universe = vanilla if not already set by container
            if not container or not container.startswith("docker://"):
                submit_lines.append("universe = vanilla")
            # Note: Conda environments are now handled through packaging and activation scripts
            # The +CondaEnv attribute is not used as we package environments for portability
        
        # Working directory
        workdir_spec = environment.get('workdir')
        if workdir_spec:
            submit_lines.append(f"initialdir = {workdir_spec}")
        else:
            submit_lines.append(f"initialdir = {workdir}")
        
        # Log files
        submit_lines.append(f"log = logs/{task.id}.log")
        submit_lines.append(f"error = logs/{task.id}.err")
        submit_lines.append(f"output = logs/{task.id}.out")
        
        # Retry policy using shared infrastructure
        retry_count = error_handling.get('retry_count')
        if retry_count:
            submit_lines.append(f"retry = {retry_count}")
        
        # Priority using shared infrastructure
        priority = task.priority.get_value_with_default(self.target_environment)
        if priority:
            submit_lines.append(f"priority = {priority}")
        
        # Environment variables
        env_vars = environment.get('env_vars')
        if env_vars:
            for key, value in env_vars.items():
                submit_lines.append(f"environment = {key}={value}")
        
        # Extra attributes (custom Condor attributes) using shared infrastructure
        for key, value in task.extra.items():
            if key == "custom_attributes":
                # Handle custom_attributes as a dictionary of individual attributes
                if isinstance(value, EnvironmentSpecificValue):
                    custom_attrs = self._get_environment_specific_value_for_target(value)
                else:
                    custom_attrs = value
                
                if isinstance(custom_attrs, dict):
                    for attr_key, attr_value in custom_attrs.items():
                        submit_lines.append(f"{attr_key} = {attr_value}")
                else:
                    # Fallback: treat as single value
                    submit_lines.append(f"{key} = {custom_attrs}")
            else:
                # Handle other extra attributes normally
                if isinstance(value, EnvironmentSpecificValue):
                    extra_value = self._get_environment_specific_value_for_target(value)
                    if extra_value is not None:
                        submit_lines.append(f"{key} = {extra_value}")
                else:
                    submit_lines.append(f"{key} = {value}")
        
        # Record losses for unsupported features
        self._record_loss_if_present_for_target(task, "time_s", "Time limits not supported in DAGMan")
        self._record_loss_if_present_for_target(task, "threads", "Thread specification not supported in DAGMan")
        self._record_loss_if_present_for_target(task, "checkpointing", "Checkpointing not supported in DAGMan")
        self._record_loss_if_present_for_target(task, "logging", "Advanced logging not supported in DAGMan")
        self._record_loss_if_present_for_target(task, "security", "Security features not supported in DAGMan")
        self._record_loss_if_present_for_target(task, "networking", "Networking features not supported in DAGMan")
        self._record_loss_if_present_for_target(task, "file_transfer_mode", "File transfer modes not supported in DAGMan")
        self._record_loss_if_present_for_target(task, "staging_required", "Staging requirements not supported in DAGMan")
        self._record_loss_if_present_for_target(task, "cleanup_after", "Cleanup policies not supported in DAGMan")
            
        # Queue
        submit_lines.append("queue")
        
        return submit_lines
    
    def _sanitize_name(self, name: str) -> str:
        """Sanitize a name for use in file paths."""
        # Replace invalid characters with underscores
        sanitized = re.sub(r'[^\w\-_.]', '_', name)
        # Ensure it doesn't start with a number
        if sanitized and sanitized[0].isdigit():
            sanitized = f"task_{sanitized}"
        return sanitized

    def _sanitize_condor_job_name(self, name: str) -> str:
        """Sanitize a task ID for use as a Condor job name."""
        # Replace invalid characters with underscores
        sanitized = re.sub(r'[^\w\-_.]', '_', name)
        # Ensure it doesn't start with a number
        if sanitized and sanitized[0].isdigit():
            sanitized = f"task_{sanitized}"
        return sanitized
    
    
# Remove unused legacy functions
# prepare_conda_setup_jobs, build_and_push_docker_images, convert_docker_to_apptainer,
# generate_job_scripts, write_condor_dag - these are not used by the main exporter


def from_workflow(wf: Workflow, out_file: Union[str, Path], **opts: Any) -> None:
    """Export a Workflow IR to DAGMan format (public API)."""
    exporter = DAGManExporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False),
        target_environment=opts.get("target_environment", "distributed_computing")
    )
    exporter.export_workflow(wf, Path(out_file), **opts)
