#!/usr/bin/env python3
"""
Example demonstrating multi-environment IR capabilities.

This example shows how a single IR can simultaneously represent a workflow
for different execution environments, preserving environment-specific information.
"""

from wf2wf.core import (
    Workflow, Task, ParameterSpec, MultiEnvironmentResourceSpec,
    MultiEnvironmentFileTransferSpec, MultiEnvironmentErrorHandlingSpec,
    EnvironmentSpecificValue, EXECUTION_ENVIRONMENTS
)
from wf2wf.environment_adaptation import adapt_workflow_for_environment


def create_multi_environment_workflow() -> Workflow:
    """Create a workflow that has different specifications for different environments."""
    
    # Create a task with multi-environment resource specifications
    multi_env_resources = MultiEnvironmentResourceSpec()
    
    # Shared filesystem: minimal resources (rely on system defaults)
    multi_env_resources.add_for_environment(
        "cpu", 1, "shared_filesystem", source_method="default", confidence=0.8
    )
    multi_env_resources.add_for_environment(
        "mem_mb", 2048, "shared_filesystem", source_method="default", confidence=0.8
    )
    
    # Distributed computing: explicit resources
    multi_env_resources.add_for_environment(
        "cpu", 4, "distributed_computing", source_method="explicit", confidence=1.0
    )
    multi_env_resources.add_for_environment(
        "mem_mb", 8192, "distributed_computing", source_method="explicit", confidence=1.0
    )
    multi_env_resources.add_for_environment(
        "disk_mb", 10240, "distributed_computing", source_method="explicit", confidence=1.0
    )
    
    # Cloud native: cloud-optimized resources
    multi_env_resources.add_for_environment(
        "cpu", 2, "cloud_native", source_method="explicit", confidence=1.0
    )
    multi_env_resources.add_for_environment(
        "mem_mb", 4096, "cloud_native", source_method="explicit", confidence=1.0
    )
    
    # Create multi-environment file transfer specifications
    multi_env_file_transfer = MultiEnvironmentFileTransferSpec()
    
    # Shared filesystem: no transfer needed
    multi_env_file_transfer.add_for_environment(
        "mode", "never", "shared_filesystem", source_method="explicit", confidence=1.0
    )
    
    # Distributed computing: manual transfer
    multi_env_file_transfer.add_for_environment(
        "mode", "always", "distributed_computing", source_method="explicit", confidence=1.0
    )
    multi_env_file_transfer.add_for_environment(
        "transfer_method", "scp", "distributed_computing", source_method="explicit", confidence=1.0
    )
    multi_env_file_transfer.add_for_environment(
        "staging_required", True, "distributed_computing", source_method="explicit", confidence=1.0
    )
    
    # Cloud native: cloud storage
    multi_env_file_transfer.add_for_environment(
        "mode", "cloud_storage", "cloud_native", source_method="explicit", confidence=1.0
    )
    multi_env_file_transfer.add_for_environment(
        "cloud_provider", "aws", "cloud_native", source_method="explicit", confidence=1.0
    )
    
    # Create multi-environment error handling specifications
    multi_env_error_handling = MultiEnvironmentErrorHandlingSpec()
    
    # Shared filesystem: basic error handling
    multi_env_error_handling.add_for_environment(
        "retry_count", 1, "shared_filesystem", source_method="default", confidence=0.8
    )
    
    # Distributed computing: robust error handling
    multi_env_error_handling.add_for_environment(
        "retry_count", 3, "distributed_computing", source_method="explicit", confidence=1.0
    )
    multi_env_error_handling.add_for_environment(
        "retry_backoff", "exponential", "distributed_computing", source_method="explicit", confidence=1.0
    )
    multi_env_error_handling.add_for_environment(
        "checkpoint_interval", 300, "distributed_computing", source_method="explicit", confidence=1.0
    )
    
    # Cloud native: cloud-optimized error handling
    multi_env_error_handling.add_for_environment(
        "retry_count", 2, "cloud_native", source_method="explicit", confidence=1.0
    )
    multi_env_error_handling.add_for_environment(
        "on_failure", "notify", "cloud_native", source_method="explicit", confidence=1.0
    )
    
    # Create the task
    task = Task(
        id="analyze_data",
        command="python analyze.py {input} {output}",
        multi_env_resources=multi_env_resources,
        multi_env_error_handling=multi_env_error_handling
    )
    
    # Add parameters with multi-environment file transfer specs
    input_param = ParameterSpec(
        id="input_file",
        type="File",
        multi_env_file_transfer=multi_env_file_transfer
    )
    output_param = ParameterSpec(
        id="output_file", 
        type="File",
        multi_env_file_transfer=multi_env_file_transfer
    )
    
    task.inputs = [input_param]
    task.outputs = [output_param]
    
    # Create the workflow
    workflow = Workflow(
        name="multi_environment_example",
        version="1.0"
    )
    workflow.add_task(task)
    
    return workflow


def demonstrate_environment_adaptation():
    """Demonstrate how the workflow adapts to different environments."""
    
    print("=== Multi-Environment IR Example ===\n")
    
    # Create the multi-environment workflow
    workflow = create_multi_environment_workflow()
    print(f"Created workflow: {workflow.name} v{workflow.version}")
    print(f"Task: {list(workflow.tasks.keys())[0]}")
    print()
    
    # Demonstrate adaptation for different environments
    environments = ["shared_filesystem", "distributed_computing", "cloud_native"]
    
    for env in environments:
        print(f"--- Adaptation for {env} ---")
        
        # Adapt the workflow for this environment
        adaptation = adapt_workflow_for_environment(workflow, env)
        
        # Show the adapted task
        task = adaptation.adapted_workflow.tasks["analyze_data"]
        cpu = task.cpu.get_value_for(env) if hasattr(task, "cpu") else None
        mem = task.mem_mb.get_value_for(env) if hasattr(task, "mem_mb") else None
        print(f"Resources: CPU={cpu}, Memory={mem}MB")
        print(f"File Transfer: {task.inputs[0].file_transfer.mode}")
        print(f"Error Handling: {task.error_handling.retry_count} retries")
        
        if adaptation.changes_made:
            print(f"Changes made: {len(adaptation.changes_made)}")
        if adaptation.warnings:
            print(f"Warnings: {len(adaptation.warnings)}")
        if adaptation.recommendations:
            print(f"Recommendations: {len(adaptation.recommendations)}")
        
        print()


def demonstrate_environment_comparison():
    """Demonstrate environment comparison capabilities."""
    
    print("=== Environment Comparison ===\n")
    
    from wf2wf.environment_adaptation import compare_environments
    
    # Compare shared filesystem vs distributed computing
    differences = compare_environments("shared_filesystem", "distributed_computing")
    
    print("Differences between shared_filesystem and distributed_computing:")
    for key, (val1, val2) in differences.items():
        print(f"  {key}: {val1} -> {val2}")
    
    print()


def demonstrate_multi_environment_access():
    """Demonstrate how to access environment-specific values directly."""
    
    print("=== Direct Multi-Environment Access ===\n")
    
    workflow = create_multi_environment_workflow()
    task = workflow.tasks["analyze_data"]
    
    # Access environment-specific resource values
    print("Resource specifications by environment:")
    for env in ["shared_filesystem", "distributed_computing", "cloud_native"]:
        cpu = task.cpu.get_value_for(env) if hasattr(task, "cpu") else None
        mem = task.mem_mb.get_value_for(env) if hasattr(task, "mem_mb") else None
        print(f"  {env}: CPU={cpu}, Memory={mem}MB")
    
    print()
    
    # Access environment-specific file transfer values
    print("File transfer specifications by environment:")
    for env in ["shared_filesystem", "distributed_computing", "cloud_native"]:
        transfer = task.inputs[0].multi_env_file_transfer.get_for_environment(env)
        print(f"  {env}: mode={transfer.mode}, method={transfer.transfer_method}")
    
    print()


if __name__ == "__main__":
    demonstrate_environment_adaptation()
    demonstrate_environment_comparison()
    demonstrate_multi_environment_access() 