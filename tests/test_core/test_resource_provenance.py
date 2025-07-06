"""
Tests for resource provenance functionality in wf2wf.

This module tests the per-field provenance tracking for resource specifications,
including source_method tracking for explicit, inferred, template, and default values.
"""

import pytest
from wf2wf.core import EnvironmentSpecificValue

def test_env_specific_value_assignment_and_retrieval():
    cpu = EnvironmentSpecificValue(4, ["shared_filesystem"])
    mem_mb = EnvironmentSpecificValue(8192, ["shared_filesystem"])
    gpu = EnvironmentSpecificValue(1, ["distributed_computing"])

    assert cpu.get_value_for("shared_filesystem") == 4
    assert mem_mb.get_value_for("shared_filesystem") == 8192
    assert gpu.get_value_for("distributed_computing") == 1
    assert gpu.get_value_for("shared_filesystem") is None

    # Add another environment
    cpu.set_for_environment(8, "distributed_computing")
    assert cpu.get_value_for("distributed_computing") == 8
    assert cpu.get_value_for("shared_filesystem") == 4 