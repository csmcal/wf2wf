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

# Import adaptation system if available
try:
    from wf2wf.adaptation import adapt_workflow, AdaptationRegistry
    ADAPTATION_AVAILABLE = True
except ImportError:
    ADAPTATION_AVAILABLE = False
    adapt_workflow = None
    AdaptationRegistry = None

import logging

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
        
        # 2. Check for missing target environment values and handle adaptation
        self._check_and_handle_environment_adaptation(workflow, **opts)
        
        # 3. Interactive prompting if enabled (before inference to allow user input)
        if self.interactive:
            self.prompter.prompt_for_missing_values(workflow, "export", self.target_environment)
        
        # 4. Infer missing values based on target format and environment (after interactive prompts)
        infer_missing_values(workflow, self.target_format, target_environment=self.target_environment, verbose=self.verbose)
        
        # 5. Record format-specific losses
        detect_and_record_export_losses(workflow, self.target_format, target_environment=self.target_environment, verbose=self.verbose)
        
        # 6. Create output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 7. Generate format-specific output
        self._generate_output(workflow, output_path, **opts)
        
        # 8. Write loss side-car
        write_loss_document(
            output_path.with_suffix(".loss.json"),
            target_engine=self.target_format,
            source_checksum=compute_checksum(workflow),
        )
        workflow.loss_map = loss_list()
        
        # 9. Report completion
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
        
        # Try to get environment-specific value for the target environment
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

    def _get_original_execution_model(self, workflow: Workflow) -> str:
        """Get original execution model from metadata."""
        if workflow.metadata and workflow.metadata.original_execution_environment:
            return workflow.metadata.original_execution_environment
        return "unknown"
    
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

    def _check_and_handle_environment_adaptation(self, workflow: Workflow, **opts: Any) -> None:
        """
        Check if target environment values are missing and handle adaptation.
        
        This method checks if the workflow has appropriate values for the target environment.
        If values are missing, it either:
        1. Automatically applies adaptation (if available and not in interactive mode)
        2. Prompts the user for adaptation decisions (if in interactive mode)
        3. Continues with defaults (if adaptation is not available)
        """
        print(f"DEBUG: Checking environment adaptation...")
        print(f"DEBUG: ADAPTATION_AVAILABLE = {ADAPTATION_AVAILABLE}")
        print(f"DEBUG: target_environment = {self.target_environment}")
        
        if not ADAPTATION_AVAILABLE:
            if self.verbose:
                print("  ⚠ Environment adaptation system not available")
            print("DEBUG: Adaptation system not available")
            return
        
        # Determine source environment
        source_environment = self._get_source_environment(workflow)
        print(f"DEBUG: source_environment = {source_environment}")
        
        # Skip if source and target environments are the same
        if source_environment == self.target_environment:
            if self.verbose:
                print(f"  ✓ No adaptation needed (same environment: {source_environment})")
            print(f"DEBUG: No adaptation needed (same environment)")
            return
        
        # Check if target environment values are missing
        missing_values = self._check_missing_target_environment_values(workflow)
        print(f"DEBUG: missing_values = {missing_values}")
        
        if not missing_values:
            if self.verbose:
                print(f"  ✓ Target environment values already present for {self.target_environment}")
            print(f"DEBUG: No missing values")
            return
        
        if self.verbose:
            print(f"  🔧 Found {len(missing_values)} tasks missing target environment values")
            print(f"  Source environment: {source_environment}")
            print(f"  Target environment: {self.target_environment}")
        
        print(f"DEBUG: Found {len(missing_values)} missing values, interactive = {self.interactive}")
        
        # Handle adaptation based on interactive mode
        if self.interactive:
            logger.debug("Handling interactive adaptation")
            self._handle_interactive_adaptation(workflow, source_environment, missing_values, **opts)
        else:
            logger.debug("Handling automatic adaptation")
            self._handle_automatic_adaptation(workflow, source_environment, **opts)
    
    def _get_source_environment(self, workflow: Workflow) -> str:
        """Determine the source environment from workflow metadata or format."""
        # Try to get from workflow metadata first
        if workflow.metadata and workflow.metadata.original_execution_environment:
            return workflow.metadata.original_execution_environment
        
        # Fall back to format-based detection
        format_to_env = {
            "snakemake": "shared_filesystem",
            "dagman": "distributed_computing",
            "nextflow": "hybrid",
            "cwl": "shared_filesystem",
            "wdl": "shared_filesystem",
            "galaxy": "shared_filesystem"
        }
        
        # Try to infer from the workflow format if available
        if hasattr(workflow, 'format') and workflow.format:
            return format_to_env.get(workflow.format, "unknown")
        
        # Default to shared_filesystem if we can't determine
        return "shared_filesystem"
    
    def _check_missing_target_environment_values(self, workflow: Workflow) -> List[str]:
        """Check which tasks are missing values for the target environment."""
        missing_tasks = []
        
        for task in workflow.tasks.values():
            has_target_values = False
            
            logger.debug(f"Checking task {task.id} for target environment {self.target_environment}")
            
            # Check if task has any values for the target environment
            for field_name in ['cpu', 'mem_mb', 'disk_mb', 'gpu', 'gpu_mem_mb', 'time_s', 'threads']:
                if hasattr(task, field_name):
                    field_value = getattr(task, field_name)
                    if isinstance(field_value, EnvironmentSpecificValue):
                        target_value = field_value.get_value_for(self.target_environment)
                        logger.debug(f"{field_name}: get_value_for({self.target_environment}) = {target_value} from {field_value}")
                        if target_value is not None:
                            has_target_values = True
                            logger.debug(f"Found target value for {field_name}: {target_value}")
                            break
            
            if not has_target_values:
                missing_tasks.append(task.id)
                logger.debug(f"Task {task.id} has no target values")
            else:
                logger.debug(f"Task {task.id} has target values")
        
        return missing_tasks
    
    def _handle_interactive_adaptation(self, workflow: Workflow, source_environment: str, 
                                     missing_values: List[str], **opts: Any) -> None:
        """Handle adaptation in interactive mode with user prompting."""
        from wf2wf.interactive import prompt
        
        if not prompt.ask(
            f"Found {len(missing_values)} tasks missing values for {self.target_environment} environment. "
            f"Apply environment adaptation from {source_environment} to {self.target_environment}?",
            default=True
        ):
            if self.verbose:
                print("  ⚠ Skipping environment adaptation (user choice)")
            return
        
        # Apply adaptation
        try:
            adapted_workflow = adapt_workflow(
                workflow, 
                source_environment, 
                self.target_environment,
                strategy=opts.get("adaptation_strategy", "balanced")
            )
            
            # Update the workflow with adapted values
            for task_id, adapted_task in adapted_workflow.tasks.items():
                if task_id in workflow.tasks:
                    # Copy adapted values to the original workflow
                    for field_name in ['cpu', 'mem_mb', 'disk_mb', 'gpu', 'gpu_mem_mb', 'time_s', 'threads']:
                        if hasattr(adapted_task, field_name) and hasattr(workflow.tasks[task_id], field_name):
                            adapted_value = getattr(adapted_task, field_name)
                            original_value = getattr(workflow.tasks[task_id], field_name)
                            if isinstance(adapted_value, EnvironmentSpecificValue) and isinstance(original_value, EnvironmentSpecificValue):
                                # Copy the target environment value
                                target_value = adapted_value.get_value_for(self.target_environment)
                                if target_value is not None:
                                    original_value.set_for_environment(target_value, self.target_environment)
            
            if self.verbose:
                print("  ✓ Environment adaptation applied successfully")
                
        except Exception as e:
            if self.verbose:
                print(f"  ⚠ Environment adaptation failed: {e}")
                print("  Continuing with existing values and defaults")
    
    def _handle_automatic_adaptation(self, workflow: Workflow, source_environment: str, **opts: Any) -> None:
        """Handle adaptation automatically without user prompting."""
        logger.debug(f"Starting automatic adaptation from {source_environment} to {self.target_environment}")
        try:
            logger.debug(f"Calling adapt_workflow...")
            adapted_workflow = adapt_workflow(
                workflow, 
                source_environment, 
                self.target_environment,
                strategy=opts.get("adaptation_strategy", "balanced")
            )
            
            # Update the workflow with adapted values
            logger.debug(f"Updating workflow with adapted values...")
            for task_id, adapted_task in adapted_workflow.tasks.items():
                if task_id in workflow.tasks:
                    logger.debug(f"Updating task {task_id}")
                    # Copy adapted values to the original workflow
                    for field_name in ['cpu', 'mem_mb', 'disk_mb', 'gpu', 'gpu_mem_mb', 'time_s', 'threads']:
                        if hasattr(adapted_task, field_name) and hasattr(workflow.tasks[task_id], field_name):
                            adapted_value = getattr(adapted_task, field_name)
                            original_value = getattr(workflow.tasks[task_id], field_name)
                            if isinstance(adapted_value, EnvironmentSpecificValue) and isinstance(original_value, EnvironmentSpecificValue):
                                # Copy the target environment value
                                target_value = adapted_value.get_value_for(self.target_environment)
                                logger.debug(f"  {field_name}: target_value = {target_value}")
                                if target_value is not None:
                                    original_value.set_for_environment(target_value, self.target_environment)
                                    logger.debug(f"  Set {field_name} = {target_value} for {self.target_environment}")
                                else:
                                    logger.debug(f"  No target value for {field_name}")
                            else:
                                logger.debug(f"  Field {field_name} is not EnvironmentSpecificValue")
                        else:
                            logger.debug(f"  Field {field_name} not found in adapted_task or workflow.tasks[{task_id}]")
            
            if self.verbose:
                print("  ✓ Environment adaptation applied automatically")
                
        except Exception as e:
            if self.verbose:
                print(f"  ⚠ Environment adaptation failed: {e}")
                print("  Continuing with existing values and defaults") 