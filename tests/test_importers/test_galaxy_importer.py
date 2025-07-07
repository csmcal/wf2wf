"""Tests for Galaxy importer functionality."""

import pytest
import json
from pathlib import Path
from wf2wf.importers import galaxy


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
                "inputs": [{"description": "Input dataset", "name": "input_data"}],
                "label": "Input Data",
                "name": "Input dataset",
                "outputs": [{"name": "output", "type": "data"}],
                "position": {"left": 10, "top": 10},
                "tool_id": None,
                "tool_state": '{"optional": false, "tag": ""}',
                "tool_version": None,
                "type": "data_input",
                "uuid": "12345678-1234-1234-1234-123456789abc",
                "workflow_outputs": [],
            },
            "1": {
                "annotation": "Process the data",
                "content_id": "cat1",
                "errors": None,
                "id": 1,
                "input_connections": {"input": {"id": 0, "output_name": "output"}},
                "inputs": [],
                "label": "Concatenate",
                "name": "Concatenate datasets",
                "outputs": [{"name": "out_file1", "type": "input"}],
                "position": {"left": 250, "top": 10},
                "tool_id": "cat1",
                "tool_state": '{"input": {"__class__": "ConnectedValue"}, "queries": []}',
                "tool_version": "1.0.0",
                "type": "tool",
                "uuid": "87654321-4321-4321-4321-210987654321",
                "workflow_outputs": [
                    {
                        "output_name": "out_file1",
                        "label": "concatenated_output",
                        "uuid": "abcdef12-3456-7890-abcd-ef1234567890",
                    }
                ],
            },
        },
        "tags": ["test", "example"],
        "uuid": "workflow-uuid-1234",
        "version": "1.0",
    }

    # Create temporary Galaxy workflow file
    galaxy_file = Path("test_workflow.ga")
    with open(galaxy_file, "w") as f:
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
        if workflow.metadata and workflow.metadata.format_specific:
            assert workflow.metadata.format_specific.get("source_format") == "galaxy"
            assert workflow.metadata.format_specific.get("galaxy_format_version") == "0.1"
            assert workflow.metadata.format_specific.get("galaxy_uuid") == "workflow-uuid-1234"

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
                "workflow_outputs": [],
            },
            "1": {
                "annotation": "Quality control step",
                "content_id": "fastqc",
                "id": 1,
                "input_connections": {"input_file": {"id": 0, "output_name": "output"}},
                "inputs": [],
                "label": "FastQC",
                "name": "FastQC",
                "outputs": [
                    {"name": "html_file", "type": "html"},
                    {"name": "text_file", "type": "txt"},
                ],
                "tool_id": "fastqc",
                "tool_state": '{"input_file": {"__class__": "ConnectedValue"}}',
                "tool_version": "0.72",
                "type": "tool",
                "uuid": "fastqc-uuid-1",
                "workflow_outputs": [],
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
                "tool_state": '{"readtype": {"fastq_in": {"__class__": "ConnectedValue"}}}',
                "tool_version": "0.38.0",
                "type": "tool",
                "uuid": "trimmomatic-uuid-1",
                "workflow_outputs": [],
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
                "tool_state": '{"fastq_input": {"__class__": "ConnectedValue"}}',
                "tool_version": "0.7.17",
                "type": "tool",
                "uuid": "bwa-uuid-1",
                "workflow_outputs": [
                    {
                        "output_name": "bam_output",
                        "label": "final_alignment",
                        "uuid": "final-output-uuid",
                    }
                ],
            },
        },
        "tags": ["genomics", "analysis"],
        "uuid": "analysis-workflow-uuid",
        "version": "2.0",
    }

    # Create temporary Galaxy workflow file
    galaxy_file = Path("test_analysis.ga")
    with open(galaxy_file, "w") as f:
        json.dump(galaxy_workflow, f)

    try:
        # Import the workflow
        workflow = galaxy.to_workflow(galaxy_file, verbose=True)

        # Verify workflow properties
        assert workflow.name == "Analysis Pipeline"
        assert workflow.version == "2.0"
        assert workflow.doc == "Multi-step analysis workflow"

        # Verify inputs
        assert len(workflow.inputs) == 1
        assert workflow.inputs[0].id == "raw_data_0"

        # Verify tasks
        assert len(workflow.tasks) == 4
        task_ids = [t.id for t in workflow.tasks.values()]
        assert "step_1" in task_ids  # FastQC
        assert "step_2" in task_ids  # Trimmomatic
        assert "step_3" in task_ids  # BWA-MEM

        # Verify dependencies
        assert len(workflow.edges) == 3
        edge_pairs = {(e.parent, e.child) for e in workflow.edges}
        expected_edges = {
            ("step_0", "step_1"),  # Raw data -> FastQC
            ("step_0", "step_2"),  # Raw data -> Trimmomatic
            ("step_2", "step_3"),  # Trimmomatic -> BWA-MEM
        }
        assert edge_pairs == expected_edges

        # Verify outputs
        assert len(workflow.outputs) == 1
        assert workflow.outputs[0].id == "final_alignment"

        # Verify metadata preservation
        if workflow.metadata and workflow.metadata.format_specific:
            assert workflow.metadata.format_specific.get("source_format") == "galaxy"
            assert workflow.metadata.format_specific.get("galaxy_format_version") == "0.1"
            assert workflow.metadata.format_specific.get("galaxy_uuid") == "analysis-workflow-uuid"

    finally:
        # Clean up
        if galaxy_file.exists():
            galaxy_file.unlink()


def test_galaxy_importer_error_handling():
    """Test Galaxy importer error handling."""

    # Test with invalid Galaxy workflow
    invalid_workflow = {
        "a_galaxy_workflow": "true",
        "format-version": "0.1",
        "name": "Invalid Workflow",
        # Missing required fields
    }

    galaxy_file = Path("test_invalid.ga")
    with open(galaxy_file, "w") as f:
        json.dump(invalid_workflow, f)

    try:
        # Should handle parsing errors gracefully
        with pytest.raises(Exception):
            galaxy.to_workflow(galaxy_file, verbose=True)
    finally:
        if galaxy_file.exists():
            galaxy_file.unlink()


def test_galaxy_parameter_type_inference():
    """Test Galaxy parameter type inference."""

    galaxy_workflow = {
        "a_galaxy_workflow": "true",
        "format-version": "0.1",
        "name": "Type Test Workflow",
        "steps": {
            "0": {
                "id": 0,
                "input_connections": {},
                "inputs": [{"name": "text_input"}],
                "label": "Text Input",
                "name": "Input dataset",
                "outputs": [{"name": "output", "type": "data"}],
                "tool_id": None,
                "tool_state": "{}",
                "tool_version": None,
                "type": "data_input",
                "workflow_outputs": [],
            }
        },
        "version": "1.0",
    }

    galaxy_file = Path("test_types.ga")
    with open(galaxy_file, "w") as f:
        json.dump(galaxy_workflow, f)

    try:
        workflow = galaxy.to_workflow(galaxy_file, verbose=True)

        # Verify type inference
        assert len(workflow.inputs) == 1
        input_spec = workflow.inputs[0]
        assert input_spec.id == "text_input_0"
        # Should default to File type for Galaxy data inputs
        assert str(input_spec.type) == "File"

    finally:
        if galaxy_file.exists():
            galaxy_file.unlink()


def test_galaxy_workflow_with_provenance():
    """Test Galaxy workflow with provenance information."""

    galaxy_workflow = {
        "a_galaxy_workflow": "true",
        "annotation": "Workflow with provenance",
        "format-version": "0.1",
        "name": "Provenance Test",
        "steps": {
            "0": {
                "id": 0,
                "input_connections": {},
                "inputs": [{"name": "input_data"}],
                "label": "Input",
                "name": "Input dataset",
                "outputs": [{"name": "output", "type": "data"}],
                "tool_id": None,
                "tool_state": "{}",
                "tool_version": None,
                "type": "data_input",
                "workflow_outputs": [],
            }
        },
        "tags": ["provenance", "test"],
        "uuid": "provenance-test-uuid",
        "version": "1.0",
    }

    galaxy_file = Path("test_provenance.ga")
    with open(galaxy_file, "w") as f:
        json.dump(galaxy_workflow, f)

    try:
        workflow = galaxy.to_workflow(galaxy_file, verbose=True)

        # Verify provenance information is preserved
        if workflow.metadata and workflow.metadata.format_specific:
            assert workflow.metadata.format_specific.get("galaxy_uuid") == "provenance-test-uuid"
            assert workflow.metadata.format_specific.get("galaxy_format_version") == "0.1"

        # Verify tags are preserved
        if workflow.metadata and workflow.metadata.format_specific:
            tags = workflow.metadata.format_specific.get("galaxy_tags", [])
            assert "provenance" in tags
            assert "test" in tags

    finally:
        if galaxy_file.exists():
            galaxy_file.unlink()
