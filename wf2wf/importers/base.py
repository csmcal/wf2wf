"""
wf2wf.importers.base – Base importer infrastructure for workflow importers.

This module provides shared infrastructure for all workflow importers, including
unified import workflow, error handling, loss side-car integration, and
interactive prompting.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from wf2wf.core import Workflow, Task, Edge
from wf2wf.importers.loss_integration import detect_and_apply_loss_sidecar, create_loss_sidecar_summary
from wf2wf.importers.inference import infer_environment_specific_values, infer_execution_model
from wf2wf.importers.interactive import prompt_for_missing_information
from wf2wf.environ import EnvironmentManager

logger = logging.getLogger(__name__)


class BaseImporter(ABC):
    """
    Base class for all workflow importers with shared functionality.
    
    This class provides a unified interface for importing workflows from various
    formats into the wf2wf intermediate representation. It handles common tasks
    like error handling, loss side-car integration, intelligent inference, and
    interactive prompting.
    """
    
    def __init__(self, interactive: bool = False, verbose: bool = False):
        """
        Initialize the base importer.
        
        Args:
            interactive: Enable interactive prompting for missing information
            verbose: Enable verbose logging
        """
        self.interactive = interactive
        self.verbose = verbose
        
        # Initialize environment manager
        self.environment_manager = EnvironmentManager(interactive=interactive, verbose=verbose)
        
        # Configure logging
        if verbose:
            logging.getLogger(__name__).setLevel(logging.DEBUG)
    
    def import_workflow(self, path: Path, **opts) -> Workflow:
        """
        Main import method with unified workflow.
        
        This method implements the standard import workflow that all importers
        should follow:
        1. Parse source format
        2. Create basic workflow structure
        3. Apply loss side-car if available
        4. Infer missing information
        5. Interactive prompting if enabled
        6. Environment management
        7. Validate and return
        
        Args:
            path: Path to the source workflow file
            **opts: Additional options specific to the importer
            
        Returns:
            Workflow object representing the imported workflow
            
        Raises:
            ImportError: If the workflow cannot be imported
            ValueError: If the workflow is invalid
        """
        try:
            # Step 1: Parse source format
            if self.verbose:
                logger.info(f"Parsing {path} with {self.__class__.__name__}")
            
            parsed_data = self._parse_source(path, **opts)
            
            # Step 2: Create basic workflow structure
            workflow = self._create_basic_workflow(parsed_data)
            
            # Step 3: Apply loss side-car if available
            detect_and_apply_loss_sidecar(workflow, path, self.verbose)
            
            # Step 4: Infer missing information
            self._infer_missing_information(workflow, path)
            
            # Step 5: Environment management
            self._handle_environment_management(workflow, path, opts)
            
            # Step 6: Interactive prompting if enabled
            if self.interactive:
                prompt_for_missing_information(workflow, self._get_source_format())
            
            # Step 7: Validate and return
            workflow.validate()
            
            if self.verbose:
                logger.info(f"Successfully imported workflow with {len(workflow.tasks)} tasks")
            
            return workflow
            
        except Exception as e:
            logger.error(f"Failed to import workflow from {path}: {e}")
            raise ImportError(f"Failed to import workflow from {path}: {e}") from e
    
    @abstractmethod
    def _parse_source(self, path: Path, **opts) -> Dict[str, Any]:
        """
        Parse source format - must be implemented by subclasses.
        
        This method should parse the source workflow file and return a dictionary
        containing all the parsed information. The structure of this dictionary
        is format-specific and will be used by other methods to create the workflow.
        
        Args:
            path: Path to the source workflow file
            **opts: Additional options specific to the importer
            
        Returns:
            Dictionary containing parsed workflow data
            
        Raises:
            ImportError: If the source cannot be parsed
        """
        raise NotImplementedError
    
    def _create_basic_workflow(self, parsed_data: Dict[str, Any]) -> Workflow:
        """
        Create basic workflow from parsed data.
        
        This method creates a basic workflow structure from the parsed data.
        It extracts tasks, edges, and basic metadata. Subclasses can override
        this method to provide format-specific workflow creation logic.
        
        Args:
            parsed_data: Dictionary containing parsed workflow data
            
        Returns:
            Basic workflow object
        """
        # Extract basic workflow information
        name = parsed_data.get('name', 'imported_workflow')
        version = parsed_data.get('version', '1.0')
        label = parsed_data.get('label')
        doc = parsed_data.get('doc')
        
        # Create workflow
        workflow = Workflow(
            name=name,
            version=version,
            label=label,
            doc=doc
        )
        
        # Extract tasks
        tasks = self._extract_tasks(parsed_data)
        for task in tasks:
            workflow.add_task(task)
        
        # Extract edges
        edges = self._extract_edges(parsed_data)
        for edge in edges:
            workflow.add_edge(edge.parent, edge.child)
        
        # Extract workflow-level inputs and outputs
        workflow.inputs = parsed_data.get('inputs', [])
        workflow.outputs = parsed_data.get('outputs', [])
        
        # Extract metadata
        workflow.provenance = parsed_data.get('provenance')
        workflow.documentation = parsed_data.get('documentation')
        workflow.intent = parsed_data.get('intent', [])
        workflow.cwl_version = parsed_data.get('cwl_version')
        workflow.bco_spec = parsed_data.get('bco_spec')
        
        return workflow
    
    def _extract_tasks(self, parsed_data: Dict[str, Any]) -> List[Task]:
        """
        Extract tasks from parsed data.
        
        This method extracts task information from the parsed data and creates
        Task objects. Subclasses should override this method to provide
        format-specific task extraction logic.
        
        Args:
            parsed_data: Dictionary containing parsed workflow data
            
        Returns:
            List of Task objects
        """
        tasks = []
        tasks_data = parsed_data.get('tasks', {})
        
        for task_id, task_data in tasks_data.items():
            if isinstance(task_data, dict):
                task = self._create_task_from_data(task_id, task_data)
                tasks.append(task)
            else:
                logger.warning(f"Invalid task data for {task_id}: {task_data}")
        
        return tasks
    
    def _create_task_from_data(self, task_id: str, task_data: Dict[str, Any]) -> Task:
        """
        Create a Task object from task data.
        
        This method creates a Task object from the task data dictionary.
        It handles environment-specific values and other Task-specific logic.
        
        Args:
            task_id: ID of the task
            task_data: Dictionary containing task data
            
        Returns:
            Task object
        """
        # Extract basic task information
        label = task_data.get('label')
        doc = task_data.get('doc')
        
        # Create task
        task = Task(id=task_id, label=label, doc=doc)
        
        # Extract environment-specific values
        self._extract_environment_specific_values(task, task_data)
        
        # Extract I/O
        task.inputs = task_data.get('inputs', [])
        task.outputs = task_data.get('outputs', [])
        
        # Extract advanced features
        if 'when' in task_data:
            task.when.set_for_environment(task_data['when'], 'shared_filesystem')
        if 'scatter' in task_data:
            task.scatter.set_for_environment(task_data['scatter'], 'shared_filesystem')
        
        # Extract metadata
        task.provenance = task_data.get('provenance')
        task.documentation = task_data.get('documentation')
        task.intent = task_data.get('intent', [])
        
        return task
    
    def _extract_environment_specific_values(self, task: Task, task_data: Dict[str, Any]):
        """
        Extract environment-specific values from task data.
        
        This method extracts environment-specific values from the task data
        and sets them on the task object. It handles the new multi-environment
        IR structure.
        
        Args:
            task: Task object to populate
            task_data: Dictionary containing task data
        """
        # Map of field names to their environment-specific counterparts
        field_mapping = {
            'command': 'command',
            'script': 'script',
            'cpu': 'cpu',
            'mem_mb': 'mem_mb',
            'disk_mb': 'disk_mb',
            'gpu': 'gpu',
            'gpu_mem_mb': 'gpu_mem_mb',
            'time_s': 'time_s',
            'threads': 'threads',
            'conda': 'conda',
            'container': 'container',
            'workdir': 'workdir',
            'env_vars': 'env_vars',
            'modules': 'modules',
            'retry_count': 'retry_count',
            'retry_delay': 'retry_delay',
            'retry_backoff': 'retry_backoff',
            'max_runtime': 'max_runtime',
            'checkpoint_interval': 'checkpoint_interval',
            'on_failure': 'on_failure',
            'failure_notification': 'failure_notification',
            'cleanup_on_failure': 'cleanup_on_failure',
            'restart_from_checkpoint': 'restart_from_checkpoint',
            'partial_results': 'partial_results',
            'priority': 'priority',
            'file_transfer_mode': 'file_transfer_mode',
            'staging_required': 'staging_required',
            'cleanup_after': 'cleanup_after',
            'cloud_provider': 'cloud_provider',
            'cloud_storage_class': 'cloud_storage_class',
            'cloud_encryption': 'cloud_encryption',
            'parallel_transfers': 'parallel_transfers',
            'bandwidth_limit': 'bandwidth_limit',
            'requirements': 'requirements',
            'hints': 'hints',
            'checkpointing': 'checkpointing',
            'logging': 'logging',
            'security': 'security',
            'networking': 'networking'
        }
        
        # Extract each field
        for source_field, target_field in field_mapping.items():
            if source_field in task_data:
                value = task_data[source_field]
                if value is not None:
                    # Set for shared_filesystem environment by default
                    task.set_for_environment(target_field, value, 'shared_filesystem')
    
    def _extract_edges(self, parsed_data: Dict[str, Any]) -> List[Edge]:
        """
        Extract edges from parsed data.
        
        This method extracts edge information from the parsed data and creates
        Edge objects. Subclasses should override this method to provide
        format-specific edge extraction logic.
        
        Args:
            parsed_data: Dictionary containing parsed workflow data
            
        Returns:
            List of Edge objects
        """
        edges = []
        edges_data = parsed_data.get('edges', [])
        
        for edge_data in edges_data:
            if isinstance(edge_data, dict) and 'parent' in edge_data and 'child' in edge_data:
                edge = Edge(parent=edge_data['parent'], child=edge_data['child'])
                edges.append(edge)
            elif isinstance(edge_data, (list, tuple)) and len(edge_data) == 2:
                edge = Edge(parent=edge_data[0], child=edge_data[1])
                edges.append(edge)
            else:
                logger.warning(f"Invalid edge data: {edge_data}")
        
        return edges
    
    def _apply_loss_sidecar(self, workflow: Workflow, source_path: Path):
        """
        Apply loss side-car if available.
        
        This method looks for a loss side-car file next to the source file
        and applies any loss information to the workflow.
        
        Args:
            workflow: Workflow object to apply loss information to
            source_path: Path to the source workflow file
        """
        loss_path = source_path.with_suffix('.loss.json')
        
        if loss_path.exists():
            if self.verbose:
                logger.info(f"Found loss side-car: {loss_path}")
            
            try:
                import json
                loss_data = json.loads(loss_path.read_text())
                
                # Apply loss information to workflow
                self._apply_loss_data(workflow, loss_data)
                
                if self.verbose:
                    logger.info(f"Applied {len(loss_data.get('entries', []))} loss entries")
                    
            except Exception as e:
                logger.warning(f"Failed to apply loss side-car {loss_path}: {e}")
    
    def _apply_loss_data(self, workflow: Workflow, loss_data: Dict[str, Any]):
        """
        Apply loss data to workflow.
        
        This method applies loss information from a loss side-car to the
        workflow, attempting to restore lost information where possible.
        
        Args:
            workflow: Workflow object to apply loss information to
            loss_data: Dictionary containing loss information
        """
        entries = loss_data.get('entries', [])
        
        for entry in entries:
            try:
                self._apply_loss_entry(workflow, entry)
            except Exception as e:
                logger.warning(f"Failed to apply loss entry {entry}: {e}")
    
    def _apply_loss_entry(self, workflow: Workflow, entry: Dict[str, Any]):
        """
        Apply a single loss entry to the workflow.
        
        This method applies a single loss entry to the workflow, attempting
        to restore lost information at the specified path.
        
        Args:
            workflow: Workflow object to apply loss information to
            entry: Dictionary containing loss entry information
        """
        json_pointer = entry.get('json_pointer', '')
        lost_value = entry.get('lost_value')
        field = entry.get('field')
        status = entry.get('status', 'lost')
        
        if status == 'reapplied':
            return  # Already applied
        
        # Parse JSON pointer to find the target location
        target = self._resolve_json_pointer(workflow, json_pointer)
        
        if target is not None and lost_value is not None:
            # Try to restore the lost value
            if hasattr(target, 'set_for_environment'):
                # Environment-specific field
                target.set_for_environment(field, lost_value, 'shared_filesystem')
            elif hasattr(target, field):
                # Regular field
                setattr(target, field, lost_value)
            else:
                # Try to set in extra dict
                if hasattr(target, 'extra'):
                    target.extra[field] = EnvironmentSpecificValue(lost_value, ['shared_filesystem'])
            
            # Mark as reapplied
            entry['status'] = 'reapplied'
    
    def _resolve_json_pointer(self, obj: Any, json_pointer: str) -> Any:
        """
        Resolve a JSON pointer to find the target object.
        
        This method resolves a JSON pointer string to find the target object
        in the workflow structure.
        
        Args:
            obj: Object to search in (usually the workflow)
            json_pointer: JSON pointer string (e.g., "/tasks/task1/cpu")
            
        Returns:
            Target object or None if not found
        """
        if not json_pointer.startswith('/'):
            return None
        
        parts = json_pointer.split('/')[1:]  # Skip empty first part
        
        current = obj
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None
        
        return current
    
    def _infer_missing_information(self, workflow: Workflow, source_path: Path):
        """
        Infer missing information in the workflow.
        
        This method uses intelligent inference to fill in missing information
        in the workflow based on the source format and content.
        
        Args:
            workflow: Workflow object to infer information for
            source_path: Path to the source workflow file
        """
        source_format = self._get_source_format()
        
        # Infer execution model
        execution_model = infer_execution_model(workflow, source_format)
        workflow.execution_model.set_for_environment(execution_model, 'shared_filesystem')
        
        # Infer environment-specific values
        infer_environment_specific_values(workflow, source_format)
    
    def _handle_environment_management(self, workflow: Workflow, source_path: Path, opts: Dict[str, Any]) -> None:
        """
        Handle environment and container management for the workflow.
        
        Args:
            workflow: Workflow to process
            source_path: Path to source file
            opts: Additional options
        """
        source_format = self._get_source_format()
        
        # Detect and parse environments
        env_info = self.environment_manager.detect_and_parse_environments(
            workflow, source_format, source_path
        )
        
        if self.verbose:
            logger.info(f"Environment analysis: {env_info['environment_metadata']}")
            if env_info['environment_warnings']:
                for warning in env_info['environment_warnings']:
                    logger.warning(warning)
        
        # Infer missing environments
        self.environment_manager.infer_missing_environments(workflow, source_format)
        
        # Prompt for missing environments if interactive
        if self.interactive:
            self.environment_manager.prompt_for_missing_environments(workflow, source_format)
        
        # Build environment images if requested
        if opts.get('build_environments', False):
            build_results = self.environment_manager.build_environment_images(
                workflow,
                registry=opts.get('registry'),
                push=opts.get('push_images', False),
                dry_run=opts.get('dry_run', True)
            )
            
            if self.verbose:
                logger.info(f"Environment build results: {len(build_results['built_images'])} built, "
                           f"{len(build_results['failed_builds'])} failed")
    
    def adapt_workflow_for_target(self, workflow: Workflow, target_format: str) -> None:
        """
        Adapt workflow for target format, including environment adaptations.
        
        Args:
            workflow: Workflow to adapt
            target_format: Target format name
        """
        # Adapt environments for target format
        self.environment_manager.adapt_environments_for_target(workflow, target_format)
        
        # Apply other format-specific adaptations
        self._apply_format_specific_adaptations(workflow, target_format)
    
    def _apply_format_specific_adaptations(self, workflow: Workflow, target_format: str) -> None:
        """
        Apply format-specific adaptations to the workflow.
        
        Args:
            workflow: Workflow to adapt
            target_format: Target format name
        """
        # This method can be overridden by subclasses for format-specific adaptations
        pass
    
    def _get_source_format(self) -> str:
        """
        Get the source format name for this importer.
        
        Returns:
            Source format name (e.g., 'snakemake', 'cwl', 'dagman')
        """
        # Default implementation - subclasses should override
        return self.__class__.__name__.lower().replace('importer', '')
    
    def _prompt_for_missing_information(self, workflow: Workflow, source_path: Path):
        """
        Interactive prompting for missing information.
        
        This method prompts the user for missing information when interactive
        mode is enabled.
        
        Args:
            workflow: Workflow object to prompt for
            source_path: Path to the source workflow file
        """
        if not self.interactive:
            return
        
        # This is now handled by the shared interactive module
        pass
    
    def _prompt_for_resource_requirements(self, workflow: Workflow):
        """
        Prompt for missing resource requirements.
        
        Args:
            workflow: Workflow object to prompt for
        """
        # This is now handled by the shared interactive module
        pass
    
    def _prompt_for_environment_specifications(self, workflow: Workflow):
        """
        Prompt for missing environment specifications.
        
        Args:
            workflow: Workflow object to prompt for
        """
        # This is now handled by the shared interactive module
        pass
    
    def _prompt_for_error_handling(self, workflow: Workflow):
        """
        Prompt for missing error handling.
        
        Args:
            workflow: Workflow object to prompt for
        """
        # This is now handled by the shared interactive module
        pass
    
    def _prompt_user(self, message: str, default: str = "") -> str:
        """
        Prompt the user for input.
        
        Args:
            message: Message to display to the user
            default: Default value to use if user just presses Enter
            
        Returns:
            User's response or default value
        """
        # This is now handled by the shared interactive module
        try:
            response = input(message)
            return response if response else default
        except (EOFError, KeyboardInterrupt):
            # User interrupted, return default
            return default
    
    def get_supported_extensions(self) -> List[str]:
        """
        Get list of file extensions supported by this importer.
        
        Returns:
            List of supported file extensions (including the dot)
        """
        return []
    
    def can_import(self, path: Path) -> bool:
        """
        Check if this importer can import the given file.
        
        Args:
            path: Path to the file to check
            
        Returns:
            True if this importer can import the file
        """
        return path.suffix.lower() in self.get_supported_extensions() 