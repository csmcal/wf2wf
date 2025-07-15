"""
wf2wf.environment_adaptation – Multi-environment IR adaptation utilities.

This module provides utilities for adapting the multi-environment IR to specific
execution environments, handling environment-specific requirements and defaults.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path

from wf2wf.core import (
    Workflow, Task, ParameterSpec, MultiEnvironmentResourceSpec,
    MultiEnvironmentFileTransferSpec, MultiEnvironmentErrorHandlingSpec,
    EXECUTION_ENVIRONMENTS, ExecutionEnvironment
)


@dataclass
class EnvironmentAdaptation:
    """Result of adapting a workflow for a specific execution environment."""
    
    target_environment: str
    adapted_workflow: Workflow
    changes_made: List[Dict[str, Any]]
    warnings: List[str]
    recommendations: List[str]
    
    def summary(self) -> str:
        """Generate a human-readable summary of the adaptation."""
        lines = [
            f"Adapted workflow for {self.target_environment} environment:",
            f"  - Changes made: {len(self.changes_made)}",
            f"  - Warnings: {len(self.warnings)}",
            f"  - Recommendations: {len(self.recommendations)}"
        ]
        
        if self.changes_made:
            lines.append("\nChanges made:")
            for change in self.changes_made:
                lines.append(f"  - {change['description']}")
        
        if self.warnings:
            lines.append("\nWarnings:")
            for warning in self.warnings:
                lines.append(f"  - {warning}")
        
        if self.recommendations:
            lines.append("\nRecommendations:")
            for rec in self.recommendations:
                lines.append(f"  - {rec}")
        
        return "\n".join(lines)


def adapt_workflow_for_environment(
    workflow: Workflow,
    target_environment: str,
    *,
    apply_defaults: bool = True,
    strict: bool = False
) -> EnvironmentAdaptation:
    """
    Adapt a workflow for a specific execution environment.
    
    Parameters
    ----------
    workflow : Workflow
        The workflow to adapt
    target_environment : str
        Target execution environment name
    apply_defaults : bool
        Whether to apply environment-specific defaults
    strict : bool
        Whether to fail on unsupported features
        
    Returns
    -------
    EnvironmentAdaptation
        The adaptation result with adapted workflow and metadata
    """
    if target_environment not in EXECUTION_ENVIRONMENTS:
        raise ValueError(f"Unknown execution environment: {target_environment}")
    
    env_def = EXECUTION_ENVIRONMENTS[target_environment]
    changes_made = []
    warnings = []
    recommendations = []
    
    # Create a copy of the workflow for adaptation
    adapted_workflow = _copy_workflow(workflow)
    
    # Adapt each task
    for task_id, task in adapted_workflow.tasks.items():
        task_changes, task_warnings, task_recs = _adapt_task_for_environment(
            task, target_environment, env_def, apply_defaults, strict
        )
        changes_made.extend(task_changes)
        warnings.extend(task_warnings)
        recommendations.extend(task_recs)
    
    # Adapt workflow-level parameters
    workflow_changes, workflow_warnings, workflow_recs = _adapt_workflow_parameters_for_environment(
        adapted_workflow, target_environment, env_def, apply_defaults, strict
    )
    changes_made.extend(workflow_changes)
    warnings.extend(workflow_warnings)
    recommendations.extend(workflow_recs)
    
    return EnvironmentAdaptation(
        target_environment=target_environment,
        adapted_workflow=adapted_workflow,
        changes_made=changes_made,
        warnings=warnings,
        recommendations=recommendations
    )


def _adapt_task_for_environment(
    task: Task,
    target_environment: str,
    env_def: ExecutionEnvironment,
    apply_defaults: bool,
    strict: bool
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Adapt a single task for the target environment."""
    changes_made = []
    warnings = []
    recommendations = []
    
    # Handle multi-environment resource specifications
    if hasattr(task, 'multi_env_resources') and task.multi_env_resources:
        # Convert multi-environment spec to single-environment spec
        adapted_resources = task.multi_env_resources.get_for_environment(target_environment)
        task.resources = adapted_resources
        changes_made.append({
            'type': 'resource_adaptation',
            'task_id': task.id,
            'description': f'Adapted resources for {target_environment} environment'
        })
    
    # Handle multi-environment file transfer specifications
    for param in task.inputs + task.outputs:
        if hasattr(param, 'multi_env_file_transfer') and param.multi_env_file_transfer:
            adapted_transfer = param.multi_env_file_transfer.get_for_environment(target_environment)
            param.file_transfer = adapted_transfer
            changes_made.append({
                'type': 'file_transfer_adaptation',
                'task_id': task.id,
                'parameter_id': param.id,
                'description': f'Adapted file transfer for {target_environment} environment'
            })
    
    # Handle multi-environment error handling specifications
    if hasattr(task, 'multi_env_error_handling') and task.multi_env_error_handling:
        adapted_error_handling = task.multi_env_error_handling.get_for_environment(target_environment)
        task.error_handling = adapted_error_handling
        changes_made.append({
            'type': 'error_handling_adaptation',
            'task_id': task.id,
            'description': f'Adapted error handling for {target_environment} environment'
        })
    
    # Apply environment-specific defaults if requested
    if apply_defaults:
        default_changes, default_warnings, default_recs = _apply_environment_defaults(
            task, target_environment, env_def
        )
        changes_made.extend(default_changes)
        warnings.extend(default_warnings)
        recommendations.extend(default_recs)
    
    # Check for unsupported features
    feature_warnings, feature_recs = _check_unsupported_features(task, target_environment, env_def, strict)
    warnings.extend(feature_warnings)
    recommendations.extend(feature_recs)
    
    return changes_made, warnings, recommendations


def _adapt_workflow_parameters_for_environment(
    workflow: Workflow,
    target_environment: str,
    env_def: ExecutionEnvironment,
    apply_defaults: bool,
    strict: bool
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Adapt workflow-level parameters for the target environment."""
    changes_made = []
    warnings = []
    recommendations = []
    
    # Handle workflow-level file transfer specifications
    for param in workflow.inputs + workflow.outputs:
        if hasattr(param, 'multi_env_file_transfer') and param.multi_env_file_transfer:
            adapted_transfer = param.multi_env_file_transfer.get_for_environment(target_environment)
            param.file_transfer = adapted_transfer
            changes_made.append({
                'type': 'workflow_file_transfer_adaptation',
                'parameter_id': param.id,
                'description': f'Adapted workflow-level file transfer for {target_environment} environment'
            })
    
    return changes_made, warnings, recommendations


def _apply_environment_defaults(
    task: Task,
    target_environment: str,
    env_def: ExecutionEnvironment
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """Apply environment-specific defaults to a task."""
    changes_made = []
    warnings = []
    recommendations = []
    
    # Apply resource defaults
    if env_def.default_resource_specification:
        cpu_val = task.cpu.get_value_for(target_environment) if hasattr(task, 'cpu') else None
        mem_val = task.mem_mb.get_value_for(target_environment) if hasattr(task, 'mem_mb') else None
        if (not cpu_val or cpu_val == 0) and (not mem_val or mem_val == 0):
            # Add default resources
            task.cpu.set_for_environment(1, target_environment)
            task.mem_mb.set_for_environment(4096, target_environment)
            changes_made.append({
                'type': 'default_resource_addition',
                'task_id': task.id,
                'description': f'Added default resources for {target_environment} environment'
            })
    
    # Apply environment isolation defaults
    if env_def.default_environment_isolation:
        container = task.container.get_value_for(target_environment)
        conda = task.conda.get_value_for(target_environment)
        if not container and not conda:
            warnings.append(f"Task {task.id} lacks environment isolation specification")
            recommendations.append(f"Consider adding container or conda specification for {target_environment}")
    
    # Apply error handling defaults
    if env_def.default_error_handling:
        if task.error_handling.retry_count == 0:
            task.error_handling.retry_count = 2
            changes_made.append({
                'type': 'default_error_handling_addition',
                'task_id': task.id,
                'description': f'Added default retry policy for {target_environment} environment'
            })
    
    return changes_made, warnings, recommendations


def _check_unsupported_features(
    task: Task,
    target_environment: str,
    env_def: ExecutionEnvironment,
    strict: bool
) -> Tuple[List[str], List[str]]:
    """Check for features not supported by the target environment."""
    warnings = []
    recommendations = []
    
    # Check GPU support
    gpu_val = task.gpu.get_value_for(target_environment) if hasattr(task, 'gpu') else None
    if gpu_val and not env_def.supports_gpu:
        msg = f"Task {task.id} requests GPU but {target_environment} may not support it"
        warnings.append(msg)
        recommendations.append(f"Verify GPU support in {target_environment} environment")
    
    # Check checkpointing support
    if task.error_handling.checkpoint_interval and not env_def.supports_checkpointing:
        msg = f"Task {task.id} uses checkpointing but {target_environment} may not support it"
        warnings.append(msg)
        recommendations.append(f"Verify checkpointing support in {target_environment} environment")
    
    # Check partial results support
    if task.error_handling.partial_results and not env_def.supports_partial_results:
        msg = f"Task {task.id} requests partial results but {target_environment} may not support it"
        warnings.append(msg)
        recommendations.append(f"Verify partial results support in {target_environment} environment")
    
    return warnings, recommendations


def _copy_workflow(workflow: Workflow) -> Workflow:
    """Create a deep copy of a workflow for adaptation."""
    # This is a simplified copy - in practice, you'd want a proper deep copy
    import copy
    return copy.deepcopy(workflow)


def get_supported_environments() -> List[str]:
    """Get list of supported execution environments."""
    return list(EXECUTION_ENVIRONMENTS.keys())


def get_environment_info(environment_name: str) -> Optional[ExecutionEnvironment]:
    """Get information about a specific execution environment."""
    return EXECUTION_ENVIRONMENTS.get(environment_name)


def compare_environments(env1: str, env2: str) -> Dict[str, Any]:
    """Compare two execution environments and highlight differences."""
    if env1 not in EXECUTION_ENVIRONMENTS or env2 not in EXECUTION_ENVIRONMENTS:
        raise ValueError(f"Unknown environment: {env1} or {env2}")
    
    e1 = EXECUTION_ENVIRONMENTS[env1]
    e2 = EXECUTION_ENVIRONMENTS[env2]
    
    differences = {
        'filesystem_type': (e1.filesystem_type, e2.filesystem_type),
        'resource_management': (e1.resource_management, e2.resource_management),
        'environment_isolation': (e1.environment_isolation, e2.environment_isolation),
        'file_transfer_mode': (e1.file_transfer_mode, e2.file_transfer_mode),
        'supports_gpu': (e1.supports_gpu, e2.supports_gpu),
        'supports_checkpointing': (e1.supports_checkpointing, e2.supports_checkpointing),
        'supports_partial_results': (e1.supports_partial_results, e2.supports_partial_results),
        'supports_cloud_storage': (e1.supports_cloud_storage, e2.supports_cloud_storage),
    }
    
    # Filter to only show differences
    return {k: v for k, v in differences.items() if v[0] != v[1]} 