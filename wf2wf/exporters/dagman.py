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
from collections import defaultdict, namedtuple
from pathlib import Path
from typing import Any, Dict, List, Union

from wf2wf.core import Workflow, Task, EnvironmentSpecificValue
from wf2wf.exporters.base import BaseExporter


class DAGManExporter(BaseExporter):
    """DAGMan exporter using shared infrastructure."""
    
    def _get_target_format(self) -> str:
        """Get the target format name."""
        return "dagman"
    
    def _generate_output(self, workflow: Workflow, output_path: Path, **opts: Any) -> None:
        """Generate DAGMan output."""
        workdir = opts.get("workdir")
        scripts_dir = opts.get("scripts_dir")
        default_memory = opts.get("default_memory", "2GB")
        default_disk = opts.get("default_disk", "2GB")
        default_cpus = opts.get("default_cpus", 1)
        inline_submit = opts.get("inline_submit", False)
        debug = opts.get("debug", False)
        # Use self.target_environment for all environment-specific logic
        target_env = self.target_environment
        
        # Apply Condor-specific inference to generate appropriate attributes
        from wf2wf.importers.inference import infer_condor_attributes
        infer_condor_attributes(workflow, target_environment=target_env)
        
        # Resolve paths & directories
        scripts_dir = Path(scripts_dir) if scripts_dir else output_path.with_name("scripts")
        scripts_dir.mkdir(parents=True, exist_ok=True)

        workdir = Path(workdir) if workdir else output_path.parent

        if self.verbose:
            print(f"[wf2wf.dagman] Writing DAG to {output_path}")
            print(f"  scripts_dir = {scripts_dir}")
            print(f"  workdir     = {workdir}")
            print(f"  target_env  = {target_env}")

        # Write wrapper shell scripts (one per task)
        script_paths: Dict[str, Path] = {}

        for task in workflow.tasks.values():
            script_file = scripts_dir / f"{_sanitize_condor_job_name(task.id)}.sh"
            _write_task_wrapper_script(task, script_file, target_env)
            script_paths[task.id] = script_file

        if self.verbose:
            print(f"  wrote {len(script_paths)} wrapper scripts → {scripts_dir}")

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
        _write_dag_file(
            workflow,
            output_path,
            script_paths,
            workdir=workdir,
            default_memory=default_memory,
            default_disk=default_disk,
            default_cpus=default_cpus,
            inline_submit=inline_submit,
            target_env=target_env,
        )


# Legacy function for backward compatibility
def from_workflow(
    wf: Workflow,
    out_file: Union[str, Path],
    *,
    workdir: Union[str, Path, None] = None,
    scripts_dir: Union[str, Path, None] = None,
    default_memory: str = "2GB",
    default_disk: str = "2GB",
    default_cpus: int = 1,
    inline_submit: bool = False,
    verbose: bool = False,
    debug: bool = False,
    **opts: Any,
) -> None:
    """Serialise *wf* into HTCondor DAGMan files (legacy function)."""
    exporter = DAGManExporter(
        interactive=opts.get("interactive", False),
        verbose=verbose
    )
    # Pass all options including inline_submit
    export_opts = {
        "workdir": workdir,
        "scripts_dir": scripts_dir,
        "default_memory": default_memory,
        "default_disk": default_disk,
        "default_cpus": default_cpus,
        "inline_submit": inline_submit,
        "debug": debug,
        **opts
    }
    exporter.export_workflow(wf, out_file, **export_opts)


# Helper functions (unchanged from original implementation)
def _sanitize_condor_job_name(name: str) -> str:
    """Sanitize name for Condor job."""
    import re
    # Replace spaces and special characters with underscores
    sanitized = re.sub(r'[^\w\-]', '_', name)
    # Ensure it doesn't start with a number
    if sanitized and sanitized[0].isdigit():
        sanitized = f"job_{sanitized}"
    return sanitized


def _write_task_wrapper_script(task: Task, path: Path, target_env: str):
    """Write wrapper script for a task."""
    # Try to get command from any environment, preferring distributed_computing
    command = None
    if isinstance(task.command, EnvironmentSpecificValue):
        command = (task.command.get_value_for(target_env) or 
                   task.command.get_value_for("shared_filesystem") or 
                   task.command.get_value_for("cloud_native"))
    else:
        # Handle legacy string command
        command = task.command
    
    script = None
    if isinstance(task.script, EnvironmentSpecificValue):
        script = (task.script.get_value_for(target_env) or 
                  task.script.get_value_for("shared_filesystem") or 
                  task.script.get_value_for("cloud_native"))
    else:
        # Handle legacy string script
        script = task.script
    
    if script:
        # Copy script file
        script_path = Path(script)
        if script_path.exists():
            shutil.copy2(script_path, path)
            # Make executable
            path.chmod(0o755)
        else:
            # Create placeholder script with proper format
            script_ext = script_path.suffix
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
        path.write_text(f"#!/bin/bash\nset -euo pipefail\n{command}\n")
        path.chmod(0o755)
    else:
        # Create placeholder script
        path.write_text(f"#!/bin/bash\nset -euo pipefail\necho 'No command defined'\nexit 1\n")
        path.chmod(0o755)


def _write_dag_file(
    wf: Workflow,
    dag_path: Path,
    script_paths: Dict[str, Path],
    *,
    workdir: Path,
    default_memory: str,
    default_disk: str,
    default_cpus: int,
    inline_submit: bool = False,
    target_env: str,
):
    """Write DAG file with job definitions."""
    dag_lines = []
    
    # Header comment
    dag_lines.extend([
        f"# DAG file generated by wf2wf from workflow '{wf.name}'",
        "# Original format: Workflow IR",
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
            submit_lines = _generate_submit_content(
                task, script_path, workdir, default_memory, default_disk, default_cpus, target_env
            )
            for line in submit_lines:
                dag_lines.append(f"    {line}")
            dag_lines.append("}")
        else:
            # External submit file
            submit_file = dag_path.parent / f"{task.id}.sub"
            _write_submit_file(
                task, submit_file, script_path, workdir, default_memory, default_disk, default_cpus, target_env
            )
            dag_lines.append(f"JOB {task.id} {submit_file.name}")
        
        # Emit RETRY and PRIORITY lines if set for any environment
        retry = (task.retry_count.get_value_for(target_env) or
                 task.retry_count.get_value_for("shared_filesystem") or
                 task.retry_count.get_value_for("cloud_native"))
        if retry and retry > 0:
            dag_lines.append(f"RETRY {task.id} {retry}")
        priority = (task.priority.get_value_for(target_env) or
                    task.priority.get_value_for("shared_filesystem") or
                    task.priority.get_value_for("cloud_native"))
        if priority and priority > 0:
            dag_lines.append(f"PRIORITY {task.id} {priority}")
        
        dag_lines.append("")

    # Dependencies
    for edge in wf.edges:
        dag_lines.append(f"PARENT {edge.parent} CHILD {edge.child}")

    # Write DAG file
    dag_path.write_text("\n".join(dag_lines))


def _write_submit_file(
    task: Task,
    submit_path: Path,
    script_path: Path,
    workdir: Path,
    default_memory: str,
    default_disk: str,
    default_cpus: int,
    target_env: str,
):
    """Write submit file for a task."""
    submit_lines = _generate_submit_content(
        task, script_path, workdir, default_memory, default_disk, default_cpus, target_env
    )
    submit_path.write_text("\n".join(submit_lines))


def _parse_memory_string(memory_str: str) -> int:
    """Parse memory string to MB."""
    memory_str = memory_str.upper()
    if memory_str.endswith("GB"):
        return int(float(memory_str[:-2]) * 1024)
    elif memory_str.endswith("MB"):
        return int(float(memory_str[:-2]))
    else:
        return int(float(memory_str))


def _generate_submit_content(
    task: Task,
    script_path: Path,
    workdir: Path,
    default_memory: str,
    default_disk: str,
    default_cpus: int,
    target_env: str,
) -> List[str]:
    """Generate submit file content for a task."""
    submit_lines = []
    
    # Executable
    relative_script_path = script_path.relative_to(workdir)
    submit_lines.append(f"executable = {relative_script_path}")
    
    # Resource requirements - use target environment values
    cpu = task.cpu.get_value_for(target_env) or default_cpus
    mem_mb = task.mem_mb.get_value_for(target_env) or _parse_memory_string(default_memory)
    disk_mb = task.disk_mb.get_value_for(target_env) or _parse_memory_string(default_disk)
    
    submit_lines.append(f"request_cpus = {cpu}")
    submit_lines.append(f"request_memory = {mem_mb}MB")
    submit_lines.append(f"request_disk = {disk_mb}MB")
    
    # GPU if specified
    gpu = task.gpu.get_value_for(target_env)
    if gpu:
        submit_lines.append(f"request_gpus = {gpu}")
    
    # GPU memory if specified
    gpu_mem = task.gpu_mem_mb.get_value_for(target_env)
    if gpu_mem:
        submit_lines.append(f"gpus_minimum_memory = {gpu_mem}")
    
    # Container if specified
    container = task.container.get_value_for(target_env)
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
    conda = task.conda.get_value_for(target_env)
    if conda:
        # Only set universe = vanilla if not already set by container
        if not container or not container.startswith("docker://"):
            submit_lines.append("universe = vanilla")
        submit_lines.append(f"+CondaEnv = {conda}")
    
    # Working directory
    submit_lines.append(f"initialdir = {workdir}")
    
    # Log files
    submit_lines.append(f"log = logs/{task.id}.log")
    submit_lines.append(f"error = logs/{task.id}.err")
    submit_lines.append(f"output = logs/{task.id}.out")
    
    # Retry policy
    retry_count = task.retry_count.get_value_for(target_env)
    if retry_count:
        submit_lines.append(f"retry = {retry_count}")
    
    # Priority
    priority = task.priority.get_value_for(target_env)
    if priority:
        submit_lines.append(f"priority = {priority}")
    
    # Environment variables
    env_vars = task.env_vars.get_value_for(target_env)
    if env_vars:
        for key, value in env_vars.items():
            submit_lines.append(f"environment = {key}={value}")
    
    # Extra attributes (custom Condor attributes)
    for key, value in task.extra.items():
        if isinstance(value, EnvironmentSpecificValue):
            extra_value = value.get_value_for(target_env)
            if extra_value is not None:
                submit_lines.append(f"{key} = {extra_value}")
        else:
            submit_lines.append(f"{key} = {value}")
    
    # Queue
    submit_lines.append("queue")
    
    return submit_lines


# Additional helper functions from original implementation
def prepare_conda_setup_jobs(dag_info, conda_prefix, verbose=False, debug=False):
    """Identifies unique conda environments and prepares setup jobs for them."""
    if verbose:
        print("INFO: Preparing conda environment setup jobs...")
    
    conda_envs = {}
    for job in dag_info["jobs"].values():
        env_spec = job.get("conda_env_spec")
        if (
            env_spec
            and Path(env_spec).is_file()
            and (env_spec.endswith(".yaml") or env_spec.endswith(".yml"))
        ):
            env_path = Path(env_spec).resolve()
            if env_path not in conda_envs:
                try:
                    content = env_path.read_bytes()
                    env_hash = hashlib.sha256(content).hexdigest()[:16]
                    env_install_path = Path(conda_prefix) / env_hash
                    conda_envs[env_path] = {
                        "hash": env_hash,
                        "install_path": env_install_path,
                        "content": content,
                    }
                except Exception as e:
                    if debug:
                        print(f"DEBUG: Failed to process conda env {env_spec}: {e}")
    
    return conda_envs


def build_and_push_docker_images(dag_info, docker_registry, verbose=False, debug=False):
    """Build and push Docker images for tasks that need them."""
    if verbose:
        print("INFO: Building and pushing Docker images...")
    
    # Implementation would go here
    pass


def convert_docker_to_apptainer(dag_info, sif_dir, verbose=False, debug=False):
    """Convert Docker images to Apptainer SIF format."""
    if verbose:
        print("INFO: Converting Docker images to Apptainer SIF...")
    
    # Implementation would go here
    pass


def generate_job_scripts(dag_info, output_dir="scripts", verbose=False, debug=False):
    """Generate job scripts from workflow information."""
    if verbose:
        print("INFO: Generating job scripts...")
    
    # Implementation would go here
    pass


def write_condor_dag(
    dag_info,
    output_file,
    script_paths,
    workdir,
    default_memory,
    default_disk,
    default_cpus,
    config,
    verbose=False,
    debug=False,
):
    """Write Condor DAG file (legacy function)."""
    if verbose:
        print("INFO: Writing Condor DAG file...")
    
    # Implementation would go here
    pass
