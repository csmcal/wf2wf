"""
wf2wf.exporters.inference – Intelligent inference for missing values in exporters.

This module provides utilities for inferring missing values when converting
from the IR to target workflow formats.
"""

from __future__ import annotations

from typing import Any, Dict, List

from wf2wf.core import Workflow, Task, EnvironmentSpecificValue


def infer_missing_values(workflow: Workflow, target_format: str, target_environment: str = "shared_filesystem", verbose: bool = False) -> None:
    """Infer missing values based on target format requirements and target environment."""
    
    if target_format == "cwl":
        _infer_cwl_values(workflow, target_environment, verbose)
    elif target_format == "dagman":
        _infer_dagman_values(workflow, target_environment, verbose)
    elif target_format == "snakemake":
        _infer_snakemake_values(workflow, target_environment, verbose)
    elif target_format == "nextflow":
        _infer_nextflow_values(workflow, target_environment, verbose)
    elif target_format == "wdl":
        _infer_wdl_values(workflow, target_environment, verbose)
    elif target_format == "galaxy":
        _infer_galaxy_values(workflow, target_environment, verbose)
    else:
        if verbose:
            print(f"Warning: No inference rules for format '{target_format}'")


def _infer_cwl_values(workflow: Workflow, environment: str, verbose: bool = False) -> None:
    """Infer missing values for CWL export."""
    
    # CWL typically runs in shared filesystem environment
    # environment = "shared_filesystem" # This line is removed as environment is now a parameter
    
    for task in workflow.tasks.values():
        # Infer resource requirements if missing
        if not _has_env_value(task.cpu, environment):
            task.cpu.set_for_environment(1, environment)
            if verbose:
                print(f"Inferred CPU=1 for task {task.id}")
        
        if not _has_env_value(task.mem_mb, environment):
            task.mem_mb.set_for_environment(4096, environment)
            if verbose:
                print(f"Inferred memory=4096MB for task {task.id}")
        
        # Infer container if missing but conda is present
        if not _has_env_value(task.container, environment) and _has_env_value(task.conda, environment):
            conda_env = task.conda.get_value_for(environment)
            if conda_env:
                # Create a generic container reference
                task.container.set_for_environment(f"conda-env:{conda_env}", environment)
                if verbose:
                    print(f"Inferred container from conda env for task {task.id}")
        
        # Infer command from script if missing
        if not _has_env_value(task.command, environment) and _has_env_value(task.script, environment):
            script_path = task.script.get_value_for(environment)
            if script_path:
                # Create a command to run the script
                if script_path.endswith('.py'):
                    task.command.set_for_environment(f"python {script_path}", environment)
                elif script_path.endswith('.sh'):
                    task.command.set_for_environment(f"bash {script_path}", environment)
                elif script_path.endswith('.R'):
                    task.command.set_for_environment(f"Rscript {script_path}", environment)
                else:
                    task.command.set_for_environment(f"./{script_path}", environment)
                if verbose:
                    print(f"Inferred command from script for task {task.id}")


def _infer_dagman_values(workflow: Workflow, environment: str, verbose: bool = False) -> None:
    """Infer missing values for DAGMan export."""
    
    # DAGMan typically runs in distributed computing environment
    # environment = "distributed_computing" # This line is removed as environment is now a parameter
    
    for task in workflow.tasks.values():
        # Infer resource requirements if missing
        if not _has_env_value(task.cpu, environment):
            task.cpu.set_for_environment(1, environment)
            if verbose:
                print(f"Inferred CPU=1 for task {task.id}")
        
        if not _has_env_value(task.mem_mb, environment):
            task.mem_mb.set_for_environment(4096, environment)
            if verbose:
                print(f"Inferred memory=4096MB for task {task.id}")
        
        if not _has_env_value(task.disk_mb, environment):
            task.disk_mb.set_for_environment(4096, environment)
            if verbose:
                print(f"Inferred disk=4096MB for task {task.id}")
        
        # Infer retry policy for distributed computing
        if not _has_env_value(task.retry_count, environment):
            task.retry_count.set_for_environment(2, environment)
            if verbose:
                print(f"Inferred retry_count=2 for task {task.id}")
        
        if not _has_env_value(task.retry_delay, environment):
            task.retry_delay.set_for_environment(60, environment)
            if verbose:
                print(f"Inferred retry_delay=60s for task {task.id}")
        
        # Infer container if missing but conda is present
        if not _has_env_value(task.container, environment) and _has_env_value(task.conda, environment):
            conda_env = task.conda.get_value_for(environment)
            if conda_env:
                # Create a generic container reference
                task.container.set_for_environment(f"conda-env:{conda_env}", environment)
                if verbose:
                    print(f"Inferred container from conda env for task {task.id}")
        
        # Infer file transfer mode for distributed computing
        if not _has_env_value(task.file_transfer_mode, environment):
            task.file_transfer_mode.set_for_environment("explicit", environment)
            if verbose:
                print(f"Inferred file_transfer_mode=explicit for task {task.id}")
        
        # Infer staging requirement for distributed computing
        if not _has_env_value(task.staging_required, environment):
            task.staging_required.set_for_environment(True, environment)
            if verbose:
                print(f"Inferred staging_required=True for task {task.id}")


def _infer_snakemake_values(workflow: Workflow, environment: str, verbose: bool = False) -> None:
    """Infer missing values for Snakemake export."""
    
    # Snakemake typically runs in shared filesystem environment
    # environment = "shared_filesystem" # This line is removed as environment is now a parameter
    
    for task in workflow.tasks.values():
        # Infer resource requirements if missing
        if not _has_env_value(task.cpu, environment):
            task.cpu.set_for_environment(1, environment)
            if verbose:
                print(f"Inferred CPU=1 for task {task.id}")
        
        if not _has_env_value(task.mem_mb, environment):
            task.mem_mb.set_for_environment(4096, environment)
            if verbose:
                print(f"Inferred memory=4096MB for task {task.id}")
        
        # Infer threads from CPU if missing
        if not _has_env_value(task.threads, environment) and _has_env_value(task.cpu, environment):
            cpu_value = task.cpu.get_value_for(environment)
            if cpu_value:
                task.threads.set_for_environment(cpu_value, environment)
                if verbose:
                    print(f"Inferred threads={cpu_value} from CPU for task {task.id}")
        
        # Infer conda environment if missing but container is present
        if not _has_env_value(task.conda, environment) and _has_env_value(task.container, environment):
            container = task.container.get_value_for(environment)
            if container and container.startswith("conda-env:"):
                conda_env = container.replace("conda-env:", "")
                task.conda.set_for_environment(conda_env, environment)
                if verbose:
                    print(f"Inferred conda env from container for task {task.id}")
        
        # Infer command from script if missing
        if not _has_env_value(task.command, environment) and _has_env_value(task.script, environment):
            script_path = task.script.get_value_for(environment)
            if script_path:
                # Create a command to run the script
                if script_path.endswith('.py'):
                    task.command.set_for_environment(f"python {script_path}", environment)
                elif script_path.endswith('.sh'):
                    task.command.set_for_environment(f"bash {script_path}", environment)
                elif script_path.endswith('.R'):
                    task.command.set_for_environment(f"Rscript {script_path}", environment)
                else:
                    task.command.set_for_environment(f"./{script_path}", environment)
                if verbose:
                    print(f"Inferred command from script for task {task.id}")


def _infer_nextflow_values(workflow: Workflow, environment: str, verbose: bool = False) -> None:
    """Infer missing values for Nextflow export."""
    
    # Nextflow typically runs in cloud-native environment
    # environment = "cloud_native" # This line is removed as environment is now a parameter
    
    for task in workflow.tasks.values():
        # Infer resource requirements if missing
        if not _has_env_value(task.cpu, environment):
            task.cpu.set_for_environment(1, environment)
            if verbose:
                print(f"Inferred CPU=1 for task {task.id}")
        
        if not _has_env_value(task.mem_mb, environment):
            task.mem_mb.set_for_environment(4096, environment)
            if verbose:
                print(f"Inferred memory=4096MB for task {task.id}")
        
        # Infer container for cloud-native execution
        if not _has_env_value(task.container, environment):
            task.container.set_for_environment("default-runtime:latest", environment)
            if verbose:
                print(f"Inferred default container for task {task.id}")
        
        # Infer retry policy for cloud execution
        if not _has_env_value(task.retry_count, environment):
            task.retry_count.set_for_environment(3, environment)
            if verbose:
                print(f"Inferred retry_count=3 for task {task.id}")
        
        # Infer file transfer mode for cloud
        if not _has_env_value(task.file_transfer_mode, environment):
            task.file_transfer_mode.set_for_environment("cloud_storage", environment)
            if verbose:
                print(f"Inferred file_transfer_mode=cloud_storage for task {task.id}")
        
        # Infer command from script if missing
        if not _has_env_value(task.command, environment) and _has_env_value(task.script, environment):
            script_path = task.script.get_value_for(environment)
            if script_path:
                # Create a command to run the script
                if script_path.endswith('.py'):
                    task.command.set_for_environment(f"python {script_path}", environment)
                elif script_path.endswith('.sh'):
                    task.command.set_for_environment(f"bash {script_path}", environment)
                elif script_path.endswith('.R'):
                    task.command.set_for_environment(f"Rscript {script_path}", environment)
                else:
                    task.command.set_for_environment(f"./{script_path}", environment)
                if verbose:
                    print(f"Inferred command from script for task {task.id}")


def _infer_wdl_values(workflow: Workflow, environment: str, verbose: bool = False) -> None:
    """Infer missing values for WDL export."""
    
    # WDL typically runs in shared filesystem environment
    # environment = "shared_filesystem" # This line is removed as environment is now a parameter
    
    for task in workflow.tasks.values():
        # Infer resource requirements if missing
        if not _has_env_value(task.cpu, environment):
            task.cpu.set_for_environment(1, environment)
            if verbose:
                print(f"Inferred CPU=1 for task {task.id}")
        
        if not _has_env_value(task.mem_mb, environment):
            task.mem_mb.set_for_environment(4096, environment)
            if verbose:
                print(f"Inferred memory=4096MB for task {task.id}")
        
        if not _has_env_value(task.disk_mb, environment):
            task.disk_mb.set_for_environment(4096, environment)
            if verbose:
                print(f"Inferred disk=4096MB for task {task.id}")
        
        # Infer container if missing but conda is present
        if not _has_env_value(task.container, environment) and _has_env_value(task.conda, environment):
            conda_env = task.conda.get_value_for(environment)
            if conda_env:
                # Create a generic container reference
                task.container.set_for_environment(f"conda-env:{conda_env}", environment)
                if verbose:
                    print(f"Inferred container from conda env for task {task.id}")
        
        # Infer command from script if missing
        if not _has_env_value(task.command, environment) and _has_env_value(task.script, environment):
            script_path = task.script.get_value_for(environment)
            if script_path:
                # Create a command to run the script
                if script_path.endswith('.py'):
                    task.command.set_for_environment(f"python {script_path}", environment)
                elif script_path.endswith('.sh'):
                    task.command.set_for_environment(f"bash {script_path}", environment)
                elif script_path.endswith('.R'):
                    task.command.set_for_environment(f"Rscript {script_path}", environment)
                else:
                    task.command.set_for_environment(f"./{script_path}", environment)
                if verbose:
                    print(f"Inferred command from script for task {task.id}")


def _infer_galaxy_values(workflow: Workflow, environment: str, verbose: bool = False) -> None:
    """Infer missing values for Galaxy export."""
    
    # Galaxy typically runs in shared filesystem environment
    # environment = "shared_filesystem" # This line is removed as environment is now a parameter
    
    for task in workflow.tasks.values():
        # Infer resource requirements if missing
        if not _has_env_value(task.cpu, environment):
            task.cpu.set_for_environment(1, environment)
            if verbose:
                print(f"Inferred CPU=1 for task {task.id}")
        
        if not _has_env_value(task.mem_mb, environment):
            task.mem_mb.set_for_environment(4096, environment)
            if verbose:
                print(f"Inferred memory=4096MB for task {task.id}")
        
        # Infer conda environment if missing but container is present
        if not _has_env_value(task.conda, environment) and _has_env_value(task.container, environment):
            container = task.container.get_value_for(environment)
            if container and container.startswith("conda-env:"):
                conda_env = container.replace("conda-env:", "")
                task.conda.set_for_environment(conda_env, environment)
                if verbose:
                    print(f"Inferred conda env from container for task {task.id}")
        
        # Infer command from script if missing
        if not _has_env_value(task.command, environment) and _has_env_value(task.script, environment):
            script_path = task.script.get_value_for(environment)
            if script_path:
                # Create a command to run the script
                if script_path.endswith('.py'):
                    task.command.set_for_environment(f"python {script_path}", environment)
                elif script_path.endswith('.sh'):
                    task.command.set_for_environment(f"bash {script_path}", environment)
                elif script_path.endswith('.R'):
                    task.command.set_for_environment(f"Rscript {script_path}", environment)
                else:
                    task.command.set_for_environment(f"./{script_path}", environment)
                if verbose:
                    print(f"Inferred command from script for task {task.id}")


def _has_env_value(env_value: EnvironmentSpecificValue, environment: str) -> bool:
    """Check if EnvironmentSpecificValue has a value for the given environment."""
    if env_value is None:
        return False
    
    # Check for environment-specific value
    value = env_value.get_value_for(environment)
    if value is not None:
        return True
    
    # Check for universal value (empty environments list)
    value = env_value.get_value_for("")
    return value is not None 