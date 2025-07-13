"""
Base classes for environment adaptation.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from wf2wf.core import Workflow, Task, EnvironmentSpecificValue
from wf2wf.loss.core import record as loss_record


class EnvironmentAdapter(ABC):
    """
    Base class for environment-specific adaptations.
    
    This class provides the foundation for adapting workflow IR objects
    when converting between different execution environments.
    """
    
    def __init__(self, source_env: str, target_env: str):
        self.source_env = source_env
        self.target_env = target_env
        self.adaptation_log = []
        
    def adapt_workflow(self, workflow: Workflow, **opts) -> Workflow:
        """
        Adapt a workflow for the target environment.
        
        Args:
            workflow: The workflow to adapt
            **opts: Additional adaptation options
            
        Returns:
            Adapted workflow
        """
        # Create a copy to avoid modifying the original
        adapted_workflow = workflow.copy()
        
        # Adapt each task
        for task_id, task in adapted_workflow.tasks.items():
            adapted_task = self.adapt_task(task, **opts)
            adapted_workflow.tasks[task_id] = adapted_task
            
        # Adapt workflow-level properties
        self._adapt_workflow_properties(adapted_workflow, **opts)
        
        return adapted_workflow
    
    def adapt_task(self, task: Task, **opts) -> Task:
        """
        Adapt a task for the target environment.
        
        Args:
            task: The task to adapt
            **opts: Additional adaptation options
            
        Returns:
            Adapted task
        """
        # Create a copy to avoid modifying the original
        adapted_task = task.copy()
        
        # Adapt resource requirements
        self._adapt_task_resources(adapted_task, **opts)
        
        # Adapt environment specifications
        self._adapt_task_environment(adapted_task, **opts)
        
        # Adapt error handling
        self._adapt_task_error_handling(adapted_task, **opts)
        
        return adapted_task
    
    def _adapt_task_resources(self, task: Task, **opts):
        """Adapt task resource requirements."""
        resource_fields = ['cpu', 'mem_mb', 'disk_mb', 'gpu', 'gpu_mem_mb', 'time_s', 'threads']
        
        for field in resource_fields:
            if hasattr(task, field):
                field_value = getattr(task, field)
                if isinstance(field_value, EnvironmentSpecificValue):
                    adapted_value = self._adapt_resource_field(field, field_value, **opts)
                    if adapted_value is not None:
                        setattr(task, field, adapted_value)
    
    def _adapt_task_environment(self, task: Task, **opts):
        """Adapt task environment specifications."""
        env_fields = ['conda', 'container', 'workdir', 'env_vars', 'modules']
        
        for field in env_fields:
            if hasattr(task, field):
                field_value = getattr(task, field)
                if isinstance(field_value, EnvironmentSpecificValue):
                    adapted_value = self._adapt_environment_field(field, field_value, **opts)
                    if adapted_value is not None:
                        setattr(task, field, adapted_value)
    
    def _adapt_task_error_handling(self, task: Task, **opts):
        """Adapt task error handling specifications."""
        error_fields = ['retry_count', 'retry_delay', 'retry_backoff', 'max_runtime', 'checkpoint_interval']
        
        for field in error_fields:
            if hasattr(task, field):
                field_value = getattr(task, field)
                if isinstance(field_value, EnvironmentSpecificValue):
                    adapted_value = self._adapt_error_handling_field(field, field_value, **opts)
                    if adapted_value is not None:
                        setattr(task, field, adapted_value)
    
    def _adapt_workflow_properties(self, workflow: Workflow, **opts):
        """Adapt workflow-level properties."""
        # Adapt execution model if needed
        if workflow.execution_model:
            adapted_model = self._adapt_execution_model(workflow.execution_model, **opts)
            if adapted_model is not None:
                workflow.execution_model = adapted_model
    
    def _adapt_resource_field(self, field_name: str, field_value: EnvironmentSpecificValue, **opts) -> Optional[EnvironmentSpecificValue]:
        """Adapt a resource field value."""
        # Get source value
        source_value = field_value.get_value_for(self.source_env)
        if source_value is None:
            return None
            
        # Apply adaptation
        adapted_value = self._adapt_resource_value(field_name, source_value, **opts)
        if adapted_value is None:
            return None
            
        # Set the adapted value for the target environment (this handles duplicates)
        field_value.set_for_environment(adapted_value, self.target_env)
        return field_value
    
    def _adapt_environment_field(self, field_name: str, field_value: EnvironmentSpecificValue, **opts) -> Optional[EnvironmentSpecificValue]:
        """Adapt an environment field value."""
        # For now, use direct mapping for environment fields
        source_value = field_value.get_value_for(self.source_env)
        if source_value is None:
            return None
            
        # Set the source value for the target environment (this handles duplicates)
        field_value.set_for_environment(source_value, self.target_env)
        return field_value
    
    def _adapt_error_handling_field(self, field_name: str, field_value: EnvironmentSpecificValue, **opts) -> Optional[EnvironmentSpecificValue]:
        """Adapt an error handling field value."""
        # For now, use direct mapping for error handling fields
        source_value = field_value.get_value_for(self.source_env)
        if source_value is None:
            return None
            
        # Set the source value for the target environment (this handles duplicates)
        field_value.set_for_environment(source_value, self.target_env)
        return field_value
    
    def _adapt_execution_model(self, execution_model: EnvironmentSpecificValue, **opts) -> Optional[EnvironmentSpecificValue]:
        """Adapt execution model specification."""
        # # For now, use direct mapping for execution model
        # source_value = execution_model.get_value_for(self.source_env)
        # if source_value is None:
        #     return None
            
        # # Create new EnvironmentSpecificValue with target environment
        # new_values = list(execution_model.values) if hasattr(execution_model, 'values') else []
        # new_values.append({
        #     "environments": [self.target_env],
        #     "value": self.target_env
        # })
        
        # return EnvironmentSpecificValue(new_values)
    
        # Simply set the execution model for the target environment
        execution_model.set_for_environment(self.target_env, self.target_env)
        return execution_model

    @abstractmethod
    def _adapt_resource_value(self, field_name: str, source_value: Any, **opts) -> Optional[Any]:
        """
        Adapt a resource value from source to target environment.
        
        Args:
            field_name: Name of the resource field
            source_value: Source environment value
            **opts: Additional adaptation options
            
        Returns:
            Adapted value for target environment, or None if no adaptation needed
        """
        pass
    
    def log_adaptation(self, field: str, old_value: Any, new_value: Any, reason: str):
        """Log an adaptation decision."""
        self.adaptation_log.append({
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
            "reason": reason,
            "source_env": self.source_env,
            "target_env": self.target_env
        })
        
        # Also record as loss for reporting
        loss_record(
            f"/adaptation/{field}",
            field,
            old_value,
            f"Adapted to {new_value}: {reason}",
            "system"
        )
    
    def get_adaptation_summary(self) -> Dict[str, Any]:
        """Get a summary of all adaptations performed."""
        return {
            "source_environment": self.source_env,
            "target_environment": self.target_env,
            "adaptations": self.adaptation_log,
            "total_adaptations": len(self.adaptation_log)
        } 