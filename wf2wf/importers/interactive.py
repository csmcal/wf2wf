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


def prompt_for_execution_model_confirmation(
    workflow: Workflow, 
    source_format: str,
    content_analysis=None,
    target_format: str = None
) -> None:
    """
    Interactive prompting for execution model confirmation and transition analysis.
    
    This function prompts the user to confirm or override the detected execution
    model and provides guidance for transitions between execution models.
    
    Args:
        workflow: Workflow to process
        source_format: Source format name
        content_analysis: Optional content analysis results
        target_format: Optional target format for transition analysis
    """
    logger.info("Checking execution model configuration...")
    
    # Get current execution model
    current_model = workflow.execution_model.get_value_for('shared_filesystem')
    if not current_model:
        current_model = 'unknown'
    
    print(f"\nCurrent execution model: {current_model}")
    
    # Show content analysis if available
    if content_analysis:
        print(f"Content analysis suggests: {content_analysis.execution_model} (confidence: {content_analysis.confidence:.2f})")
        
        if content_analysis.indicators:
            print(f"\nDetection evidence:")
            for model_type, indicators in content_analysis.indicators.items():
                if indicators:
                    print(f"  {model_type}:")
                    for indicator in indicators[:2]:  # Show first 2 indicators
                        print(f"    - {indicator}")
                    if len(indicators) > 2:
                        print(f"    ... and {len(indicators) - 2} more")
    
    # Prompt for model confirmation/override
    if content_analysis and content_analysis.execution_model != current_model:
        response = _prompt_user(
            f"Content analysis suggests {content_analysis.execution_model} but current model is {current_model}. "
            f"Update execution model? (y/n): ",
            default="y",
            validation_func=_validate_yes_no
        )
        if response.lower() in ['y', 'yes']:
            workflow.execution_model.set_for_environment(content_analysis.execution_model, 'shared_filesystem')
            logger.info(f"Updated execution model to {content_analysis.execution_model}")
    
    # Analyze transition if target format is specified
    if target_format:
        _prompt_for_transition_analysis(workflow, source_format, target_format)


def _prompt_for_transition_analysis(workflow: Workflow, source_format: str, target_format: str):
    """
    Prompt for execution model transition analysis.
    
    Args:
        workflow: Workflow to analyze
        source_format: Source format name
        target_format: Target format name
    """
    from wf2wf.workflow_analysis import analyze_execution_model_transition
    
    # Get execution model spec
    if hasattr(workflow, 'execution_model_spec'):
        source_spec = workflow.execution_model_spec
    else:
        # Create basic spec
        current_model = workflow.execution_model.get_value_for('shared_filesystem') or 'unknown'
        from wf2wf.core import ExecutionModelSpec
        source_spec = ExecutionModelSpec(
            model=current_model,
            source_format=source_format,
            detection_method="interactive",
            detection_confidence=0.5
        )
    
    # Analyze transition
    analysis = analyze_execution_model_transition(source_spec, target_format)
    
    print(f"\nExecution model transition analysis:")
    print(f"  From: {analysis['source_model']} ({source_format})")
    print(f"  To: {analysis['target_model']} ({target_format})")
    
    if analysis['required_changes']:
        print(f"\nRequired changes:")
        for change in analysis['required_changes']:
            print(f"  - {change}")
    
    if analysis['potential_issues']:
        print(f"\nPotential issues:")
        for issue in analysis['potential_issues']:
            print(f"  ⚠ {issue}")
    
    if analysis['recommendations']:
        print(f"\nRecommendations:")
        for rec in analysis['recommendations']:
            print(f"  💡 {rec}")
    
    # Prompt for automatic fixes
    if analysis['required_changes']:
        response = _prompt_user(
            f"\nApply automatic fixes for {len(analysis['required_changes'])} required changes? (y/n): ",
            default="y",
            validation_func=_validate_yes_no
        )
        if response.lower() in ['y', 'yes']:
            _apply_transition_fixes(workflow, analysis)


def _apply_transition_fixes(workflow: Workflow, analysis: Dict[str, Any]):
    """
    Apply automatic fixes for execution model transition.
    
    Args:
        workflow: Workflow to fix
        analysis: Transition analysis results
    """
    logger.info("Applying automatic transition fixes...")
    
    fixes_applied = 0
    
    for change in analysis['required_changes']:
        if change == 'file_transfer_specification':
            # Add file transfer specifications
            for task in workflow.tasks.values():
                if task.file_transfer_mode.get_value_for('shared_filesystem') is None:
                    task.file_transfer_mode.set_for_environment('explicit', 'shared_filesystem')
                    fixes_applied += 1
        
        elif change == 'resource_specification':
            # Add resource specifications
            for task in workflow.tasks.values():
                if task.cpu.get_value_for('shared_filesystem') is None:
                    task.cpu.set_for_environment(1, 'shared_filesystem')
                    fixes_applied += 1
                if task.mem_mb.get_value_for('shared_filesystem') is None:
                    task.mem_mb.set_for_environment(2048, 'shared_filesystem')
                    fixes_applied += 1
                if task.disk_mb.get_value_for('shared_filesystem') is None:
                    task.disk_mb.set_for_environment(4096, 'shared_filesystem')
                    fixes_applied += 1
        
        elif change == 'environment_isolation':
            # Add environment isolation
            for task in workflow.tasks.values():
                if (task.container.get_value_for('shared_filesystem') is None and 
                    task.conda.get_value_for('shared_filesystem') is None):
                    # Try to infer container from command
                    command = task.command.get_value_for('shared_filesystem')
                    if command and any(tool in command.lower() for tool in ['python', 'rscript', 'julia']):
                        task.container.set_for_environment('python:3.9', 'shared_filesystem')
                        fixes_applied += 1
        
        elif change == 'error_handling_specification':
            # Add error handling
            for task in workflow.tasks.values():
                if task.retry_count.get_value_for('shared_filesystem') is None:
                    task.retry_count.set_for_environment(2, 'shared_filesystem')
                    fixes_applied += 1
                if task.retry_delay.get_value_for('shared_filesystem') is None:
                    task.retry_delay.set_for_environment(60, 'shared_filesystem')
                    fixes_applied += 1
    
    if fixes_applied > 0:
        print(f"Applied {fixes_applied} automatic fixes")
        logger.info(f"Applied {fixes_applied} automatic transition fixes")
    else:
        print("No automatic fixes were needed or applied")


def prompt_for_workflow_optimization(workflow: Workflow, target_format: str):
    """
    Interactive prompting for workflow optimization based on target format.
    
    Args:
        workflow: Workflow to optimize
        target_format: Target format name
    """
    logger.info(f"Checking for {target_format} optimizations...")
    
    optimizations = []
    
    # Check for format-specific optimizations
    if target_format == 'dagman':
        optimizations.extend(_check_dagman_optimizations(workflow))
    elif target_format == 'nextflow':
        optimizations.extend(_check_nextflow_optimizations(workflow))
    elif target_format == 'cwl':
        optimizations.extend(_check_cwl_optimizations(workflow))
    
    if optimizations:
        print(f"\nFound {len(optimizations)} potential optimizations for {target_format}:")
        for i, opt in enumerate(optimizations, 1):
            print(f"  {i}. {opt['description']}")
            if opt.get('impact'):
                print(f"     Impact: {opt['impact']}")
        
        response = _prompt_user(
            f"\nApply these optimizations? (y/n): ",
            default="y",
            validation_func=_validate_yes_no
        )
        if response.lower() in ['y', 'yes']:
            _apply_workflow_optimizations(workflow, optimizations)


def _check_dagman_optimizations(workflow: Workflow) -> List[Dict[str, Any]]:
    """Check for DAGMan-specific optimizations."""
    optimizations = []
    
    # Check for GPU tasks without proper requirements
    for task in workflow.tasks.values():
        gpu_value = task.gpu.get_value_for('shared_filesystem')
        if gpu_value and gpu_value > 0:
            # Check if GPU requirements are set
            if not task.extra.get('requirements'):
                optimizations.append({
                    'type': 'gpu_requirements',
                    'description': f"Add GPU requirements for task '{task.id}'",
                    'impact': 'Better job placement on GPU nodes',
                    'task_id': task.id
                })
    
    # Check for high-memory tasks without memory requirements
    for task in workflow.tasks.values():
        mem_value = task.mem_mb.get_value_for('shared_filesystem')
        if mem_value and mem_value > 8192:  # 8GB
            if not task.extra.get('requirements'):
                optimizations.append({
                    'type': 'memory_requirements',
                    'description': f"Add memory requirements for task '{task.id}'",
                    'impact': 'Better job placement on high-memory nodes',
                    'task_id': task.id
                })
    
    return optimizations


def _check_nextflow_optimizations(workflow: Workflow) -> List[Dict[str, Any]]:
    """Check for Nextflow-specific optimizations."""
    optimizations = []
    
    # Check for tasks without publishDir
    for task in workflow.tasks.values():
        if task.outputs and not task.extra.get('publish_dir'):
            optimizations.append({
                'type': 'publish_dir',
                'description': f"Add publishDir for task '{task.id}' outputs",
                'impact': 'Better output file organization',
                'task_id': task.id
            })
    
    return optimizations


def _check_cwl_optimizations(workflow: Workflow) -> List[Dict[str, Any]]:
    """Check for CWL-specific optimizations."""
    optimizations = []
    
    # Check for tasks without proper input/output specifications
    for task in workflow.tasks.values():
        if not task.inputs and task.command.get_value_for('shared_filesystem'):
            optimizations.append({
                'type': 'input_specs',
                'description': f"Add input specifications for task '{task.id}'",
                'impact': 'Better CWL compliance and validation',
                'task_id': task.id
            })
        
        if not task.outputs and task.command.get_value_for('shared_filesystem'):
            optimizations.append({
                'type': 'output_specs',
                'description': f"Add output specifications for task '{task.id}'",
                'impact': 'Better CWL compliance and validation',
                'task_id': task.id
            })
    
    return optimizations


def _apply_workflow_optimizations(workflow: Workflow, optimizations: List[Dict[str, Any]]):
    """Apply workflow optimizations."""
    logger.info(f"Applying {len(optimizations)} workflow optimizations...")
    
    for opt in optimizations:
        task = workflow.tasks.get(opt['task_id'])
        if not task:
            continue
        
        if opt['type'] == 'gpu_requirements':
            task.extra['requirements'] = EnvironmentSpecificValue("(HasGPU == True)", ['distributed_computing'])
        
        elif opt['type'] == 'memory_requirements':
            mem_value = task.mem_mb.get_value_for('shared_filesystem') or 8192
            task.extra['requirements'] = EnvironmentSpecificValue(f"(Memory >= {mem_value})", ['distributed_computing'])
        
        elif opt['type'] == 'publish_dir':
            task.extra['publish_dir'] = EnvironmentSpecificValue("results/", ['shared_filesystem'])
        
        elif opt['type'] == 'input_specs':
            # Add basic input specification
            from wf2wf.core import ParameterSpec
            task.inputs.append(ParameterSpec(
                id="input_file",
                type="File",
                doc="Input file for processing"
            ))
        
        elif opt['type'] == 'output_specs':
            # Add basic output specification
            from wf2wf.core import ParameterSpec
            task.outputs.append(ParameterSpec(
                id="output_file",
                type="File",
                doc="Output file from processing"
            ))
    
    print(f"Applied {len(optimizations)} optimizations")
    logger.info(f"Applied {len(optimizations)} workflow optimizations")


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