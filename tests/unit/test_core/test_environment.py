"""
Consolidated environment tests for wf2wf core functionality.

This file combines all environment-related tests that were previously scattered
across multiple test files to improve organization and reduce duplication.
"""

import json
import sys
import pathlib
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

# Allow running tests without installing package
proj_root = pathlib.Path(__file__).resolve().parents[3]

if "wf2wf" not in sys.modules:
    spec = importlib.util.spec_from_file_location("wf2wf", proj_root / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["wf2wf"] = module  # type: ignore[assignment]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[arg-type]

from wf2wf.core import (
    Workflow, Task, EnvironmentSpecificValue,
    CheckpointSpec, LoggingSpec, SecuritySpec, NetworkingSpec,
    WF2WFJSONEncoder, WF2WFJSONDecoder
)
from wf2wf.environ import EnvironmentManager


class TestEnvironmentSpecificValue:
    """Test EnvironmentSpecificValue functionality."""

    def test_empty_environment_specific_value(self):
        """Test empty EnvironmentSpecificValue creation and behavior."""
        env_value = EnvironmentSpecificValue()
        
        # Test basic properties
        assert len(env_value.values) == 0
        assert env_value.get_value_for("any_env") is None
        assert env_value.get_value_with_default("any_env") is None

    def test_single_environment_value(self):
        """Test single environment value creation and retrieval."""
        env_value = EnvironmentSpecificValue(value=42, environments=["shared_filesystem"])
        
        # Test value retrieval
        assert env_value.get_value_for("shared_filesystem") == 42
        assert env_value.get_value_for("other_env") is None
        assert env_value.get_value_with_default("shared_filesystem") == 42
        assert env_value.get_value_with_default("other_env") is None

    def test_multiple_environment_values(self):
        """Test multiple environment values."""
        env_value = EnvironmentSpecificValue(value=4, environments=["shared_filesystem"])
        env_value.set_for_environment(8, "distributed_computing")
        env_value.set_for_environment(16, "cloud_native")
        
        # Test all values are preserved
        assert env_value.get_value_for("shared_filesystem") == 4
        assert env_value.get_value_for("distributed_computing") == 8
        assert env_value.get_value_for("cloud_native") == 16
        assert env_value.get_value_for("other_env") is None

    def test_complex_value_types(self):
        """Test complex value types in EnvironmentSpecificValue."""
        # Test with dict values
        env_value = EnvironmentSpecificValue(
            value={"cpu": 4, "memory": "8GB"}, 
            environments=["shared_filesystem"]
        )
        env_value.set_for_environment(
            {"cpu": 8, "memory": "16GB", "gpu": 1}, 
            "distributed_computing"
        )
        
        # Verify
        shared_value = env_value.get_value_for("shared_filesystem")
        assert shared_value["cpu"] == 4
        assert shared_value["memory"] == "8GB"
        
        distributed_value = env_value.get_value_for("distributed_computing")
        assert distributed_value["cpu"] == 8
        assert distributed_value["memory"] == "16GB"
        assert distributed_value["gpu"] == 1

    def test_list_values(self):
        """Test list values in EnvironmentSpecificValue."""
        env_value = EnvironmentSpecificValue(
            value=["file1.txt", "file2.txt"], 
            environments=["shared_filesystem"]
        )
        env_value.set_for_environment(
            ["file1.txt", "file2.txt", "file3.txt"], 
            "distributed_computing"
        )
        
        # Verify
        assert env_value.get_value_for("shared_filesystem") == ["file1.txt", "file2.txt"]
        assert env_value.get_value_for("distributed_computing") == ["file1.txt", "file2.txt", "file3.txt"]

    def test_none_values(self):
        """Test handling of None values."""
        env_value = EnvironmentSpecificValue(value=None, environments=["shared_filesystem"])
        env_value.set_for_environment(None, "distributed_computing")
        
        # Verify None values are handled correctly
        assert env_value.get_value_for("shared_filesystem") is None
        assert env_value.get_value_for("distributed_computing") is None


class TestEnvironmentSpecificValueRoundtrip:
    """Test round-trip serialization of EnvironmentSpecificValue objects."""

    def test_empty_environment_specific_value_roundtrip(self):
        """Test round-trip of empty EnvironmentSpecificValue."""
        env_value = EnvironmentSpecificValue()
        
        # Serialize
        serialized = json.dumps(env_value, cls=WF2WFJSONEncoder)
        data = json.loads(serialized)
        
        # Deserialize
        decoded = WF2WFJSONDecoder.decode_environment_specific_value(data)
        
        # Verify
        assert len(decoded.values) == 0
        assert decoded.get_value_for("any_env") is None

    def test_single_environment_value_roundtrip(self):
        """Test round-trip of single environment value."""
        env_value = EnvironmentSpecificValue(value=42, environments=["shared_filesystem"])
        
        # Serialize
        serialized = json.dumps(env_value, cls=WF2WFJSONEncoder)
        data = json.loads(serialized)
        
        # Deserialize
        decoded = WF2WFJSONDecoder.decode_environment_specific_value(data)
        
        # Verify
        assert decoded.get_value_for("shared_filesystem") == 42
        assert decoded.get_value_for("other_env") is None

    def test_multiple_environment_values_roundtrip(self):
        """Test round-trip of multiple environment values."""
        env_value = EnvironmentSpecificValue(value=4, environments=["shared_filesystem"])
        env_value.set_for_environment(8, "distributed_computing")
        env_value.set_for_environment(16, "cloud_native")
        
        # Serialize
        serialized = json.dumps(env_value, cls=WF2WFJSONEncoder)
        data = json.loads(serialized)
        
        # Deserialize
        decoded = WF2WFJSONDecoder.decode_environment_specific_value(data)
        
        # Verify all values are preserved
        assert decoded.get_value_for("shared_filesystem") == 4
        assert decoded.get_value_for("distributed_computing") == 8
        assert decoded.get_value_for("cloud_native") == 16
        assert decoded.get_value_for("other_env") is None

    def test_complex_value_types_roundtrip(self):
        """Test round-trip of complex value types."""
        # Test with dict values
        env_value = EnvironmentSpecificValue(
            value={"cpu": 4, "memory": "8GB"}, 
            environments=["shared_filesystem"]
        )
        env_value.set_for_environment(
            {"cpu": 8, "memory": "16GB", "gpu": 1}, 
            "distributed_computing"
        )
        
        # Serialize
        serialized = json.dumps(env_value, cls=WF2WFJSONEncoder)
        data = json.loads(serialized)
        
        # Deserialize
        decoded = WF2WFJSONDecoder.decode_environment_specific_value(data)
        
        # Verify
        shared_value = decoded.get_value_for("shared_filesystem")
        assert shared_value["cpu"] == 4
        assert shared_value["memory"] == "8GB"
        
        distributed_value = decoded.get_value_for("distributed_computing")
        assert distributed_value["cpu"] == 8
        assert distributed_value["memory"] == "16GB"
        assert distributed_value["gpu"] == 1


class TestEnvironmentManager:
    """Test cases for the EnvironmentManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.env_manager = EnvironmentManager(interactive=False, verbose=True)
        
        # Create a test workflow
        self.workflow = Workflow(name="test_workflow")
        
        # Add test tasks with correct EnvironmentSpecificValue structure
        task1 = Task(
            id="task1",
            command=EnvironmentSpecificValue("python script.py", ["shared_filesystem"]),
            container=EnvironmentSpecificValue("python:3.9", ["shared_filesystem"]),
            cpu=EnvironmentSpecificValue(2, ["shared_filesystem"]),
            mem_mb=EnvironmentSpecificValue(4096, ["shared_filesystem"])
        )
        
        task2 = Task(
            id="task2",
            command=EnvironmentSpecificValue("blast -query input.fasta", ["shared_filesystem"]),
            conda=EnvironmentSpecificValue("environment.yml", ["shared_filesystem"]),
            cpu=EnvironmentSpecificValue(4, ["shared_filesystem"]),
            mem_mb=EnvironmentSpecificValue(8192, ["shared_filesystem"])
        )
        
        task3 = Task(
            id="task3",
            command=EnvironmentSpecificValue("echo 'hello world'", ["shared_filesystem"])
            # No environment specification
        )
        
        self.workflow.add_task(task1)
        self.workflow.add_task(task2)
        self.workflow.add_task(task3)
    
    def test_detect_and_parse_environments(self):
        """Test environment detection and parsing."""
        source_path = Path("/tmp/test_workflow.smk")
        
        env_info = self.env_manager.detect_and_parse_environments(
            self.workflow, "snakemake", source_path
        )
        
        # Check detected containers
        assert "python:3.9" in env_info['containers']
        
        # Check detected conda environments
        assert "environment.yml" in env_info['conda_environments']
        
        # Check environment files
        assert "environment.yml" in env_info['environment_files']
        
        # Check missing environments
        assert "task3" in env_info['missing_environments']
        
        # Check metadata
        assert env_info['environment_metadata']['source_format'] == "snakemake"
        assert env_info['environment_metadata']['total_tasks'] == 3
        assert env_info['environment_metadata']['tasks_with_environments'] == 2
        assert env_info['environment_metadata']['tasks_without_environments'] == 1
    
    def test_analyze_task_environment(self):
        """Test individual task environment analysis."""
        task = self.workflow.tasks["task1"]
        source_path = Path("/tmp/test_workflow.smk")
        
        env_info = self.env_manager._analyze_task_environment(task, source_path)
        
        assert env_info['container'] == "python:3.9"
        assert env_info['conda'] is None
        assert env_info['environment_file'] is None
        assert env_info['metadata']['container_source'] == 'explicit'
        assert len(env_info['warnings']) == 0
    
    def test_analyze_task_environment_with_conda(self):
        """Test task environment analysis with conda specification."""
        task = self.workflow.tasks["task2"]
        source_path = Path("/tmp/test_workflow.smk")
        
        env_info = self.env_manager._analyze_task_environment(task, source_path)
        
        assert env_info['container'] is None
        assert env_info['conda'] == "environment.yml"
        assert env_info['environment_file'] == "environment.yml"
        assert env_info['metadata']['conda_source'] == 'explicit'
    
    def test_analyze_task_environment_without_env(self):
        """Test task environment analysis without environment specification."""
        task = self.workflow.tasks["task3"]
        source_path = Path("/tmp/test_workflow.smk")
        
        env_info = self.env_manager._analyze_task_environment(task, source_path)
        
        assert env_info['container'] is None
        assert env_info['conda'] is None
        assert env_info['environment_file'] is None
        assert len(env_info['warnings']) == 0
    
    def test_is_environment_file(self):
        """Test environment file detection."""
        # Test environment file extensions
        assert self.env_manager._is_environment_file("environment.yml") is True
        assert self.env_manager._is_environment_file("environment.yaml") is True
        assert self.env_manager._is_environment_file("requirements.txt") is True
        assert self.env_manager._is_environment_file("environment.lock") is True
        
        # Test container images (should not be files)
        assert self.env_manager._is_environment_file("python:3.9") is False
        assert self.env_manager._is_environment_file("docker://python:3.9") is False
        assert self.env_manager._is_environment_file("ubuntu:20.04") is False
        
        # Test relative paths
        assert self.env_manager._is_environment_file("./env/environment.yml") is True
        assert self.env_manager._is_environment_file("../environments/bio.yml") is True
        
        # Test empty or None
        assert self.env_manager._is_environment_file("") is False
        assert self.env_manager._is_environment_file(None) is False
    
    def test_infer_missing_environments(self):
        """Test inference of missing environment specifications."""
        # Clear environment specifications from task3
        task3 = self.workflow.tasks["task3"]
        task3.container = EnvironmentSpecificValue()
        task3.conda = EnvironmentSpecificValue()
        
        self.env_manager.infer_missing_environments(self.workflow, "snakemake")
        
        # Check that container was inferred for task3
        container = task3.container.get_value_for('shared_filesystem')
        assert container is not None
        assert "ubuntu" in container  # Should infer ubuntu for echo command
    
    def test_infer_container_from_command(self):
        """Test container inference from command."""
        # Test Python commands
        container = self.env_manager._infer_container_from_command("python script.py")
        assert "python" in container
        
        # Test R commands
        container = self.env_manager._infer_container_from_command("rscript analysis.R")
        assert "rocker" in container
        
        # Test bioinformatics commands
        container = self.env_manager._infer_container_from_command("blast -query input.fasta")
        assert "biocontainers" in container
        
        # Test machine learning commands
        container = self.env_manager._infer_container_from_command("python -c 'import tensorflow'")
        assert "tensorflow" in container
        
        # Test general Linux commands
        container = self.env_manager._infer_container_from_command("echo 'hello world'")
        assert "ubuntu" in container
        
        # Test None/empty commands
        assert self.env_manager._infer_container_from_command(None) is None
        assert self.env_manager._infer_container_from_command("") is None
    
    def test_infer_conda_environment_from_command(self):
        """Test conda environment inference from command."""
        # Test Python commands
        conda_env = self.env_manager._infer_conda_environment_from_command("python script.py")
        assert conda_env == "environment.yml"
        
        # Test R commands
        conda_env = self.env_manager._infer_conda_environment_from_command("rscript analysis.R")
        assert conda_env == "r_environment.yml"
        
        # Test bioinformatics commands
        conda_env = self.env_manager._infer_conda_environment_from_command("blast -query input.fasta")
        assert conda_env == "bioinformatics.yml"
        
        # Test None/empty commands
        assert self.env_manager._infer_conda_environment_from_command(None) is None
        assert self.env_manager._infer_conda_environment_from_command("") is None


class TestEnvironmentManagerIntegration:
    """Integration tests for EnvironmentManager."""

    def test_full_workflow_environment_processing(self):
        """Test complete workflow environment processing."""
        env_manager = EnvironmentManager(interactive=False, verbose=True)
        
        # Create a complex workflow with mixed environment specifications
        workflow = Workflow(name="complex_workflow")
        
        # Task with container
        task1 = Task(
            id="python_task",
            command=EnvironmentSpecificValue("python analysis.py", ["shared_filesystem"]),
            container=EnvironmentSpecificValue("python:3.9", ["shared_filesystem"])
        )
        
        # Task with conda
        task2 = Task(
            id="r_task",
            command=EnvironmentSpecificValue("rscript analysis.R", ["shared_filesystem"]),
            conda=EnvironmentSpecificValue("r_environment.yml", ["shared_filesystem"])
        )
        
        # Task without environment (should be inferred)
        task3 = Task(
            id="echo_task",
            command=EnvironmentSpecificValue("echo 'hello world'", ["shared_filesystem"])
        )
        
        workflow.add_task(task1)
        workflow.add_task(task2)
        workflow.add_task(task3)
        
        # Process environments
        env_info = env_manager.detect_and_parse_environments(
            workflow, "snakemake", Path("/tmp/workflow.smk")
        )
        
        # Verify results
        assert len(env_info['containers']) == 1
        assert "python:3.9" in env_info['containers']
        
        assert len(env_info['conda_environments']) == 1
        assert "r_environment.yml" in env_info['conda_environments']
        
        assert len(env_info['missing_environments']) == 1
        assert "echo_task" in env_info['missing_environments']
        
        # Test inference
        env_manager.infer_missing_environments(workflow, "snakemake")
        
        # Verify inference worked
        container = task3.container.get_value_for('shared_filesystem')
        assert container is not None
        assert "ubuntu" in container


class TestNewSpecClassesRoundtrip:
    """Test round-trip serialization of new spec classes."""

    def test_checkpoint_spec_roundtrip(self):
        """Test round-trip of CheckpointSpec."""
        checkpoint = CheckpointSpec(
            strategy="filesystem",
            interval=300,
            storage_location="/tmp/checkpoints",
            enabled=True,
            notes="Test checkpoint configuration"
        )
        
        # Serialize
        serialized = json.dumps(checkpoint, cls=WF2WFJSONEncoder)
        data = json.loads(serialized)
        
        # Deserialize
        decoded = WF2WFJSONDecoder.decode_spec(data, CheckpointSpec)
        
        # Verify
        assert decoded.strategy == "filesystem"
        assert decoded.interval == 300
        assert decoded.storage_location == "/tmp/checkpoints"
        assert decoded.enabled is True
        assert decoded.notes == "Test checkpoint configuration"

    def test_logging_spec_roundtrip(self):
        """Test round-trip of LoggingSpec."""
        logging = LoggingSpec(
            log_level="INFO",
            log_format="json",
            log_destination="/tmp/workflow.log",
            aggregation="syslog",
            notes="Test logging configuration"
        )
        
        # Serialize
        serialized = json.dumps(logging, cls=WF2WFJSONEncoder)
        data = json.loads(serialized)
        
        # Deserialize
        decoded = WF2WFJSONDecoder.decode_spec(data, LoggingSpec)
        
        # Verify
        assert decoded.log_level == "INFO"
        assert decoded.log_format == "json"
        assert decoded.log_destination == "/tmp/workflow.log"
        assert decoded.aggregation == "syslog"
        assert decoded.notes == "Test logging configuration"

    def test_security_spec_roundtrip(self):
        """Test round-trip of SecuritySpec."""
        security = SecuritySpec(
            encryption="AES256",
            access_policies="restricted",
            secrets={"API_KEY": "secret_value", "DB_PASSWORD": "db_secret"},
            authentication="kerberos",
            notes="Test security configuration"
        )
        
        # Serialize
        serialized = json.dumps(security, cls=WF2WFJSONEncoder)
        data = json.loads(serialized)
        
        # Deserialize
        decoded = WF2WFJSONDecoder.decode_spec(data, SecuritySpec)
        
        # Verify
        assert decoded.encryption == "AES256"
        assert decoded.access_policies == "restricted"
        assert decoded.secrets == {"API_KEY": "secret_value", "DB_PASSWORD": "db_secret"}
        assert decoded.authentication == "kerberos"
        assert decoded.notes == "Test security configuration"

    def test_networking_spec_roundtrip(self):
        """Test round-trip of NetworkingSpec."""
        networking = NetworkingSpec(
            network_mode="bridge",
            allowed_ports=[8080, 9000],
            egress_rules=["allow outbound to api.example.com"],
            ingress_rules=["allow inbound from 192.168.1.0/24"],
            notes="Test networking configuration"
        )
        
        # Serialize
        serialized = json.dumps(networking, cls=WF2WFJSONEncoder)
        data = json.loads(serialized)
        
        # Deserialize
        decoded = WF2WFJSONDecoder.decode_spec(data, NetworkingSpec)
        
        # Verify
        assert decoded.network_mode == "bridge"
        assert decoded.allowed_ports == [8080, 9000]
        assert decoded.egress_rules == ["allow outbound to api.example.com"]
        assert decoded.ingress_rules == ["allow inbound from 192.168.1.0/24"]
        assert decoded.notes == "Test networking configuration"


class TestTaskEnvironmentSpecificFieldsRoundtrip:
    """Test round-trip serialization of tasks with environment-specific fields."""

    def test_task_with_environment_specific_command(self):
        """Test round-trip of task with environment-specific command."""
        task = Task(
            id="test_task",
            command=EnvironmentSpecificValue("python script.py", ["shared_filesystem"]),
            script=EnvironmentSpecificValue("scripts/script.py", ["shared_filesystem"])
        )
        
        # Serialize
        serialized = json.dumps(task, cls=WF2WFJSONEncoder)
        data = json.loads(serialized)
        
        # Deserialize
        decoded = WF2WFJSONDecoder.decode_task(data)
        
        # Verify
        assert decoded.id == "test_task"
        assert decoded.command.get_value_for("shared_filesystem") == "python script.py"
        assert decoded.script.get_value_for("shared_filesystem") == "scripts/script.py"

    def test_task_with_environment_specific_resources(self):
        """Test round-trip of task with environment-specific resources."""
        task = Task(
            id="resource_task",
            cpu=EnvironmentSpecificValue(4, ["shared_filesystem"]),
            mem_mb=EnvironmentSpecificValue(8192, ["shared_filesystem"]),
            disk_mb=EnvironmentSpecificValue(10240, ["shared_filesystem"]),
            gpu=EnvironmentSpecificValue(1, ["distributed_computing"])
        )
        
        # Serialize
        serialized = json.dumps(task, cls=WF2WFJSONEncoder)
        data = json.loads(serialized)
        
        # Deserialize
        decoded = WF2WFJSONDecoder.decode_task(data)
        
        # Verify
        assert decoded.id == "resource_task"
        assert decoded.cpu.get_value_for("shared_filesystem") == 4
        assert decoded.mem_mb.get_value_for("shared_filesystem") == 8192
        assert decoded.disk_mb.get_value_for("shared_filesystem") == 10240
        assert decoded.gpu.get_value_for("distributed_computing") == 1
        assert decoded.gpu.get_value_for("shared_filesystem") is None

    def test_task_with_new_spec_classes(self):
        """Test round-trip of task with new spec classes."""
        task = Task(
            id="spec_task",
            checkpoint=CheckpointSpec(
                strategy="filesystem",
                interval=300,
                enabled=True
            ),
            logging=LoggingSpec(
                log_level="INFO",
                log_format="json"
            ),
            security=SecuritySpec(
                encryption="AES256",
                access_policies="restricted"
            ),
            networking=NetworkingSpec(
                network_mode="bridge",
                allowed_ports=[8080]
            )
        )
        
        # Serialize
        serialized = json.dumps(task, cls=WF2WFJSONEncoder)
        data = json.loads(serialized)
        
        # Deserialize
        decoded = WF2WFJSONDecoder.decode_task(data)
        
        # Verify
        assert decoded.id == "spec_task"
        assert decoded.checkpoint.strategy == "filesystem"
        assert decoded.checkpoint.interval == 300
        assert decoded.checkpoint.enabled is True
        assert decoded.logging.log_level == "INFO"
        assert decoded.logging.log_format == "json"
        assert decoded.security.encryption == "AES256"
        assert decoded.security.access_policies == "restricted"
        assert decoded.networking.network_mode == "bridge"
        assert decoded.networking.allowed_ports == [8080]


class TestEdgeCasesAndRobustness:
    """Test edge cases and robustness of environment functionality."""

    def test_none_values_in_environment_specific_fields(self):
        """Test handling of None values in environment-specific fields."""
        task = Task(
            id="none_task",
            command=EnvironmentSpecificValue(None, ["shared_filesystem"]),
            cpu=EnvironmentSpecificValue(None, ["shared_filesystem"])
        )
        
        # Serialize
        serialized = json.dumps(task, cls=WF2WFJSONEncoder)
        data = json.loads(serialized)
        
        # Deserialize
        decoded = WF2WFJSONDecoder.decode_task(data)
        
        # Verify None values are preserved
        assert decoded.command.get_value_for("shared_filesystem") is None
        assert decoded.cpu.get_value_for("shared_filesystem") is None

    def test_empty_spec_objects(self):
        """Test handling of empty spec objects."""
        task = Task(
            id="empty_spec_task",
            checkpoint=CheckpointSpec(),
            logging=LoggingSpec(),
            security=SecuritySpec(),
            networking=NetworkingSpec()
        )
        
        # Serialize
        serialized = json.dumps(task, cls=WF2WFJSONEncoder)
        data = json.loads(serialized)
        
        # Deserialize
        decoded = WF2WFJSONDecoder.decode_task(data)
        
        # Verify empty specs are preserved
        assert decoded.checkpoint is not None
        assert decoded.logging is not None
        assert decoded.security is not None
        assert decoded.networking is not None

    def test_malformed_json_handling(self):
        """Test handling of malformed JSON data."""
        # Test with invalid JSON
        with pytest.raises(json.JSONDecodeError):
            WF2WFJSONDecoder.decode_environment_specific_value("invalid json")

    def test_spec_decoding_with_invalid_data(self):
        """Test spec decoding with invalid data."""
        # Test with None data
        with pytest.raises(ValueError):
            WF2WFJSONDecoder.decode_spec(None, CheckpointSpec)
        
        # Test with empty dict
        with pytest.raises(ValueError):
            WF2WFJSONDecoder.decode_spec({}, CheckpointSpec) 