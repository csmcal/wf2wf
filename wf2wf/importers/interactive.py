"""
wf2wf.importers.interactive – Interactive prompting for missing workflow information.

This module provides interactive prompting capabilities for filling in missing
workflow information through user interaction. It integrates with the environment
manager for comprehensive environment handling.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Callable

from wf2wf.core import Task, Workflow, EnvironmentSpecificValue
from wf2wf.environ import EnvironmentManager

logger = logging.getLogger(__name__)


def prompt_for_missing_information(
    workflow: Workflow, 
    source_format: str
) -> None:
    """
    Prompt user for missing workflow information.
    
    This function analyzes the workflow and prompts the user for any missing
    information that could improve the workflow specification.
    
    Args:
        workflow: Workflow to process
        source_format: Source format name
    """
    logger.info("Starting interactive workflow completion...")
    
    # Initialize environment manager for environment-specific prompting
    env_manager = EnvironmentManager(interactive=True, verbose=True)
    
    # Prompt for resource requirements
    _prompt_for_resource_requirements(workflow)
    
    # Prompt for environment specifications
    env_manager.prompt_for_missing_environments(workflow, source_format)
    
    # Prompt for error handling
    _prompt_for_error_handling(workflow)
    
    # Prompt for advanced features
    _prompt_for_advanced_features(workflow)
    
    # Prompt for workflow-level information
    _prompt_for_workflow_information(workflow)
    
    logger.info("Interactive workflow completion finished")


def _prompt_for_resource_requirements(workflow: Workflow):
    """
    Prompt for missing resource requirements.
    
    Args:
        workflow: Workflow object to prompt for
    """
    logger.info("Checking for missing resource requirements...")
    
    for task in workflow.tasks.values():
        task_id = task.id
        
        # Check CPU requirements
        if task.cpu.get_value_for('shared_filesystem') is None:
            response = _prompt_user(
                f"Task '{task_id}' has no CPU specification. "
                f"Enter number of CPUs (default: 1): ",
                default="1",
                validation_func=_validate_positive_integer
            )
            if response:
                try:
                    cpu_count = int(response)
                    task.cpu.set_for_environment(cpu_count, 'shared_filesystem')
                    logger.info(f"Set CPU count for task '{task_id}' to {cpu_count}")
                except ValueError:
                    logger.warning(f"Invalid CPU count: {response}")
        
        # Check memory requirements
        if task.mem_mb.get_value_for('shared_filesystem') is None:
            response = _prompt_user(
                f"Task '{task_id}' has no memory specification. "
                f"Enter memory in MB (default: 2048): ",
                default="2048",
                validation_func=_validate_positive_integer
            )
            if response:
                try:
                    memory_mb = int(response)
                    task.mem_mb.set_for_environment(memory_mb, 'shared_filesystem')
                    logger.info(f"Set memory for task '{task_id}' to {memory_mb}MB")
                except ValueError:
                    logger.warning(f"Invalid memory specification: {response}")
        
        # Check disk requirements
        if task.disk_mb.get_value_for('shared_filesystem') is None:
            response = _prompt_user(
                f"Task '{task_id}' has no disk specification. "
                f"Enter disk space in MB (default: 2048): ",
                default="2048",
                validation_func=_validate_positive_integer
            )
            if response:
                try:
                    disk_mb = int(response)
                    task.disk_mb.set_for_environment(disk_mb, 'shared_filesystem')
                    logger.info(f"Set disk space for task '{task_id}' to {disk_mb}MB")
                except ValueError:
                    logger.warning(f"Invalid disk specification: {response}")
        
        # Check GPU requirements
        if task.gpu.get_value_for('shared_filesystem') is None:
            response = _prompt_user(
                f"Task '{task_id}' has no GPU specification. "
                f"Enter number of GPUs (default: 0): ",
                default="0",
                validation_func=_validate_non_negative_integer
            )
            if response:
                try:
                    gpu_count = int(response)
                    task.gpu.set_for_environment(gpu_count, 'shared_filesystem')
                    logger.info(f"Set GPU count for task '{task_id}' to {gpu_count}")
                except ValueError:
                    logger.warning(f"Invalid GPU count: {response}")


def _prompt_for_error_handling(workflow: Workflow):
    """
    Prompt for missing error handling.
    
    Args:
        workflow: Workflow object to prompt for
    """
    logger.info("Checking for missing error handling...")
    
    for task in workflow.tasks.values():
        task_id = task.id
        
        # Check retry specifications
        if task.retry_count.get_value_for('shared_filesystem') is None:
            response = _prompt_user(
                f"Task '{task_id}' has no retry specification. "
                f"Enter number of retries (default: 0): ",
                default="0",
                validation_func=_validate_non_negative_integer
            )
            if response:
                try:
                    retry_count = int(response)
                    task.retry_count.set_for_environment(retry_count, 'shared_filesystem')
                    logger.info(f"Set retry count for task '{task_id}' to {retry_count}")
                except ValueError:
                    logger.warning(f"Invalid retry count: {response}")
        
        # Check retry delay
        if task.retry_delay.get_value_for('shared_filesystem') is None:
            response = _prompt_user(
                f"Task '{task_id}' has no retry delay specification. "
                f"Enter retry delay in seconds (default: 60): ",
                default="60",
                validation_func=_validate_positive_integer
            )
            if response:
                try:
                    retry_delay = int(response)
                    task.retry_delay.set_for_environment(retry_delay, 'shared_filesystem')
                    logger.info(f"Set retry delay for task '{task_id}' to {retry_delay} seconds")
                except ValueError:
                    logger.warning(f"Invalid retry delay: {response}")
        
        # Check max runtime
        if task.max_runtime.get_value_for('shared_filesystem') is None:
            response = _prompt_user(
                f"Task '{task_id}' has no max runtime specification. "
                f"Enter max runtime in seconds (default: 3600, 0 for no limit): ",
                default="3600",
                validation_func=_validate_non_negative_integer
            )
            if response:
                try:
                    max_runtime = int(response)
                    if max_runtime > 0:
                        task.max_runtime.set_for_environment(max_runtime, 'shared_filesystem')
                        logger.info(f"Set max runtime for task '{task_id}' to {max_runtime} seconds")
                    else:
                        logger.info(f"No max runtime set for task '{task_id}'")
                except ValueError:
                    logger.warning(f"Invalid max runtime: {response}")


def _prompt_for_advanced_features(workflow: Workflow):
    """
    Prompt for missing advanced features.
    
    Args:
        workflow: Workflow object to prompt for
    """
    logger.info("Checking for missing advanced features...")
    
    for task in workflow.tasks.values():
        task_id = task.id
        
        # Check priority
        if task.priority.get_value_for('shared_filesystem') is None:
            response = _prompt_user(
                f"Task '{task_id}' has no priority specification. "
                f"Enter priority (higher = more important, default: 0): ",
                default="0",
                validation_func=_validate_integer
            )
            if response:
                try:
                    priority = int(response)
                    task.priority.set_for_environment(priority, 'shared_filesystem')
                    logger.info(f"Set priority for task '{task_id}' to {priority}")
                except ValueError:
                    logger.warning(f"Invalid priority: {response}")
        
        # Check file transfer mode
        if task.file_transfer_mode.get_value_for('shared_filesystem') is None:
            response = _prompt_user(
                f"Task '{task_id}' has no file transfer mode specification. "
                f"Choose file transfer mode:\n"
                f"  1. auto (automatic)\n"
                f"  2. explicit (manual)\n"
                f"  3. never (no transfer)\n"
                f"  4. cloud_storage (cloud storage)\n"
                f"Enter choice (1/2/3/4): ",
                default="1",
                validation_func=_validate_transfer_mode_choice
            )
            if response:
                transfer_modes = {
                    "1": "auto",
                    "2": "explicit", 
                    "3": "never",
                    "4": "cloud_storage"
                }
                transfer_mode = transfer_modes.get(response, "auto")
                task.file_transfer_mode.set_for_environment(transfer_mode, 'shared_filesystem')
                logger.info(f"Set file transfer mode for task '{task_id}' to {transfer_mode}")


def _prompt_for_workflow_information(workflow: Workflow):
    """
    Prompt for missing workflow-level information.
    
    Args:
        workflow: Workflow object to prompt for
    """
    logger.info("Checking for missing workflow-level information...")
    
    # Check workflow name
    if not workflow.name or workflow.name == 'imported_workflow':
        response = _prompt_user(
            f"Workflow has no name. Enter workflow name: ",
            default="my_workflow"
        )
        if response:
            workflow.name = response
            logger.info(f"Set workflow name to '{response}'")
    
    # Check workflow version
    if not workflow.version or workflow.version == '1.0':
        response = _prompt_user(
            f"Workflow has no version. Enter workflow version: ",
            default="1.0"
        )
        if response:
            workflow.version = response
            logger.info(f"Set workflow version to '{response}'")
    
    # Check workflow description
    if not workflow.doc:
        response = _prompt_user(
            f"Workflow has no description. Enter workflow description (optional): ",
            default=""
        )
        if response:
            workflow.doc = response
            logger.info(f"Set workflow description")


def prompt_for_environment_adaptation(
    workflow: Workflow, 
    target_environment: str
) -> None:
    """
    Prompt for environment-specific adaptations.
    
    Args:
        workflow: Workflow to adapt
        target_environment: Target environment name
    """
    logger.info(f"Prompting for {target_environment} environment adaptations...")
    
    # Initialize environment manager
    env_manager = EnvironmentManager(interactive=True, verbose=True)
    
    # Prompt for environment-specific resources
    _prompt_for_environment_resources(workflow, target_environment)
    
    # Prompt for environment-specific error handling
    _prompt_for_environment_error_handling(workflow, target_environment)
    
    # Prompt for environment-specific file transfer
    _prompt_for_environment_file_transfer(workflow, target_environment)
    
    # Prompt for environment-specific security
    _prompt_for_environment_security(workflow, target_environment)


def _prompt_for_environment_resources(workflow: Workflow, environment: str):
    """
    Prompt for environment-specific resource requirements.
    
    Args:
        workflow: Workflow to process
        environment: Target environment name
    """
    logger.info(f"Prompting for {environment} resource requirements...")
    
    for task in workflow.tasks.values():
        task_id = task.id
        
        # Check if task has environment-specific resources
        if task.cpu.get_value_for(environment) is None:
            response = _prompt_user(
                f"Task '{task_id}' has no {environment} CPU specification. "
                f"Enter number of CPUs for {environment} (default: 1): ",
                default="1",
                validation_func=_validate_positive_integer
            )
            if response:
                try:
                    cpu_count = int(response)
                    task.cpu.set_for_environment(cpu_count, environment)
                    logger.info(f"Set {environment} CPU count for task '{task_id}' to {cpu_count}")
                except ValueError:
                    logger.warning(f"Invalid CPU count: {response}")
        
        if task.mem_mb.get_value_for(environment) is None:
            response = _prompt_user(
                f"Task '{task_id}' has no {environment} memory specification. "
                f"Enter memory in MB for {environment} (default: 4096): ",
                default="4096",
                validation_func=_validate_positive_integer
            )
            if response:
                try:
                    memory_mb = int(response)
                    task.mem_mb.set_for_environment(memory_mb, environment)
                    logger.info(f"Set {environment} memory for task '{task_id}' to {memory_mb}MB")
                except ValueError:
                    logger.warning(f"Invalid memory specification: {response}")


def _prompt_for_environment_error_handling(workflow: Workflow, environment: str):
    """
    Prompt for environment-specific error handling.
    
    Args:
        workflow: Workflow to process
        environment: Target environment name
    """
    logger.info(f"Prompting for {environment} error handling...")
    
    for task in workflow.tasks.values():
        task_id = task.id
        
        if task.retry_count.get_value_for(environment) is None:
            response = _prompt_user(
                f"Task '{task_id}' has no {environment} retry specification. "
                f"Enter number of retries for {environment} (default: 2): ",
                default="2",
                validation_func=_validate_non_negative_integer
            )
            if response:
                try:
                    retry_count = int(response)
                    task.retry_count.set_for_environment(retry_count, environment)
                    logger.info(f"Set {environment} retry count for task '{task_id}' to {retry_count}")
                except ValueError:
                    logger.warning(f"Invalid retry count: {response}")


def _prompt_for_environment_file_transfer(workflow: Workflow, environment: str):
    """
    Prompt for environment-specific file transfer settings.
    
    Args:
        workflow: Workflow to process
        environment: Target environment name
    """
    logger.info(f"Prompting for {environment} file transfer settings...")
    
    for task in workflow.tasks.values():
        task_id = task.id
        
        if task.file_transfer_mode.get_value_for(environment) is None:
            response = _prompt_user(
                f"Task '{task_id}' has no {environment} file transfer mode. "
                f"Choose {environment} file transfer mode:\n"
                f"  1. auto (automatic)\n"
                f"  2. explicit (manual)\n"
                f"  3. never (no transfer)\n"
                f"  4. cloud_storage (cloud storage)\n"
                f"Enter choice (1/2/3/4): ",
                default="1",
                validation_func=_validate_transfer_mode_choice
            )
            if response:
                transfer_modes = {
                    "1": "auto",
                    "2": "explicit", 
                    "3": "never",
                    "4": "cloud_storage"
                }
                transfer_mode = transfer_modes.get(response, "auto")
                task.file_transfer_mode.set_for_environment(transfer_mode, environment)
                logger.info(f"Set {environment} file transfer mode for task '{task_id}' to {transfer_mode}")


def _prompt_for_environment_security(workflow: Workflow, environment: str):
    """
    Prompt for environment-specific security settings.
    
    Args:
        workflow: Workflow to process
        environment: Target environment name
    """
    if environment in ['cloud_native', 'hybrid']:
        logger.info(f"Prompting for {environment} security settings...")
        
        for task in workflow.tasks.values():
            task_id = task.id
            
            # Check if security spec exists
            security = task.security.get_value_for(environment)
            if security is None:
                response = _prompt_user(
                    f"Task '{task_id}' has no {environment} security specification. "
                    f"Enable security features for {environment}? (y/n): ",
                    default="y",
                    validation_func=_validate_yes_no
                )
                if response.lower() == 'y':
                    # Create basic security spec
                    from wf2wf.core import SecuritySpec
                    security_spec = SecuritySpec(
                        encryption="AES256",
                        access_policies="least-privilege",
                        authentication="oauth",
                        notes=f"Auto-configured security for {environment}"
                    )
                    task.security.set_for_environment(security_spec, environment)
                    logger.info(f"Enabled security features for task '{task_id}' in {environment}")


def _prompt_user(
    message: str, 
    default: str = "", 
    validation_func: Optional[Callable] = None
) -> str:
    """
    Prompt user for input with validation.
    
    Args:
        message: Message to display
        default: Default value
        validation_func: Optional validation function
        
    Returns:
        User input or default value
    """
    try:
        import click
        
        # Use click for better UX if available
        if default:
            message = f"{message} [{default}]: "
        else:
            message = f"{message}: "
        
        while True:
            response = click.prompt(message, default=default, show_default=False)
            
            if validation_func:
                try:
                    validation_func(response)
                except ValueError as e:
                    click.echo(f"Invalid input: {e}")
                    continue
            
            return response
            
    except ImportError:
        # Fallback to basic input
        if default:
            message = f"{message} [{default}]: "
        else:
            message = f"{message}: "
        
        while True:
            response = input(message).strip()
            if not response and default:
                response = default
            
            if validation_func:
                try:
                    validation_func(response)
                except ValueError as e:
                    print(f"Invalid input: {e}")
                    continue  # Continue the loop instead of recursive call
            
            return response


def _validate_positive_integer(value: str) -> None:
    """
    Validate that a string represents a positive integer.
    
    Args:
        value: String to validate
        
    Raises:
        ValueError: If validation fails
    """
    try:
        int_val = int(value)
        if int_val <= 0:
            raise ValueError("Value must be a positive integer")
    except ValueError:
        raise ValueError("Value must be a positive integer")


def _validate_non_negative_integer(value: str) -> None:
    """
    Validate that a string represents a non-negative integer.
    
    Args:
        value: String to validate
        
    Raises:
        ValueError: If validation fails
    """
    try:
        int_val = int(value)
        if int_val < 0:
            raise ValueError("Value must be a non-negative integer")
    except ValueError:
        raise ValueError("Value must be a non-negative integer")


def _validate_integer(value: str) -> None:
    """
    Validate that a string represents an integer.
    
    Args:
        value: String to validate
        
    Raises:
        ValueError: If validation fails
    """
    try:
        int(value)
    except ValueError:
        raise ValueError("Value must be an integer")


def _validate_transfer_mode_choice(value: str) -> None:
    """
    Validate transfer mode choice.
    
    Args:
        value: String to validate
        
    Raises:
        ValueError: If validation fails
    """
    valid_choices = ['1', '2', '3', '4']
    if value not in valid_choices:
        raise ValueError("Please enter a valid choice (1/2/3/4)")


def _validate_yes_no(value: str) -> None:
    """
    Validate yes/no choice.
    
    Args:
        value: String to validate
        
    Raises:
        ValueError: If validation fails
    """
    valid_choices = ['y', 'yes', 'n', 'no']
    if value.lower() not in valid_choices:
        raise ValueError("Please enter 'y' or 'n'") 