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

from wf2wf.core import Workflow, Task, EnvironmentSpec, ResourceSpec
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

        wf = Workflow(name="config_test", config=config)
        assert wf.config["default_memory"] == "8GB"
        assert wf.config["default_disk"] == "10GB"
        assert wf.config["default_cpus"] == 4
        assert wf.config["conda_prefix"] == "/opt/conda/envs"

    def test_workflow_config_serialization(self):
        """Test workflow configuration serialization/deserialization."""
        config = {
            "memory_default": "16GB",
            "custom_attributes": {"requirements": '(OpSysAndVer == "CentOS7")'},
        }

        wf = Workflow(name="serialization_test", config=config)

        # Convert to JSON and back
        wf_json = wf.to_json()
        wf_dict = json.loads(wf_json)

        assert wf_dict["config"]["memory_default"] == "16GB"
        assert (
            wf_dict["config"]["custom_attributes"]["requirements"]
            == '(OpSysAndVer == "CentOS7")'
        )

        # Reconstruct workflow
        wf_restored = Workflow.from_json(wf_json)
        assert wf_restored.config["memory_default"] == "16GB"
        assert (
            wf_restored.config["custom_attributes"]["requirements"]
            == '(OpSysAndVer == "CentOS7")'
        )

    def test_resource_defaults_application(self):
        """Test that resource defaults are properly applied."""
        # Create workflow with default resource configuration
        config = {"default_memory": "4GB", "default_disk": "20GB", "default_cpus": 2}
        wf = Workflow(name="defaults_test", config=config)

        # Task without explicit resources should use defaults when exported
        task_no_resources = Task(id="default_task", command="echo 'using defaults'")
        wf.add_task(task_no_resources)

        # Task with explicit resources should override defaults
        task_with_resources = Task(
            id="explicit_task",
            command="echo 'explicit resources'",
            resources=ResourceSpec(cpu=8, mem_mb=16384),
        )
        wf.add_task(task_with_resources)

        assert len(wf.tasks) == 2
        assert wf.tasks["default_task"].resources.cpu == 1  # Default from ResourceSpec
        assert wf.tasks["explicit_task"].resources.cpu == 8  # Explicit override

    def test_workflow_metadata_preservation(self):
        """Test that workflow metadata is preserved through operations."""
        metadata = {
            "author": "test_user",
            "description": "Test workflow for metadata preservation",
            "version": "1.0.0",
            "tags": ["test", "metadata"],
        }

        wf = Workflow(name="metadata_test", meta=metadata)

        # Add some tasks
        task1 = Task(id="task1", command="echo 'task1'")
        task2 = Task(id="task2", command="echo 'task2'")
        wf.add_task(task1)
        wf.add_task(task2)
        wf.add_edge("task1", "task2")

        # Metadata should be preserved
        assert wf.meta["author"] == "test_user"
        assert wf.meta["description"] == "Test workflow for metadata preservation"
        assert wf.meta["version"] == "1.0.0"
        assert "test" in wf.meta["tags"]
        assert "metadata" in wf.meta["tags"]


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
            command="echo 'custom attributes'",
            resources=ResourceSpec(extra=custom_attrs),
        )

        assert task.resources.extra["requirements"] == '(OpSysAndVer == "CentOS7")'
        assert task.resources.extra["+WantGPULab"] == "true"
        assert task.resources.extra["rank"] == "Memory"
        assert task.resources.extra["+ProjectName"] == '"MyProject"'

    def test_dagman_export_custom_attributes(self, tmp_path):
        """Test that custom Condor attributes are exported to DAG file."""
        wf = Workflow(name="custom_attrs_test")

        custom_attrs = {
            "requirements": "(HasLargeScratch == True)",
            "+WantGPULab": "true",
        }

        task = Task(
            id="custom_task",
            command="python gpu_analysis.py",
            resources=ResourceSpec(cpu=4, mem_mb=8192, gpu=1, extra=custom_attrs),
        )
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
        task = Task(
            id="mixed_resources",
            command="python complex_job.py",
            resources=ResourceSpec(
                cpu=16,
                mem_mb=32768,
                disk_mb=100000,
                gpu=2,
                gpu_mem_mb=8000,
                extra={
                    "requirements": '(OpSysAndVer == "CentOS7")',
                    "+WantGPULab": "true",
                    "rank": "Memory",
                },
            ),
        )

        # Standard resources
        assert task.resources.cpu == 16
        assert task.resources.mem_mb == 32768
        assert task.resources.disk_mb == 100000
        assert task.resources.gpu == 2
        assert task.resources.gpu_mem_mb == 8000

        # Custom attributes
        assert task.resources.extra["requirements"] == '(OpSysAndVer == "CentOS7")'
        assert task.resources.extra["+WantGPULab"] == "true"
        assert task.resources.extra["rank"] == "Memory"


class TestWorkflowValidationAndErrorHandling:
    """Test workflow validation and error handling."""

    def test_invalid_json_config_handling(self):
        """Test handling of invalid JSON in configuration."""
        # This would typically be tested at the CLI level, but we can test
        # the core functionality of handling malformed config

        # Valid JSON should work
        valid_config = '{"default_memory": "8GB", "default_cpus": 4}'
        config_dict = json.loads(valid_config)
        wf = Workflow(name="valid_config", config=config_dict)
        assert wf.config["default_memory"] == "8GB"
        assert wf.config["default_cpus"] == 4

        # Invalid JSON should raise appropriate error
        invalid_config = (
            '{"default_memory": "8GB", "default_cpus": 4'  # Missing closing brace
        )
        with pytest.raises(json.JSONDecodeError):
            json.loads(invalid_config)

    def test_resource_validation_edge_cases(self):
        """Test resource validation with edge cases."""
        # Zero resources should be allowed
        task_zero = Task(
            id="zero_resources",
            command="echo 'minimal'",
            resources=ResourceSpec(cpu=0, mem_mb=0, disk_mb=0),
        )
        assert task_zero.resources.cpu == 0
        assert task_zero.resources.mem_mb == 0
        assert task_zero.resources.disk_mb == 0

        # Large resource values should be allowed
        task_large = Task(
            id="large_resources",
            command="echo 'large'",
            resources=ResourceSpec(
                cpu=128, mem_mb=1048576, disk_mb=10485760
            ),  # 1TB RAM, 10TB disk
        )
        assert task_large.resources.cpu == 128
        assert task_large.resources.mem_mb == 1048576
        assert task_large.resources.disk_mb == 10485760

    def test_workflow_consistency_validation(self):
        """Test validation of workflow consistency."""
        wf = Workflow(name="consistency_test")

        # Add tasks
        task1 = Task(id="task1", command="echo 'task1'")
        task2 = Task(id="task2", command="echo 'task2'")
        task3 = Task(id="task3", command="echo 'task3'")

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
        wf = Workflow(
            name="complex_integration",
            config={"default_memory": "4GB", "conda_prefix": "/opt/conda/envs"},
            meta={"author": "integration_test", "version": "1.0"},
        )

        # Task with conda environment and custom resources
        conda_task = Task(
            id="conda_analysis",
            command="python analyze.py",
            environment=EnvironmentSpec(conda="analysis.yaml"),
            resources=ResourceSpec(
                cpu=8, mem_mb=16384, extra={"requirements": "(HasLargeScratch == True)"}
            ),
        )
        wf.add_task(conda_task)

        # Task with container and GPU
        container_task = Task(
            id="gpu_processing",
            command="python gpu_process.py",
            environment=EnvironmentSpec(
                container="docker://tensorflow/tensorflow:latest-gpu"
            ),
            resources=ResourceSpec(cpu=4, mem_mb=8192, gpu=1, gpu_mem_mb=4000),
        )
        wf.add_task(container_task)

        # Regular task
        regular_task = Task(id="final_summary", command="python summarize.py")
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
                "resources": ResourceSpec(cpu=2, mem_mb=4096),
            },
            {
                "id": "analyze",
                "command": "python analyze.py --input clean_data.csv --output results.json",
                "environment": EnvironmentSpec(conda="analysis_env.yaml"),
                "resources": ResourceSpec(cpu=4, mem_mb=8192),
            },
            {
                "id": "visualize",
                "command": "python plot.py --input results.json --output plots.png",
                "environment": EnvironmentSpec(container="docker://python:3.9-slim"),
                "resources": ResourceSpec(cpu=1, mem_mb=2048),
            },
        ]

        # Add tasks to workflow
        for task_config in tasks_config:
            task = Task(
                id=task_config["id"],
                command=task_config["command"],
                environment=task_config.get("environment"),
                resources=task_config["resources"],
            )
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
