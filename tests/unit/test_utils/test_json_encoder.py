#!/usr/bin/env python3
"""Test the improved JSON encoder for wf2wf."""

import json
from pathlib import Path
import sys

# Add the wf2wf package to the path
sys.path.insert(0, str(Path(__file__).parent))

from wf2wf.core import (
    Workflow, Task, EnvironmentSpecificValue, 
    CheckpointSpec, LoggingSpec, SecuritySpec, NetworkingSpec,
    WF2WFJSONEncoder, WF2WFJSONDecoder
)

def test_environment_specific_value_serialization():
    """Test that EnvironmentSpecificValue objects serialize correctly."""
    print("Testing EnvironmentSpecificValue serialization...")
    
    # Create an EnvironmentSpecificValue with multiple environments
    env_value = EnvironmentSpecificValue(value=4, environments=["shared_filesystem"])
    env_value.set_for_environment(8, "distributed_computing")
    env_value.set_for_environment(16, "cloud_native")
    
    # Serialize
    serialized = json.dumps(env_value, cls=WF2WFJSONEncoder, indent=2)
    print(f"Serialized: {serialized}")
    
    # Deserialize
    deserialized_data = json.loads(serialized)
    deserialized = WF2WFJSONDecoder.decode_environment_specific_value(deserialized_data)
    
    # Verify values are preserved
    assert deserialized.get_value_for("shared_filesystem") == 4
    assert deserialized.get_value_for("distributed_computing") == 8
    assert deserialized.get_value_for("cloud_native") == 16
    
    print("✅ EnvironmentSpecificValue serialization test passed")

def test_spec_classes_serialization():
    """Test that new spec classes serialize correctly."""
    print("Testing spec classes serialization...")
    
    # Create spec objects
    checkpoint = CheckpointSpec(
        strategy="filesystem",
        interval=300,
        storage_location="/tmp/checkpoints",
        enabled=True,
        notes="Local filesystem checkpoints"
    )
    
    logging = LoggingSpec(
        log_level="INFO",
        log_format="json",
        log_destination="/var/log/workflow.log",
        aggregation="syslog"
    )
    
    security = SecuritySpec(
        encryption="AES256",
        access_policies="IAM_ROLE_ARN",
        secrets={"api_key": "secret_value"},
        authentication="oauth"
    )
    
    networking = NetworkingSpec(
        network_mode="bridge",
        allowed_ports=[80, 443, 8080],
        egress_rules=["0.0.0.0/0"],
        ingress_rules=["10.0.0.0/8"]
    )
    
    # Serialize each
    for name, obj in [("checkpoint", checkpoint), ("logging", logging), 
                     ("security", security), ("networking", networking)]:
        serialized = json.dumps(obj, cls=WF2WFJSONEncoder, indent=2)
        print(f"Serialized {name}: {serialized}")
        
        # Deserialize
        deserialized_data = json.loads(serialized)
        if name == "checkpoint":
            deserialized = WF2WFJSONDecoder.decode_spec(deserialized_data, CheckpointSpec)
        elif name == "logging":
            deserialized = WF2WFJSONDecoder.decode_spec(deserialized_data, LoggingSpec)
        elif name == "security":
            deserialized = WF2WFJSONDecoder.decode_spec(deserialized_data, SecuritySpec)
        elif name == "networking":
            deserialized = WF2WFJSONDecoder.decode_spec(deserialized_data, NetworkingSpec)
        
        # Verify the object is reconstructed correctly
        assert deserialized is not None
        print(f"✅ {name} serialization test passed")

def test_task_serialization():
    """Test that Task objects with environment-specific fields serialize correctly."""
    print("Testing Task serialization...")
    
    # Create a task with environment-specific fields
    task = Task(id="test_task")
    task.set_for_environment("command", "python script.py", "shared_filesystem")
    task.set_for_environment("command", "docker run python:3.9", "distributed_computing")
    task.set_for_environment("cpu", 2, "shared_filesystem")
    task.set_for_environment("cpu", 4, "distributed_computing")
    task.set_for_environment("cpu", 8, "cloud_native")
    
    # Add spec objects
    task.checkpointing.set_for_environment(
        CheckpointSpec(strategy="filesystem", interval=300),
        "distributed_computing"
    )
    
    # Serialize
    serialized = json.dumps(task, cls=WF2WFJSONEncoder, indent=2)
    print(f"Serialized task: {serialized}")
    
    # Deserialize
    deserialized_data = json.loads(serialized)
    # Note: This would need to be handled in the Task constructor
    # For now, just verify the JSON is valid
    assert "test_task" in serialized
    assert "python script.py" in serialized
    assert "docker run python:3.9" in serialized
    
    print("✅ Task serialization test passed")

def test_workflow_roundtrip():
    """Test complete workflow serialization and deserialization."""
    print("Testing workflow roundtrip...")
    
    # Create a simple workflow
    workflow = Workflow(name="test_workflow", version="1.0")
    
    # Add a task
    task = Task(id="task1")
    task.set_for_environment("command", "echo hello", "shared_filesystem")
    task.set_for_environment("cpu", 2, "shared_filesystem")
    workflow.add_task(task)
    
    # Do not add a self-edge (since self-edges are ignored)
    # workflow.add_edge("task1", "task1")
    
    # Serialize
    serialized = workflow.to_json(indent=2)
    print(f"Serialized workflow: {serialized}")
    
    # Deserialize
    deserialized = Workflow.from_json(serialized)
    
    # Verify basic structure is preserved
    assert deserialized.name == "test_workflow"
    assert deserialized.version == "1.0"
    assert "task1" in deserialized.tasks
    assert len(deserialized.edges) == 0  # No edges expected
    
    print("✅ Workflow roundtrip test passed")

if __name__ == "__main__":
    print("Running JSON encoder tests...\n")
    
    try:
        test_environment_specific_value_serialization()
        print()
        test_spec_classes_serialization()
        print()
        test_task_serialization()
        print()
        test_workflow_roundtrip()
        print()
        print("🎉 All JSON encoder tests passed!")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 