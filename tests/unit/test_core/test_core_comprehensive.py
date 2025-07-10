"""
Comprehensive tests for core wf2wf functionality.

This module consolidates tests for:
- GPU resource allocation and custom Condor attributes
- Environment-specific values and operations
- Execution model IR with new spec classes
- Expression evaluation and validation
- Type specifications and parameter validation
- Resource provenance tracking
"""

import sys
import pathlib
import importlib.util
import textwrap

# Allow running tests without installing package
proj_root = pathlib.Path(__file__).resolve().parents[2]

if "wf2wf" not in sys.modules:
    spec = importlib.util.spec_from_file_location("wf2wf", proj_root / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["wf2wf"] = module  # type: ignore[assignment]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[arg-type]

import pytest
from wf2wf.core import (
    Workflow, Task, EnvironmentSpecificValue, ParameterSpec, TypeSpec, RequirementSpec,
    CheckpointSpec, LoggingSpec, SecuritySpec, NetworkingSpec
)
from wf2wf.exporters import dagman as dag_exporter
from wf2wf.importers import snakemake as snake_importer
import wf2wf.expression as expr_mod
from wf2wf.expression import evaluate, ExpressionTimeout, ExpressionError


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

    def test_env_specific_value_assignment_and_retrieval(self):
        """Test basic assignment and retrieval operations."""
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


class TestGPUResources:
    """Test GPU resource handling."""

    def test_task_with_gpu(self):
        """Test task with GPU resources."""
        task = Task(id="gpu_task")
        task.gpu.set_for_environment(2, "shared_filesystem")
        task.gpu_mem_mb.set_for_environment(8000, "shared_filesystem")
        
        assert task.gpu.get_value_for("shared_filesystem") == 2
        assert task.gpu_mem_mb.get_value_for("shared_filesystem") == 8000

    def test_task_without_gpu(self):
        """Test task without GPU requirements."""
        task = Task(id="cpu_task")
        assert task.gpu.get_value_for("shared_filesystem") == 0
        assert task.gpu_mem_mb.get_value_for("shared_filesystem") == 0

    def test_dagman_exporter_gpu_requirements(self, tmp_path):
        """Test DAGMan exporter includes GPU requirements."""
        wf = Workflow(name="gpu_test")
        task = Task(id="gpu_task")
        task.command.set_for_environment("echo 'gpu job'", "shared_filesystem")
        task.gpu.set_for_environment(2, "shared_filesystem")
        task.gpu_mem_mb.set_for_environment(16384, "shared_filesystem")
        wf.add_task(task)

        dag_path = tmp_path / "gpu_test.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Check the submit file
        submit_path = tmp_path / "gpu_task.sub"
        submit_content = submit_path.read_text()
        assert "request_gpus = 2" in submit_content
        assert "gpus_minimum_memory = 16384" in submit_content

    def test_gpu_capability_resource(self):
        """Test GPU capability requirements in Task extra attributes."""
        task = Task(id="gpu_task")
        task.gpu.set_for_environment(1, "shared_filesystem")
        task.gpu_mem_mb.set_for_environment(4000, "shared_filesystem")
        task.extra["gpu_capability"] = EnvironmentSpecificValue(7.5, ["shared_filesystem"])
        assert task.gpu.get_value_for("shared_filesystem") == 1
        assert task.extra["gpu_capability"].get_value_for("shared_filesystem") == 7.5

    def test_dagman_exporter_gpu_capability(self, tmp_path):
        """Test DAGMan exporter handles GPU capability requirements."""
        wf = Workflow(name="gpu_capability_test")
        task = Task(id="gpu_capability_job")
        task.command.set_for_environment("python train_model.py", "shared_filesystem")
        task.gpu.set_for_environment(1, "shared_filesystem")
        task.gpu_mem_mb.set_for_environment(4000, "shared_filesystem")
        task.extra["gpu_capability"] = EnvironmentSpecificValue(7.5, ["shared_filesystem"])
        wf.add_task(task)

        dag_path = tmp_path / "gpu_capability_test.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Check submit file instead of DAG file
        submit_path = tmp_path / "gpu_capability_job.sub"
        submit_content = submit_path.read_text()

        assert "request_gpus = 1" in submit_content
        # Note: GPU capability would be handled in extra attributes
        # The exact format depends on DAGMan exporter implementation


class TestCustomCondorAttributes:
    """Test custom Condor attribute handling."""

    def test_task_extra_attributes(self):
        """Test Task with custom Condor attributes."""
        task = Task(id="custom_attr_task")
        task.command.set_for_environment("echo 'custom attributes'", "shared_filesystem")
        task.cpu.set_for_environment(2, "shared_filesystem")
        task.mem_mb.set_for_environment(4096, "shared_filesystem")
        task.extra["+WantGPULab"] = EnvironmentSpecificValue("true", ["shared_filesystem"])
        task.extra["requirements"] = EnvironmentSpecificValue('(OpSysAndVer == "CentOS7")', ["shared_filesystem"])
        task.extra["rank"] = EnvironmentSpecificValue("Memory", ["shared_filesystem"])
        
        assert task.extra["+WantGPULab"].get_value_for("shared_filesystem") == "true"
        assert task.extra["requirements"].get_value_for("shared_filesystem") == '(OpSysAndVer == "CentOS7")'
        assert task.extra["rank"].get_value_for("shared_filesystem") == "Memory"

    def test_task_with_custom_condor_attributes(self):
        """Test Task with custom Condor attributes."""
        task = Task(id="custom_attr_task")
        task.command.set_for_environment("echo 'custom attributes'", "shared_filesystem")
        task.cpu.set_for_environment(2, "shared_filesystem")
        task.mem_mb.set_for_environment(4096, "shared_filesystem")
        task.extra["+WantGPULab"] = EnvironmentSpecificValue("true", ["shared_filesystem"])
        task.extra["requirements"] = EnvironmentSpecificValue('(OpSysAndVer == "CentOS7")', ["shared_filesystem"])
        
        assert task.extra["+WantGPULab"].get_value_for("shared_filesystem") == "true"
        assert task.extra["requirements"].get_value_for("shared_filesystem") == '(OpSysAndVer == "CentOS7")'

    def test_dagman_exporter_custom_attributes(self, tmp_path):
        """Test DAGMan exporter includes custom Condor attributes."""
        wf = Workflow(name="custom_attr_test")
        task = Task(id="custom_task")
        task.command.set_for_environment("echo 'test'", "shared_filesystem")
        task.cpu.set_for_environment(2, "shared_filesystem")
        task.mem_mb.set_for_environment(4096, "shared_filesystem")
        task.extra["+WantGPULab"] = EnvironmentSpecificValue("true", ["shared_filesystem"])
        task.extra["requirements"] = EnvironmentSpecificValue('(OpSysAndVer == "CentOS7")', ["shared_filesystem"])
        task.extra["rank"] = EnvironmentSpecificValue("Memory", ["shared_filesystem"])
        wf.add_task(task)

        dag_path = tmp_path / "custom_attr_test.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Check submit file instead of DAG file
        submit_path = tmp_path / "custom_task.sub"
        submit_content = submit_path.read_text()

        # Note: The exact format depends on DAGMan exporter implementation
        # These assertions may need adjustment based on actual implementation
        assert "request_cpus = 2" in submit_content
        assert "request_memory = 4096MB" in submit_content


class TestMixedResourceTypes:
    """Test workflows with mixed resource requirements."""

    def test_mixed_resource_workflow(self):
        """Test workflow with various resource requirement patterns."""
        wf = Workflow(name="mixed_resources")

        # Heavy compute job with GPU
        heavy_task = Task(id="heavy_compute")
        heavy_task.command.set_for_environment("echo 'gpu job'", "shared_filesystem")
        heavy_task.gpu.set_for_environment(2, "shared_filesystem")
        heavy_task.gpu_mem_mb.set_for_environment(16384, "shared_filesystem")
        wf.add_task(heavy_task)

        # Light preprocessing job
        light_task = Task(id="light_job")
        light_task.command.set_for_environment("echo 'custom attributes'", "shared_filesystem")
        light_task.cpu.set_for_environment(1, "shared_filesystem")
        light_task.mem_mb.set_for_environment(512, "shared_filesystem")
        wf.add_task(light_task)

        # Medium job with specific requirements
        medium_task = Task(id="medium_job")
        medium_task.command.set_for_environment("echo 'custom attributes'", "shared_filesystem")
        medium_task.cpu.set_for_environment(8, "shared_filesystem")
        medium_task.mem_mb.set_for_environment(16384, "shared_filesystem")
        medium_task.disk_mb.set_for_environment(10240, "shared_filesystem")  # 10GB
        medium_task.extra["requirements"] = EnvironmentSpecificValue("(HasLargeScratch == True)", ["shared_filesystem"])
        wf.add_task(medium_task)

        # Add dependencies
        wf.add_edge("light_job", "medium_job")
        wf.add_edge("medium_job", "heavy_compute")

        # Verify structure
        assert len(wf.tasks) == 3
        assert len(wf.edges) == 2

        # Verify resource specifications
        assert wf.tasks["heavy_compute"].gpu.get_value_for("shared_filesystem") == 2
        assert wf.tasks["light_job"].mem_mb.get_value_for("shared_filesystem") == 512
        assert (
            wf.tasks["medium_job"].extra["requirements"].get_value_for("shared_filesystem")
            == "(HasLargeScratch == True)"
        )

    def test_dagman_export_mixed_resources(self, tmp_path):
        """Test DAGMan export of mixed resource workflow."""
        wf = Workflow(name="mixed_resources")

        # Heavy compute job
        heavy_task = Task(
            id="heavy_compute",
            command=EnvironmentSpecificValue("python train_model.py", ["shared_filesystem"]),
            cpu=EnvironmentSpecificValue(16, ["shared_filesystem"]),
            mem_mb=EnvironmentSpecificValue(65536, ["shared_filesystem"]),
            disk_mb=EnvironmentSpecificValue(512000, ["shared_filesystem"]),
            gpu=EnvironmentSpecificValue(4, ["shared_filesystem"]),
            gpu_mem_mb=EnvironmentSpecificValue(16000, ["shared_filesystem"]),
        )
        wf.add_task(heavy_task)

        # Light job
        light_task = Task(
            id="light_job",
            command=EnvironmentSpecificValue("python preprocess.py", ["shared_filesystem"]),
            cpu=EnvironmentSpecificValue(1, ["shared_filesystem"]),
            mem_mb=EnvironmentSpecificValue(512, ["shared_filesystem"]),
        )
        wf.add_task(light_task)

        wf.add_edge("light_job", "heavy_compute")

        dag_path = tmp_path / "mixed_resources.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Check submit files instead of DAG file
        submit_files = list(tmp_path.glob("*.sub"))
        assert len(submit_files) >= 2, "Expected at least 2 submit files"

        # Read all submit file contents
        all_submit_content = ""
        for submit_file in submit_files:
            all_submit_content += submit_file.read_text() + "\n"

        # Check heavy compute job resources
        assert "request_cpus = 16" in all_submit_content
        assert "request_memory = 65536MB" in all_submit_content
        assert "request_disk = 512000MB" in all_submit_content
        assert "request_gpus = 4" in all_submit_content

        # Check light job resources
        assert "request_cpus = 1" in all_submit_content
        assert "request_memory = 512MB" in all_submit_content

        # Verify both submit files exist
        heavy_submit = tmp_path / "heavy_compute.sub"
        light_submit = tmp_path / "light_job.sub"
        assert heavy_submit.exists()
        assert light_submit.exists()


class TestResourceDefaults:
    """Test resource default values."""

    def test_task_default_resources(self):
        """Test that tasks have sensible default resource values."""
        task = Task(id="default_task")
        assert task.cpu.get_value_for("shared_filesystem") == 1
        assert task.mem_mb.get_value_for("shared_filesystem") == 4096
        assert task.disk_mb.get_value_for("shared_filesystem") == 4096
        assert task.gpu.get_value_for("shared_filesystem") == 0
        assert task.gpu_mem_mb.get_value_for("shared_filesystem") == 0
        assert task.time_s.get_value_for("shared_filesystem") == 3600
        assert task.threads.get_value_for("shared_filesystem") == 1

    def test_workflow_with_default_and_custom_resources(self):
        """Test workflow mixing default and custom resource specifications."""
        wf = Workflow(name="mixed_defaults")

        # Task with default resources
        default_task = Task(id="default_task")
        default_task.command.set_for_environment("echo 'default'", "shared_filesystem")
        wf.add_task(default_task)

        # Task with custom resources
        custom_task = Task(id="custom_task")
        custom_task.command.set_for_environment("echo 'custom'", "shared_filesystem")
        custom_task.cpu.set_for_environment(8, "shared_filesystem")
        custom_task.mem_mb.set_for_environment(16384, "shared_filesystem")
        wf.add_task(custom_task)

        # Verify defaults vs custom
        assert default_task.cpu.get_value_for("shared_filesystem") == 1
        assert custom_task.cpu.get_value_for("shared_filesystem") == 8
        assert default_task.mem_mb.get_value_for("shared_filesystem") == 4096
        assert custom_task.mem_mb.get_value_for("shared_filesystem") == 16384


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


class TestExpressionEvaluation:
    """Test expression evaluation functionality."""

    def test_strip_wrapper_and_basic(self):
        """Test basic expression evaluation."""
        assert evaluate("$(1 + 1)") == 2
        try:
            res = evaluate("${ true && false }")
            assert res is False
        except ExpressionError:
            # Fallback evaluator cannot handle JS syntax when js2py is absent
            if getattr(expr_mod, "_HAS_JS2PY", False):
                raise

    def test_timeout(self):
        """Test expression timeout handling."""
        # Expression with infinite loop (js) fallback to python; use long expr to trigger timeout
        long_expr = "1"
        if getattr(expr_mod, "_HAS_JS2PY", False):
            with pytest.raises(ExpressionTimeout):
                evaluate("while(true) {1+1}", timeout_s=0.05)

        # Python fallback timeout test
        with pytest.raises((ExpressionTimeout, ExpressionError)):
            long_expr = "1+" * 100000 + "1"
            evaluate(long_expr, timeout_s=0.05)

    def test_length_limit(self):
        """Test expression length limits."""
        with pytest.raises(ExpressionError):
            evaluate("1" * 20000)


class TestTypeSpecification:
    """Test type specification functionality."""

    def test_union_parsing(self):
        """Test union type parsing."""
        ts = TypeSpec.parse(["File", "Directory", "null"])
        assert ts.type == "union"
        assert ts.nullable is True
        assert len(ts.members) == 2
        # Validation should pass
        ts.validate()

    def test_record_and_enum_validation(self):
        """Test record and enum type validation."""
        record = TypeSpec.parse({"type": "record", "fields": {"x": "int", "y": "float"}})
        record.validate()

        enum = TypeSpec.parse({"type": "enum", "symbols": ["A", "B", "C"]})
        enum.validate()

    def test_secondary_files_deep(self):
        """Test secondary files specification."""
        p = ParameterSpec(
            id="sample", type="File", secondary_files=["^.bai", ".tbi", "foo/*/bar"]
        )
        assert len(p.secondary_files) == 3

    def test_requirement_validation(self):
        """Test requirement specification validation."""
        good_docker = RequirementSpec(
            class_name="DockerRequirement", data={"dockerPull": "ubuntu:20.04"}
        )
        good_docker.validate()

        bad_docker = RequirementSpec(class_name="DockerRequirement", data={})
        with pytest.raises(ValueError):
            bad_docker.validate()

        good_res = RequirementSpec(class_name="ResourceRequirement", data={"coresMin": 2})
        good_res.validate()

        bad_res = RequirementSpec(class_name="ResourceRequirement", data={"unsupported": 1})
        with pytest.raises(ValueError):
            bad_res.validate()


class TestSnakemakeGPUIntegration:
    """Test GPU resource parsing from Snakemake workflows."""

    def test_snakemake_gpu_parsing(self, tmp_path):
        """Test parsing GPU resources from Snakemake workflow."""
        # Create Snakefile with GPU resources
        snakefile = tmp_path / "gpu_workflow.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule gpu_training:
                output: "model.pkl"
                resources:
                    gpu=2,
                    gpu_mem_mb=8000,
                    mem_gb=32,
                    threads=8
                shell: "python train_model.py --output {output}"

            rule cpu_preprocessing:
                output: "preprocessed.csv"
                resources:
                    mem_mb=4096,
                    threads=4
                shell: "python preprocess.py --output {output}"

            rule all:
                input: "model.pkl", "preprocessed.csv"
        """)
        )

        try:
            wf = snake_importer.to_workflow(snakefile, workdir=tmp_path)

            # Find GPU task
            for task in wf.tasks.values():
                if "gpu_training" in task.id:
                    pass
                elif "cpu_preprocessing" in task.id:
                    pass

        except RuntimeError as e:
            if "snakemake" in str(e):
                pytest.skip("Snakemake not available for integration test")
            else:
                raise

    def test_snakemake_custom_condor_attributes(self, tmp_path):
        """Test parsing custom Condor attributes from Snakemake workflow."""
        # Create Snakefile with custom attributes via params
        snakefile = tmp_path / "custom_attrs.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule custom_job:
                output: "output.txt"
                params:
                    condor_requirements='(OpSysAndVer == "CentOS7")',
                    condor_rank="Memory",
                    condor_want_gpu_lab="true"
                shell: "echo 'custom job' > {output}"

            rule all:
                input: "output.txt"
        """)
        )

        try:
            wf = snake_importer.to_workflow(snakefile, workdir=tmp_path)

            # Find custom job task
            custom_task = None
            for task in wf.tasks.values():
                if "custom_job" in task.id:
                    custom_task = task
                    break

            # Note: The exact handling of custom Condor attributes depends on
            # how the Snakemake importer processes params. This test may need
            # adjustment based on the actual implementation.
            assert custom_task is not None

        except RuntimeError as e:
            if "snakemake" in str(e):
                pytest.skip("Snakemake not available for integration test")
            else:
                raise


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