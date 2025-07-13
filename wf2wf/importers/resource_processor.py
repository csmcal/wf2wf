"""
wf2wf.importers.resource_processor – Shared Resource Processing for Importers

This module provides shared resource processing functionality that can be used
by all importers to handle resource inference, validation, and interactive prompting.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from wf2wf.core import Workflow, Task
from wf2wf import prompt


def process_workflow_resources(
    workflow: Workflow,
    resource_profile: Optional[str] = None,
    infer_resources: bool = False,
    validate_resources: bool = False,
    target_environment: str = "cluster",
    interactive: bool = False,
    verbose: bool = False,
) -> None:
    """
    Process resource requirements for a workflow.
    
    This function can be called by any importer to handle resource processing
    in a consistent way across all workflow formats.
    
    Parameters
    ----------
    workflow : Workflow
        The workflow to process resources for
    resource_profile : Optional[str]
        Resource profile to apply (shared, cluster, cloud, hpc, gpu, etc.)
    infer_resources : bool
        Whether to infer resources from command/script content
    validate_resources : bool
        Whether to validate resource specifications
    target_environment : str
        Target environment for validation (shared, cluster, cloud, hpc)
    interactive : bool
        Whether to prompt user for missing information
    verbose : bool
        Whether to print verbose output
    """
    
    try:
        from wf2wf.resource_utils import (
            apply_resource_profile,
            infer_resources_from_command,
            validate_resources as validate_resources_func,
            suggest_resource_profile,
            get_available_profiles
        )
    except ImportError:
        if verbose:
            print("⚠ Resource utilities not available - skipping resource management")
        return
    
    if verbose:
        print("🔧 Processing resource requirements...")
    
    # Apply resource inference if requested
    if infer_resources:
        if verbose:
            print("  Inferring resource requirements from commands...")
        
        for task in workflow.tasks.values():
            inferred = infer_resources_from_command(task.command, task.script, target_environment)
            
            # Only apply inferred values if current values are missing (None)
            if task.cpu.get_value_with_default(target_environment) is None and "cpu" in inferred:
                task.cpu.set_for_environment(inferred["cpu"], target_environment)
            if task.mem_mb.get_value_with_default(target_environment) is None and "mem_mb" in inferred:
                task.mem_mb.set_for_environment(inferred["mem_mb"], target_environment)
            if task.disk_mb.get_value_with_default(target_environment) is None and "disk_mb" in inferred:
                task.disk_mb.set_for_environment(inferred["disk_mb"], target_environment)
            if task.gpu.get_value_with_default(target_environment) is None and "gpu" in inferred:
                task.gpu.set_for_environment(inferred["gpu"], target_environment)
            if task.gpu_mem_mb.get_value_with_default(target_environment) is None and "gpu_mem_mb" in inferred:
                task.gpu_mem_mb.set_for_environment(inferred["gpu_mem_mb"], target_environment)
    
    # Apply resource profile if specified
    if resource_profile:
        if verbose:
            print(f"  Applying resource profile: {resource_profile}")
        
        for task in workflow.tasks.values():
            apply_resource_profile(task, resource_profile)
    
    # Validate resources if requested
    if validate_resources:
        if verbose:
            print(f"  Validating resources for target environment: {target_environment}")
        
        all_issues = []
        for task in workflow.tasks.values():
            issues = validate_resources_func(task, target_environment)
            if issues:
                all_issues.extend([f"{task.id}: {issue}" for issue in issues])
        
        if all_issues:
            print(f"⚠ Resource validation found {len(all_issues)} issues:")
            for issue in all_issues[:10]:  # Show first 10 issues
                print(f"  • {issue}")
            if len(all_issues) > 10:
                print(f"  ... and {len(all_issues) - 10} more issues")
        else:
            if verbose:
                print("  ✓ All resource specifications are valid")
    
    # Interactive prompting for missing resources
    if interactive:
        _interactive_resource_prompting(
            workflow, target_environment, verbose
        )
    
    # Suggest resource profiles for tasks without specifications
    if verbose:
        _suggest_resource_profiles(workflow, target_environment)


def _interactive_resource_prompting(
    workflow: Workflow, 
    target_environment: str, 
    verbose: bool = False
) -> None:
    """Handle interactive prompting for missing resource information."""
    
    # Check for missing critical resources
    missing_resources = []
    for task in workflow.tasks.values():
        if task.cpu.get_value_with_default(target_environment) is None:
            missing_resources.append(f"{task.id} (CPU)")
        if task.mem_mb.get_value_with_default(target_environment) is None:
            missing_resources.append(f"{task.id} (memory)")
        if task.disk_mb.get_value_with_default(target_environment) is None:
            missing_resources.append(f"{task.id} (disk)")
        # Note: Time is not typically a resource specification in workflow engines
    
    if missing_resources:
        if prompt.ask(
            f"Found {len(missing_resources)} tasks without explicit resource requirements. "
            f"Distributed systems require explicit resource allocation. "
            f"Add default resource specifications?", 
            default=True
        ):
            # Apply sensible defaults based on target environment
            defaults = _get_default_resources(target_environment)
            for task in workflow.tasks.values():
                if task.cpu.get_value_with_default(target_environment) is None:
                    task.cpu.set_for_environment(defaults["cpu"], target_environment)
                if task.mem_mb.get_value_with_default(target_environment) is None:
                    task.mem_mb.set_for_environment(defaults["memory"], target_environment)
                if task.disk_mb.get_value_with_default(target_environment) is None:
                    task.disk_mb.set_for_environment(defaults["disk"], target_environment)
            
            if verbose:
                print(f"  Applied default resources: CPU={defaults['cpu']}, "
                      f"Memory={defaults['memory']}MB, Disk={defaults['disk']}MB")


def _get_default_resources(target_environment: str) -> Dict[str, int]:
    """Get default resource values for a target environment."""
    defaults = {
        "shared": {"cpu": 1, "memory": 512, "disk": 1024},
        "cluster": {"cpu": 1, "memory": 2048, "disk": 4096},
        "cloud": {"cpu": 2, "memory": 4096, "disk": 8192},
        "hpc": {"cpu": 4, "memory": 8192, "disk": 16384},
    }
    return defaults.get(target_environment, defaults["cluster"])


def _suggest_resource_profiles(
    workflow: Workflow, 
    target_environment: str
) -> None:
    """Suggest resource profiles for tasks with incomplete specifications."""
    
    try:
        from wf2wf.resource_utils import suggest_resource_profile
    except ImportError:
        return
    
    tasks_without_resources = []
    for task in workflow.tasks.values():
        if (task.cpu.get_value_with_default(target_environment) is None or 
            task.mem_mb.get_value_with_default(target_environment) is None or 
            task.disk_mb.get_value_with_default(target_environment) is None):
            tasks_without_resources.append(task.id)
        # Note: Time is not typically a resource specification in workflow engines
    
    if tasks_without_resources:
        print(f"  ⚠ {len(tasks_without_resources)} tasks have incomplete resource specifications")
        if len(tasks_without_resources) <= 5:
            for task_id in tasks_without_resources:
                suggested = suggest_resource_profile(workflow.tasks[task_id], target_environment)
                print(f"    {task_id}: consider --resource-profile {suggested}")
        else:
            print(f"    Consider using --resource-profile cluster for default specifications")


def check_workflow_compatibility(
    workflow: Workflow,
    target_format: str,
    interactive: bool = False,
    verbose: bool = False
) -> None:
    """
    Check workflow compatibility with target format and suggest improvements.
    
    This function can be called by any importer to check for common issues
    when converting between workflow formats.
    
    Parameters
    ----------
    workflow : Workflow
        The workflow to check
    target_format : str
        Target format (dagman, nextflow, cwl, etc.)
    interactive : bool
        Whether to prompt user for missing information
    verbose : bool
        Whether to print verbose output
    """
    
    if not interactive:
        return
    
    # Check for container specifications when converting to distributed systems
    if target_format in ["dagman", "nextflow"]:
        uncontainerized_tasks = []
        for task in workflow.tasks.values():
            # Get environment-specific values for shared_filesystem environment
            container = task.container.get_value_for('shared_filesystem')
            conda = task.conda.get_value_for('shared_filesystem')
            if not container and not conda:
                uncontainerized_tasks.append(task.id)
        
        if uncontainerized_tasks:
            if prompt.ask(
                f"Found {len(uncontainerized_tasks)} tasks without container or conda specifications. "
                f"Distributed systems typically require explicit environment isolation. "
                f"Add container specifications or conda environments?", 
                default=True
            ):
                print("Enable --auto-env to automatically build containers for these tasks.")
    
    # Check for error handling when converting to distributed systems
    if target_format in ["dagman", "nextflow"]:
        tasks_without_retry = []
        for task in workflow.tasks.values():
            if task.retry_count.get_value_for('shared_filesystem') == 0:
                tasks_without_retry.append(task.id)
        
        if tasks_without_retry:
            if prompt.ask(
                f"Found {len(tasks_without_retry)} tasks without retry specifications. "
                f"Distributed systems benefit from explicit error handling. "
                f"Add retry specifications for failed tasks?", 
                default=True
            ):
                # Apply default retry settings
                for task in workflow.tasks.values():
                    if task.retry_count.get_value_for('shared_filesystem') == 0:
                        task.retry_count.set_for_environment(2, 'shared_filesystem')  # Default 2 retries
                if verbose:
                    print("  Applied default retry settings (2 retries)")
    
    # Check for file transfer modes when converting between filesystem types
    if target_format in ["dagman"]:
        auto_transfer_files = []
        for task in workflow.tasks.values():
            for param in task.inputs + task.outputs:
                if hasattr(param, 'transfer_mode') and param.transfer_mode == "auto":
                    auto_transfer_files.append(f"{task.id}.{param.id}")
        
        if auto_transfer_files:
            if prompt.ask(
                f"Found {len(auto_transfer_files)} files with auto-detected transfer modes. "
                f"Review and adjust file transfer behavior for distributed computing?", 
                default=True
            ):
                if verbose:
                    print("  File transfer modes will be automatically detected based on file paths.") 