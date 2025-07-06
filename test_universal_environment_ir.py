#!/usr/bin/env python3
"""
Test universal environment-aware IR implementation.
"""

from wf2wf.core import (
    Workflow, Task, EnvironmentSpecificValue, EXECUTION_ENVIRONMENTS,
    EnvironmentAdapter, ParameterSpec
)

def test_environment_specific_values():
    """Test EnvironmentSpecificValue functionality."""
    print("Testing EnvironmentSpecificValue...")
    
    # Create environment-specific values
    esv = EnvironmentSpecificValue()
    esv.set_for_environment(1, "shared_filesystem")
    esv.set_for_environment(4, "distributed_computing")
    esv.set_for_environment(8, "cloud_native")
    
    # Test applicability
    assert esv.is_applicable_to("shared_filesystem")
    assert esv.is_applicable_to("distributed_computing")
    assert esv.is_applicable_to("cloud_native")
    assert not esv.is_applicable_to("edge")
    
    # Test value retrieval
    assert esv.get_value_for("shared_filesystem") == 1
    assert esv.get_value_for("distributed_computing") == 4
    assert esv.get_value_for("cloud_native") == 8
    assert esv.get_value_for("edge") is None
    
    print("✓ EnvironmentSpecificValue tests passed")

def test_universal_task():
    """Test universal environment-aware Task."""
    print("Testing universal Task...")
    
    # Create a task with environment-specific values
    task = Task(id="test_task")
    
    # Set different CPU values for different environments
    task.cpu.set_for_environment(1, "shared_filesystem")
    task.cpu.set_for_environment(4, "distributed_computing")
    task.cpu.set_for_environment(8, "cloud_native")
    
    # Set different memory values
    task.mem_mb.set_for_environment(2048, "shared_filesystem")
    task.mem_mb.set_for_environment(8192, "distributed_computing")
    task.mem_mb.set_for_environment(16384, "cloud_native")
    
    # Set different retry counts
    task.retry_count.set_for_environment(0, "shared_filesystem")
    task.retry_count.set_for_environment(2, "distributed_computing")
    task.retry_count.set_for_environment(3, "cloud_native")
    
    # Debug: Print what values are stored
    print(f"CPU values: {task.cpu.values}")
    print(f"Memory values: {task.mem_mb.values}")
    print(f"Retry values: {task.retry_count.values}")
    
    # Test environment-specific retrieval
    shared_config = task.get_for_environment("shared_filesystem")
    distributed_config = task.get_for_environment("distributed_computing")
    cloud_config = task.get_for_environment("cloud_native")
    
    print(f"Shared config CPU: {shared_config.get('cpu')}")
    print(f"Distributed config CPU: {distributed_config.get('cpu')}")
    print(f"Cloud config CPU: {cloud_config.get('cpu')}")
    
    assert shared_config["cpu"] == 1
    assert shared_config["mem_mb"] == 2048
    assert shared_config["retry_count"] == 0
    
    assert distributed_config["cpu"] == 4
    assert distributed_config["mem_mb"] == 8192
    assert distributed_config["retry_count"] == 2
    
    assert cloud_config["cpu"] == 8
    assert cloud_config["mem_mb"] == 16384
    assert cloud_config["retry_count"] == 3
    
    print("✓ Universal Task tests passed")

def test_universal_workflow():
    """Test universal environment-aware Workflow."""
    print("Testing universal Workflow...")
    
    # Create a workflow
    workflow = Workflow(name="test_workflow")
    
    # Add a task
    task = Task(id="analyze_data")
    task.set_for_environment("cpu", 1, "shared_filesystem")
    task.set_for_environment("cpu", 4, "distributed_computing")
    task.set_for_environment("cpu", 8, "cloud_native")
    
    workflow.add_task(task)
    
    # Test workflow environment adaptation
    shared_workflow = workflow.get_for_environment("shared_filesystem")
    distributed_workflow = workflow.get_for_environment("distributed_computing")
    cloud_workflow = workflow.get_for_environment("cloud_native")
    
    assert shared_workflow["tasks"]["analyze_data"]["cpu"] == 1
    assert distributed_workflow["tasks"]["analyze_data"]["cpu"] == 4
    assert cloud_workflow["tasks"]["analyze_data"]["cpu"] == 8
    
    print("✓ Universal Workflow tests passed")

def test_environment_adapter():
    """Test EnvironmentAdapter functionality."""
    print("Testing EnvironmentAdapter...")
    
    # Create a workflow with minimal configuration
    workflow = Workflow(name="test_workflow")
    task = Task(id="analyze_data")
    workflow.add_task(task)
    
    # Create adapter
    adapter = EnvironmentAdapter(workflow)
    
    # Adapt for distributed computing
    adapted_workflow = adapter.adapt_for_environment("distributed_computing")
    
    # Check that defaults were applied
    adapted_task = adapted_workflow.tasks["analyze_data"]
    distributed_config = adapted_task.get_for_environment("distributed_computing")
    
    # Should have default resource specifications
    assert distributed_config.get("cpu") is not None
    assert distributed_config.get("mem_mb") is not None
    assert distributed_config.get("disk_mb") is not None
    
    # Should have default error handling
    assert distributed_config.get("retry_count") is not None
    
    print("✓ EnvironmentAdapter tests passed")

def test_execution_environments():
    """Test predefined execution environments."""
    print("Testing execution environments...")
    
    # Check that all environments are defined
    expected_envs = ["shared_filesystem", "distributed_computing", "cloud_native", "hybrid", "edge"]
    for env_name in expected_envs:
        assert env_name in EXECUTION_ENVIRONMENTS
        env = EXECUTION_ENVIRONMENTS[env_name]
        assert env.name == env_name
        assert env.display_name is not None
        assert env.description is not None
    
    # Check specific characteristics
    shared = EXECUTION_ENVIRONMENTS["shared_filesystem"]
    assert shared.filesystem_type == "shared"
    assert shared.resource_management == "implicit"
    assert not shared.default_resource_specification
    
    distributed = EXECUTION_ENVIRONMENTS["distributed_computing"]
    assert distributed.filesystem_type == "distributed"
    assert distributed.resource_management == "explicit"
    assert distributed.default_resource_specification
    
    cloud = EXECUTION_ENVIRONMENTS["cloud_native"]
    assert cloud.filesystem_type == "cloud_storage"
    assert cloud.resource_management == "dynamic"
    assert cloud.supports_cloud_storage
    
    print("✓ Execution environments tests passed")

def test_parameter_spec_environment_awareness():
    """Test ParameterSpec environment awareness."""
    print("Testing ParameterSpec environment awareness...")
    
    # Create a parameter with environment-specific transfer modes
    param = ParameterSpec(id="input_file", type="File")
    
    # Set different transfer modes for different environments
    param.transfer_mode.set_for_environment("never", "shared_filesystem")
    param.transfer_mode.set_for_environment("explicit", "distributed_computing")
    param.transfer_mode.set_for_environment("cloud_storage", "cloud_native")
    
    # Test environment-specific retrieval
    assert param.transfer_mode.get_value_for("shared_filesystem") == "never"
    assert param.transfer_mode.get_value_for("distributed_computing") == "explicit"
    assert param.transfer_mode.get_value_for("cloud_native") == "cloud_storage"
    
    print("✓ ParameterSpec environment awareness tests passed")

def main():
    """Run all tests."""
    print("Testing Universal Environment-Aware IR Implementation")
    print("=" * 60)
    
    test_environment_specific_values()
    test_universal_task()
    test_universal_workflow()
    test_environment_adapter()
    test_execution_environments()
    test_parameter_spec_environment_awareness()
    
    print("\n" + "=" * 60)
    print("All tests passed! Universal environment-aware IR is working correctly.")
    
    # Demonstrate the power of the universal approach
    print("\nDemonstration:")
    print("-" * 30)
    
    # Create a single workflow that works for all environments
    workflow = Workflow(name="universal_workflow")
    
    task = Task(id="data_analysis")
    
    # Set environment-specific configurations
    task.set_for_environment("cpu", 1, "shared_filesystem")
    task.set_for_environment("cpu", 4, "distributed_computing")
    task.set_for_environment("cpu", 8, "cloud_native")
    
    task.set_for_environment("mem_mb", 2048, "shared_filesystem")
    task.set_for_environment("mem_mb", 8192, "distributed_computing")
    task.set_for_environment("mem_mb", 16384, "cloud_native")
    
    task.set_for_environment("retry_count", 0, "shared_filesystem")
    task.set_for_environment("retry_count", 2, "distributed_computing")
    task.set_for_environment("retry_count", 3, "cloud_native")
    
    task.set_for_environment("container", None, "shared_filesystem")
    task.set_for_environment("container", "analysis:latest", "distributed_computing")
    task.set_for_environment("container", "gcr.io/project/analysis:latest", "cloud_native")
    
    workflow.add_task(task)
    
    print("Single workflow configuration for all environments:")
    for env_name in ["shared_filesystem", "distributed_computing", "cloud_native"]:
        config = task.get_for_environment(env_name)
        print(f"  {env_name}:")
        print(f"    CPU: {config['cpu']}")
        print(f"    Memory: {config['mem_mb']} MB")
        print(f"    Retries: {config['retry_count']}")
        print(f"    Container: {config.get('container', 'None')}")
        print()

if __name__ == "__main__":
    main() 