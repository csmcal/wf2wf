"""
Comprehensive round-trip tests for environment-specific fields and new spec classes.
Tests JSON serialization/deserialization fidelity for all new IR features.
"""

import json
import pytest
from pathlib import Path
from wf2wf.core import (
    Workflow, Task, EnvironmentSpecificValue,
    CheckpointSpec, LoggingSpec, SecuritySpec, NetworkingSpec,
    WF2WFJSONEncoder, WF2WFJSONDecoder
)


class TestEnvironmentSpecificValueRoundtrip:
    """Test round-trip serialization of EnvironmentSpecificValue objects."""

    def test_empty_environment_specific_value(self):
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

    def test_single_environment_value(self):
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

    def test_multiple_environment_values(self):
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

    def test_complex_value_types(self):
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

    def test_list_values(self):
        """Test round-trip of list values."""
        env_value = EnvironmentSpecificValue(
            value=["file1.txt", "file2.txt"], 
            environments=["shared_filesystem"]
        )
        env_value.set_for_environment(
            ["file1.txt", "file2.txt", "file3.txt"], 
            "distributed_computing"
        )
        
        # Serialize
        serialized = json.dumps(env_value, cls=WF2WFJSONEncoder)
        data = json.loads(serialized)
        
        # Deserialize
        decoded = WF2WFJSONDecoder.decode_environment_specific_value(data)
        
        # Verify
        assert decoded.get_value_for("shared_filesystem") == ["file1.txt", "file2.txt"]
        assert decoded.get_value_for("distributed_computing") == ["file1.txt", "file2.txt", "file3.txt"]


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
            ingress_rules=["allow inbound from 10.0.0.0/8"],
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
        assert decoded.ingress_rules == ["allow inbound from 10.0.0.0/8"]
        assert decoded.notes == "Test networking configuration"


class TestTaskEnvironmentSpecificFieldsRoundtrip:
    """Test round-trip of Task objects with environment-specific fields."""

    def test_task_with_environment_specific_command(self):
        """Test round-trip of Task with environment-specific command."""
        task = Task(id="test_task")
        task.command.set_for_environment("python script.py", "shared_filesystem")
        task.command.set_for_environment("docker run python:3.9 script.py", "distributed_computing")
        
        # Create workflow and serialize
        workflow = Workflow(name="test_workflow")
        workflow.add_task(task)
        
        # Serialize
        serialized = workflow.to_json()
        data = json.loads(serialized)
        
        # Deserialize
        decoded_workflow = Workflow.from_dict(data)
        decoded_task = decoded_workflow.tasks["test_task"]
        
        # Verify
        assert decoded_task.command.get_value_for("shared_filesystem") == "python script.py"
        assert decoded_task.command.get_value_for("distributed_computing") == "docker run python:3.9 script.py"

    def test_task_with_environment_specific_resources(self):
        """Test round-trip of Task with environment-specific resources."""
        task = Task(id="test_task")
        task.cpu.set_for_environment(2, "shared_filesystem")
        task.cpu.set_for_environment(4, "distributed_computing")
        task.cpu.set_for_environment(8, "cloud_native")
        
        task.mem_mb.set_for_environment(4096, "shared_filesystem")
        task.mem_mb.set_for_environment(8192, "distributed_computing")
        task.mem_mb.set_for_environment(16384, "cloud_native")
        
        # Create workflow and serialize
        workflow = Workflow(name="test_workflow")
        workflow.add_task(task)
        
        # Serialize
        serialized = workflow.to_json()
        data = json.loads(serialized)
        
        # Deserialize
        decoded_workflow = Workflow.from_dict(data)
        decoded_task = decoded_workflow.tasks["test_task"]
        
        # Verify
        assert decoded_task.cpu.get_value_for("shared_filesystem") == 2
        assert decoded_task.cpu.get_value_for("distributed_computing") == 4
        assert decoded_task.cpu.get_value_for("cloud_native") == 8
        
        assert decoded_task.mem_mb.get_value_for("shared_filesystem") == 4096
        assert decoded_task.mem_mb.get_value_for("distributed_computing") == 8192
        assert decoded_task.mem_mb.get_value_for("cloud_native") == 16384

    def test_task_with_new_spec_classes(self):
        """Test round-trip of Task with new spec classes."""
        task = Task(id="test_task")
        
        # Set environment-specific spec values
        task.checkpointing.set_for_environment(
            CheckpointSpec(strategy="filesystem", interval=300),
            "distributed_computing"
        )
        
        task.logging.set_for_environment(
            LoggingSpec(log_level="INFO", log_format="json"),
            "cloud_native"
        )
        
        task.security.set_for_environment(
            SecuritySpec(encryption="AES256"),
            "cloud_native"
        )
        
        task.networking.set_for_environment(
            NetworkingSpec(network_mode="bridge"),
            "distributed_computing"
        )
        
        # Create workflow and serialize
        workflow = Workflow(name="test_workflow")
        workflow.add_task(task)
        
        # Serialize
        serialized = workflow.to_json()
        data = json.loads(serialized)
        
        # Deserialize
        decoded_workflow = Workflow.from_dict(data)
        decoded_task = decoded_workflow.tasks["test_task"]
        
        # Verify checkpointing
        checkpoint = decoded_task.checkpointing.get_value_for("distributed_computing")
        assert checkpoint.strategy == "filesystem"
        assert checkpoint.interval == 300
        
        # Verify logging
        logging = decoded_task.logging.get_value_for("cloud_native")
        assert logging.log_level == "INFO"
        assert logging.log_format == "json"
        
        # Verify security
        security = decoded_task.security.get_value_for("cloud_native")
        assert security.encryption == "AES256"
        
        # Verify networking
        networking = decoded_task.networking.get_value_for("distributed_computing")
        assert networking.network_mode == "bridge"

    def test_task_with_all_environment_specific_fields(self):
        """Test round-trip of Task with all environment-specific fields populated."""
        task = Task(id="comprehensive_task")
        
        # Set values for multiple environments
        environments = ["shared_filesystem", "distributed_computing", "cloud_native"]
        
        for env in environments:
            task.command.set_for_environment(f"echo hello from {env}", env)
            task.cpu.set_for_environment(len(env), env)
            task.mem_mb.set_for_environment(1024 * len(env), env)
            task.container.set_for_environment(f"docker://test:{env}", env)
            
            # Set spec values
            task.checkpointing.set_for_environment(
                CheckpointSpec(strategy=env, interval=100 + len(env)),
                env
            )
            
            task.logging.set_for_environment(
                LoggingSpec(log_level="INFO", log_destination=f"/tmp/{env}.log"),
                env
            )
            
            task.security.set_for_environment(
                SecuritySpec(encryption=env),
                env
            )
            
            task.networking.set_for_environment(
                NetworkingSpec(network_mode=env),
                env
            )
        
        # Create workflow and serialize
        workflow = Workflow(name="comprehensive_workflow")
        workflow.add_task(task)
        
        # Serialize
        serialized = workflow.to_json()
        data = json.loads(serialized)
        
        # Deserialize
        decoded_workflow = Workflow.from_dict(data)
        decoded_task = decoded_workflow.tasks["comprehensive_task"]
        
        # Verify all values are preserved
        for env in environments:
            assert decoded_task.command.get_value_for(env) == f"echo hello from {env}"
            assert decoded_task.cpu.get_value_for(env) == len(env)
            assert decoded_task.mem_mb.get_value_for(env) == 1024 * len(env)
            assert decoded_task.container.get_value_for(env) == f"docker://test:{env}"
            
            # Verify spec values
            checkpoint = decoded_task.checkpointing.get_value_for(env)
            assert checkpoint.strategy == env
            assert checkpoint.interval == 100 + len(env)
            
            logging = decoded_task.logging.get_value_for(env)
            assert logging.log_destination == f"/tmp/{env}.log"
            
            security = decoded_task.security.get_value_for(env)
            assert security.encryption == env
            
            networking = decoded_task.networking.get_value_for(env)
            assert networking.network_mode == env


class TestWorkflowRoundtrip:
    """Test complete workflow round-trip with environment-specific features."""

    def test_complete_workflow_roundtrip(self):
        """Test complete workflow round-trip with all new features."""
        # Create workflow
        workflow = Workflow(name="test_workflow", version="1.0")
        
        # Add tasks with environment-specific configurations
        task1 = Task(id="task1")
        task1.command.set_for_environment("python process.py", "shared_filesystem")
        task1.command.set_for_environment("docker run python:3.9 process.py", "distributed_computing")
        task1.cpu.set_for_environment(2, "shared_filesystem")
        task1.cpu.set_for_environment(4, "distributed_computing")
        task1.checkpointing.set_for_environment(
            CheckpointSpec(strategy="filesystem", interval=300),
            "distributed_computing"
        )
        workflow.add_task(task1)
        
        task2 = Task(id="task2")
        task2.command.set_for_environment("python analyze.py", "shared_filesystem")
        task2.command.set_for_environment("docker run python:3.9 analyze.py", "distributed_computing")
        task2.cpu.set_for_environment(4, "shared_filesystem")
        task2.cpu.set_for_environment(8, "distributed_computing")
        task2.logging.set_for_environment(
            LoggingSpec(log_level="DEBUG", log_format="json"),
            "cloud_native"
        )
        workflow.add_task(task2)
        
        # Add edge
        workflow.add_edge("task1", "task2")
        
        # Serialize
        serialized = workflow.to_json()
        data = json.loads(serialized)
        
        # Deserialize
        decoded_workflow = Workflow.from_dict(data)
        
        # Verify workflow structure
        assert decoded_workflow.name == "test_workflow"
        assert decoded_workflow.version == "1.0"
        assert len(decoded_workflow.tasks) == 2
        assert len(decoded_workflow.edges) == 1
        
        # Verify task1
        decoded_task1 = decoded_workflow.tasks["task1"]
        assert decoded_task1.command.get_value_for("shared_filesystem") == "python process.py"
        assert decoded_task1.command.get_value_for("distributed_computing") == "docker run python:3.9 process.py"
        assert decoded_task1.cpu.get_value_for("shared_filesystem") == 2
        assert decoded_task1.cpu.get_value_for("distributed_computing") == 4
        
        checkpoint = decoded_task1.checkpointing.get_value_for("distributed_computing")
        assert checkpoint.strategy == "filesystem"
        assert checkpoint.interval == 300
        
        # Verify task2
        decoded_task2 = decoded_workflow.tasks["task2"]
        assert decoded_task2.command.get_value_for("shared_filesystem") == "python analyze.py"
        assert decoded_task2.command.get_value_for("distributed_computing") == "docker run python:3.9 analyze.py"
        assert decoded_task2.cpu.get_value_for("shared_filesystem") == 4
        assert decoded_task2.cpu.get_value_for("distributed_computing") == 8
        
        logging = decoded_task2.logging.get_value_for("cloud_native")
        assert logging.log_level == "DEBUG"
        assert logging.log_format == "json"
        
        # Verify edge
        edge = decoded_workflow.edges[0]
        assert edge.parent == "task1"
        assert edge.child == "task2"

    def test_workflow_with_mixed_environment_configurations(self):
        """Test workflow with tasks having different environment configurations."""
        workflow = Workflow(name="mixed_workflow")
        
        # Task optimized for shared filesystem
        shared_task = Task(id="shared_task")
        shared_task.command.set_for_environment("python local_script.py", "shared_filesystem")
        shared_task.cpu.set_for_environment(1, "shared_filesystem")
        shared_task.mem_mb.set_for_environment(2048, "shared_filesystem")
        workflow.add_task(shared_task)
        
        # Task optimized for distributed computing
        distributed_task = Task(id="distributed_task")
        distributed_task.command.set_for_environment("docker run compute:latest", "distributed_computing")
        distributed_task.cpu.set_for_environment(8, "distributed_computing")
        distributed_task.mem_mb.set_for_environment(16384, "distributed_computing")
        distributed_task.checkpointing.set_for_environment(
            CheckpointSpec(strategy="filesystem", interval=600),
            "distributed_computing"
        )
        workflow.add_task(distributed_task)
        
        # Task optimized for cloud
        cloud_task = Task(id="cloud_task")
        cloud_task.command.set_for_environment("k8s run cloud-job", "cloud_native")
        cloud_task.cpu.set_for_environment(16, "cloud_native")
        cloud_task.mem_mb.set_for_environment(32768, "cloud_native")
        cloud_task.security.set_for_environment(
            SecuritySpec(encryption="AES256", access_policies="restricted"),
            "cloud_native"
        )
        workflow.add_task(cloud_task)
        
        # Serialize and deserialize
        serialized = workflow.to_json()
        decoded_workflow = Workflow.from_dict(json.loads(serialized))
        
        # Verify each task has appropriate environment-specific configurations
        decoded_shared = decoded_workflow.tasks["shared_task"]
        assert decoded_shared.command.get_value_for("shared_filesystem") == "python local_script.py"
        assert decoded_shared.cpu.get_value_for("shared_filesystem") == 1
        
        decoded_distributed = decoded_workflow.tasks["distributed_task"]
        assert decoded_distributed.command.get_value_for("distributed_computing") == "docker run compute:latest"
        assert decoded_distributed.cpu.get_value_for("distributed_computing") == 8
        checkpoint = decoded_distributed.checkpointing.get_value_for("distributed_computing")
        assert checkpoint.strategy == "filesystem"
        assert checkpoint.interval == 600
        
        decoded_cloud = decoded_workflow.tasks["cloud_task"]
        assert decoded_cloud.command.get_value_for("cloud_native") == "k8s run cloud-job"
        assert decoded_cloud.cpu.get_value_for("cloud_native") == 16
        security = decoded_cloud.security.get_value_for("cloud_native")
        assert security.encryption == "AES256"
        assert security.access_policies == "restricted"


class TestEdgeCasesAndRobustness:
    """Test edge cases and robustness of environment-specific round-trip."""

    def test_none_values_in_environment_specific_fields(self):
        """Test handling of None values in environment-specific fields."""
        task = Task(id="test_task")
        task.command.set_for_environment(None, "shared_filesystem")
        task.cpu.set_for_environment(None, "distributed_computing")
        
        workflow = Workflow(name="test_workflow")
        workflow.add_task(task)
        
        # Serialize and deserialize
        serialized = workflow.to_json()
        decoded_workflow = Workflow.from_dict(json.loads(serialized))
        decoded_task = decoded_workflow.tasks["test_task"]
        
        # Verify None values are preserved
        assert decoded_task.command.get_value_for("shared_filesystem") is None
        assert decoded_task.cpu.get_value_for("distributed_computing") is None

    def test_empty_spec_objects(self):
        """Test round-trip of empty spec objects."""
        task = Task(id="test_task")
        
        # Set empty spec objects
        task.checkpointing.set_for_environment(CheckpointSpec(), "shared_filesystem")
        task.logging.set_for_environment(LoggingSpec(), "shared_filesystem")
        task.security.set_for_environment(SecuritySpec(), "shared_filesystem")
        task.networking.set_for_environment(NetworkingSpec(), "shared_filesystem")
        
        workflow = Workflow(name="test_workflow")
        workflow.add_task(task)
        
        # Serialize and deserialize
        serialized = workflow.to_json()
        decoded_workflow = Workflow.from_dict(json.loads(serialized))
        decoded_task = decoded_workflow.tasks["test_task"]
        
        # Verify empty spec objects are preserved
        checkpoint = decoded_task.checkpointing.get_value_for("shared_filesystem")
        assert isinstance(checkpoint, CheckpointSpec)
        assert checkpoint.strategy is None
        assert checkpoint.interval is None
        
        logging = decoded_task.logging.get_value_for("shared_filesystem")
        assert isinstance(logging, LoggingSpec)
        assert logging.log_level is None
        assert logging.log_format is None
        
        security = decoded_task.security.get_value_for("shared_filesystem")
        assert isinstance(security, SecuritySpec)
        assert security.encryption is None
        assert security.access_policies is None
        
        networking = decoded_task.networking.get_value_for("shared_filesystem")
        assert isinstance(networking, NetworkingSpec)
        assert networking.network_mode is None
        assert networking.allowed_ports == []

    def test_malformed_json_handling(self):
        """Test handling of malformed JSON data."""
        # Test with invalid data structure
        invalid_data = {"invalid": "structure"}
        decoded = WF2WFJSONDecoder.decode_environment_specific_value(invalid_data)
        assert isinstance(decoded, EnvironmentSpecificValue)
        assert len(decoded.values) == 0
        
        # Test with None data
        decoded = WF2WFJSONDecoder.decode_environment_specific_value(None)
        assert isinstance(decoded, EnvironmentSpecificValue)
        assert len(decoded.values) == 0
        
        # Test with empty dict
        decoded = WF2WFJSONDecoder.decode_environment_specific_value({})
        assert isinstance(decoded, EnvironmentSpecificValue)
        assert len(decoded.values) == 0

    def test_spec_decoding_with_invalid_data(self):
        """Test spec decoding with invalid data."""
        # Test with None data
        decoded = WF2WFJSONDecoder.decode_spec(None, CheckpointSpec)
        assert decoded is None
        
        # Test with empty dict
        decoded = WF2WFJSONDecoder.decode_spec({}, CheckpointSpec)
        assert isinstance(decoded, CheckpointSpec)
        assert decoded.strategy is None
        assert decoded.interval is None
        
        # Test with invalid field data
        invalid_data = {"strategy": "invalid", "interval": "not_a_number"}
        decoded = WF2WFJSONDecoder.decode_spec(invalid_data, CheckpointSpec)
        assert isinstance(decoded, CheckpointSpec)
        assert decoded.strategy == "invalid"
        # interval should be None due to type conversion failure 