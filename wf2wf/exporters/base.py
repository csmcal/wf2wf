"""
wf2wf.exporters.base – Shared infrastructure for all exporters.

This module provides a base class and shared utilities for all workflow exporters,
enabling consistent behavior across different output formats.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from wf2wf.core import Workflow, Task, EnvironmentSpecificValue
from wf2wf.loss import (
    reset as loss_reset,
    record as loss_record,
    write as loss_write,
    as_list as loss_list,
    prepare as loss_prepare,
    compute_checksum,
    write_loss_document,
    detect_and_record_export_losses,
)
from wf2wf.exporters.inference import infer_missing_values
from wf2wf.interactive import get_prompter

logger = logging.getLogger(__name__)


class BaseExporter(ABC):
    """Base class for all exporters with shared functionality."""
    
    def __init__(self, interactive: bool = False, verbose: bool = False, target_environment: str = "shared_filesystem"):
        self.interactive = interactive
        self.verbose = verbose
        self.target_format = self._get_target_format()
        self.target_environment = target_environment
        self.prompter = get_prompter()
        self.prompter.interactive = interactive
        self.prompter.verbose = verbose
    
    @abstractmethod
    def _get_target_format(self) -> str:
        """Get the target format name."""
        pass
    
    def export_workflow(self, workflow: Workflow, output_path: Union[str, Path], **opts: Any) -> None:
        """Main export method with shared workflow."""
        output_path = Path(output_path)
        
        if self.verbose:
            print(f"Exporting workflow '{workflow.name}' to {self.target_format}")
            print(f"  Target environment: {self.target_environment}")
            print(f"  Output: {output_path}")
            print(f"  Tasks: {len(workflow.tasks)}")
            print(f"  Dependencies: {len(workflow.edges)}")
        
        # 1. Prepare loss tracking
        loss_prepare(workflow.loss_map)
        loss_reset()
        
        # 2. Infer missing values based on target format and environment
        infer_missing_values(workflow, self.target_format, target_environment=self.target_environment, verbose=self.verbose)
        
        # 3. Interactive prompting if enabled
        if self.interactive:
            self.prompter.prompt_for_missing_values(workflow, "export", self.target_environment)
        
        # 4. Record format-specific losses
        detect_and_record_export_losses(workflow, self.target_format, target_environment=self.target_environment, verbose=self.verbose)
        
        # 5. Create output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 6. Generate format-specific output
        self._generate_output(workflow, output_path, **opts)
        
        # 7. Write loss side-car
        write_loss_document(
            output_path.with_suffix(".loss.json"),
            target_engine=self.target_format,
            source_checksum=compute_checksum(workflow),
        )
        workflow.loss_map = loss_list()
        
        # 8. Report completion
        if self.verbose:
            print(f"✓ {self.target_format.title()} workflow exported to {output_path}")
            print(f"  Target environment: {self.target_environment}")
            print(f"  Loss side-car: {output_path.with_suffix('.loss.json')}")
            print(f"Successfully exported workflow to {output_path}")
    
    @abstractmethod
    def _generate_output(self, workflow: Workflow, output_path: Path, **opts: Any) -> None:
        """Generate format-specific output - must be implemented by subclasses."""
        pass
    
    def _get_environment_specific_value(self, env_value: EnvironmentSpecificValue, 
                                      environment: str = "shared_filesystem") -> Any:
        """Get value for specific environment, with fallback to universal value."""
        if env_value is None:
            return None
        
        # Handle ScatterSpec objects - they don't have environment-specific values
        from wf2wf.core import ScatterSpec
        if isinstance(env_value, ScatterSpec):
            return env_value
        
        # Try to get environment-specific value
        value = env_value.get_value_for(environment)
        if value is not None:
            return value
        
        # Fallback to universal value (empty environments list)
        return env_value.get_value_for("")
    
    def _record_loss_if_present(self, task: Task, field_name: str, 
                               environment: str = "shared_filesystem", 
                               reason: str = "Feature not supported in target format") -> None:
        """Record loss if a field has a value for the given environment."""
        if not hasattr(task, field_name):
            return
        
        field_value = getattr(task, field_name)
        if isinstance(field_value, EnvironmentSpecificValue):
            value = field_value.get_value_for(environment)
            if value is not None:
                loss_record(
                    f"/tasks/{task.id}/{field_name}",
                    field_name,
                    value,
                    reason,
                    "user"
                )
    
    def _get_task_resources(self, task: Task, environment: str = "shared_filesystem") -> Dict[str, Any]:
        """Get task resources for specific environment."""
        resources = {}
        
        # Get environment-specific resource values
        for field_name in ['cpu', 'mem_mb', 'disk_mb', 'gpu', 'gpu_mem_mb', 'time_s', 'threads']:
            if hasattr(task, field_name):
                value = self._get_environment_specific_value(getattr(task, field_name), environment)
                if value is not None:
                    resources[field_name] = value
        
        return resources
    
    def _get_task_environment(self, task: Task, environment: str = "shared_filesystem") -> Dict[str, Any]:
        """Get task environment specifications for specific environment."""
        env_spec = {}
        
        # Get environment-specific environment values
        for field_name in ['conda', 'container', 'workdir', 'env_vars', 'modules']:
            if hasattr(task, field_name):
                value = self._get_environment_specific_value(getattr(task, field_name), environment)
                if value is not None:
                    env_spec[field_name] = value
        
        return env_spec
    
    def _get_task_error_handling(self, task: Task, environment: str = "shared_filesystem") -> Dict[str, Any]:
        """Get task error handling specifications for specific environment."""
        error_spec = {}
        
        # Get environment-specific error handling values
        for field_name in ['retry_count', 'retry_delay', 'retry_backoff', 'max_runtime', 'checkpoint_interval']:
            if hasattr(task, field_name):
                value = self._get_environment_specific_value(getattr(task, field_name), environment)
                if value is not None:
                    error_spec[field_name] = value
        
        return error_spec
    
    def _get_task_file_transfer(self, task: Task, environment: str = "shared_filesystem") -> Dict[str, Any]:
        """Get task file transfer specifications for specific environment."""
        transfer_spec = {}
        
        # Get environment-specific file transfer values
        for field_name in ['file_transfer_mode', 'staging_required', 'cleanup_after']:
            if hasattr(task, field_name):
                value = self._get_environment_specific_value(getattr(task, field_name), environment)
                if value is not None:
                    transfer_spec[field_name] = value
        
        return transfer_spec
    
    def _get_task_advanced_features(self, task: Task, environment: str = "shared_filesystem") -> Dict[str, Any]:
        """Get task advanced features for specific environment."""
        features = {}
        
        # Get environment-specific advanced feature values
        for field_name in ['checkpointing', 'logging', 'security', 'networking']:
            if hasattr(task, field_name):
                value = self._get_environment_specific_value(getattr(task, field_name), environment)
                if value is not None:
                    features[field_name] = value
        
        return features
    
    def _get_workflow_requirements(self, workflow: Workflow, environment: str = "shared_filesystem") -> List[Any]:
        """Get workflow requirements for specific environment."""
        requirements = self._get_environment_specific_value(workflow.requirements, environment)
        return requirements if requirements is not None else []
    
    def _get_workflow_hints(self, workflow: Workflow, environment: str = "shared_filesystem") -> List[Any]:
        """Get workflow hints for specific environment."""
        hints = self._get_environment_specific_value(workflow.hints, environment)
        return hints if hints is not None else []
    
    def _get_execution_model(self, workflow: Workflow, environment: str = "shared_filesystem") -> str:
        """Get execution model for specific environment."""
        model = self._get_environment_specific_value(workflow.execution_model, environment)
        return model if model is not None else "unknown"
    
    # Convenience methods that use target_environment by default
    def _get_task_resources_for_target(self, task: Task) -> Dict[str, Any]:
        """Get task resources for target environment."""
        return self._get_task_resources(task, self.target_environment)
    
    def _get_task_environment_for_target(self, task: Task) -> Dict[str, Any]:
        """Get task environment specifications for target environment."""
        return self._get_task_environment(task, self.target_environment)
    
    def _get_task_error_handling_for_target(self, task: Task) -> Dict[str, Any]:
        """Get task error handling specifications for target environment."""
        return self._get_task_error_handling(task, self.target_environment)
    
    def _get_task_file_transfer_for_target(self, task: Task) -> Dict[str, Any]:
        """Get task file transfer specifications for target environment."""
        return self._get_task_file_transfer(task, self.target_environment)
    
    def _get_task_advanced_features_for_target(self, task: Task) -> Dict[str, Any]:
        """Get task advanced features for target environment."""
        return self._get_task_advanced_features(task, self.target_environment)
    
    def _get_workflow_requirements_for_target(self, workflow: Workflow) -> List[Any]:
        """Get workflow requirements for target environment."""
        return self._get_workflow_requirements(workflow, self.target_environment)
    
    def _get_workflow_hints_for_target(self, workflow: Workflow) -> List[Any]:
        """Get workflow hints for target environment."""
        return self._get_workflow_hints(workflow, self.target_environment)
    
    def _get_execution_model_for_target(self, workflow: Workflow) -> str:
        """Get execution model for target environment."""
        return self._get_execution_model(workflow, self.target_environment)
    
    def _get_environment_specific_value_for_target(self, env_value: EnvironmentSpecificValue) -> Any:
        """Get value for target environment, with fallback to universal value."""
        return self._get_environment_specific_value(env_value, self.target_environment)
    
    def _record_loss_if_present_for_target(self, task: Task, field_name: str, 
                                          reason: str = "Feature not supported in target format") -> None:
        """Record loss if a field has a value for the target environment."""
        self._record_loss_if_present(task, field_name, self.target_environment, reason)
    
    def _sanitize_name(self, name: str) -> str:
        """Sanitize name for target format."""
        # Remove or replace characters that might cause issues in various formats
        import re
        # Replace spaces and special characters with underscores
        sanitized = re.sub(r'[^\w\-]', '_', name)
        # Ensure it doesn't start with a number
        if sanitized and sanitized[0].isdigit():
            sanitized = f"task_{sanitized}"
        return sanitized
    
    def _write_file(self, content: str, path: Path, encoding: str = "utf-8") -> None:
        """Write content to file with proper error handling."""
        try:
            path.write_text(content, encoding=encoding)
            if self.verbose:
                print(f"  Wrote: {path}")
        except Exception as e:
            raise RuntimeError(f"Failed to write {path}: {e}")
    
    def _write_json(self, data: Dict[str, Any], path: Path, indent: int = 2) -> None:
        """Write JSON data to file."""
        try:
            with path.open('w', encoding='utf-8') as f:
                json.dump(data, f, indent=indent, sort_keys=True)
            if self.verbose:
                print(f"  Wrote JSON: {path}")
        except Exception as e:
            raise RuntimeError(f"Failed to write JSON {path}: {e}")
    
    def _write_yaml(self, data: Dict[str, Any], path: Path) -> None:
        """Write YAML data to file."""
        try:
            import yaml
            with path.open('w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            if self.verbose:
                print(f"  Wrote YAML: {path}")
        except Exception as e:
            raise RuntimeError(f"Failed to write YAML {path}: {e}")
    
    def _get_task_metadata(self, task: Task) -> Dict[str, Any]:
        """Get task metadata for preservation in target format."""
        metadata = {}
        
        # Add direct task fields
        if task.label:
            metadata['label'] = task.label
        if task.doc:
            metadata['doc'] = task.doc
        
        # Add metadata object if present
        if task.metadata:
            metadata.update(task.metadata.format_specific)
            metadata.update(task.metadata.uninterpreted)
        
        # Add provenance and documentation if present
        if task.provenance:
            metadata['provenance'] = task.provenance.__dict__
        if task.documentation:
            metadata['documentation'] = task.documentation.__dict__
        
        return metadata
    
    def _get_workflow_metadata(self, workflow: Workflow) -> Dict[str, Any]:
        """Get workflow metadata for preservation in target format."""
        metadata = {}
        
        # Add direct workflow fields
        if workflow.label:
            metadata['label'] = workflow.label
        if workflow.doc:
            metadata['doc'] = workflow.doc
        
        # Add metadata object if present
        if workflow.metadata:
            if hasattr(workflow.metadata, 'format_specific'):
                # It's a MetadataSpec object
                metadata.update(workflow.metadata.format_specific)
                metadata.update(workflow.metadata.uninterpreted)
            elif isinstance(workflow.metadata, dict):
                # It's a dict
                metadata.update(workflow.metadata)
        
        # Add provenance and documentation if present
        if workflow.provenance:
            metadata['provenance'] = workflow.provenance.__dict__
        if workflow.documentation:
            metadata['documentation'] = workflow.documentation.__dict__
        
        return metadata 