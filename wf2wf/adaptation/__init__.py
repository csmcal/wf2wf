"""
Workflow IR Environment Adaptation System

This module provides functionality to adapt workflow IR objects when converting
between different execution environments, addressing the classic "environment
adaptation" problem in workflow IRs.
"""

from .base import EnvironmentAdapter
from .registry import AdaptationRegistry
from .environments import EnvironmentMapper

__all__ = [
    "EnvironmentAdapter",
    "AdaptationRegistry", 
    "EnvironmentMapper",
    "adapt_workflow",
    "adapt_task"
]

def adapt_workflow(workflow, source_env: str, target_env: str, **opts):
    """
    Adapt a workflow for the target environment.
    
    Args:
        workflow: The workflow to adapt
        source_env: Source execution environment
        target_env: Target execution environment
        **opts: Additional adaptation options
        
    Returns:
        Adapted workflow
    """
    adapter = AdaptationRegistry().get_adapter(source_env, target_env)
    return adapter.adapt_workflow(workflow, **opts)

def adapt_task(task, source_env: str, target_env: str, **opts):
    """
    Adapt a task for the target environment.
    
    Args:
        task: The task to adapt
        source_env: Source execution environment
        target_env: Target execution environment
        **opts: Additional adaptation options
        
    Returns:
        Adapted task
    """
    adapter = AdaptationRegistry().get_adapter(source_env, target_env)
    return adapter.adapt_task(task, **opts) 