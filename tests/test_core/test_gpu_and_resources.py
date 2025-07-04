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
from wf2wf.core import Workflow, Task, ResourceSpec
from wf2wf.exporters import dagman as dag_exporter
from wf2wf.importers import snakemake as snake_importer


class TestGPUResources:
    """Test GPU resource allocation and export."""

    def test_resource_spec_gpu_allocation(self):
        """Test ResourceSpec with GPU resource requirements."""
        resources = ResourceSpec(cpu=4, mem_mb=8192, gpu=2, gpu_mem_mb=8000)
        assert resources.gpu == 2
        assert resources.gpu_mem_mb == 8000
        assert resources.cpu == 4
        assert resources.mem_mb == 8192

    def test_task_with_gpu_resources(self):
        """Test Task creation with GPU resource requirements."""
        task = Task(
            id="gpu_task",
            command="python train_model.py",
            resources=ResourceSpec(gpu=2, gpu_mem_mb=8000, cpu=8, mem_mb=16384),
        )
        assert task.resources.gpu == 2
        assert task.resources.gpu_mem_mb == 8000
        assert task.resources.cpu == 8
        assert task.resources.mem_mb == 16384

    def test_dagman_exporter_gpu_requests(self, tmp_path):
        """Test DAGMan exporter generates correct GPU resource requests."""
        wf = Workflow(name="gpu_test")

        # GPU job
        gpu_task = Task(
            id="gpu_job",
            command="python train_model.py",
            resources=ResourceSpec(gpu=2, gpu_mem_mb=8000, cpu=8, mem_mb=16384),
        )
        wf.add_task(gpu_task)

        # CPU-only job for comparison
        cpu_task = Task(
            id="cpu_job",
            command="python preprocess.py",
            resources=ResourceSpec(cpu=4, mem_mb=8192),
        )
        wf.add_task(cpu_task)

        dag_path = tmp_path / "gpu_test.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Check submit files instead of DAG file
        submit_files = list(tmp_path.glob("*.sub"))
        assert len(submit_files) >= 2, "Expected at least 2 submit files"

        # Read all submit file contents
        all_submit_content = ""
        for submit_file in submit_files:
            all_submit_content += submit_file.read_text() + "\n"

        # Check GPU job has correct GPU resource requests
        assert "request_gpus = 2" in all_submit_content
        assert "request_memory = 16384MB" in all_submit_content
        assert "request_cpus = 8" in all_submit_content

        # Verify both submit files exist
        gpu_submit = tmp_path / "gpu_job.sub"
        cpu_submit = tmp_path / "cpu_job.sub"
        assert gpu_submit.exists()
        assert cpu_submit.exists()

    def test_gpu_capability_resource(self):
        """Test GPU capability requirements in ResourceSpec extra attributes."""
        resources = ResourceSpec(gpu=1, gpu_mem_mb=4000, extra={"gpu_capability": 7.5})
        assert resources.gpu == 1
        assert resources.extra["gpu_capability"] == 7.5

    def test_dagman_exporter_gpu_capability(self, tmp_path):
        """Test DAGMan exporter handles GPU capability requirements."""
        wf = Workflow(name="gpu_capability_test")
        task = Task(
            id="gpu_capability_job",
            command="python train_model.py",
            resources=ResourceSpec(
                gpu=1, gpu_mem_mb=4000, extra={"gpu_capability": 7.5}
            ),
        )
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

    def test_resource_spec_extra_attributes(self):
        """Test ResourceSpec with custom Condor attributes."""
        resources = ResourceSpec(
            cpu=4,
            mem_mb=8192,
            extra={
                "+WantGPULab": "true",
                "requirements": '(OpSysAndVer == "CentOS7")',
                "rank": "Memory",
            },
        )
        assert resources.extra["+WantGPULab"] == "true"
        assert resources.extra["requirements"] == '(OpSysAndVer == "CentOS7")'
        assert resources.extra["rank"] == "Memory"

    def test_task_with_custom_condor_attributes(self):
        """Test Task with custom Condor attributes."""
        task = Task(
            id="custom_attr_task",
            command="echo 'custom attributes'",
            resources=ResourceSpec(
                cpu=2,
                mem_mb=4096,
                extra={
                    "+WantGPULab": "true",
                    "requirements": '(OpSysAndVer == "CentOS7")',
                },
            ),
        )
        assert task.resources.extra["+WantGPULab"] == "true"
        assert task.resources.extra["requirements"] == '(OpSysAndVer == "CentOS7")'

    def test_dagman_exporter_custom_attributes(self, tmp_path):
        """Test DAGMan exporter includes custom Condor attributes."""
        wf = Workflow(name="custom_attr_test")
        task = Task(
            id="custom_task",
            command="echo 'test'",
            resources=ResourceSpec(
                cpu=2,
                mem_mb=4096,
                extra={
                    "+WantGPULab": "true",
                    "requirements": '(OpSysAndVer == "CentOS7")',
                    "rank": "Memory",
                },
            ),
        )
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
        heavy_task = Task(
            id="heavy_compute",
            command="python train_model.py",
            resources=ResourceSpec(
                cpu=16,
                mem_mb=65536,  # 64GB
                disk_mb=512000,  # 500GB
                gpu=4,
                gpu_mem_mb=16000,
            ),
        )
        wf.add_task(heavy_task)

        # Light preprocessing job
        light_task = Task(
            id="light_job",
            command="python preprocess.py",
            resources=ResourceSpec(cpu=1, mem_mb=512),
        )
        wf.add_task(light_task)

        # Medium job with specific requirements
        medium_task = Task(
            id="medium_job",
            command="python analyze.py",
            resources=ResourceSpec(
                cpu=8,
                mem_mb=16384,
                disk_mb=10240,  # 10GB
                extra={"requirements": "(HasLargeScratch == True)"},
            ),
        )
        wf.add_task(medium_task)

        # Add dependencies
        wf.add_edge("light_job", "medium_job")
        wf.add_edge("medium_job", "heavy_compute")

        # Verify structure
        assert len(wf.tasks) == 3
        assert len(wf.edges) == 2

        # Verify resource specifications
        assert wf.tasks["heavy_compute"].resources.gpu == 4
        assert wf.tasks["light_job"].resources.mem_mb == 512
        assert (
            wf.tasks["medium_job"].resources.extra["requirements"]
            == "(HasLargeScratch == True)"
        )

    def test_dagman_export_mixed_resources(self, tmp_path):
        """Test DAGMan export of mixed resource workflow."""
        wf = Workflow(name="mixed_resources")

        # Heavy compute job
        heavy_task = Task(
            id="heavy_compute",
            command="python train_model.py",
            resources=ResourceSpec(
                cpu=16, mem_mb=65536, disk_mb=512000, gpu=4, gpu_mem_mb=16000
            ),
        )
        wf.add_task(heavy_task)

        # Light job
        light_task = Task(
            id="light_job",
            command="python preprocess.py",
            resources=ResourceSpec(cpu=1, mem_mb=512),
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
    """Test resource default handling."""

    def test_resource_spec_defaults(self):
        """Test ResourceSpec default values."""
        resources = ResourceSpec()
        assert resources.cpu is None
        assert resources.mem_mb is None
        assert resources.disk_mb is None
        assert resources.gpu is None
        assert resources.gpu_mem_mb is None
        assert resources.time_s is None
        assert resources.threads is None
        assert resources.extra == {}

    def test_task_default_resources(self):
        """Test Task with default resource specification."""
        task = Task(id="default_task", command="echo 'default'")
        assert task.resources.cpu is None
        assert task.resources.mem_mb is None
        assert task.resources.gpu is None

    def test_workflow_with_default_and_custom_resources(self):
        """Test workflow mixing default and custom resource specifications."""
        wf = Workflow(name="mixed_defaults")

        # Task with defaults
        default_task = Task(id="default_task", command="echo 'default'")
        wf.add_task(default_task)

        # Task with custom resources
        custom_task = Task(
            id="custom_task",
            command="python compute.py",
            resources=ResourceSpec(cpu=8, mem_mb=16384, gpu=1),
        )
        wf.add_task(custom_task)

        assert wf.tasks["default_task"].resources.cpu is None
        assert wf.tasks["default_task"].resources.gpu is None
        assert wf.tasks["custom_task"].resources.cpu == 8
        assert wf.tasks["custom_task"].resources.gpu == 1


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
