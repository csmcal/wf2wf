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

from wf2wf.core import Workflow, Task, Edge, TypeSpec
from wf2wf.environ import EnvironmentManager
from wf2wf.interactive import get_prompter
from wf2wf.loss import detect_and_apply_loss_sidecar, create_loss_sidecar_summary
from wf2wf.importers.inference import infer_environment_specific_values
from wf2wf.workflow_analysis import detect_execution_model_from_content, create_execution_model_spec
from wf2wf.importers.inference import infer_condor_attributes
from wf2wf.importers.resource_processor import process_workflow_resources
from wf2wf.interactive import get_prompter
from wf2wf.utils.format_detection import detect_input_format, can_import
from wf2wf.core import MetadataSpec

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
        
        # Initialize interactive prompter
        self.prompter = get_prompter()
        self.prompter.interactive = interactive
        self.prompter.verbose = verbose
        
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
            path: Path to source workflow file
            **opts: Import options
            
        Returns:
            Workflow object representing the imported workflow
            
        Raises:
            ImportError: If the workflow cannot be imported
            ValueError: If the workflow is invalid
        """
        # Store source path and opts for later use
        self._source_path = path
        self._opts = opts
        
        # Convert string to Path if needed
        if isinstance(path, str):
            path = Path(path)
        
        # Set up logging
        if opts.get("verbose"):
            self.verbose = True
        if opts.get("debug"):
            self.debug = True
        if opts.get("interactive"):
            self.interactive = True
            
        try:
            # Step 0: Early execution model detection and confirmation (ONLY ONCE)
            if self.verbose:
                logger.info(f"Step 0: Detecting execution model for {path}")
            
            # Get content analysis for execution model detection
            content_analysis = detect_execution_model_from_content(path, self._get_source_format())
            
            # Interactive execution model confirmation if enabled
            if self.interactive:
                from wf2wf.interactive import prompt_for_execution_model_confirmation
                # Get user selection for execution model
                self._selected_execution_model = prompt_for_execution_model_confirmation(
                    self._get_source_format(),
                    content_analysis
                )
            else:
                # Use content analysis result or format default
                if content_analysis and content_analysis.execution_model:
                    self._selected_execution_model = content_analysis.execution_model
                else:
                    # Use format-based default
                    format_defaults = {
                        "snakemake": "shared_filesystem",
                        "dagman": "distributed_computing", 
                        "nextflow": "hybrid",
                        "cwl": "shared_filesystem",
                        "wdl": "shared_filesystem",
                        "galaxy": "shared_filesystem"
                    }
                    self._selected_execution_model = format_defaults.get(self._get_source_format().lower(), "shared_filesystem")
            
            if self.verbose:
                logger.info(f"Selected execution model: {self._selected_execution_model}")
            
            # Step 1: Parse source format
            if self.verbose:
                logger.info(f"Step 1: Parsing {path} with {self.__class__.__name__}")
            
            parsed_data = self._parse_source(path, **opts)
            
            # Step 2: Create basic workflow structure
            workflow = self._create_basic_workflow(parsed_data)
            
            # Store the original execution environment in metadata
            if not workflow.metadata:
                workflow.metadata = MetadataSpec()
            workflow.metadata.original_execution_environment = self._selected_execution_model
            workflow.metadata.original_source_format = self._get_source_format()
            workflow.metadata.source_format = self._get_source_format()
            
            if self.verbose:
                logger.info(f"Stored original execution environment '{self._selected_execution_model}' in metadata")
            
            # Step 3: Apply loss side-car if available
            detect_and_apply_loss_sidecar(workflow, path, self.verbose)
            
            # Step 4: Infer missing information
            self._infer_missing_information(workflow, path)
            
            # Step 5: Environment management
            self._handle_environment_management(workflow, path, opts)
            
            # Step 6: Interactive prompting if enabled
            if self.interactive:
                # Only prompt for missing information, not execution model
                from wf2wf.interactive import prompt_for_missing_information
                
                # Standard missing information prompting
                prompt_for_missing_information(workflow, self._get_source_format())
                
                # Check for target format optimization if specified
                target_format = opts.get('target_format')
                if target_format:
                    from wf2wf.interactive import prompt_for_workflow_optimization
                    prompt_for_workflow_optimization(workflow, target_format)
            
            # Step 7: Validate and return
            workflow.validate()
            
            # Step 8: Validate workflow functionality
            self._validate_workflow_functionality(workflow, self._selected_execution_model)
            
            if self.verbose:
                logger.info(f"Successfully imported workflow with {len(workflow.tasks)} tasks")
            
            return workflow
            
        except Exception as e:
            logger.error(f"Failed to import workflow from {path}: {e}")
            raise ImportError(f"Failed to import workflow from {path}: {e}") from e
    
    def analyze_target_adaptation(self, workflow: Workflow, target_format: str) -> Dict[str, Any]:
        """
        Analyze what adaptations are needed for the target format.
        
        This method provides comprehensive analysis of what changes are needed
        when converting to a specific target format, including execution model
        transitions and format-specific requirements.
        
        Args:
            workflow: Workflow to analyze
            target_format: Target format name
            
        Returns:
            Dictionary containing adaptation analysis
        """
        analysis = {
            'target_format': target_format,
            'source_format': self._get_source_format(),
            'execution_model_transition': None,
            'required_adaptations': [],
            'optional_optimizations': [],
            'potential_issues': [],
            'recommendations': []
        }
        
        # Analyze execution model transition
        analysis['execution_model_transition'] = self._analyze_execution_model_transition(workflow, target_format)
        
        # Add format-specific analysis
        format_analysis = self._analyze_format_specific_requirements(workflow, target_format)
        analysis['required_adaptations'].extend(format_analysis.get('required', []))
        analysis['optional_optimizations'].extend(format_analysis.get('optional', []))
        analysis['potential_issues'].extend(format_analysis.get('issues', []))
        analysis['recommendations'].extend(format_analysis.get('recommendations', []))
        
        # Add resource analysis
        resource_analysis = self._analyze_resource_requirements(workflow, target_format)
        analysis['required_adaptations'].extend(resource_analysis.get('required', []))
        analysis['potential_issues'].extend(resource_analysis.get('issues', []))
        
        # Add environment analysis
        env_analysis = self._analyze_environment_requirements(workflow, target_format)
        analysis['required_adaptations'].extend(env_analysis.get('required', []))
        analysis['potential_issues'].extend(env_analysis.get('issues', []))
        
        return analysis
    
    def _analyze_format_specific_requirements(self, workflow: Workflow, target_format: str) -> Dict[str, List[str]]:
        """
        Analyze format-specific requirements for the target format.
        
        Args:
            workflow: Workflow to analyze
            target_format: Target format name
            
        Returns:
            Dictionary containing format-specific analysis
        """
        analysis = {
            'required': [],
            'optional': [],
            'issues': [],
            'recommendations': []
        }
        
        if target_format == 'dagman':
            # DAGMan-specific requirements
            for task in workflow.tasks.values():
                if not task.command.get_value_for('shared_filesystem'):
                    analysis['required'].append(f"Task '{task.id}' needs executable specification")
                
                if not task.extra.get('requirements') and task.gpu.get_value_for('shared_filesystem'):
                    analysis['optional'].append(f"Task '{task.id}' could benefit from GPU requirements")
                
                if not task.retry_count.get_value_for('shared_filesystem'):
                    analysis['recommendations'].append(f"Task '{task.id}' should have retry specification")
        
        elif target_format == 'nextflow':
            # Nextflow-specific requirements
            for task in workflow.tasks.values():
                if not task.inputs:
                    analysis['required'].append(f"Task '{task.id}' needs input specifications")
                
                if not task.outputs:
                    analysis['required'].append(f"Task '{task.id}' needs output specifications")
                
                if not task.extra.get('publish_dir') and task.outputs:
                    analysis['optional'].append(f"Task '{task.id}' could use publishDir for outputs")
        
        elif target_format == 'cwl':
            # CWL-specific requirements
            for task in workflow.tasks.values():
                if not task.inputs:
                    analysis['required'].append(f"Task '{task.id}' needs input parameter specifications")
                
                if not task.outputs:
                    analysis['required'].append(f"Task '{task.id}' needs output parameter specifications")
                
                if task.command.get_value_for('shared_filesystem') and not task.script.get_value_for('shared_filesystem'):
                    analysis['recommendations'].append(f"Task '{task.id}' should use script instead of command for CWL")
        
        return analysis
    
    def _analyze_resource_requirements(self, workflow: Workflow, target_format: str) -> Dict[str, List[str]]:
        """
        Analyze resource requirements for the target format.
        
        Args:
            workflow: Workflow to analyze
            target_format: Target format name
            
        Returns:
            Dictionary containing resource analysis
        """
        analysis = {
            'required': [],
            'issues': []
        }
        
        # Check for missing resource specifications in distributed formats
        if target_format in ['dagman', 'nextflow']:
            for task in workflow.tasks.values():
                if task.cpu.get_value_for('shared_filesystem') is None:
                    analysis['required'].append(f"Task '{task.id}' needs CPU specification")
                
                if task.mem_mb.get_value_for('shared_filesystem') is None:
                    analysis['required'].append(f"Task '{task.id}' needs memory specification")
                
                if task.disk_mb.get_value_for('shared_filesystem') is None:
                    analysis['required'].append(f"Task '{task.id}' needs disk specification")
                
                # Check for reasonable resource values
                cpu_value = task.cpu.get_value_for('shared_filesystem')
                if cpu_value and cpu_value > 32:
                    analysis['issues'].append(f"Task '{task.id}' has very high CPU requirement ({cpu_value})")
                
                mem_value = task.mem_mb.get_value_for('shared_filesystem')
                if mem_value and mem_value > 65536:  # 64GB
                    analysis['issues'].append(f"Task '{task.id}' has very high memory requirement ({mem_value}MB)")
        
        return analysis
    
    def _analyze_environment_requirements(self, workflow: Workflow, target_format: str) -> Dict[str, List[str]]:
        """
        Analyze environment requirements for the target format.
        
        Args:
            workflow: Workflow to analyze
            target_format: Target format name
            
        Returns:
            Dictionary containing environment analysis
        """
        analysis = {
            'required': [],
            'issues': []
        }
        
        # Check for environment isolation in distributed formats
        if target_format in ['dagman', 'nextflow']:
            for task in workflow.tasks.values():
                if (task.container.get_value_for('shared_filesystem') is None and 
                    task.conda.get_value_for('shared_filesystem') is None):
                    analysis['required'].append(f"Task '{task.id}' needs container or conda specification")
        
        # Check for environment consistency
        containers = set()
        conda_envs = set()
        
        for task in workflow.tasks.values():
            container = task.container.get_value_for('shared_filesystem')
            if container:
                containers.add(container)
            
            conda = task.conda.get_value_for('shared_filesystem')
            if conda:
                conda_envs.add(conda)
        
        if len(containers) > 5:
            analysis['issues'].append(f"Workflow uses {len(containers)} different containers - consider consolidation")
        
        if len(conda_envs) > 3:
            analysis['issues'].append(f"Workflow uses {len(conda_envs)} different conda environments - consider consolidation")
        
        return analysis
    
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
    
    def _create_task_from_data(self, task_id: str, task_data: Dict[str, Any], source_environment: str = None) -> Task:
        """
        Create a Task object from task data.
        
        This method creates a Task object from the task data dictionary.
        It handles environment-specific values and other Task-specific logic.
        
        Args:
            task_id: ID of the task
            task_data: Dictionary containing task data
            source_environment: Source execution environment (auto-detected if None)
            
        Returns:
            Task object
        """
        # Auto-detect source environment if not provided
        if source_environment is None:
            source_environment = self._get_format_default_execution_model(self._get_source_format())
        
        # Extract basic task information
        label = task_data.get('label')
        doc = task_data.get('doc')
        
        # Create task
        task = Task(id=task_id, label=label, doc=doc)
        
        # Extract environment-specific values
        self._extract_environment_specific_values(task, task_data, source_environment)
        
        # Extract I/O
        task.inputs = task_data.get('inputs', [])
        task.outputs = task_data.get('outputs', [])
        
        # Extract advanced features
        if 'when' in task_data:
            task.when.set_for_environment(task_data['when'], source_environment)
        if 'scatter' in task_data:
            task.scatter.set_for_environment(task_data['scatter'], source_environment)
        
        # Extract metadata
        task.provenance = task_data.get('provenance')
        task.documentation = task_data.get('documentation')
        task.intent = task_data.get('intent', [])
        
        return task
    
    def _extract_environment_specific_values(self, task: Task, task_data: Dict[str, Any], source_environment: str = None):
        """
        Extract environment-specific values from task data.
        
        This method extracts environment-specific values from the task data
        and sets them on the task object. It handles the new multi-environment
        IR structure.
        
        Args:
            task: Task object to populate
            task_data: Dictionary containing task data
            source_environment: Source execution environment (auto-detected if None)
        """
        # Auto-detect source environment if not provided
        if source_environment is None:
            source_environment = self._get_format_default_execution_model(self._get_source_format())
        
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
                    # Set for the detected source environment
                    task.set_for_environment(target_field, value, source_environment)
                    # ALSO set as default value for fallback
                    task.set_for_environment(target_field, value, None)  # None = default
    
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
        
        # Use the execution model that was selected during import
        execution_model = self._selected_execution_model
        
        # Infer environment-specific values for the selected execution model
        infer_environment_specific_values(workflow, source_format, execution_model)
        
        # Infer Condor-specific attributes if converting to DAGMan
        if source_format == 'snakemake':
            infer_condor_attributes(workflow, 'distributed_computing')

    def _get_format_default_execution_model(self, source_format: str) -> str:
        """
        Get the default execution model for a given format.
        
        Args:
            source_format: Source format name
            
        Returns:
            Default execution model for the format
        """
        format_models = {
            'snakemake': 'shared_filesystem',
            'dagman': 'distributed_computing',
            'nextflow': 'hybrid',
            'cwl': 'shared_filesystem',
            'wdl': 'shared_filesystem',
            'galaxy': 'shared_filesystem'
        }
        return format_models.get(source_format.lower(), 'unknown')

    def _analyze_execution_model_transition(self, workflow: Workflow, target_format: str) -> Dict[str, Any]:
        """
        Analyze what changes are needed when transitioning between execution models.
        
        Args:
            workflow: Workflow to analyze
            target_format: Target format name
            
        Returns:
            Analysis of required changes and potential issues
        """
        from wf2wf.workflow_analysis import analyze_execution_model_transition
        
        if not hasattr(workflow, 'execution_model_spec'):
            # Create a basic execution model spec if not available
            source_model = workflow.metadata.original_execution_environment if workflow.metadata else 'unknown'
            from wf2wf.core import ExecutionModelSpec
            workflow.execution_model_spec = ExecutionModelSpec(
                model=source_model,
                source_format=self._get_source_format(),
                detection_method="workflow_analysis",
                detection_confidence=0.5
            )
        
        analysis = analyze_execution_model_transition(workflow.execution_model_spec, target_format)
        
        if self.verbose:
            logger.info(f"Execution model transition analysis:")
            logger.info(f"  Source: {analysis['source_model']}")
            logger.info(f"  Target: {analysis['target_model']}")
            logger.info(f"  Required changes: {analysis['required_changes']}")
            if analysis['potential_issues']:
                logger.warning(f"  Potential issues: {analysis['potential_issues']}")
            if analysis['recommendations']:
                logger.info(f"  Recommendations: {analysis['recommendations']}")
        
        return analysis
    
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
        return can_import(path, self.get_supported_extensions())
    
    def _validate_workflow_functionality(self, workflow: Workflow, execution_model: str) -> None:
        """
        Validate that the workflow is functional and not malformed.
        
        This method checks for common issues that would make a workflow non-functional:
        - Tasks with no inputs, outputs, or commands
        - Empty workflows
        - Tasks with malformed resource specifications
        - Tasks with invalid environment specifications
        
        Args:
            workflow: The workflow to validate
            
        Raises:
            ValueError: If the workflow is non-functional or malformed
        """
        if not workflow.tasks:
            raise ValueError("Workflow contains no tasks - cannot be executed")
        
        problematic_tasks = []
        
        for task_id, task in workflow.tasks.items():
            issues = []
            
            # Check if task has any meaningful content
            has_inputs = len(task.inputs) > 0
            has_outputs = len(task.outputs) > 0
            has_command = task.command.get_value_for(execution_model) is not None
            has_script = task.script.get_value_for(execution_model) is not None
            
            if not (has_inputs or has_outputs or has_command or has_script):
                issues.append("Task has no inputs, outputs, commands, or scripts")
            
            # Check for malformed resource specifications
            resources = task.mem_mb.get_value_for(execution_model)
            if resources is not None and not isinstance(resources, (int, float)) and resources <= 0:
                issues.append(f"Invalid memory specification: {resources}")
            
            cpu = task.cpu.get_value_for(execution_model)
            if cpu is not None and not isinstance(cpu, (int, float)) and cpu <= 0:
                issues.append(f"Invalid CPU specification: {cpu}")
            
            # Check for malformed environment specifications
            conda = task.conda.get_value_for(execution_model)
            if conda is not None and not isinstance(conda, str):
                issues.append(f"Invalid conda specification: {conda}")
            
            container = task.container.get_value_for(execution_model)
            if container is not None and not isinstance(container, str):
                issues.append(f"Invalid container specification: {container}")
            
            # Check for malformed parameter specifications
            for param in task.inputs + task.outputs:
                if not param.id or not param.id.strip():
                    issues.append("Parameter has empty or missing ID")
                if not isinstance(param.type, (str, TypeSpec)):
                    issues.append(f"Parameter {param.id} has invalid type specification")
            
            if issues:
                problematic_tasks.append((task_id, issues))
        
        if problematic_tasks:
            error_msg = "Workflow contains non-functional or malformed tasks:\n"
            for task_id, issues in problematic_tasks:
                error_msg += f"  - Task '{task_id}':\n"
                for issue in issues:
                    error_msg += f"    * {issue}\n"
            raise ValueError(error_msg)
        
        # Check for circular dependencies
        self._check_circular_dependencies(workflow)
        
        if self.verbose:
            logger.info(f"Workflow functionality validation passed - {len(workflow.tasks)} tasks are functional")
    
    def _check_circular_dependencies(self, workflow: Workflow) -> None:
        """
        Check for circular dependencies in the workflow.
        
        Args:
            workflow: The workflow to check
            
        Raises:
            ValueError: If circular dependencies are detected
        """
        # Build adjacency list
        graph = {task_id: [] for task_id in workflow.tasks.keys()}
        for edge in workflow.edges:
            if edge.parent in graph and edge.child in graph:
                graph[edge.parent].append(edge.child)
        
        # Detect cycles using DFS
        visited = set()
        rec_stack = set()
        
        def has_cycle(node):
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        for node in graph:
            if node not in visited:
                if has_cycle(node):
                    raise ValueError("Workflow contains circular dependencies")