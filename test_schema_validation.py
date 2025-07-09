#!/usr/bin/env python3
"""Test script to validate the current schema against the core implementation."""

import json
import tempfile
from pathlib import Path
from wf2wf.core import Workflow, Task, Edge, EnvironmentSpecificValue, ParameterSpec, MetadataSpec
from wf2wf.validate import validate_workflow

def test_basic_workflow_validation():
    """Test basic workflow validation."""
    print("Testing basic workflow validation...")
    
    # Create a simple workflow
    workflow = Workflow(name="test_workflow")
    
    # Add a task
    task = Task(
        id="test_task",
        command=EnvironmentSpecificValue("echo hello", ["shared_filesystem"]),
        cpu=EnvironmentSpecificValue(1, ["shared_filesystem"])
    )
    workflow.add_task(task)
    
    # Add an edge (self-reference to test edge validation)
    workflow.add_edge("test_task", "test_task")
    
    # Test validation
    try:
        validate_workflow(workflow)
        print("✓ Basic workflow validation passed")
    except Exception as e:
        print(f"✗ Basic workflow validation failed: {e}")
        return False
    
    return True

def test_advanced_workflow_validation():
    """Test advanced workflow validation with all features."""
    print("Testing advanced workflow validation...")
    
    # Create input/output parameters
    input_param = ParameterSpec(id="input.txt", type="File")
    output_param = ParameterSpec(id="output.txt", type="File")
    
    # Create a workflow with advanced features
    workflow = Workflow(
        name="advanced_workflow",
        version="2.0",
        label="Advanced Test Workflow",
        doc="A workflow with advanced features for testing"
    )
    
    # Add a task with advanced features
    task = Task(
        id="advanced_task",
        label="Advanced Task",
        doc="A task with advanced features",
        inputs=[input_param],
        outputs=[output_param],
        command=EnvironmentSpecificValue("python process.py", ["shared_filesystem"]),
        script=EnvironmentSpecificValue("scripts/process.py", ["shared_filesystem"]),
        cpu=EnvironmentSpecificValue(4, ["shared_filesystem"]),
        mem_mb=EnvironmentSpecificValue(8192, ["shared_filesystem"]),
        disk_mb=EnvironmentSpecificValue(10240, ["shared_filesystem"]),
        gpu=EnvironmentSpecificValue(1, ["shared_filesystem"]),
        gpu_mem_mb=EnvironmentSpecificValue(4096, ["shared_filesystem"]),
        time_s=EnvironmentSpecificValue(3600, ["shared_filesystem"]),
        threads=EnvironmentSpecificValue(8, ["shared_filesystem"]),
        conda=EnvironmentSpecificValue("test_env", ["shared_filesystem"]),
        container=EnvironmentSpecificValue("docker://python:3.9", ["shared_filesystem"]),
        workdir=EnvironmentSpecificValue("/work", ["shared_filesystem"]),
        env_vars=EnvironmentSpecificValue({"DATA_DIR": "/data"}, ["shared_filesystem"]),
        modules=EnvironmentSpecificValue(["python/3.9"], ["shared_filesystem"]),
        retry_count=EnvironmentSpecificValue(3, ["shared_filesystem"]),
        retry_delay=EnvironmentSpecificValue(60, ["shared_filesystem"]),
        retry_backoff=EnvironmentSpecificValue("exponential", ["shared_filesystem"]),
        max_runtime=EnvironmentSpecificValue(7200, ["shared_filesystem"]),
        checkpoint_interval=EnvironmentSpecificValue(300, ["shared_filesystem"]),
        on_failure=EnvironmentSpecificValue("continue", ["shared_filesystem"]),
        failure_notification=EnvironmentSpecificValue("email@example.com", ["shared_filesystem"]),
        cleanup_on_failure=EnvironmentSpecificValue(True, ["shared_filesystem"]),
        restart_from_checkpoint=EnvironmentSpecificValue(False, ["shared_filesystem"]),
        partial_results=EnvironmentSpecificValue(True, ["shared_filesystem"]),
        priority=EnvironmentSpecificValue(10, ["shared_filesystem"]),
        file_transfer_mode=EnvironmentSpecificValue("auto", ["shared_filesystem"]),
        staging_required=EnvironmentSpecificValue(False, ["shared_filesystem"]),
        cleanup_after=EnvironmentSpecificValue(True, ["shared_filesystem"]),
        cloud_provider=EnvironmentSpecificValue("aws", ["shared_filesystem"]),
        cloud_storage_class=EnvironmentSpecificValue("standard", ["shared_filesystem"]),
        cloud_encryption=EnvironmentSpecificValue(True, ["shared_filesystem"]),
        parallel_transfers=EnvironmentSpecificValue(4, ["shared_filesystem"]),
        bandwidth_limit=EnvironmentSpecificValue("100MB/s", ["shared_filesystem"])
    )
    
    workflow.add_task(task)
    
    # Test validation
    try:
        validate_workflow(workflow)
        print("✓ Advanced workflow validation passed")
    except Exception as e:
        print(f"✗ Advanced workflow validation failed: {e}")
        return False
    
    return True

def test_metadata_validation():
    """Test metadata validation."""
    print("Testing metadata validation...")
    
    # Create a workflow with metadata
    workflow = Workflow(name="metadata_workflow")
    
    # Add metadata
    metadata = MetadataSpec(
        source_format="snakemake",
        source_file="workflow.smk",
        source_version="1.0",
        parsing_notes=["Test note"],
        conversion_warnings=["Test warning"],
        format_specific={"snakemake_config": {"threads": 4}},
        uninterpreted={"unknown_field": "value"},
        annotations={"user_note": "Test annotation"},
        environment_metadata={"shared_filesystem": {"optimized": True}},
        validation_errors=[],
        quality_metrics={"completeness": 0.95}
    )
    
    workflow.metadata = metadata
    
    # Add a task
    task = Task(id="test_task")
    workflow.add_task(task)
    
    # Test validation
    try:
        validate_workflow(workflow)
        print("✓ Metadata validation passed")
    except Exception as e:
        print(f"✗ Metadata validation failed: {e}")
        return False
    
    return True

def test_json_serialization_validation():
    """Test JSON serialization and validation."""
    print("Testing JSON serialization and validation...")
    
    # Create a workflow
    workflow = Workflow(name="json_test_workflow")
    
    # Add a task
    task = Task(
        id="json_task",
        command=EnvironmentSpecificValue("echo test", ["shared_filesystem"])
    )
    workflow.add_task(task)
    
    # Serialize to JSON
    try:
        json_str = workflow.to_json()
        print(f"✓ JSON serialization successful (length: {len(json_str)})")
        
        # Parse back
        parsed_workflow = Workflow.from_json(json_str)
        print("✓ JSON deserialization successful")
        
        # Validate parsed workflow
        validate_workflow(parsed_workflow)
        print("✓ Parsed workflow validation passed")
        
    except Exception as e:
        print(f"✗ JSON serialization/validation failed: {e}")
        return False
    
    return True

def test_schema_file_validation():
    """Test that the schema file itself is valid JSON Schema."""
    print("Testing schema file validation...")
    
    schema_file = Path(__file__).parent / "wf2wf" / "schemas" / "v0.1" / "wf.json"
    
    try:
        with open(schema_file, 'r') as f:
            schema = json.load(f)
        
        # Check required JSON Schema fields
        required_fields = ["$schema", "type", "properties"]
        for field in required_fields:
            if field not in schema:
                print(f"✗ Schema missing required field: {field}")
                return False
        
        print("✓ Schema file is valid JSON")
        print(f"✓ Schema has {len(schema.get('definitions', {}))} definitions")
        
    except Exception as e:
        print(f"✗ Schema file validation failed: {e}")
        return False
    
    return True

def main():
    """Run all validation tests."""
    print("Running schema validation tests...\n")
    
    tests = [
        test_schema_file_validation,
        test_basic_workflow_validation,
        test_advanced_workflow_validation,
        test_metadata_validation,
        test_json_serialization_validation
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            print()
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with exception: {e}")
            print()
    
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ All validation tests passed!")
        return True
    else:
        print("✗ Some validation tests failed!")
        return False

if __name__ == "__main__":
    main() 