"""Tests for CLI integration and command-line interface functionality."""

import sys
import pathlib
import importlib.util
import pytest
import json

# Allow running tests without installing package
proj_root = pathlib.Path(__file__).resolve().parents[1]

if "wf2wf" not in sys.modules:
    spec = importlib.util.spec_from_file_location("wf2wf", proj_root / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["wf2wf"] = module  # type: ignore[assignment]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[arg-type]

from wf2wf.core import Workflow, Task
from wf2wf.exporters import dagman as dag_exporter

# Test if snakemake importer is available without importing it
import importlib.util
SNAKEMAKE_AVAILABLE = importlib.util.find_spec("wf2wf.importers.snakemake") is not None


class TestConfigurationFileHandling:
    """Test configuration file parsing and CLI argument precedence."""

    def test_workflow_config_storage(self):
        """Test that workflow configuration is properly stored."""
        config = {
            "default_memory": "8GB",
            "default_disk": "10GB",
            "default_cpus": 4,
            "conda_prefix": "/opt/conda/envs",
        }

        # Create metadata spec with config data
        from wf2wf.core import MetadataSpec
        metadata = MetadataSpec(format_specific={"config": config})
        
        wf = Workflow(name="config_test", metadata=metadata)
        assert wf.metadata.format_specific["config"]["default_memory"] == "8GB"
        assert wf.metadata.format_specific["config"]["default_disk"] == "10GB"
        assert wf.metadata.format_specific["config"]["default_cpus"] == 4
        assert wf.metadata.format_specific["config"]["conda_prefix"] == "/opt/conda/envs"

    def test_workflow_config_serialization(self):
        """Test workflow configuration serialization/deserialization."""
        config = {
            "memory_default": "16GB",
            "custom_attributes": {"requirements": '(OpSysAndVer == "CentOS7")'},
        }

        # Create metadata spec with config data
        from wf2wf.core import MetadataSpec
        metadata = MetadataSpec(format_specific={"config": config})
        
        wf = Workflow(name="serialization_test", metadata=metadata)

        # Convert to JSON and back
        wf_json = wf.to_json()
        wf_dict = json.loads(wf_json)

        assert wf_dict["metadata"]["format_specific"]["config"]["memory_default"] == "16GB"
        assert (
            wf_dict["metadata"]["format_specific"]["config"]["custom_attributes"]["requirements"]
            == '(OpSysAndVer == "CentOS7")'
        )

        # Reconstruct workflow
        wf_restored = Workflow.from_json(wf_json)
        assert wf_restored.metadata.format_specific["config"]["memory_default"] == "16GB"
        assert (
            wf_restored.metadata.format_specific["config"]["custom_attributes"]["requirements"]
            == '(OpSysAndVer == "CentOS7")'
        )

    def test_resource_defaults_application(self):
        """Test applying resource defaults to tasks without explicit resources."""
        wf = Workflow(name="defaults_test")

        # Task without explicit resources
        default_task = Task(id="default_task")
        default_task.command.set_for_environment("echo 'default'", "distributed_computing")
        wf.add_task(default_task)

        # Default resource values
        default_cpu = 4
        default_mem_mb = 8192
        default_disk_mb = 10240

        # Simulate applying defaults to tasks without explicit resources
        for task in wf.tasks.values():
            # Check if task has environment-specific values set
            if not task.cpu.has_environment_specific_value("distributed_computing"):
                task.cpu.set_for_environment(default_cpu, "distributed_computing")
            if not task.mem_mb.has_environment_specific_value("distributed_computing"):
                task.mem_mb.set_for_environment(default_mem_mb, "distributed_computing")
            if not task.disk_mb.has_environment_specific_value("distributed_computing"):
                task.disk_mb.set_for_environment(default_disk_mb, "distributed_computing")

        # Verify defaults were applied correctly
        assert wf.tasks["default_task"].cpu.get_value_with_default("distributed_computing") == 4
        assert wf.tasks["default_task"].mem_mb.get_value_with_default("distributed_computing") == 8192
        assert wf.tasks["default_task"].disk_mb.get_value_with_default("distributed_computing") == 10240

    def test_workflow_metadata_preservation(self):
        """Test that workflow metadata is preserved through operations."""
        metadata = {
            "author": "test_user",
            "description": "Test workflow for metadata preservation",
            "version": "1.0.0",
            "tags": ["test", "metadata"],
        }

        # Create metadata spec with meta data
        from wf2wf.core import MetadataSpec
        metadata_spec = MetadataSpec(format_specific={"meta": metadata})
        
        wf = Workflow(name="metadata_test", metadata=metadata_spec)

        # Add some tasks
        task1 = Task(id="task1")
        task1.command.set_for_environment("echo 'task1'", "distributed_computing")
        task2 = Task(id="task2")
        task2.command.set_for_environment("echo 'task2'", "distributed_computing")
        wf.add_task(task1)
        wf.add_task(task2)
        wf.add_edge("task1", "task2")

        # Metadata should be preserved
        assert wf.metadata.format_specific["meta"]["author"] == "test_user"
        assert wf.metadata.format_specific["meta"]["description"] == "Test workflow for metadata preservation"
        assert wf.metadata.format_specific["meta"]["version"] == "1.0.0"
        assert "test" in wf.metadata.format_specific["meta"]["tags"]
        assert "metadata" in wf.metadata.format_specific["meta"]["tags"]


class TestResourceDefaultsAndCustomization:
    """Test resource defaults and customization options."""

    def test_custom_condor_attributes_parsing(self):
        """Test parsing of custom Condor attributes from configuration."""
        custom_attrs = {
            "requirements": '(OpSysAndVer == "CentOS7")',
            "+WantGPULab": "true",
            "rank": "Memory",
            "+ProjectName": '"MyProject"',
        }

        task = Task(
            id="custom_attrs_task",
        )
        task.command.set_for_environment("echo 'custom attributes'", "distributed_computing")
        task.extra = custom_attrs

        assert task.extra["requirements"] == '(OpSysAndVer == "CentOS7")'
        assert task.extra["+WantGPULab"] == "true"
        assert task.extra["rank"] == "Memory"
        assert task.extra["+ProjectName"] == '"MyProject"'

    def test_dagman_export_custom_attributes(self, tmp_path):
        """Test that custom Condor attributes are exported to DAG file."""
        wf = Workflow(name="custom_attrs_test")

        custom_attrs = {
            "requirements": "(HasLargeScratch == True)",
            "+WantGPULab": "true",
        }

        task = Task(
            id="custom_task",
        )
        task.command.set_for_environment("python gpu_analysis.py", "distributed_computing")
        task.cpu.set_for_environment(4, "distributed_computing")
        task.mem_mb.set_for_environment(8192, "distributed_computing")
        task.gpu.set_for_environment(1, "distributed_computing")
        task.extra = custom_attrs
        wf.add_task(task)

        dag_path = tmp_path / "custom_attrs.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Check submit file for custom attributes
        submit_path = tmp_path / "custom_task.sub"
        submit_content = submit_path.read_text()

        # Check that custom attributes are included
        assert "requirements = (HasLargeScratch == True)" in submit_content
        assert "+WantGPULab = true" in submit_content

        # Check that standard resources are also included
        assert "request_cpus = 4" in submit_content
        assert "request_memory = 8192MB" in submit_content
        assert "request_gpus = 1" in submit_content

    def test_mixed_resource_specifications(self):
        """Test mixing standard and custom resource specifications."""
        task = Task(id="mixed_resources")
        task.command.set_for_environment("python complex_job.py", "distributed_computing")
        task.cpu.set_for_environment(16, "distributed_computing")
        task.mem_mb.set_for_environment(32768, "distributed_computing")
        task.disk_mb.set_for_environment(100000, "distributed_computing")
        task.gpu.set_for_environment(2, "distributed_computing")
        task.gpu_mem_mb.set_for_environment(8000, "distributed_computing")
        task.extra = {
                    "requirements": '(OpSysAndVer == "CentOS7")',
                    "+WantGPULab": "true",
                    "rank": "Memory",
        }

        # Standard resources
        assert task.cpu.get_value_with_default("distributed_computing") == 16
        assert task.mem_mb.get_value_with_default("distributed_computing") == 32768
        assert task.disk_mb.get_value_with_default("distributed_computing") == 100000
        assert task.gpu.get_value_with_default("distributed_computing") == 2
        assert task.gpu_mem_mb.get_value_with_default("distributed_computing") == 8000
        assert task.extra["requirements"] == '(OpSysAndVer == "CentOS7")'
        assert task.extra["+WantGPULab"] == "true"
        assert task.extra["rank"] == "Memory"


class TestWorkflowValidationAndErrorHandling:
    """Test workflow validation and error handling."""

    def test_invalid_json_config_handling(self):
        """Test handling of invalid JSON in configuration."""
        # This would typically be tested at the CLI level, but we can test
        # the core functionality of handling malformed config

        # Valid JSON should work
        valid_config = '{"default_memory": "8GB", "default_cpus": 4}'
        config_dict = json.loads(valid_config)
        
        # Create metadata spec with config data
        from wf2wf.core import MetadataSpec
        metadata = MetadataSpec(format_specific={"config": config_dict})
        
        wf = Workflow(name="valid_config", metadata=metadata)
        assert wf.metadata.format_specific["config"]["default_memory"] == "8GB"
        assert wf.metadata.format_specific["config"]["default_cpus"] == 4

        # Invalid JSON should raise appropriate error
        invalid_config = (
            '{"default_memory": "8GB", "default_cpus": 4'  # Missing closing brace
        )
        with pytest.raises(json.JSONDecodeError):
            json.loads(invalid_config)

    def test_resource_validation_edge_cases(self):
        """Test resource validation with edge cases."""
        # Zero resources should be allowed
        task_zero = Task(id="zero_resources")
        task_zero.command.set_for_environment("echo 'minimal'", "distributed_computing")
        task_zero.cpu.set_for_environment(0, "distributed_computing")
        task_zero.mem_mb.set_for_environment(0, "distributed_computing")
        task_zero.disk_mb.set_for_environment(0, "distributed_computing")
        assert task_zero.cpu.get_value_with_default("distributed_computing") == 0
        assert task_zero.mem_mb.get_value_with_default("distributed_computing") == 0
        assert task_zero.disk_mb.get_value_with_default("distributed_computing") == 0

        # Large resource values should be allowed
        task_large = Task(id="large_resources")
        task_large.command.set_for_environment("echo 'large'", "distributed_computing")
        task_large.cpu.set_for_environment(128, "distributed_computing")
        task_large.mem_mb.set_for_environment(1048576, "distributed_computing")
        task_large.disk_mb.set_for_environment(10485760, "distributed_computing")
        assert task_large.cpu.get_value_with_default("distributed_computing") == 128
        assert task_large.mem_mb.get_value_with_default("distributed_computing") == 1048576
        assert task_large.disk_mb.get_value_with_default("distributed_computing") == 10485760

    def test_workflow_consistency_validation(self):
        """Test validation of workflow consistency."""
        wf = Workflow(name="consistency_test")

        # Add tasks
        task1 = Task(id="task1")
        task1.command.set_for_environment("echo 'task1'", "distributed_computing")
        task2 = Task(id="task2")
        task2.command.set_for_environment("echo 'task2'", "distributed_computing")
        task3 = Task(id="task3")
        task3.command.set_for_environment("echo 'task3'", "distributed_computing")

        wf.add_task(task1)
        wf.add_task(task2)
        wf.add_task(task3)

        # Add valid dependencies
        wf.add_edge("task1", "task2")
        wf.add_edge("task2", "task3")

        # Workflow should be valid
        assert len(wf.tasks) == 3
        assert len(wf.edges) == 2

        # Check that all referenced tasks exist
        for edge in wf.edges:
            assert edge.parent in wf.tasks
            assert edge.child in wf.tasks


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple features."""

    def test_complex_workflow_integration(self, tmp_path):
        """Test complex workflow with multiple features combined."""
        # Create metadata spec with config and meta data
        from wf2wf.core import MetadataSpec
        metadata = MetadataSpec(format_specific={
            "config": {"default_memory": "4GB", "conda_prefix": "/opt/conda/envs"},
            "meta": {"author": "integration_test", "version": "1.0"}
        })
        
        wf = Workflow(name="complex_integration", metadata=metadata)

        # Task with conda environment and custom resources
        conda_task = Task(
            id="conda_analysis",
        )
        conda_task.command.set_for_environment("python analyze.py", "distributed_computing")
        conda_task.cpu.set_for_environment(8, "distributed_computing")
        conda_task.mem_mb.set_for_environment(16384, "distributed_computing")
        conda_task.conda.set_for_environment("analysis_env.yaml", "distributed_computing")
        conda_task.extra = {"requirements": "(HasLargeScratch == True)"}
        wf.add_task(conda_task)

        # Task with container and GPU
        container_task = Task(
            id="gpu_processing",
        )
        container_task.command.set_for_environment("python gpu_process.py", "distributed_computing")
        container_task.cpu.set_for_environment(4, "distributed_computing")
        container_task.mem_mb.set_for_environment(8192, "distributed_computing")
        container_task.gpu.set_for_environment(1, "distributed_computing")
        container_task.gpu_mem_mb.set_for_environment(4000, "distributed_computing")
        container_task.container.set_for_environment("docker://gpu-python:latest", "distributed_computing")
        wf.add_task(container_task)

        # Regular task
        regular_task = Task(id="final_summary")
        regular_task.command.set_for_environment("python summarize.py", "distributed_computing")
        wf.add_task(regular_task)

        # Add dependencies
        wf.add_edge("conda_analysis", "gpu_processing")
        wf.add_edge("gpu_processing", "final_summary")

        # Export to DAG
        dag_path = tmp_path / "complex_integration.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        dag_content = dag_path.read_text()

        # Verify all tasks are present
        assert "JOB conda_analysis" in dag_content
        assert "JOB gpu_processing" in dag_content
        assert "JOB final_summary" in dag_content

        # Check submit files for universe and resource specifications
        conda_submit = tmp_path / "conda_analysis.sub"
        gpu_submit = tmp_path / "gpu_processing.sub"

        conda_content = conda_submit.read_text()
        gpu_content = gpu_submit.read_text()

        # Verify different universes are used appropriately
        assert "universe = vanilla" in conda_content  # For conda task
        assert "universe = docker" in gpu_content  # For container task

        # Verify resources
        assert "request_cpus = 8" in conda_content  # Conda task
        assert "request_cpus = 4" in gpu_content  # GPU task
        assert "request_gpus = 1" in gpu_content  # GPU task

        # Verify custom attributes
        assert "requirements = (HasLargeScratch == True)" in conda_content

        # Verify dependencies
        assert "PARENT conda_analysis CHILD gpu_processing" in dag_content
        assert "PARENT gpu_processing CHILD final_summary" in dag_content

    def test_end_to_end_workflow_processing(self, tmp_path):
        """Test end-to-end workflow processing from creation to export."""
        # Create a workflow programmatically
        wf = Workflow(name="end_to_end_test")

        # Add tasks with various configurations
        tasks_config = [
            {
                "id": "preprocess",
                "command": "python preprocess.py --input raw_data.txt --output clean_data.csv",
                "resources": {"cpu": 2, "mem_mb": 4096},
            },
            {
                "id": "analyze",
                "command": "python analyze.py --input clean_data.csv --output results.json",
                "environment": {"conda": "analysis_env.yaml"},
                "resources": {"cpu": 4, "mem_mb": 8192},
            },
            {
                "id": "visualize",
                "command": "python plot.py --input results.json --output plots.png",
                "environment": {"container": "docker://python:3.9-slim"},
                "resources": {"cpu": 1, "mem_mb": 2048},
            },
        ]

        # Add tasks to workflow
        for task_config in tasks_config:
            task = Task(id=task_config["id"])
            task.command.set_for_environment(task_config["command"], "distributed_computing")
            
            # Set resources
            if "resources" in task_config:
                resources = task_config["resources"]
                if "cpu" in resources:
                    task.cpu.set_for_environment(resources["cpu"], "distributed_computing")
                if "mem_mb" in resources:
                    task.mem_mb.set_for_environment(resources["mem_mb"], "distributed_computing")
            
            # Set environment-specific values
            if "environment" in task_config:
                env = task_config["environment"]
                if "conda" in env:
                    task.conda.set_for_environment(env["conda"], "distributed_computing")
                if "container" in env:
                    task.container.set_for_environment(env["container"], "distributed_computing")
            
            wf.add_task(task)

        # Add dependencies
        wf.add_edge("preprocess", "analyze")
        wf.add_edge("analyze", "visualize")

        # Validate workflow structure
        assert len(wf.tasks) == 3
        assert len(wf.edges) == 2

        # Export to DAG
        dag_path = tmp_path / "end_to_end.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Verify DAG file was created and has expected content
        assert dag_path.exists()
        dag_content = dag_path.read_text()

        # Check all jobs are present
        for task_config in tasks_config:
            assert f"JOB {task_config['id']}" in dag_content

        # Check dependencies are correct
        assert "PARENT preprocess CHILD analyze" in dag_content
        assert "PARENT analyze CHILD visualize" in dag_content

        # Check submit files for resource specifications
        preprocess_submit = tmp_path / "preprocess.sub"
        analyze_submit = tmp_path / "analyze.sub"
        visualize_submit = tmp_path / "visualize.sub"

        preprocess_content = preprocess_submit.read_text()
        analyze_content = analyze_submit.read_text()
        visualize_content = visualize_submit.read_text()

        # Verify resource specifications
        assert "request_cpus = 2" in preprocess_content  # preprocess
        assert "request_cpus = 4" in analyze_content  # analyze
        assert "request_cpus = 1" in visualize_content  # visualize

        # Verify different execution environments
        assert "universe = vanilla" in analyze_content  # conda task
        assert "universe = docker" in visualize_content  # container task
