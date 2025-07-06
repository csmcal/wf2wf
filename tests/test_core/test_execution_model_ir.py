"""
Tests for enhanced IR with environment-specific values and execution model support.
"""

import pytest
from wf2wf.core import (
    Workflow, Task, EnvironmentSpecificValue, ParameterSpec,
    CheckpointSpec, LoggingSpec, SecuritySpec, NetworkingSpec
)


class TestEnvironmentSpecificValue:
    """Test EnvironmentSpecificValue functionality."""
    
    def test_environment_specific_value_creation(self):
        """Test creating EnvironmentSpecificValue with different environments."""
        # Single environment
        cpu = EnvironmentSpecificValue(4, ["shared_filesystem"])
        assert cpu.get_value_for("shared_filesystem") == 4
        assert cpu.get_value_for("distributed_computing") is None
        
        # Multiple environments
        mem = EnvironmentSpecificValue(8192, ["shared_filesystem", "distributed_computing"])
        assert mem.get_value_for("shared_filesystem") == 8192
        assert mem.get_value_for("distributed_computing") == 8192
        assert mem.get_value_for("cloud_native") is None
        
    def test_environment_specific_value_operations(self):
        """Test EnvironmentSpecificValue operations."""
        cpu = EnvironmentSpecificValue(2, ["shared_filesystem"])
        
        # Add environment
        cpu.add_environment("distributed_computing")
        assert cpu.get_value_for("distributed_computing") == 2
        
        # Set for specific environment
        cpu.set_for_environment(8, "cloud_native")
        assert cpu.get_value_for("cloud_native") == 8
        assert cpu.get_value_for("shared_filesystem") == 2
        
        # Remove environment
        cpu.remove_environment("shared_filesystem")
        assert cpu.get_value_for("shared_filesystem") is None
        assert cpu.get_value_for("distributed_computing") == 2
        
    def test_environment_specific_value_all_environments(self):
        """Test getting all environments."""
        cpu = EnvironmentSpecificValue(4, ["shared_filesystem"])
        cpu.set_for_environment(8, "distributed_computing")
        cpu.set_for_environment(16, "cloud_native")
        
        envs = cpu.all_environments()
        assert "shared_filesystem" in envs
        assert "distributed_computing" in envs
        assert "cloud_native" in envs
        assert len(envs) == 3


class TestTaskEnvironmentSpecificFields:
    """Test Task with environment-specific fields."""
    
    def test_task_with_environment_specific_resources(self):
        """Test creating a task with environment-specific resource requirements."""
        task = Task(id="test_task")
        
        # Set different CPU requirements for different environments
        task.cpu.set_for_environment(2, "shared_filesystem")
        task.cpu.set_for_environment(8, "distributed_computing")
        task.cpu.set_for_environment(16, "cloud_native")
        
        # Set different memory requirements
        task.mem_mb.set_for_environment(4096, "shared_filesystem")
        task.mem_mb.set_for_environment(16384, "distributed_computing")
        task.mem_mb.set_for_environment(32768, "cloud_native")
        
        # Verify environment-specific values
        assert task.cpu.get_value_for("shared_filesystem") == 2
        assert task.cpu.get_value_for("distributed_computing") == 8
        assert task.cpu.get_value_for("cloud_native") == 16
        
        assert task.mem_mb.get_value_for("shared_filesystem") == 4096
        assert task.mem_mb.get_value_for("distributed_computing") == 16384
        assert task.mem_mb.get_value_for("cloud_native") == 32768
        
    def test_task_with_environment_specific_containers(self):
        """Test creating a task with environment-specific container specifications."""
        task = Task(id="test_task")
        
        # Set different containers for different environments
        task.container.set_for_environment("python:3.9", "shared_filesystem")
        task.container.set_for_environment("docker://python:3.9-slim", "distributed_computing")
        task.container.set_for_environment("gcr.io/project/python:3.9", "cloud_native")
        
        # Verify environment-specific values
        assert task.container.get_value_for("shared_filesystem") == "python:3.9"
        assert task.container.get_value_for("distributed_computing") == "docker://python:3.9-slim"
        assert task.container.get_value_for("cloud_native") == "gcr.io/project/python:3.9"
        
    def test_task_with_environment_specific_error_handling(self):
        """Test creating a task with environment-specific error handling."""
        task = Task(id="test_task")
        
        # Set different retry configurations for different environments
        task.retry_count.set_for_environment(0, "shared_filesystem")
        task.retry_count.set_for_environment(3, "distributed_computing")
        task.retry_count.set_for_environment(5, "cloud_native")
        
        task.retry_delay.set_for_environment(0, "shared_filesystem")
        task.retry_delay.set_for_environment(60, "distributed_computing")
        task.retry_delay.set_for_environment(120, "cloud_native")
        
        # Verify environment-specific values
        assert task.retry_count.get_value_for("shared_filesystem") == 0
        assert task.retry_count.get_value_for("distributed_computing") == 3
        assert task.retry_count.get_value_for("cloud_native") == 5


class TestNewSpecClasses:
    """Test the new spec classes (CheckpointSpec, LoggingSpec, SecuritySpec, NetworkingSpec)."""
    
    def test_checkpoint_spec(self):
        """Test CheckpointSpec functionality."""
        checkpoint = CheckpointSpec(
            strategy="filesystem",
            interval=300,
            storage_location="/tmp/checkpoints",
            enabled=True,
            notes="Checkpoint every 5 minutes"
        )
        
        assert checkpoint.strategy == "filesystem"
        assert checkpoint.interval == 300
        assert checkpoint.storage_location == "/tmp/checkpoints"
        assert checkpoint.enabled == True
        assert checkpoint.notes == "Checkpoint every 5 minutes"
        
    def test_logging_spec(self):
        """Test LoggingSpec functionality."""
        logging = LoggingSpec(
            log_level="INFO",
            log_format="json",
            log_destination="/var/log/workflow.log",
            aggregation="syslog",
            notes="Structured logging for monitoring"
        )
        
        assert logging.log_level == "INFO"
        assert logging.log_format == "json"
        assert logging.log_destination == "/var/log/workflow.log"
        assert logging.aggregation == "syslog"
        assert logging.notes == "Structured logging for monitoring"
        
    def test_security_spec(self):
        """Test SecuritySpec functionality."""
        security = SecuritySpec(
            encryption="AES256",
            access_policies="role-based",
            secrets={"api_key": "secret123"},
            authentication="kerberos",
            notes="High security requirements"
        )
        
        assert security.encryption == "AES256"
        assert security.access_policies == "role-based"
        assert security.secrets == {"api_key": "secret123"}
        assert security.authentication == "kerberos"
        assert security.notes == "High security requirements"
        
    def test_networking_spec(self):
        """Test NetworkingSpec functionality."""
        networking = NetworkingSpec(
            network_mode="bridge",
            allowed_ports=[80, 443, 8080],
            egress_rules=["allow outbound to internet"],
            ingress_rules=["allow inbound from internal"],
            notes="Restricted network access"
        )
        
        assert networking.network_mode == "bridge"
        assert networking.allowed_ports == [80, 443, 8080]
        assert networking.egress_rules == ["allow outbound to internet"]
        assert networking.ingress_rules == ["allow inbound from internal"]
        assert networking.notes == "Restricted network access"


class TestTaskWithNewSpecs:
    """Test Task with the new spec classes."""
    
    def test_task_with_checkpointing(self):
        """Test creating a task with checkpointing specification."""
        task = Task(id="test_task")
        
        checkpoint = CheckpointSpec(
            strategy="filesystem",
            interval=300,
            enabled=True
        )
        
        task.checkpointing.set_for_environment(checkpoint, "distributed_computing")
        
        checkpoint_value = task.checkpointing.get_value_for("distributed_computing")
        assert isinstance(checkpoint_value, CheckpointSpec)
        assert checkpoint_value.strategy == "filesystem"
        assert checkpoint_value.interval == 300
        assert checkpoint_value.enabled == True
        
    def test_task_with_logging(self):
        """Test creating a task with logging specification."""
        task = Task(id="test_task")
        
        logging = LoggingSpec(
            log_level="DEBUG",
            log_format="json",
            log_destination="/tmp/task.log"
        )
        
        task.logging.set_for_environment(logging, "cloud_native")
        
        logging_value = task.logging.get_value_for("cloud_native")
        assert isinstance(logging_value, LoggingSpec)
        assert logging_value.log_level == "DEBUG"
        assert logging_value.log_format == "json"
        assert logging_value.log_destination == "/tmp/task.log"
        
    def test_task_with_security(self):
        """Test creating a task with security specification."""
        task = Task(id="test_task")
        
        security = SecuritySpec(
            encryption="AES256",
            access_policies="least-privilege",
            secrets={"db_password": "secret"}
        )
        
        task.security.set_for_environment(security, "cloud_native")
        
        security_value = task.security.get_value_for("cloud_native")
        assert isinstance(security_value, SecuritySpec)
        assert security_value.encryption == "AES256"
        assert security_value.access_policies == "least-privilege"
        assert security_value.secrets == {"db_password": "secret"}
        
    def test_task_with_networking(self):
        """Test creating a task with networking specification."""
        task = Task(id="test_task")
        
        networking = NetworkingSpec(
            network_mode="vpc",
            allowed_ports=[443],
            egress_rules=["allow https outbound"]
        )
        
        task.networking.set_for_environment(networking, "cloud_native")
        
        networking_value = task.networking.get_value_for("cloud_native")
        assert isinstance(networking_value, NetworkingSpec)
        assert networking_value.network_mode == "vpc"
        assert networking_value.allowed_ports == [443]
        assert networking_value.egress_rules == ["allow https outbound"]


class TestWorkflowEnvironmentSpecific:
    """Test Workflow with environment-specific fields."""
    
    def test_workflow_with_environment_specific_execution_model(self):
        """Test creating a workflow with environment-specific execution model."""
        workflow = Workflow(name="test_workflow")
        
        # Set different execution models for different environments
        workflow.execution_model.set_for_environment("shared_filesystem", "shared_filesystem")
        workflow.execution_model.set_for_environment("distributed_computing", "distributed_computing")
        workflow.execution_model.set_for_environment("cloud_native", "cloud_native")
        
        # Verify environment-specific values
        assert workflow.execution_model.get_value_for("shared_filesystem") == "shared_filesystem"
        assert workflow.execution_model.get_value_for("distributed_computing") == "distributed_computing"
        assert workflow.execution_model.get_value_for("cloud_native") == "cloud_native"
        
    def test_workflow_get_for_environment(self):
        """Test getting workflow configuration for specific environment."""
        workflow = Workflow(name="test_workflow")
        
        # Add a task with environment-specific values
        task = Task(id="test_task")
        task.cpu.set_for_environment(4, "shared_filesystem")
        task.cpu.set_for_environment(8, "distributed_computing")
        task.mem_mb.set_for_environment(8192, "distributed_computing")
        
        workflow.add_task(task)
        
        # Get configuration for shared_filesystem environment
        shared_config = workflow.get_for_environment("shared_filesystem")
        assert shared_config["name"] == "test_workflow"
        assert "test_task" in shared_config["tasks"]
        assert shared_config["tasks"]["test_task"]["cpu"] == 4
        assert shared_config["tasks"]["test_task"]["mem_mb"] == 4096  # Default value
        
        # Get configuration for distributed_computing environment
        distributed_config = workflow.get_for_environment("distributed_computing")
        assert distributed_config["tasks"]["test_task"]["cpu"] == 8
        assert distributed_config["tasks"]["test_task"]["mem_mb"] == 8192


class TestSerialization:
    """Test serialization of environment-specific values."""
    
    def test_workflow_serialization(self):
        """Test that workflows with environment-specific values serialize correctly."""
        workflow = Workflow(name="test_workflow")
        
        # Add a task with environment-specific values
        task = Task(id="test_task")
        task.cpu.set_for_environment(4, ["shared_filesystem"])
        task.cpu.set_for_environment(8, ["distributed_computing"])
        
        workflow.add_task(task)
        
        # Serialize to dict
        workflow_dict = workflow.to_dict()
        
        # Verify serialization
        assert "tasks" in workflow_dict
        assert "test_task" in workflow_dict["tasks"]
        assert "cpu" in workflow_dict["tasks"]["test_task"]
        
        # Deserialize
        workflow2 = Workflow.from_dict(workflow_dict)
        
        # Verify deserialization
        assert workflow2.tasks["test_task"].cpu.get_value_for("shared_filesystem") == 4
        assert workflow2.tasks["test_task"].cpu.get_value_for("distributed_computing") == 8 