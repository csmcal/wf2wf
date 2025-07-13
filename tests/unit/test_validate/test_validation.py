"""
Consolidated validation tests for wf2wf.

This file combines all validation-related tests that were previously scattered
across multiple test files to improve organization and reduce duplication.
"""

import json
import tempfile
from pathlib import Path
import pytest

from wf2wf.core import Workflow, Task, Edge, EnvironmentSpecificValue, ParameterSpec, MetadataSpec
from wf2wf.validate import (
    validate_workflow,
    validate_workflow_enhanced,
    validate_workflow_with_enhanced_checks,
    validate_environment_name,
    validate_resource_value,
    validate_file_path,
    validate_environment_specific_value,
    get_validation_summary,
    validate_bco,
    VALID_ENVIRONMENTS,
    RESOURCE_VALIDATION_RULES,
    FILE_PATH_PATTERNS
)


class TestEnvironmentValidation:
    """Test environment name validation."""

    def test_valid_environments(self):
        """Test that all predefined environments are valid."""
        for env in VALID_ENVIRONMENTS:
            assert validate_environment_name(env), f"Valid environment {env} failed validation"
    
    def test_invalid_environments(self):
        """Test that invalid environment names are rejected."""
        invalid_envs = ["invalid_env", "test", "", "random_name"]
        for env in invalid_envs:
            if env:  # Skip empty string
                assert not validate_environment_name(env), f"Invalid environment {env} passed validation"
    
    def test_environment_constants(self):
        """Test that VALID_ENVIRONMENTS contains expected values."""
        expected_environments = {"shared_filesystem", "distributed_computing", "cloud_native", "hybrid", "local"}
        assert VALID_ENVIRONMENTS == expected_environments, f"Expected {expected_environments}, got {VALID_ENVIRONMENTS}"


class TestResourceValidation:
    """Test resource value validation."""

    def test_valid_resource_values(self):
        """Test that valid resource values pass validation."""
        valid_resources = [
            ("cpu", 4),
            ("mem_mb", 8192),
            ("disk_mb", 10240),
            ("gpu", 2),
            ("gpu_mem_mb", 4096),
            ("time_s", 3600),
            ("threads", 8),
            ("retry_count", 3),
            ("priority", 10)
        ]
        
        for resource_name, value in valid_resources:
            assert validate_resource_value(resource_name, value), f"Valid {resource_name}={value} failed validation"
    
    def test_invalid_resource_values(self):
        """Test that invalid resource values are rejected."""
        invalid_resources = [
            ("cpu", 0),  # Must be >= 1
            ("cpu", -1),  # Must be >= 1
            ("mem_mb", 0),  # Must be >= 1
            ("gpu", -1),  # Must be >= 0
            ("time_s", 0),  # Must be >= 1
            ("threads", 0),  # Must be >= 1
            ("priority", 1001),  # Must be <= 1000
            ("priority", -1001),  # Must be >= -1000
        ]
        
        for resource_name, value in invalid_resources:
            assert not validate_resource_value(resource_name, value), f"Invalid {resource_name}={value} passed validation"
    
    def test_resource_validation_rules(self):
        """Test that RESOURCE_VALIDATION_RULES contains expected values."""
        assert "cpu" in RESOURCE_VALIDATION_RULES, "CPU rules missing"
        assert "mem_mb" in RESOURCE_VALIDATION_RULES, "Memory rules missing"
        assert RESOURCE_VALIDATION_RULES["cpu"]["min"] == 1, "CPU min should be 1"
        assert RESOURCE_VALIDATION_RULES["cpu"]["max"] == 1024, "CPU max should be 1024"


class TestFilePathValidation:
    """Test file path validation."""

    def test_valid_paths(self):
        """Test that valid file paths pass validation."""
        valid_paths = [
            ("/data/input.txt", "unix_path"),
            ("C:\\data\\input.txt", "windows_path"),
            ("https://example.com/file.txt", "url"),
            ("ubuntu:20.04", "docker_image"),
            ("my_env", "conda_env"),
            ("user/repo:tag", "docker_image")
        ]
        
        for path, path_type in valid_paths:
            assert validate_file_path(path, path_type), f"Valid {path_type} path '{path}' failed validation"
    
    def test_invalid_paths(self):
        """Test that invalid file paths are rejected."""
        invalid_paths = [
            ("/data/<invalid>.txt", "unix_path"),  # Invalid characters
            ("invalid://url", "url"),  # Invalid URL format
            ("Invalid:Image", "docker_image"),  # Uppercase letters not allowed
            ("myimage", "docker_image"),  # Missing tag
            ("myimage:tag$", "docker_image"),  # Invalid character in tag
            ("", "conda_env"),  # Empty conda env name
        ]
        
        for path, path_type in invalid_paths:
            assert not validate_file_path(path, path_type), f"Invalid {path_type} path '{path}' passed validation"
    
    def test_file_path_patterns(self):
        """Test that FILE_PATH_PATTERNS contains expected patterns."""
        expected_patterns = ["unix_path", "windows_path", "url", "docker_image", "conda_env"]
        for pattern in expected_patterns:
            assert pattern in FILE_PATH_PATTERNS, f"Missing pattern: {pattern}"


class TestEnvironmentSpecificValueValidation:
    """Test EnvironmentSpecificValue validation."""

    def test_valid_environment_specific_value(self):
        """Test that valid EnvironmentSpecificValue objects pass validation."""
        valid_env_value = {
            "values": [
                {
                    "value": "python script.py",
                    "environments": ["shared_filesystem"]
                }
            ],
            "default_value": None
        }
        
        issues = validate_environment_specific_value(valid_env_value)
        assert not issues, f"Valid EnvironmentSpecificValue failed validation: {issues}"
    
    def test_invalid_environment_specific_value(self):
        """Test that invalid EnvironmentSpecificValue objects are rejected."""
        invalid_env_value = {
            "values": [
                {
                    "value": "python script.py",
                    "environments": ["invalid_env"]  # Invalid environment
                }
            ],
            "default_value": None
        }
        
        issues = validate_environment_specific_value(invalid_env_value)
        assert issues, "Invalid EnvironmentSpecificValue passed validation"
    
    def test_malformed_environment_specific_value(self):
        """Test that malformed EnvironmentSpecificValue objects are rejected."""
        # Missing values field
        malformed_value = {"default_value": None}
        issues = validate_environment_specific_value(malformed_value)
        assert issues, "Malformed EnvironmentSpecificValue passed validation"
        
        # Values not a list
        malformed_value = {"values": "not_a_list", "default_value": None}
        issues = validate_environment_specific_value(malformed_value)
        assert issues, "Malformed EnvironmentSpecificValue passed validation"


class TestWorkflowValidation:
    """Test workflow validation."""

    def test_basic_workflow_validation(self):
        """Test basic workflow validation."""
        # Create a simple workflow
        workflow = Workflow(name="test_workflow")
        
        # Add a task
        task = Task(
            id="test_task",
            command=EnvironmentSpecificValue("echo hello", ["shared_filesystem"]),
            cpu=EnvironmentSpecificValue(1, ["shared_filesystem"])
        )
        workflow.add_task(task)
        
        # Test validation
        try:
            validate_workflow(workflow)
        except Exception as e:
            pytest.fail(f"Basic workflow validation failed: {e}")
    
    def test_enhanced_workflow_validation(self):
        """Test enhanced workflow validation."""
        # Create a valid workflow
        workflow = Workflow(name="test_workflow")
        
        task1 = Task(
            id="prepare_data",
            command=EnvironmentSpecificValue("python prepare.py", ["shared_filesystem"]),
            cpu=EnvironmentSpecificValue(2, ["shared_filesystem"]),
            mem_mb=EnvironmentSpecificValue(4096, ["shared_filesystem"])
        )
        workflow.add_task(task1)
        
        task2 = Task(
            id="analyze_data",
            command=EnvironmentSpecificValue("python analyze.py", ["shared_filesystem"]),
            cpu=EnvironmentSpecificValue(4, ["shared_filesystem"]),
            mem_mb=EnvironmentSpecificValue(8192, ["shared_filesystem"])
        )
        workflow.add_task(task2)
        
        # Add edge
        workflow.add_edge("prepare_data", "analyze_data")
        
        # Test enhanced validation
        issues = validate_workflow_enhanced(workflow)
        assert not issues, f"Enhanced workflow validation failed: {issues}"
    
    def test_comprehensive_workflow_validation(self):
        """Test comprehensive workflow validation."""
        # Create a valid workflow
        workflow = Workflow(name="test_workflow")
        
        task = Task(
            id="test_task",
            command=EnvironmentSpecificValue("python script.py", ["shared_filesystem"]),
            cpu=EnvironmentSpecificValue(2, ["shared_filesystem"])
        )
        workflow.add_task(task)
        
        # Test comprehensive validation
        try:
            validate_workflow_with_enhanced_checks(workflow)
        except Exception as e:
            pytest.fail(f"Comprehensive workflow validation failed: {e}")
    
    def test_validation_summary(self):
        """Test validation summary generation."""
        # Create a valid workflow
        workflow = Workflow(name="test_workflow")
        
        task1 = Task(
            id="prepare_data",
            command=EnvironmentSpecificValue("python prepare.py", ["shared_filesystem"]),
            cpu=EnvironmentSpecificValue(2, ["shared_filesystem"])
        )
        workflow.add_task(task1)
        
        task2 = Task(
            id="analyze_data",
            command=EnvironmentSpecificValue("python analyze.py", ["shared_filesystem"]),
            cpu=EnvironmentSpecificValue(4, ["shared_filesystem"])
        )
        workflow.add_task(task2)
        
        workflow.add_edge("prepare_data", "analyze_data")
        
        # Test validation summary
        summary = get_validation_summary(workflow)
        assert summary["valid"], f"Validation summary shows invalid workflow: {summary['issues']}"
        assert summary["stats"]["task_count"] == 2, f"Expected 2 tasks, got {summary['stats']['task_count']}"
        assert summary["stats"]["edge_count"] == 1, f"Expected 1 edge, got {summary['stats']['edge_count']}"


class TestAdvancedWorkflowValidation:
    """Test advanced workflow validation with all features."""

    def test_advanced_workflow_validation(self):
        """Test advanced workflow validation with all features."""
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
        )
        task.inputs = [input_param]
        task.outputs = [output_param]
        task.command.set_for_environment("python process.py", "shared_filesystem")
        task.script.set_for_environment("scripts/process.py", "shared_filesystem")
        task.cpu.set_for_environment(4, "shared_filesystem")
        task.mem_mb.set_for_environment(8192, "shared_filesystem")
        task.disk_mb.set_for_environment(10240, "shared_filesystem")
        task.gpu.set_for_environment(1, "shared_filesystem")
        task.gpu_mem_mb.set_for_environment(4096, "shared_filesystem")
        task.time_s.set_for_environment(3600, "shared_filesystem")
        task.threads.set_for_environment(8, "shared_filesystem")
        task.conda.set_for_environment("test_env", "shared_filesystem")
        task.container.set_for_environment("docker://python:3.9", "shared_filesystem")
        task.workdir.set_for_environment("/work", "shared_filesystem")
        task.env_vars.set_for_environment({"DATA_DIR": "/data"}, "shared_filesystem")
        task.modules.set_for_environment(["python/3.9"], "shared_filesystem")
        task.retry_count.set_for_environment(3, "shared_filesystem")
        task.retry_delay.set_for_environment(60, "shared_filesystem")
        task.retry_backoff.set_for_environment("exponential", "shared_filesystem")
        task.max_runtime.set_for_environment(7200, "shared_filesystem")
        task.checkpoint_interval.set_for_environment(300, "shared_filesystem")
        task.on_failure.set_for_environment("continue", "shared_filesystem")
        task.failure_notification.set_for_environment("email@example.com", "shared_filesystem")
        task.cleanup_on_failure.set_for_environment(True, "shared_filesystem")
        task.restart_from_checkpoint.set_for_environment(False, "shared_filesystem")
        task.partial_results.set_for_environment(True, "shared_filesystem")
        task.priority.set_for_environment(10, "shared_filesystem")
        task.file_transfer_mode.set_for_environment("auto", "shared_filesystem")
        task.staging_required.set_for_environment(False, "shared_filesystem")
        task.cleanup_after.set_for_environment(True, "shared_filesystem")
        task.cloud_provider.set_for_environment("aws", "shared_filesystem")
        task.cloud_storage_class.set_for_environment("standard", "shared_filesystem")
        task.cloud_encryption.set_for_environment(True, "shared_filesystem")
        task.parallel_transfers.set_for_environment(4, "shared_filesystem")
        task.bandwidth_limit.set_for_environment("100MB/s", "shared_filesystem")
        
        workflow.add_task(task)
        
        # Test validation
        try:
            validate_workflow(workflow)
        except Exception as e:
            pytest.fail(f"Advanced workflow validation failed: {e}")


class TestMetadataValidation:
    """Test metadata validation."""

    def test_metadata_validation(self):
        """Test metadata validation."""
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
        except Exception as e:
            pytest.fail(f"Metadata validation failed: {e}")


class TestJsonSerializationValidation:
    """Test JSON serialization and validation."""

    def test_json_serialization_validation(self):
        """Test JSON serialization and validation."""
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
            
            # Parse back
            parsed_workflow = Workflow.from_json(json_str)
            
            # Validate parsed workflow
            validate_workflow(parsed_workflow)
            
        except Exception as e:
            pytest.fail(f"JSON serialization/validation failed: {e}")


class TestSchemaFileValidation:
    """Test that the schema file itself is valid JSON Schema."""

    def test_schema_file_validation(self):
        """Test that the schema file itself is valid JSON Schema."""
        # Use project-root-relative path
        import os
        repo_root = Path(__file__).parent.parent.parent.parent
        schema_file = repo_root / "wf2wf" / "schemas" / "v0.1" / "wf.json"
        try:
            with open(schema_file, 'r') as f:
                schema = json.load(f)
            # Check required JSON Schema fields
            required_fields = ["$schema", "type", "properties"]
            for field in required_fields:
                if field not in schema:
                    pytest.fail(f"Schema missing required field: {field}")
            # Check that schema has definitions
            assert "definitions" in schema, "Schema missing definitions"
        except Exception as e:
            pytest.fail(f"Schema file validation failed: {e}")


class TestBCOValidation:
    """Test BioCompute Object validation."""

    def test_basic_bco_validation(self):
        """Test basic BCO validation."""
        # Create a minimal valid BCO
        bco = {
            "object_id": "test_bco",
            "spec_version": "https://w3id.org/ieee/ieee-2791-schema/2791object.json",
            "provenance_domain": {
                "name": "Test BCO",
                "version": "1.0.0",
                "created": "2023-01-01T00:00:00Z",
                "modified": "2023-01-01T00:00:00Z",
                "contributors": [
                    {
                        "name": "Test Contributor",
                        "email": "test@example.com",
                        "orcid": "https://orcid.org/0000-0000-0000-0000"
                    }
                ]
            }
        }
        
        # Test validation
        try:
            validate_bco(bco)
        except Exception as e:
            pytest.fail(f"BCO validation failed: {e}")
    
    def test_invalid_bco_validation(self):
        """Test that invalid BCOs are rejected."""
        # Missing required fields
        invalid_bco = {
            "object_id": "test_bco"
            # Missing spec_version and provenance_domain
        }
        
        with pytest.raises(Exception):
            validate_bco(invalid_bco) 