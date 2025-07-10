#!/usr/bin/env python3
"""Test script demonstrating the new MetadataSpec functionality."""

from wf2wf.core import Task, Workflow, MetadataSpec, EnvironmentSpecificValue

def test_metadata_spec():
    """Demonstrate how MetadataSpec preserves uninterpreted information."""
    
    # Create a workflow with metadata
    workflow = Workflow(
        name="test_workflow",
        version="1.0"
    )
    
    # Create metadata to store uninterpreted information
    metadata = MetadataSpec(
        source_format="snakemake",
        source_file="workflow.smk",
        source_version="7.0"
    )
    
    # Add format-specific data that couldn't be mapped to IR fields
    metadata.add_format_specific("snakemake_config", {
        "cores": 8,
        "memory": "16G",
        "cluster_config": {
            "queue": "long",
            "account": "bioinformatics"
        }
    })
    
    # Add uninterpreted fields from source
    metadata.add_uninterpreted("unknown_field_1", "some_value")
    metadata.add_uninterpreted("custom_annotation", {
        "priority": "high",
        "tags": ["qc", "validation"]
    })
    
    # Add parsing notes
    metadata.add_parsing_note("Warning: Found unknown resource specification 'gpu_memory'")
    metadata.add_parsing_note("Info: Converted 'threads' to 'cpu' field")
    
    # Add environment-specific metadata
    metadata.add_environment_metadata("distributed_computing", "queue_name", "long")
    metadata.add_environment_metadata("distributed_computing", "account", "bioinformatics")
    metadata.add_environment_metadata("cloud_native", "instance_type", "c5.2xlarge")
    
    # Attach metadata to workflow
    workflow.metadata = metadata
    
    # Create a task with metadata
    task = Task(id="test_task")
    
    task_metadata = MetadataSpec(
        source_format="snakemake",
        source_file="workflow.smk"
    )
    
    # Add task-specific uninterpreted data
    task_metadata.add_format_specific("snakemake_rule", {
        "wildcards": ["{sample}", "{condition}"],
        "localrules": ["all"],
        "checkpoint": "checkpoint_rule"
    })
    
    task_metadata.add_uninterpreted("custom_retry_policy", {
        "max_retries": 5,
        "backoff_factor": 2,
        "retry_on": ["memory_error", "timeout"]
    })
    
    task.metadata = task_metadata
    
    workflow.add_task(task)
    
    # Test serialization
    print("=== Original Workflow ===")
    print(f"Workflow name: {workflow.name}")
    print(f"Source format: {workflow.metadata.source_format}")
    print(f"Format-specific data: {workflow.metadata.format_specific}")
    print(f"Uninterpreted fields: {workflow.metadata.uninterpreted}")
    print(f"Parsing notes: {workflow.metadata.parsing_notes}")
    print(f"Environment metadata: {workflow.metadata.environment_metadata}")
    
    # Serialize to JSON
    json_str = workflow.to_json()
    print(f"\n=== JSON Serialization ===")
    print(json_str[:500] + "..." if len(json_str) > 500 else json_str)
    
    # Deserialize from JSON
    workflow_restored = Workflow.from_json(json_str)
    print(f"\n=== Restored Workflow ===")
    print(f"Workflow name: {workflow_restored.name}")
    print(f"Source format: {workflow_restored.metadata.source_format}")
    print(f"Format-specific data: {workflow_restored.metadata.format_specific}")
    print(f"Uninterpreted fields: {workflow_restored.metadata.uninterpreted}")
    print(f"Parsing notes: {workflow_restored.metadata.parsing_notes}")
    print(f"Environment metadata: {workflow_restored.metadata.environment_metadata}")
    
    # Test environment-specific metadata access
    print(f"\n=== Environment-Specific Metadata ===")
    print(f"Distributed computing metadata: {workflow_restored.metadata.get_environment_metadata('distributed_computing')}")
    print(f"Cloud native metadata: {workflow_restored.metadata.get_environment_metadata('cloud_native')}")
    
    print("\n✅ MetadataSpec test completed successfully!")

if __name__ == "__main__":
    test_metadata_spec() 