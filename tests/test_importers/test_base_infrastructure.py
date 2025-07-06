"""
Tests for the new shared importer infrastructure.

This module tests the base importer class and shared infrastructure modules
to ensure they work correctly together.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from typing import Dict, Any

from wf2wf.importers.base import BaseImporter
from wf2wf.importers.loss_integration import detect_and_apply_loss_sidecar, create_loss_sidecar_summary
from wf2wf.importers.inference import infer_environment_specific_values, infer_execution_model
from wf2wf.importers.interactive import prompt_for_missing_information
from wf2wf.core import Workflow, Task, EnvironmentSpecificValue


class TestBaseImporter(BaseImporter):
    """Test implementation of BaseImporter for testing."""
    
    def _parse_source(self, path: Path, **opts) -> Dict[str, Any]:
        """Parse test source file."""
        return {
            'name': 'test_workflow',
            'version': '1.0',
            'tasks': {
                'test_task': {
                    'command': 'echo "hello world"',
                    'cpu': 1,
                    'mem_mb': 1024
                }
            },
            'edges': []
        }
    
    def _create_basic_workflow(self, parsed_data: Dict[str, Any]) -> Workflow:
        """Create basic workflow from parsed data."""
        workflow = Workflow(
            name=parsed_data['name'],
            version=parsed_data['version']
        )
        
        # Add tasks
        for task_id, task_data in parsed_data['tasks'].items():
            task = Task(id=task_id)
            if 'command' in task_data:
                task.command.set_for_environment(task_data['command'], 'shared_filesystem')
            if 'cpu' in task_data:
                task.cpu.set_for_environment(task_data['cpu'], 'shared_filesystem')
            if 'mem_mb' in task_data:
                task.mem_mb.set_for_environment(task_data['mem_mb'], 'shared_filesystem')
            workflow.add_task(task)
        
        # Add edges
        for edge_data in parsed_data['edges']:
            workflow.add_edge(edge_data['parent'], edge_data['child'])
        
        return workflow
    
    def _get_source_format(self) -> str:
        """Get source format name."""
        return 'test'
    
    def get_supported_extensions(self):
        """Test implementation of get_supported_extensions."""
        return ['.test']


class TestBaseImporterInfrastructure:
    """Test the base importer infrastructure."""
    
    def test_base_importer_initialization(self):
        """Test that BaseImporter initializes correctly."""
        importer = TestBaseImporter(interactive=True, verbose=True)
        assert importer.interactive is True
        assert importer.verbose is True
    
    def test_base_importer_import_workflow(self, tmp_path):
        """Test that BaseImporter can import a workflow."""
        # Create a test file
        test_file = tmp_path / "test.workflow"
        test_file.write_text("test content")
        
        importer = TestBaseImporter(interactive=False, verbose=False)
        workflow = importer.import_workflow(test_file)
        
        assert isinstance(workflow, Workflow)
        assert workflow.name == 'test_workflow'
        assert workflow.version == '1.0'
        assert len(workflow.tasks) == 1
        assert 'test_task' in workflow.tasks
    
    def test_base_importer_with_interactive_mode(self, tmp_path):
        """Test that BaseImporter works with interactive mode."""
        # Create a test file
        test_file = tmp_path / "test.workflow"
        test_file.write_text("test content")
        
        importer = TestBaseImporter(interactive=True, verbose=False)
        
        # Mock the interactive prompting to avoid user input
        with patch('wf2wf.importers.interactive.prompt_for_missing_information'):
            workflow = importer.import_workflow(test_file)
        
        assert isinstance(workflow, Workflow)
    
    def test_base_importer_source_format_detection(self):
        """Test that source format detection works correctly."""
        importer = TestBaseImporter()
        assert importer._get_source_format() == 'test'
    
    def test_base_importer_supported_extensions(self):
        """Test that supported extensions are detected correctly."""
        importer = TestBaseImporter()
        assert '.test' in importer.get_supported_extensions()
        assert importer.can_import(Path('test.workflow')) is False
        assert importer.can_import(Path('test.test')) is True


class TestLossIntegration:
    """Test the loss integration module."""
    
    def test_detect_and_apply_loss_sidecar_no_file(self, tmp_path):
        """Test that loss side-car detection works when no file exists."""
        workflow = Workflow(name='test')
        test_file = tmp_path / "test.workflow"
        test_file.write_text("test content")
        
        result = detect_and_apply_loss_sidecar(workflow, test_file, verbose=False)
        assert result is False
    
    def test_create_loss_sidecar_summary_no_file(self, tmp_path):
        """Test that loss side-car summary works when no file exists."""
        workflow = Workflow(name='test')
        test_file = tmp_path / "test.workflow"
        test_file.write_text("test content")
        
        summary = create_loss_sidecar_summary(workflow, test_file)
        assert summary['loss_sidecar_found'] is False
        assert summary['total_entries'] == 0


class TestInference:
    """Test the inference module."""
    
    def test_infer_execution_model(self):
        """Test execution model inference."""
        workflow = Workflow(name='test')
        
        # Test with empty workflow
        model = infer_execution_model(workflow, 'snakemake')
        assert model in ['sequential', 'pipeline', 'parallel', 'dynamic']
    
    def test_infer_environment_specific_values(self):
        """Test environment-specific value inference."""
        workflow = Workflow(name='test')
        task = Task(id='test_task')
        workflow.add_task(task)
        
        # Test inference
        infer_environment_specific_values(workflow, 'snakemake')
        
        # Check that some values were inferred
        assert task.cpu.get_value_for('shared_filesystem') is not None
        assert task.mem_mb.get_value_for('shared_filesystem') is not None


class TestInteractive:
    """Test the interactive module."""
    
    def test_prompt_for_missing_information(self):
        """Test interactive prompting for missing information."""
        workflow = Workflow(name='test')
        task = Task(id='test_task')
        workflow.add_task(task)
        
        # Mock user input to avoid actual prompting
        with patch('builtins.input', return_value='1'):
            prompt_for_missing_information(workflow, 'snakemake')
        
        # The function should complete without errors


class TestIntegration:
    """Test integration between modules."""
    
    def test_full_import_workflow(self, tmp_path):
        """Test the full import workflow with all components."""
        # Create a test file
        test_file = tmp_path / "test.workflow"
        test_file.write_text("test content")
        
        # Create importer with all features enabled
        importer = TestBaseImporter(interactive=True, verbose=True)
        
        # Mock interactive prompting
        with patch('wf2wf.importers.interactive.prompt_for_missing_information'):
            workflow = importer.import_workflow(test_file)
        
        # Verify the workflow was created correctly
        assert isinstance(workflow, Workflow)
        assert workflow.name == 'test_workflow'
        assert len(workflow.tasks) == 1
        
        # Verify that inference was applied
        task = workflow.tasks['test_task']
        assert task.cpu.get_value_for('shared_filesystem') is not None
        assert task.mem_mb.get_value_for('shared_filesystem') is not None
        
        # Verify that execution model was inferred
        assert workflow.execution_model.get_value_for('shared_filesystem') is not None
    
    def test_environment_specific_values(self, tmp_path):
        """Test that environment-specific values are handled correctly."""
        # Create a test file
        test_file = tmp_path / "test.workflow"
        test_file.write_text("test content")
        
        importer = TestBaseImporter(interactive=False, verbose=False)
        workflow = importer.import_workflow(test_file)
        
        task = workflow.tasks['test_task']
        
        # Test that environment-specific values can be set and retrieved
        task.cpu.set_for_environment(4, 'distributed_computing')
        task.mem_mb.set_for_environment(8192, 'cloud_native')
        
        assert task.cpu.get_value_for('distributed_computing') == 4
        assert task.mem_mb.get_value_for('cloud_native') == 8192
        assert task.cpu.get_value_for('shared_filesystem') != 4  # Different environment 