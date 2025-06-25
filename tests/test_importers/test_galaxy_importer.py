"""Tests for Galaxy importer functionality."""

import pytest
import json
from pathlib import Path
from wf2wf.importers import galaxy
from wf2wf.core import Workflow, Task


def test_galaxy_importer_basic_workflow():
    """Test importing a basic Galaxy workflow."""
    
    galaxy_workflow = {
        "a_galaxy_workflow": "true",
        "annotation": "A simple test workflow",
        "format-version": "0.1",
        "name": "Test Workflow",
        "steps": {
            "0": {
                "annotation": "Input data",
                "content_id": None,
                "errors": None,
                "id": 0,
                "input_connections": {},
                "inputs": [
                    {
                        "description": "Input dataset",
                        "name": "input_data"
                    }
                ],
                "label": "Input Data",
                "name": "Input dataset",
                "outputs": [
                    {
                        "name": "output",
                        "type": "data"
                    }
                ],
                "position": {
                    "left": 10,
                    "top": 10
                },
                "tool_id": None,
                "tool_state": "{\"optional\": false, \"tag\": \"\"}",
                "tool_version": None,
                "type": "data_input",
                "uuid": "12345678-1234-1234-1234-123456789abc",
                "workflow_outputs": []
            },
            "1": {
                "annotation": "Process the data",
                "content_id": "cat1",
                "errors": None,
                "id": 1,
                "input_connections": {
                    "input": {
                        "id": 0,
                        "output_name": "output"
                    }
                },
                "inputs": [],
                "label": "Concatenate",
                "name": "Concatenate datasets",
                "outputs": [
                    {
                        "name": "out_file1",
                        "type": "input"
                    }
                ],
                "position": {
                    "left": 250,
                    "top": 10
                },
                "tool_id": "cat1",
                "tool_state": "{\"input\": {\"__class__\": \"ConnectedValue\"}, \"queries\": []}",
                "tool_version": "1.0.0",
                "type": "tool",
                "uuid": "87654321-4321-4321-4321-210987654321",
                "workflow_outputs": [
                    {
                        "output_name": "out_file1",
                        "label": "concatenated_output",
                        "uuid": "abcdef12-3456-7890-abcd-ef1234567890"
                    }
                ]
            }
        },
        "tags": ["test", "example"],
        "uuid": "workflow-uuid-1234",
        "version": "1.0"
    }
    
    # Create temporary Galaxy workflow file
    galaxy_file = Path("test_workflow.ga")
    with open(galaxy_file, 'w') as f:
        json.dump(galaxy_workflow, f)
    
    try:
        # Import the workflow
        workflow = galaxy.to_workflow(galaxy_file, verbose=True)
        
        # Verify workflow properties
        assert workflow.name == "Test Workflow"
        assert workflow.version == "1.0"
        assert workflow.doc == "A simple test workflow"
        
        # Verify inputs
        assert len(workflow.inputs) == 1
        assert workflow.inputs[0].id == "input_0"
        assert workflow.inputs[0].type == "File"
        
        # Verify tasks
        assert len(workflow.tasks) == 2
        task_ids = [t.id for t in workflow.tasks.values()]
        assert "step_1" in task_ids  # tool step
        task = next(t for t in workflow.tasks.values() if t.id == "step_1")
        assert task.label == "Concatenate"
        
        # Verify outputs
        assert len(workflow.outputs) == 1
        assert workflow.outputs[0].id == "concatenated_output"
        
        # Verify metadata preservation
        assert workflow.meta['source_format'] == 'galaxy'
        assert workflow.meta['galaxy_format_version'] == '0.1'
        assert workflow.meta['galaxy_uuid'] == 'workflow-uuid-1234'
        
    finally:
        # Clean up
        if galaxy_file.exists():
            galaxy_file.unlink()


def test_galaxy_importer_multiple_steps():
    """Test importing a Galaxy workflow with multiple steps and dependencies."""
    
    galaxy_workflow = {
        "a_galaxy_workflow": "true",
        "annotation": "Multi-step analysis workflow",
        "format-version": "0.1",
        "name": "Analysis Pipeline",
        "steps": {
            "0": {
                "annotation": "Raw data input",
                "content_id": None,
                "id": 0,
                "input_connections": {},
                "inputs": [{"description": "Raw data", "name": "raw_data"}],
                "label": "Raw Data",
                "name": "Input dataset",
                "outputs": [{"name": "output", "type": "data"}],
                "tool_id": None,
                "tool_state": "{}",
                "tool_version": None,
                "type": "data_input",
                "uuid": "input-uuid-1",
                "workflow_outputs": []
            },
            "1": {
                "annotation": "Quality control step",
                "content_id": "fastqc",
                "id": 1,
                "input_connections": {
                    "input_file": {"id": 0, "output_name": "output"}
                },
                "inputs": [],
                "label": "FastQC",
                "name": "FastQC",
                "outputs": [
                    {"name": "html_file", "type": "html"},
                    {"name": "text_file", "type": "txt"}
                ],
                "tool_id": "fastqc",
                "tool_state": "{\"input_file\": {\"__class__\": \"ConnectedValue\"}}",
                "tool_version": "0.72",
                "type": "tool",
                "uuid": "fastqc-uuid-1",
                "workflow_outputs": []
            },
            "2": {
                "annotation": "Trimming step",
                "content_id": "trimmomatic",
                "id": 2,
                "input_connections": {
                    "readtype|fastq_in": {"id": 0, "output_name": "output"}
                },
                "inputs": [],
                "label": "Trimmomatic",
                "name": "Trimmomatic",
                "outputs": [{"name": "fastq_out", "type": "fastqsanger"}],
                "tool_id": "trimmomatic",
                "tool_state": "{\"readtype\": {\"fastq_in\": {\"__class__\": \"ConnectedValue\"}}}",
                "tool_version": "0.38.0",
                "type": "tool",
                "uuid": "trimmomatic-uuid-1",
                "workflow_outputs": []
            },
            "3": {
                "annotation": "Final analysis",
                "content_id": "bwa_mem",
                "id": 3,
                "input_connections": {
                    "fastq_input": {"id": 2, "output_name": "fastq_out"}
                },
                "inputs": [],
                "label": "BWA-MEM",
                "name": "Map with BWA-MEM",
                "outputs": [{"name": "bam_output", "type": "bam"}],
                "tool_id": "bwa_mem",
                "tool_state": "{\"fastq_input\": {\"__class__\": \"ConnectedValue\"}}",
                "tool_version": "0.7.17",
                "type": "tool",
                "uuid": "bwa-uuid-1",
                "workflow_outputs": [
                    {
                        "output_name": "bam_output",
                        "label": "final_alignment",
                        "uuid": "final-output-uuid"
                    }
                ]
            }
        },
        "tags": ["genomics", "analysis"],
        "uuid": "analysis-workflow-uuid",
        "version": "2.0"
    }
    
    # Create temporary Galaxy workflow file
    galaxy_file = Path("test_analysis.ga")
    with open(galaxy_file, 'w') as f:
        json.dump(galaxy_workflow, f)
    
    try:
        # Import the workflow
        workflow = galaxy.to_workflow(galaxy_file, verbose=True)
        
        # Verify workflow properties
        assert workflow.name == "Analysis Pipeline"
        assert workflow.version == "2.0"
        
        # Verify inputs
        assert len(workflow.inputs) == 1
        assert workflow.inputs[0].id == "input_0"
        
        # Verify tasks (includes placeholder for data input)
        assert len(workflow.tasks) == 4
        task_ids = [t.id for t in workflow.tasks.values()]
        assert "step_1" in task_ids  # FastQC
        assert "step_2" in task_ids  # Trimmomatic
        assert "step_3" in task_ids  # BWA-MEM
        
        # Verify dependencies (edges)
        assert len(workflow.edges) >= 3  # includes placeholder data_input dependencies
        
        # Verify outputs
        assert len(workflow.outputs) == 1
        assert workflow.outputs[0].id == "final_alignment"
        
    finally:
        # Clean up
        if galaxy_file.exists():
            galaxy_file.unlink()


def test_galaxy_importer_error_handling():
    """Test error handling for invalid Galaxy files."""
    
    # Test with non-existent file
    with pytest.raises(FileNotFoundError):
        galaxy.to_workflow("nonexistent.ga")
    
    # Test with invalid JSON content
    invalid_galaxy = Path("invalid.ga")
    invalid_galaxy.write_text("this is not valid JSON")
    
    try:
        with pytest.raises(RuntimeError):
            galaxy.to_workflow(invalid_galaxy)
    finally:
        if invalid_galaxy.exists():
            invalid_galaxy.unlink()
    
    # Test with valid JSON but invalid Galaxy format
    invalid_format = Path("invalid_format.ga")
    with open(invalid_format, 'w') as f:
        json.dump({"not": "a galaxy workflow"}, f)
    
    try:
        # This should still work but create an empty workflow
        workflow = galaxy.to_workflow(invalid_format)
        assert workflow.name == "invalid_format"
        assert len(workflow.tasks) == 0
    finally:
        if invalid_format.exists():
            invalid_format.unlink()


def test_galaxy_parameter_type_inference():
    """Test Galaxy parameter type inference."""
    
    from wf2wf.importers.galaxy import _infer_galaxy_parameter_type
    
    # Basic types
    assert _infer_galaxy_parameter_type("string value") == "string"
    assert _infer_galaxy_parameter_type(42) == "int"
    assert _infer_galaxy_parameter_type(3.14) == "float"
    assert _infer_galaxy_parameter_type(True) == "boolean"
    assert _infer_galaxy_parameter_type(False) == "boolean"
    
    # Complex types
    assert _infer_galaxy_parameter_type(["item1", "item2"]) == "array<string>"
    assert _infer_galaxy_parameter_type({"src": "hda", "id": "123"}) == "File"
    assert _infer_galaxy_parameter_type({"key": "value"}) == "string"


def test_galaxy_workflow_with_provenance():
    """Test Galaxy workflow with creator and license information."""
    
    galaxy_workflow = {
        "a_galaxy_workflow": "true",
        "annotation": "Test workflow with provenance",
        "creator": ["Dr. Test", "Lab Assistant"],
        "license": "MIT",
        "format-version": "0.1",
        "name": "Provenance Test",
        "steps": {},
        "tags": ["test", "provenance"],
        "uuid": "provenance-test-uuid",
        "version": "1.0"
    }
    
    # Create temporary Galaxy workflow file
    galaxy_file = Path("test_provenance.ga")
    with open(galaxy_file, 'w') as f:
        json.dump(galaxy_workflow, f)
    
    try:
        # Import the workflow
        workflow = galaxy.to_workflow(galaxy_file, verbose=True)
        
        # Verify provenance information
        assert workflow.provenance is not None
        assert len(workflow.provenance.authors) == 2
        assert workflow.provenance.authors[0]['name'] == "Dr. Test"
        assert workflow.provenance.authors[1]['name'] == "Lab Assistant"
        assert workflow.provenance.license == "MIT"
        assert workflow.provenance.version == "1.0"
        
    finally:
        # Clean up
        if galaxy_file.exists():
            galaxy_file.unlink() 