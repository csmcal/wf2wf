"""
wf2wf.exporters.interactive – Interactive prompting for missing values in exporters.

This module provides utilities for interactive prompting when converting
from the IR to target workflow formats.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from wf2wf.core import Workflow, Task, EnvironmentSpecificValue


def prompt_for_missing_values(workflow: Workflow, target_format: str, target_environment: str = "shared_filesystem") -> None:
    """Prompt user for missing values based on target format requirements and target environment."""
    
    # Check if interactive mode is disabled via environment variable
    if os.environ.get("WF2WF_NO_PROMPT") == "1":
        return
    
    if target_format == "cwl":
        _prompt_cwl_values(workflow, target_environment)
    elif target_format == "dagman":
        _prompt_dagman_values(workflow, target_environment)
    elif target_format == "snakemake":
        _prompt_snakemake_values(workflow, target_environment)
    elif target_format == "nextflow":
        _prompt_nextflow_values(workflow, target_environment)
    elif target_format == "wdl":
        _prompt_wdl_values(workflow, target_environment)
    elif target_format == "galaxy":
        _prompt_galaxy_values(workflow, target_environment)
    else:
        print(f"Warning: No interactive prompts for format '{target_format}'")


def _prompt_cwl_values(workflow: Workflow, environment: str) -> None:
    """Prompt for missing values for CWL export."""
    
    print("\n=== CWL Export Configuration ===")
    
    for task in workflow.tasks.values():
        task_prompts = []
        
        # Check for missing resource requirements
        if not _has_env_value(task.cpu, environment):
            task_prompts.append(("CPU cores", "cpu", int, 1))
        
        if not _has_env_value(task.mem_mb, environment):
            task_prompts.append(("Memory (MB)", "mem_mb", int, 4096))
        
        # Check for missing container specification
        if not _has_env_value(task.container, environment) and not _has_env_value(task.conda, environment):
            task_prompts.append(("Container image", "container", str, "default-runtime:latest"))
        
        # Check for missing command
        if not _has_env_value(task.command, environment) and not _has_env_value(task.script, environment):
            task_prompts.append(("Command", "command", str, ""))
        
        if task_prompts:
            print(f"\nTask: {task.id}")
            for prompt_text, field_name, value_type, default in task_prompts:
                value = _prompt_user(f"{prompt_text} (default: {default}): ", value_type, default)
                if value is not None:
                    getattr(task, field_name).set_for_environment(value, environment)


def _prompt_dagman_values(workflow: Workflow, environment: str) -> None:
    """Prompt for missing values for DAGMan export."""
    
    print("\n=== DAGMan Export Configuration ===")
    
    for task in workflow.tasks.values():
        task_prompts = []
        
        # Check for missing resource requirements
        if not _has_env_value(task.cpu, environment):
            task_prompts.append(("CPU cores", "cpu", int, 1))
        
        if not _has_env_value(task.mem_mb, environment):
            task_prompts.append(("Memory (MB)", "mem_mb", int, 4096))
        
        if not _has_env_value(task.disk_mb, environment):
            task_prompts.append(("Disk space (MB)", "disk_mb", int, 4096))
        
        # Check for missing retry policy
        if not _has_env_value(task.retry_count, environment):
            task_prompts.append(("Retry count", "retry_count", int, 2))
        
        if not _has_env_value(task.retry_delay, environment):
            task_prompts.append(("Retry delay (seconds)", "retry_delay", int, 60))
        
        # Check for missing container specification
        if not _has_env_value(task.container, environment) and not _has_env_value(task.conda, environment):
            task_prompts.append(("Container image", "container", str, "default-runtime:latest"))
        
        # Check for missing command
        if not _has_env_value(task.command, environment) and not _has_env_value(task.script, environment):
            task_prompts.append(("Command", "command", str, ""))
        
        if task_prompts:
            print(f"\nTask: {task.id}")
            for prompt_text, field_name, value_type, default in task_prompts:
                value = _prompt_user(f"{prompt_text} (default: {default}): ", value_type, default)
                if value is not None:
                    getattr(task, field_name).set_for_environment(value, environment)


def _prompt_snakemake_values(workflow: Workflow, environment: str) -> None:
    """Prompt for missing values for Snakemake export."""
    
    print("\n=== Snakemake Export Configuration ===")
    
    for task in workflow.tasks.values():
        task_prompts = []
        
        # Check for missing resource requirements
        if not _has_env_value(task.cpu, environment):
            task_prompts.append(("CPU cores", "cpu", int, 1))
        
        if not _has_env_value(task.mem_mb, environment):
            task_prompts.append(("Memory (MB)", "mem_mb", int, 4096))
        
        if not _has_env_value(task.threads, environment):
            task_prompts.append(("Threads", "threads", int, 1))
        
        # Check for missing environment specification
        if not _has_env_value(task.conda, environment) and not _has_env_value(task.container, environment):
            choice = _prompt_choice("Environment type", ["conda", "container", "none"], "conda")
            if choice == "conda":
                conda_env = _prompt_user("Conda environment file: ", str, "environment.yml")
                if conda_env:
                    task.conda.set_for_environment(conda_env, environment)
            elif choice == "container":
                container = _prompt_user("Container image: ", str, "default-runtime:latest")
                if container:
                    task.container.set_for_environment(container, environment)
        
        # Check for missing command
        if not _has_env_value(task.command, environment) and not _has_env_value(task.script, environment):
            task_prompts.append(("Command", "command", str, ""))
        
        if task_prompts:
            print(f"\nTask: {task.id}")
            for prompt_text, field_name, value_type, default in task_prompts:
                value = _prompt_user(f"{prompt_text} (default: {default}): ", value_type, default)
                if value is not None:
                    getattr(task, field_name).set_for_environment(value, environment)


def _prompt_nextflow_values(workflow: Workflow, environment: str) -> None:
    """Prompt for missing values for Nextflow export."""
    
    print("\n=== Nextflow Export Configuration ===")
    
    for task in workflow.tasks.values():
        task_prompts = []
        
        # Check for missing resource requirements
        if not _has_env_value(task.cpu, environment):
            task_prompts.append(("CPU cores", "cpu", int, 1))
        
        if not _has_env_value(task.mem_mb, environment):
            task_prompts.append(("Memory (MB)", "mem_mb", int, 4096))
        
        # Check for missing container specification
        if not _has_env_value(task.container, environment):
            task_prompts.append(("Container image", "container", str, "default-runtime:latest"))
        
        # Check for missing retry policy
        if not _has_env_value(task.retry_count, environment):
            task_prompts.append(("Retry count", "retry_count", int, 3))
        
        # Check for missing command
        if not _has_env_value(task.command, environment) and not _has_env_value(task.script, environment):
            task_prompts.append(("Command", "command", str, ""))
        
        if task_prompts:
            print(f"\nTask: {task.id}")
            for prompt_text, field_name, value_type, default in task_prompts:
                value = _prompt_user(f"{prompt_text} (default: {default}): ", value_type, default)
                if value is not None:
                    getattr(task, field_name).set_for_environment(value, environment)


def _prompt_wdl_values(workflow: Workflow, environment: str) -> None:
    """Prompt for missing values for WDL export."""
    
    print("\n=== WDL Export Configuration ===")
    
    for task in workflow.tasks.values():
        task_prompts = []
        
        # Check for missing resource requirements
        if not _has_env_value(task.cpu, environment):
            task_prompts.append(("CPU cores", "cpu", int, 1))
        
        if not _has_env_value(task.mem_mb, environment):
            task_prompts.append(("Memory (MB)", "mem_mb", int, 4096))
        
        if not _has_env_value(task.disk_mb, environment):
            task_prompts.append(("Disk space (MB)", "disk_mb", int, 4096))
        
        # Check for missing container specification
        if not _has_env_value(task.container, environment) and not _has_env_value(task.conda, environment):
            task_prompts.append(("Container image", "container", str, "default-runtime:latest"))
        
        # Check for missing command
        if not _has_env_value(task.command, environment) and not _has_env_value(task.script, environment):
            task_prompts.append(("Command", "command", str, ""))
        
        if task_prompts:
            print(f"\nTask: {task.id}")
            for prompt_text, field_name, value_type, default in task_prompts:
                value = _prompt_user(f"{prompt_text} (default: {default}): ", value_type, default)
                if value is not None:
                    getattr(task, field_name).set_for_environment(value, environment)


def _prompt_galaxy_values(workflow: Workflow, environment: str) -> None:
    """Prompt for missing values for Galaxy export."""
    
    print("\n=== Galaxy Export Configuration ===")
    
    for task in workflow.tasks.values():
        task_prompts = []
        
        # Check for missing resource requirements
        if not _has_env_value(task.cpu, environment):
            task_prompts.append(("CPU cores", "cpu", int, 1))
        
        if not _has_env_value(task.mem_mb, environment):
            task_prompts.append(("Memory (MB)", "mem_mb", int, 4096))
        
        # Check for missing environment specification
        if not _has_env_value(task.conda, environment) and not _has_env_value(task.container, environment):
            choice = _prompt_choice("Environment type", ["conda", "container", "none"], "conda")
            if choice == "conda":
                conda_env = _prompt_user("Conda environment file: ", str, "environment.yml")
                if conda_env:
                    task.conda.set_for_environment(conda_env, environment)
            elif choice == "container":
                container = _prompt_user("Container image: ", str, "default-runtime:latest")
                if container:
                    task.container.set_for_environment(container, environment)
        
        # Check for missing command
        if not _has_env_value(task.command, environment) and not _has_env_value(task.script, environment):
            task_prompts.append(("Command", "command", str, ""))
        
        if task_prompts:
            print(f"\nTask: {task.id}")
            for prompt_text, field_name, value_type, default in task_prompts:
                value = _prompt_user(f"{prompt_text} (default: {default}): ", value_type, default)
                if value is not None:
                    getattr(task, field_name).set_for_environment(value, environment)


def _prompt_user(prompt: str, value_type: type, default: Any) -> Optional[Any]:
    """Prompt user for input with type conversion and default value."""
    try:
        user_input = input(prompt).strip()
        if not user_input:
            return default
        return value_type(user_input)
    except (ValueError, KeyboardInterrupt):
        print(f"Using default value: {default}")
        return default


def _prompt_choice(prompt: str, choices: List[str], default: str) -> str:
    """Prompt user to choose from a list of options."""
    print(f"{prompt}:")
    for i, choice in enumerate(choices, 1):
        marker = " (default)" if choice == default else ""
        print(f"  {i}. {choice}{marker}")
    
    try:
        user_input = input("Enter choice: ").strip()
        if not user_input:
            return default
        
        choice_index = int(user_input) - 1
        if 0 <= choice_index < len(choices):
            return choices[choice_index]
        else:
            print(f"Invalid choice. Using default: {default}")
            return default
    except (ValueError, KeyboardInterrupt):
        print(f"Using default choice: {default}")
        return default


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