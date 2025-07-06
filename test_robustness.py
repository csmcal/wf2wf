#!/usr/bin/env python3
"""Test the robustness improvements in the JSON encoder."""

import json
from pathlib import Path
import sys

# Add the wf2wf package to the path
sys.path.insert(0, str(Path(__file__).parent))

from wf2wf.core import (
    EnvironmentSpecificValue, CheckpointSpec, LoggingSpec, 
    SecuritySpec, NetworkingSpec, WF2WFJSONEncoder, WF2WFJSONDecoder
)

def test_empty_environment_specific_value():
    """Test that empty EnvironmentSpecificValue objects are handled gracefully."""
    print("Testing empty EnvironmentSpecificValue...")
    
    # Test completely empty object
    empty_env = EnvironmentSpecificValue()
    serialized = json.dumps(empty_env, cls=WF2WFJSONEncoder, indent=2)
    print(f"Empty serialized: {serialized}")
    
    # Deserialize
    deserialized_data = json.loads(serialized)
    deserialized = WF2WFJSONDecoder.decode_environment_specific_value(deserialized_data)
    
    # Verify it's still empty
    assert len(deserialized.values) == 0
    assert len(deserialized.all_environments()) == 0
    
    print("✅ Empty EnvironmentSpecificValue test passed")

def test_malformed_environment_specific_value():
    """Test that malformed EnvironmentSpecificValue objects are handled gracefully."""
    print("Testing malformed EnvironmentSpecificValue...")
    
    # Create a malformed object by directly manipulating the internal structure
    malformed = EnvironmentSpecificValue()
    malformed.values = [{"invalid": "structure"}]  # Missing required fields
    
    serialized = json.dumps(malformed, cls=WF2WFJSONEncoder, indent=2)
    print(f"Malformed serialized: {serialized}")
    
    # Should not crash and should include error information
    assert "_error" in serialized or "values" in serialized
    
    print("✅ Malformed EnvironmentSpecificValue test passed")

def test_nested_dataclasses():
    """Test that nested dataclasses are handled recursively."""
    print("Testing nested dataclasses...")
    
    # Create a complex nested structure
    checkpoint = CheckpointSpec(
        strategy="filesystem",
        interval=300,
        storage_location="/tmp/checkpoints",
        enabled=True,
        notes="Local filesystem checkpoints"
    )
    
    # Create an EnvironmentSpecificValue containing the checkpoint
    env_value = EnvironmentSpecificValue()
    env_value.set_for_environment(checkpoint, "distributed_computing")
    
    serialized = json.dumps(env_value, cls=WF2WFJSONEncoder, indent=2)
    print(f"Nested dataclass serialized: {serialized}")
    
    # Should serialize without errors
    assert "strategy" in serialized
    assert "filesystem" in serialized
    assert "interval" in serialized
    assert "300" in serialized
    
    print("✅ Nested dataclasses test passed")

def test_edge_cases():
    """Test various edge cases and error conditions."""
    print("Testing edge cases...")
    
    # Test None values in spec classes
    checkpoint_with_nones = CheckpointSpec(
        strategy="filesystem",
        interval=300,
        storage_location=None,  # None value
        enabled=None,  # None value
        notes=None  # None value
    )
    
    serialized = json.dumps(checkpoint_with_nones, cls=WF2WFJSONEncoder, indent=2)
    print(f"Spec with None values: {serialized}")
    
    # Should only include non-None fields
    assert "strategy" in serialized
    assert "interval" in serialized
    assert "storage_location" not in serialized
    assert "enabled" not in serialized
    assert "notes" not in serialized
    
    # Test empty collections
    security_empty = SecuritySpec(
        encryption="AES256",
        access_policies="IAM_ROLE_ARN",
        secrets={},  # Empty dict
        authentication="oauth",
        notes="Test"
    )
    
    serialized = json.dumps(security_empty, cls=WF2WFJSONEncoder, indent=2)
    print(f"Spec with empty collections: {serialized}")
    
    # Should skip empty collections
    assert "encryption" in serialized
    assert "access_policies" in serialized
    assert "authentication" in serialized
    assert "notes" in serialized
    assert "secrets" not in serialized  # Empty dict should be skipped
    
    print("✅ Edge cases test passed")

def test_decoder_robustness():
    """Test that the decoder handles various input formats robustly."""
    print("Testing decoder robustness...")
    
    # Test with invalid input
    invalid_data = "not a dict"
    result = WF2WFJSONDecoder.decode_environment_specific_value(invalid_data)
    assert isinstance(result, EnvironmentSpecificValue)
    assert len(result.values) == 0
    
    # Test with missing fields
    incomplete_data = {"some_field": "value"}
    result = WF2WFJSONDecoder.decode_environment_specific_value(incomplete_data)
    assert isinstance(result, EnvironmentSpecificValue)
    
    # Test with error markers
    error_data = {
        "values": [],
        "environments": [],
        "_error": "Some error occurred"
    }
    result = WF2WFJSONDecoder.decode_environment_specific_value(error_data)
    assert isinstance(result, EnvironmentSpecificValue)
    
    # Test spec decoder with invalid data
    result = WF2WFJSONDecoder.decode_spec("not a dict", CheckpointSpec)
    assert result is None
    
    # Test spec decoder with error markers
    error_spec_data = {
        "strategy": "filesystem",
        "_error": "Some error occurred"
    }
    result = WF2WFJSONDecoder.decode_spec(error_spec_data, CheckpointSpec)
    assert result is not None
    assert result.strategy == "filesystem"
    
    print("✅ Decoder robustness test passed")

def test_complex_roundtrip():
    """Test complex roundtrip serialization and deserialization."""
    print("Testing complex roundtrip...")
    
    # Create a complex object with multiple environments and spec classes
    env_value = EnvironmentSpecificValue(value=4, environments=["shared_filesystem"])
    env_value.set_for_environment(8, "distributed_computing", "inferred", 0.8)
    env_value.set_for_environment(16, "cloud_native", "explicit", 1.0)
    
    # Add a checkpoint spec
    checkpoint = CheckpointSpec(
        strategy="filesystem",
        interval=300,
        storage_location="/tmp/checkpoints",
        enabled=True
    )
    
    # Serialize
    serialized = json.dumps({
        "env_value": env_value,
        "checkpoint": checkpoint
    }, cls=WF2WFJSONEncoder, indent=2)
    
    print(f"Complex serialized: {serialized}")
    
    # Deserialize
    deserialized_data = json.loads(serialized)
    
    # Decode the environment value
    decoded_env = WF2WFJSONDecoder.decode_environment_specific_value(deserialized_data["env_value"])
    
    # Verify values are preserved
    assert decoded_env.get_value_for("shared_filesystem") == 4
    assert decoded_env.get_value_for("distributed_computing") == 8
    assert decoded_env.get_value_for("cloud_native") == 16
    
    # Decode the checkpoint
    decoded_checkpoint = WF2WFJSONDecoder.decode_spec(deserialized_data["checkpoint"], CheckpointSpec)
    
    # Verify checkpoint is preserved
    assert decoded_checkpoint.strategy == "filesystem"
    assert decoded_checkpoint.interval == 300
    assert decoded_checkpoint.storage_location == "/tmp/checkpoints"
    assert decoded_checkpoint.enabled is True
    
    print("✅ Complex roundtrip test passed")

if __name__ == "__main__":
    print("Running robustness tests...\n")
    
    try:
        test_empty_environment_specific_value()
        print()
        test_malformed_environment_specific_value()
        print()
        test_nested_dataclasses()
        print()
        test_edge_cases()
        print()
        test_decoder_robustness()
        print()
        test_complex_roundtrip()
        print()
        print("🎉 All robustness tests passed!")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1) 