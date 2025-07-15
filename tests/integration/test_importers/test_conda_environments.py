"""Tests for conda environment management functionality."""

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

try:
    from wf2wf.importers import snakemake as snake_importer

    SNAKEMAKE_AVAILABLE = True
except ImportError:
    SNAKEMAKE_AVAILABLE = False


class TestCondaEnvironmentSetup:
    """Test conda environment setup and management."""

    def test_conda_environment_spec_creation(self):
        """Test creating environment-specific conda environment."""
        task = Task(id="test_task")
        task.conda.set_for_environment("environment.yaml", "shared_filesystem")
        assert task.conda.get_value_for("shared_filesystem") == "environment.yaml"

    def test_task_with_conda_environment(self):
        """Test creating task with conda environment."""
        task = Task(id="conda_task")
        task.command.set_for_environment("python analyze.py", "shared_filesystem")
        task.conda.set_for_environment("analysis.yaml", "shared_filesystem")
        assert task.conda.get_value_for("shared_filesystem") == "analysis.yaml"
        assert task.container.get_value_for("shared_filesystem") is None

    def test_workflow_with_multiple_conda_environments(self):
        """Test workflow with multiple different conda environments."""
        wf = Workflow(name="multi_conda")

        # Task 1 with first environment
        task1 = Task(id="task1")
        task1.command.set_for_environment("python preprocess.py", "shared_filesystem")
        task1.conda.set_for_environment("preprocess_env.yaml", "shared_filesystem")
        wf.add_task(task1)

        # Task 2 with second environment
        task2 = Task(id="task2")
        task2.command.set_for_environment("python analyze.py", "shared_filesystem")
        task2.conda.set_for_environment("analysis_env.yaml", "shared_filesystem")
        wf.add_task(task2)

        # Task 3 reusing first environment
        task3 = Task(id="task3")
        task3.command.set_for_environment("python postprocess.py", "shared_filesystem")
        task3.conda.set_for_environment("preprocess_env.yaml", "shared_filesystem")
        wf.add_task(task3)

        wf.add_edge("task1", "task2")
        wf.add_edge("task2", "task3")

        assert len(wf.tasks) == 3
        assert wf.tasks["task1"].conda.get_value_for("shared_filesystem") == "preprocess_env.yaml"
        assert wf.tasks["task2"].conda.get_value_for("shared_filesystem") == "analysis_env.yaml"
        assert wf.tasks["task3"].conda.get_value_for("shared_filesystem") == "preprocess_env.yaml"

    def test_dagman_export_conda_environment(self, tmp_path):
        """Test DAGMan export with conda environment."""
        wf = Workflow(name="conda_workflow")

        task = Task(id="conda_analysis")
        task.command.set_for_environment("python analyze.py --input data.csv --output results.json", "distributed_computing")
        task.conda.set_for_environment("analysis_env.yaml", "distributed_computing")
        task.cpu.set_for_environment(4, "distributed_computing")
        task.mem_mb.set_for_environment(8192, "distributed_computing")
        wf.add_task(task)

        dag_path = tmp_path / "conda_workflow.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Check submit file instead of DAG file
        submit_path = tmp_path / "conda_analysis.sub"
        submit_content = submit_path.read_text()

        # Check basic submit file structure
        assert "universe = vanilla" in submit_content
        assert "request_cpus = 4" in submit_content
        assert "request_memory = 8192MB" in submit_content

        # Check that script was generated
        scripts_dir = tmp_path / "scripts"
        script_files = list(scripts_dir.glob("conda_analysis.*"))
        assert len(script_files) >= 1

    def test_conda_with_resource_specifications(self):
        """Test conda environment combined with resource specifications."""
        task = Task(id="resource_conda_task")
        task.command.set_for_environment("python intensive_analysis.py", "shared_filesystem")
        task.conda.set_for_environment("gpu_env.yaml", "shared_filesystem")
        task.cpu.set_for_environment(16, "shared_filesystem")
        task.mem_mb.set_for_environment(32768, "shared_filesystem")
        task.gpu.set_for_environment(2, "shared_filesystem")
        task.gpu_mem_mb.set_for_environment(8000, "shared_filesystem")

        assert task.conda.get_value_for("shared_filesystem") == "gpu_env.yaml"
        assert task.cpu.get_value_for("shared_filesystem") == 16
        assert task.mem_mb.get_value_for("shared_filesystem") == 32768
        assert task.gpu.get_value_for("shared_filesystem") == 2
        assert task.gpu_mem_mb.get_value_for("shared_filesystem") == 8000


class TestCondaEnvironmentParsing:
    """Test parsing conda environments from Snakemake workflows."""

    @pytest.mark.skipif(not SNAKEMAKE_AVAILABLE, reason="Snakemake not available")
    def test_snakemake_conda_environment_parsing(self, tmp_path):
        """Test parsing conda environment from Snakemake workflow."""
        # Create conda environment file
        env_file = tmp_path / "analysis.yaml"
        env_file.write_text(
            textwrap.dedent("""
            channels:
              - conda-forge
              - bioconda
            dependencies:
              - python=3.9
              - pandas
              - numpy
              - matplotlib
        """)
        )

        # Create Snakefile with conda environment
        snakefile = tmp_path / "conda_workflow.smk"
        snakefile.write_text(
            textwrap.dedent(f"""
            rule data_analysis:
                input: "data.csv"
                output: "results.json"
                conda: "{env_file}"
                resources:
                    mem_gb=8,
                    threads=4
                shell: "python analyze.py --input {{input}} --output {{output}}"

            rule visualization:
                input: "results.json"
                output: "plots.png"
                conda: "{env_file}"
                shell: "python plot.py --input {{input}} --output {{output}}"

            rule all:
                input: "results.json", "plots.png"
        """)
        )

        # Create dummy input file
        (tmp_path / "data.csv").write_text("col1,col2\n1,2\n3,4\n")

        try:
            wf = snake_importer.to_workflow(snakefile, workdir=tmp_path)

            # Find tasks with conda environments
            conda_tasks = []
            for task in wf.tasks.values():
                if task.conda.get_value_for("shared_filesystem"):
                    conda_tasks.append(task)

            assert (
                len(conda_tasks) >= 1
            ), f"Should have at least 1 task with conda environment, found {len(conda_tasks)}"

            # Check that conda environment path is preserved
            for task in conda_tasks:
                assert task.conda.get_value_for("shared_filesystem") == str(env_file)

        except RuntimeError as e:
            if "snakemake" in str(e):
                pytest.skip("Snakemake not available for integration test")
            else:
                raise

    @pytest.mark.skipif(not SNAKEMAKE_AVAILABLE, reason="Snakemake not available")
    def test_snakemake_conda_with_container_priority(self, tmp_path):
        """Test that container takes priority over conda when both are specified."""
        # Create conda environment file
        env_file = tmp_path / "analysis.yaml"
        env_file.write_text(
            textwrap.dedent("""
            channels:
              - conda-forge
            dependencies:
              - python=3.9
              - pandas
        """)
        )

        # Create Snakefile with both conda and container
        snakefile = tmp_path / "mixed_workflow.smk"
        snakefile.write_text(
            textwrap.dedent(f"""
            rule mixed_task:
                input: "data.csv"
                output: "results.json"
                conda: "{env_file}"
                container: "docker://python:3.9"
                shell: "python analyze.py --input {{input}} --output {{output}}"

            rule all:
                input: "results.json"
        """)
        )

        # Create dummy input file
        (tmp_path / "data.csv").write_text("col1,col2\n1,2\n3,4\n")

        try:
            wf = snake_importer.to_workflow(snakefile, workdir=tmp_path)

            # Find the mixed task
            mixed_task = None
            for task in wf.tasks.values():
                if task.id == "mixed_task":
                    mixed_task = task
                    break

            assert mixed_task is not None, "Should have found mixed_task"

            # In the new IR, both conda and container can coexist
            # The exporter will decide which to use based on the target environment
            assert mixed_task.conda.get_value_for("shared_filesystem") == str(env_file)
            assert mixed_task.container.get_value_for("shared_filesystem") == "docker://python:3.9"

        except RuntimeError as e:
            if "snakemake" in str(e):
                pytest.skip("Snakemake not available for integration test")
            else:
                raise


class TestCondaEnvironmentExport:
    """Test conda environment export functionality."""

    def test_conda_environment_export_vanilla_universe(self, tmp_path):
        """Test conda environment export with vanilla universe."""
        wf = Workflow(name="conda_vanilla")

        task = Task(id="conda_task")
        task.command.set_for_environment("python process.py", "distributed_computing")
        task.conda.set_for_environment("processing.yaml", "distributed_computing")
        task.cpu.set_for_environment(2, "distributed_computing")
        task.mem_mb.set_for_environment(4096, "distributed_computing")
        wf.add_task(task)

        dag_path = tmp_path / "conda_vanilla.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Check submit file
        submit_path = tmp_path / "conda_task.sub"
        submit_content = submit_path.read_text()

        # Should use vanilla universe for conda
        assert "universe = vanilla" in submit_content
        assert "request_cpus = 2" in submit_content
        assert "request_memory = 4096MB" in submit_content

        # Check that conda environment is referenced in the script
        scripts_dir = tmp_path / "scripts"
        script_files = list(scripts_dir.glob("conda_task.*"))
        assert len(script_files) >= 1

        # Read the script to check for conda activation
        script_content = script_files[0].read_text()
        assert "conda" in script_content.lower() or "environment" in script_content.lower()

    def test_multiple_conda_environments_export(self, tmp_path):
        """Test export with multiple different conda environments."""
        wf = Workflow(name="multi_conda_export")

        # Task 1 with first environment
        task1 = Task(id="preprocess")
        task1.command.set_for_environment("python preprocess.py", "shared_filesystem")
        task1.conda.set_for_environment("preprocess.yaml", "distributed_computing")
        wf.add_task(task1)

        # Task 2 with second environment
        task2 = Task(id="analyze")
        task2.command.set_for_environment("python analyze.py", "shared_filesystem")
        task2.conda.set_for_environment("analysis.yaml", "distributed_computing")
        wf.add_task(task2)

        wf.add_edge("preprocess", "analyze")

        dag_path = tmp_path / "multi_conda.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Check both submit files
        submit1_path = tmp_path / "preprocess.sub"
        submit2_path = tmp_path / "analyze.sub"

        assert submit1_path.exists()
        assert submit2_path.exists()

        # Both should use vanilla universe
        submit1_content = submit1_path.read_text()
        submit2_content = submit2_path.read_text()

        assert "universe = vanilla" in submit1_content
        assert "universe = vanilla" in submit2_content


class TestCondaEnvironmentValidation:
    """Test conda environment validation."""

    def test_conda_environment_file_validation(self):
        """Test validation of conda environment specifications."""
        # Test valid conda environment
        task = Task(id="valid_task")
        task.conda.set_for_environment("environment.yaml", "shared_filesystem")
        assert task.conda.get_value_for("shared_filesystem") == "environment.yaml"

        # Test conda environment name
        task2 = Task(id="name_task")
        task2.conda.set_for_environment("myenv", "shared_filesystem")
        assert task2.conda.get_value_for("shared_filesystem") == "myenv"

        # Test empty conda environment (should be allowed)
        task3 = Task(id="empty_task")
        task3.conda.set_for_environment("", "shared_filesystem")
        assert task3.conda.get_value_for("shared_filesystem") == ""

        # Test no conda environment
        task4 = Task(id="no_conda_task")
        assert task4.conda.get_value_for("shared_filesystem") is None

    def test_conda_with_resources_validation(self):
        """Test conda environment combined with resource validation."""
        task = Task(id="resource_task")
        task.command.set_for_environment("python validate.py", "shared_filesystem")
        task.conda.set_for_environment("validation.yaml", "shared_filesystem")
        task.cpu.set_for_environment(2, "shared_filesystem")
        task.mem_mb.set_for_environment(4096, "shared_filesystem")
        task.disk_mb.set_for_environment(10240, "shared_filesystem")

        # Validate that all fields are set correctly
        assert task.conda.get_value_for("shared_filesystem") == "validation.yaml"
        assert task.cpu.get_value_for("shared_filesystem") == 2
        assert task.mem_mb.get_value_for("shared_filesystem") == 4096
        assert task.disk_mb.get_value_for("shared_filesystem") == 10240

    def test_workflow_conda_environment_consistency(self):
        """Test workflow-level conda environment consistency."""
        wf = Workflow(name="consistent_conda")

        # Create tasks with consistent conda environment
        task1 = Task(id="task1")
        task1.conda.set_for_environment("shared_env.yaml", "shared_filesystem")
        wf.add_task(task1)

        task2 = Task(id="task2")
        task2.conda.set_for_environment("shared_env.yaml", "shared_filesystem")
        wf.add_task(task2)

        # Verify consistency
        env1 = task1.conda.get_value_for("shared_filesystem")
        env2 = task2.conda.get_value_for("shared_filesystem")
        assert env1 == env2 == "shared_env.yaml"
