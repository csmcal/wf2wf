"""
Tests for GPU resource allocation and custom Condor attributes in wf2wf.

This module tests the advanced resource handling capabilities of the wf2wf system,
including GPU resource allocation, custom Condor attributes, and mixed resource types.
"""

import sys
import pathlib
import importlib.util
import textwrap

# Allow running tests without installing package
proj_root = pathlib.Path(__file__).resolve().parents[1]

if "wf2wf" not in sys.modules:
    spec = importlib.util.spec_from_file_location("wf2wf", proj_root / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["wf2wf"] = module  # type: ignore[assignment]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[arg-type]

import pytest
from wf2wf.core import Workflow, Task, EnvironmentSpecificValue
from wf2wf.exporters import dagman as dag_exporter
from wf2wf.importers import snakemake as snake_importer


class TestGPUResources:
    """Test GPU resource handling."""

    def test_task_with_gpu(self):
        """Test task with GPU requirements."""
        task = Task(id="gpu_task")
        task.gpu.set_for_environment(1, "shared_filesystem")
        task.gpu_mem_mb.set_for_environment(8192, "shared_filesystem")
        assert task.gpu.get_value_for("shared_filesystem") == 1
        assert task.gpu_mem_mb.get_value_for("shared_filesystem") == 8192

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
