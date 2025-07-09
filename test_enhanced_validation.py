#!/usr/bin/env python3
"""Test script for enhanced validation functions."""

import tempfile
from pathlib import Path
from wf2wf.core import Workflow, Task, Edge, EnvironmentSpecificValue, ParameterSpec
from wf2wf.validate import (
    validate_workflow,
    validate_workflow_enhanced,
    validate_workflow_with_enhanced_checks,
    validate_environment_name,
    validate_resource_value,
    validate_file_path,
    validate_environment_specific_value,
    get_validation_summary,
    VALID_ENVIRONMENTS,
    RESOURCE_VALIDATION_RULES,
    FILE_PATH_PATTERNS
)

def test_environment_validation():
    """Test environment name validation."""
    print("Testing environment name validation...")
    
    # Test valid environments
    for env in VALID_ENVIRONMENTS:
        assert validate_environment_name(env), f"Valid environment {env} failed validation"
    
    # Test invalid environments
    invalid_envs = ["invalid_env", "test", "", None]
    for env in invalid_envs:
        if env is not None:
            assert not validate_environment_name(env), f"Invalid environment {env} passed validation"
    
    print("✓ Environment validation tests passed")

def test_resource_validation():
    """Test resource value validation."""
    print("Testing resource value validation...")
    
    # Test valid resource values
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
    
    # Test invalid resource values
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
    
    print("✓ Resource validation tests passed")

def test_file_path_validation():
    """Test file path validation."""
    print("Testing file path validation...")
    
    # Test valid paths
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
    
    # Test invalid paths
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
    
    print("✓ File path validation tests passed")

def test_environment_specific_value_validation():
    """Test EnvironmentSpecificValue validation."""
    print("Testing EnvironmentSpecificValue validation...")
    
    # Test valid EnvironmentSpecificValue
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
    
    # Test invalid EnvironmentSpecificValue
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
    
    print("✓ EnvironmentSpecificValue validation tests passed")

def test_workflow_validation():
    """Test workflow validation."""
    print("Testing workflow validation...")
    
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
    
    # Test basic validation
    try:
        validate_workflow(workflow)
        print("✓ Basic workflow validation passed")
    except Exception as e:
        assert False, f"Basic workflow validation failed: {e}"
    
    # Test enhanced validation
    issues = validate_workflow_enhanced(workflow)
    assert not issues, f"Enhanced workflow validation failed: {issues}"
    print("✓ Enhanced workflow validation passed")
    
    # Test comprehensive validation
    try:
        validate_workflow_with_enhanced_checks(workflow)
        print("✓ Comprehensive workflow validation passed")
    except Exception as e:
        assert False, f"Comprehensive workflow validation failed: {e}"
    
    # Test validation summary
    summary = get_validation_summary(workflow)
    assert summary["valid"], f"Validation summary shows invalid workflow: {summary['issues']}"
    assert summary["stats"]["task_count"] == 2, f"Expected 2 tasks, got {summary['stats']['task_count']}"
    assert summary["stats"]["edge_count"] == 1, f"Expected 1 edge, got {summary['stats']['edge_count']}"
    print("✓ Validation summary test passed")

def test_validation_constants():
    """Test validation constants."""
    print("Testing validation constants...")
    
    # Test VALID_ENVIRONMENTS
    expected_environments = {"shared_filesystem", "distributed_computing", "cloud_native", "hybrid", "local"}
    assert VALID_ENVIRONMENTS == expected_environments, f"Expected {expected_environments}, got {VALID_ENVIRONMENTS}"
    
    # Test RESOURCE_VALIDATION_RULES
    assert "cpu" in RESOURCE_VALIDATION_RULES, "CPU rules missing"
    assert "mem_mb" in RESOURCE_VALIDATION_RULES, "Memory rules missing"
    assert RESOURCE_VALIDATION_RULES["cpu"]["min"] == 1, "CPU min should be 1"
    assert RESOURCE_VALIDATION_RULES["cpu"]["max"] == 1024, "CPU max should be 1024"
    
    # Test FILE_PATH_PATTERNS
    expected_patterns = ["unix_path", "windows_path", "url", "docker_image", "conda_env"]
    for pattern in expected_patterns:
        assert pattern in FILE_PATH_PATTERNS, f"Missing pattern: {pattern}"
    
    print("✓ Validation constants tests passed")

def main():
    """Run all validation tests."""
    print("Running enhanced validation tests...\n")
    
    test_validation_constants()
    test_environment_validation()
    test_resource_validation()
    test_file_path_validation()
    test_environment_specific_value_validation()
    test_workflow_validation()
    
    print("\n🎉 All enhanced validation tests passed!")

if __name__ == "__main__":
    main() 