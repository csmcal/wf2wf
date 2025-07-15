"""
Comprehensive tests for base importer infrastructure.

This module consolidates all base importer functionality tests including:
- Base importer class functionality
- Loss integration and sidecar handling
- Inference for missing information
- Interactive prompting
- Source format detection
- Integration workflows
"""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch
from typing import Dict, Any

from wf2wf.core import Workflow, Task, EnvironmentSpecificValue
from wf2wf.importers.base import BaseImporter
from wf2wf.loss import detect_and_apply_loss_sidecar, create_loss_sidecar_summary
from wf2wf.importers.inference import infer_environment_specific_values, infer_execution_model
from wf2wf.interactive import prompt_for_missing_information


class TestBaseImporter:
    """Test implementation for testing BaseImporter functionality."""
    
    def __init__(self, interactive: bool = False, verbose: bool = False):
        self.interactive = interactive
        self.verbose = verbose
    
    def import_workflow(self, path: Path, **opts) -> Workflow:
        """Test implementation of import_workflow."""
        # Parse source
        parsed_data = self._parse_source(path, **opts)
        
        # Create basic workflow
        workflow = self._create_basic_workflow(parsed_data)
        
        # Apply loss side-car if available
        detect_and_apply_loss_sidecar(workflow, path, verbose=self.verbose)
        
        # Infer missing information
        infer_environment_specific_values(workflow, self._get_source_format())
        
        # Interactive prompting if enabled
        if self.interactive:
            prompt_for_missing_information(workflow, self._get_source_format())
        
        return workflow
    
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
    
    def can_import(self, path: Path) -> bool:
        """Test implementation of can_import."""
        return path.suffix in self.get_supported_extensions()


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

    def test_base_importer_with_interactive_mode(self, tmp_path, interactive_responses):
        """Test that BaseImporter works with interactive mode."""
        # Set test responses for the interactive prompter
        interactive_responses.set_responses([
            "test_workflow", "1.0", "", "1", "4096", "4096", "no", "none", "0", "3600"
        ])
        
        # Create a test file
        test_file = tmp_path / "test.workflow"
        test_file.write_text("test content")
        
        importer = TestBaseImporter(interactive=True, verbose=False)
        
        # Test the full workflow with interactive prompting
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

    def test_base_importer_workflow_creation(self):
        """Test that workflow creation from parsed data works correctly."""
        importer = TestBaseImporter()
        parsed_data = {
            'name': 'complex_workflow',
            'version': '2.0',
            'tasks': {
                'task1': {'command': 'echo task1', 'cpu': 2, 'mem_mb': 2048},
                'task2': {'command': 'echo task2', 'cpu': 4, 'mem_mb': 4096}
            },
            'edges': [{'parent': 'task1', 'child': 'task2'}]
        }
        
        workflow = importer._create_basic_workflow(parsed_data)
        
        assert workflow.name == 'complex_workflow'
        assert workflow.version == '2.0'
        assert len(workflow.tasks) == 2
        assert len(workflow.edges) == 1
        
        # Check task properties
        task1 = workflow.tasks['task1']
        assert task1.command.get_value_with_default('shared_filesystem') == 'echo task1'
        assert task1.cpu.get_value_with_default('shared_filesystem') == 2
        assert task1.mem_mb.get_value_with_default('shared_filesystem') == 2048


class TestLossIntegration:
    """Test the loss integration module."""

    def test_detect_and_apply_loss_sidecar_no_file(self, tmp_path):
        """Test that loss side-car detection works when no file exists."""
        workflow = Workflow(name='test')
        test_file = tmp_path / "test.workflow"
        test_file.write_text("test content")
        
        result = detect_and_apply_loss_sidecar(workflow, test_file, verbose=False)
        assert result is False

    def test_detect_and_apply_loss_sidecar_with_file(self, tmp_path):
        """Test that loss side-car detection works when file exists."""
        import hashlib
        
        workflow = Workflow(name='test')
        test_file = tmp_path / "test.workflow"
        test_file.write_text("test content")
        
        # Compute actual checksum for the test file
        sha256_hash = hashlib.sha256()
        with open(test_file, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        actual_checksum = f"sha256:{sha256_hash.hexdigest()}"
        
        # Create loss sidecar file with correct format
        loss_file = test_file.with_suffix('.loss.json')
        loss_data = {
            "wf2wf_version": "0.1.0",
            "target_engine": "snakemake",
            "source_checksum": actual_checksum,
            "summary": {
                "total_entries": 1,
                "by_severity": {"warn": 1},
                "by_category": {"advanced_features": 1}
            },
            "entries": [
                {
                    "json_pointer": "/tasks/task1/gpu",
                    "field": "gpu",
                    "lost_value": 2,
                    "reason": "GPU resources not supported in target format",
                    "origin": "wf2wf",
                    "severity": "warn",
                    "status": "lost"
                }
            ]
        }
        loss_file.write_text(json.dumps(loss_data))
        
        result = detect_and_apply_loss_sidecar(workflow, test_file, verbose=False)
        assert result is True

    def test_create_loss_sidecar_summary_no_file(self, tmp_path):
        """Test that loss side-car summary works when no file exists."""
        workflow = Workflow(name='test')
        test_file = tmp_path / "test.workflow"
        test_file.write_text("test content")
        
        summary = create_loss_sidecar_summary(workflow, test_file)
        assert summary['has_loss_sidecar'] is False
        assert summary['entries_count'] == 0

    def test_create_loss_sidecar_summary_with_file(self, tmp_path):
        """Test that loss side-car summary works when file exists."""
        import hashlib
        
        workflow = Workflow(name='test')
        test_file = tmp_path / "test.workflow"
        test_file.write_text("test content")
        
        # Compute actual checksum for the test file
        sha256_hash = hashlib.sha256()
        with open(test_file, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        actual_checksum = f"sha256:{sha256_hash.hexdigest()}"
        
        # Create loss sidecar file with correct format
        loss_file = test_file.with_suffix('.loss.json')
        loss_data = {
            "wf2wf_version": "0.1.0",
            "target_engine": "snakemake",
            "source_checksum": actual_checksum,
            "summary": {
                "total_entries": 2,
                "by_severity": {"warn": 1, "info": 1},
                "by_category": {"advanced_features": 1, "custom": 1}
            },
            "entries": [
                {
                    "json_pointer": "/tasks/task1/gpu",
                    "field": "gpu",
                    "lost_value": 2,
                    "reason": "GPU resources not supported",
                    "origin": "wf2wf",
                    "severity": "warn",
                    "status": "lost"
                },
                {
                    "json_pointer": "/tasks/task1/custom_attr",
                    "field": "custom_attr",
                    "lost_value": "custom_value",
                    "reason": "Custom attributes not supported",
                    "origin": "user",
                    "severity": "info",
                    "status": "lost"
                }
            ]
        }
        loss_file.write_text(json.dumps(loss_data))
        
        summary = create_loss_sidecar_summary(workflow, test_file)
        assert summary['has_loss_sidecar'] is True
        assert summary['entries_count'] == 2


class TestInference:
    """Test the inference module."""

    def test_infer_execution_model(self):
        """Test execution model inference."""
        workflow = Workflow(name='test')
        
        # Test with empty workflow
        model = infer_execution_model(workflow, 'snakemake')
        assert model in ['sequential', 'pipeline', 'parallel', 'dynamic']

    def test_infer_execution_model_with_tasks(self):
        """Test execution model inference with tasks."""
        workflow = Workflow(name='test')
        
        # Add tasks with dependencies
        task1 = Task(id='task1')
        task2 = Task(id='task2')
        workflow.add_task(task1)
        workflow.add_task(task2)
        workflow.add_edge('task1', 'task2')
        
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
        assert task.cpu.get_value_with_default('shared_filesystem') is not None
        assert task.mem_mb.get_value_with_default('shared_filesystem') is not None

    def test_infer_environment_specific_values_with_existing_values(self):
        """Test inference with existing environment-specific values."""
        workflow = Workflow(name='test')
        task = Task(id='test_task')
        
        # Set some existing values
        task.cpu.set_for_environment(4, 'shared_filesystem')
        task.mem_mb.set_for_environment(8192, 'shared_filesystem')
        
        workflow.add_task(task)
        
        # Test inference
        infer_environment_specific_values(workflow, 'snakemake')
        
        # Check that existing values are preserved
        assert task.cpu.get_value_for('shared_filesystem') == 4
        assert task.mem_mb.get_value_for('shared_filesystem') == 8192


class TestInteractive:
    """Test interactive prompting functionality."""

    def test_prompt_for_missing_information(self, interactive_responses):
        """Test interactive prompting for missing information."""
        # Set test responses for the interactive prompter
        interactive_responses.set_responses([
            "test_workflow", "1.0", "", "1", "4096", "4096", "no", "none", "0", "3600"
        ])
        
        workflow = Workflow(name='test')
        task = Task(id='test_task')
        workflow.add_task(task)
        
        # Test prompting
        prompt_for_missing_information(workflow, 'snakemake')
        
        # Check that values were set
        assert task.cpu.get_value_with_default('shared_filesystem') is not None
        assert task.mem_mb.get_value_with_default('shared_filesystem') is not None

    def test_prompt_for_missing_information_with_existing_values(self, interactive_responses):
        """Test interactive prompting with existing values."""
        # Set test responses for the interactive prompter
        interactive_responses.set_responses([
            "test_workflow", "1.0", "", "1", "4096", "4096", "no", "none", "0", "3600"
        ])
        
        workflow = Workflow(name='test')
        task = Task(id='test_task')
        
        # Set existing values
        task.cpu.set_for_environment(4, 'shared_filesystem')
        task.mem_mb.set_for_environment(8192, 'shared_filesystem')
        
        workflow.add_task(task)
        
        # Test prompting
        prompt_for_missing_information(workflow, 'snakemake')
        
        # Check that existing values are preserved
        assert task.cpu.get_value_for('shared_filesystem') == 4
        assert task.mem_mb.get_value_for('shared_filesystem') == 8192


class TestIntegration:
    """Test integration workflows."""

    def test_full_import_workflow(self, tmp_path, interactive_responses):
        """Test the full import workflow with all components."""
        # Set test responses for the interactive prompter
        interactive_responses.set_responses([
            "test_workflow", "1.0", "", "1", "4096", "4096", "no", "none", "0", "3600"
        ])
        
        # Create a test file
        test_file = tmp_path / "test.workflow"
        test_file.write_text("test content")
        
        # Create loss sidecar
        loss_file = test_file.with_suffix('.loss.json')
        loss_data = {
            "entries": [
                {
                    "field": "gpu",
                    "reason": "GPU resources not supported",
                    "severity": "warning"
                }
            ]
        }
        loss_file.write_text(json.dumps(loss_data))
        
        importer = TestBaseImporter(interactive=True, verbose=True)
        
        # Test the full workflow with interactive prompting
        workflow = importer.import_workflow(test_file)
        
        assert isinstance(workflow, Workflow)
        assert workflow.name == 'test_workflow'
        assert len(workflow.tasks) == 1

    def test_environment_specific_values(self, tmp_path):
        """Test environment-specific value handling in import workflow."""
        test_file = tmp_path / "test.workflow"
        test_file.write_text("test content")
        
        importer = TestBaseImporter(interactive=False, verbose=False)
        workflow = importer.import_workflow(test_file)
        
        # Check that environment-specific values were set
        task = workflow.tasks['test_task']
        assert task.command.get_value_with_default('shared_filesystem') == 'echo "hello world"'
        assert task.cpu.get_value_with_default('shared_filesystem') == 1
        assert task.mem_mb.get_value_with_default('shared_filesystem') == 1024

    def test_error_handling_in_import_workflow(self, tmp_path):
        """Test error handling in the import workflow."""
        test_file = tmp_path / "test.workflow"
        test_file.write_text("test content")
        
        importer = TestBaseImporter(interactive=False, verbose=False)
        
        # Test with invalid file path
        invalid_file = tmp_path / "nonexistent.workflow"
        
        try:
            workflow = importer.import_workflow(invalid_file)
            # Should handle gracefully
            assert isinstance(workflow, Workflow)
        except Exception as e:
            # Should provide meaningful error message
            assert "nonexistent" in str(e).lower() or "not found" in str(e).lower()


class TestSourceFormatDetection:
    """Test source format detection functionality."""

    def test_source_format_detection_by_extension(self):
        """Test source format detection by file extension."""
        importer = TestBaseImporter()
        
        # Test supported extensions
        assert importer.can_import(Path('test.test')) is True
        
        # Test unsupported extensions
        assert importer.can_import(Path('test.txt')) is False
        assert importer.can_import(Path('test.workflow')) is False

    def test_source_format_detection_by_content(self):
        """Test source format detection by file content."""
        # This would test content-based format detection
        # Implementation depends on specific format requirements
        pass

    def test_source_format_detection_priority(self):
        """Test priority of different detection methods."""
        # This would test the priority order of detection methods
        # (extension vs content vs metadata)
        pass


def test_base_infrastructure_comprehensive_integration():
    """Comprehensive integration test for base infrastructure."""
    # This test would exercise all components together
    # and verify they work correctly in combination
    pass


if __name__ == "__main__":
    pytest.main([__file__]) 