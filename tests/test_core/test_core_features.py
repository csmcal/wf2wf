"""
Comprehensive tests for core wf2wf features:
- Containers/Conda environment handling
- Run-blocks & script directive processing
- Retry/priority preservation and export
- DAGMan exporter universe selection (docker/vanilla+Singularity)
"""

import os
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
from wf2wf.core import Workflow, Task, EnvironmentSpec
from wf2wf.exporters import dagman as dag_exporter
from wf2wf.importers import snakemake as snake_importer


class TestContainersConda:
    """Test container and conda environment handling."""

    def test_environment_spec_container_docker(self):
        """Test EnvironmentSpec with Docker container."""
        env = EnvironmentSpec(container="docker://python:3.9-slim")
        assert env.container == "docker://python:3.9-slim"
        assert env.conda is None

    def test_environment_spec_container_singularity(self):
        """Test EnvironmentSpec with Singularity container."""
        env = EnvironmentSpec(container="/path/to/image.sif")
        assert env.container == "/path/to/image.sif"
        assert env.conda is None

    def test_environment_spec_conda_file(self):
        """Test EnvironmentSpec with conda YAML file."""
        env = EnvironmentSpec(conda="environment.yaml")
        assert env.conda == "environment.yaml"
        assert env.container is None

    def test_environment_spec_conda_name(self):
        """Test EnvironmentSpec with conda environment name."""
        env = EnvironmentSpec(conda="myenv")
        assert env.conda == "myenv"
        assert env.container is None

    def test_container_priority_over_conda(self):
        """Test that container takes priority when both are specified."""
        env = EnvironmentSpec(
            container="docker://python:3.9-slim", conda="environment.yaml"
        )
        # Both should be preserved in the IR
        assert env.container == "docker://python:3.9-slim"
        assert env.conda == "environment.yaml"

    def test_dagman_exporter_docker_universe(self, tmp_path):
        """Test DAGMan exporter chooses docker universe for Docker containers."""
        wf = Workflow(name="docker_test")
        task = Task(
            id="docker_task",
            command="echo 'hello from docker'",
            environment=EnvironmentSpec(container="docker://python:3.9-slim"),
        )
        wf.add_task(task)

        dag_path = tmp_path / "docker_test.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Check the submit file, not the DAG file
        submit_path = tmp_path / "docker_task.sub"
        submit_content = submit_path.read_text()
        assert "universe = docker" in submit_content
        assert "docker_image = python:3.9-slim" in submit_content
        assert "universe = vanilla" not in submit_content

    def test_dagman_exporter_singularity_universe(self, tmp_path):
        """Test DAGMan exporter chooses vanilla universe + SingularityImage for Singularity."""
        wf = Workflow(name="singularity_test")
        task = Task(
            id="singularity_task",
            command="echo 'hello from singularity'",
            environment=EnvironmentSpec(container="/path/to/image.sif"),
        )
        wf.add_task(task)

        dag_path = tmp_path / "singularity_test.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Check the submit file, not the DAG file
        submit_path = tmp_path / "singularity_task.sub"
        submit_content = submit_path.read_text()
        assert "universe = vanilla" in submit_content
        assert '+SingularityImage = "/path/to/image.sif"' in submit_content
        assert "universe = docker" not in submit_content

    def test_dagman_exporter_conda_vanilla_universe(self, tmp_path):
        """Test DAGMan exporter uses vanilla universe for conda environments."""
        wf = Workflow(name="conda_test")
        task = Task(
            id="conda_task",
            command="echo 'hello from conda'",
            environment=EnvironmentSpec(conda="environment.yaml"),
        )
        wf.add_task(task)

        dag_path = tmp_path / "conda_test.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Check the submit file, not the DAG file
        submit_path = tmp_path / "conda_task.sub"
        submit_content = submit_path.read_text()
        assert "universe = vanilla" in submit_content
        assert "universe = docker" not in submit_content
        assert "+SingularityImage" not in submit_content

    def test_container_priority_snakemake_parsing(self, tmp_path):
        """Test that container_priority.smk correctly prioritizes container over conda."""
        # Create the test Snakefile
        snakefile = tmp_path / "container_priority.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule container_override:
                output: "container_test.txt"
                container: "docker://python:3.9-slim"
                conda: "environment.yaml"
                shell: "echo 'This job should run in python:3.9-slim' > {output}"

            rule all:
                input: "container_test.txt"
        """)
        )

        # Create dummy environment file
        env_file = tmp_path / "environment.yaml"
        env_file.write_text("name: test\ndependencies:\n  - python=3.9")

        # Parse with Snakemake importer
        try:
            wf = snake_importer.to_workflow(snakefile, workdir=tmp_path)

            # Find the container_override task
            container_task = None
            for task in wf.tasks.values():
                if "container_override" in task.id:
                    container_task = task
                    break

            assert container_task is not None, "container_override task not found"
            assert container_task.environment.container == "docker://python:3.9-slim"
            assert container_task.environment.conda == "environment.yaml"

            # Test DAG export prioritizes container
            dag_path = tmp_path / "test.dag"
            dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

            # Check the submit file for the container task
            submit_files = list(tmp_path.glob("*.sub"))
            assert len(submit_files) > 0, "No submit files found"

            # Find the submit file for the container_override task
            container_submit_content = None
            for submit_file in submit_files:
                content = submit_file.read_text()
                if "universe = docker" in content:
                    container_submit_content = content
                    break

            assert (
                container_submit_content is not None
            ), "Docker universe not found in any submit file"
            assert "docker_image = python:3.9-slim" in container_submit_content

        except RuntimeError as e:
            if "snakemake" in str(e):
                pytest.skip("Snakemake not available for integration test")
            else:
                raise


class TestRunBlocksAndScripts:
    """Test run-block and script directive processing."""

    def test_task_with_command(self):
        """Test basic task with shell command."""
        task = Task(id="shell_task", command="echo 'hello world'")
        assert task.command == "echo 'hello world'"
        assert task.script is None

    def test_task_with_python_script(self):
        """Test task with Python script."""
        task = Task(id="python_task", script="analyze.py")
        assert task.script == "analyze.py"
        assert task.command is None

    def test_task_with_r_script(self):
        """Test task with R script."""
        task = Task(id="r_task", script="plot.R")
        assert task.script == "plot.R"
        assert task.command is None

    def test_write_task_wrapper_script_command(self, tmp_path):
        """Test _write_task_wrapper_script with shell command."""
        task = Task(id="shell_task", command="echo 'hello world' > output.txt")
        script_path = tmp_path / "shell_task.sh"

        dag_exporter._write_task_wrapper_script(task, script_path)

        assert script_path.exists()
        assert script_path.is_file()
        # Check file is executable
        assert os.access(script_path, os.X_OK)

        content = script_path.read_text()
        assert "#!/usr/bin/env bash" in content
        assert "set -euo pipefail" in content
        assert "echo 'hello world' > output.txt" in content

    def test_write_task_wrapper_script_python(self, tmp_path):
        """Test _write_task_wrapper_script with Python script."""
        task = Task(id="python_task", script="analyze.py")
        script_path = tmp_path / "python_task.sh"

        dag_exporter._write_task_wrapper_script(task, script_path)

        assert script_path.exists()
        assert os.access(script_path, os.X_OK)

        content = script_path.read_text()
        assert "#!/usr/bin/env bash" in content
        assert "python analyze.py" in content

    def test_write_task_wrapper_script_r(self, tmp_path):
        """Test _write_task_wrapper_script with R script."""
        task = Task(id="r_task", script="plot.R")
        script_path = tmp_path / "r_task.sh"

        dag_exporter._write_task_wrapper_script(task, script_path)

        assert script_path.exists()
        assert os.access(script_path, os.X_OK)

        content = script_path.read_text()
        assert "#!/usr/bin/env bash" in content
        assert "Rscript plot.R" in content

    def test_write_task_wrapper_script_unknown_extension(self, tmp_path):
        """Test _write_task_wrapper_script with unknown script extension."""
        task = Task(id="unknown_task", script="process.xyz")
        script_path = tmp_path / "unknown_task.sh"

        dag_exporter._write_task_wrapper_script(task, script_path)

        assert script_path.exists()
        assert os.access(script_path, os.X_OK)

        content = script_path.read_text()
        assert "#!/usr/bin/env bash" in content
        assert "bash process.xyz" in content

    def test_write_task_wrapper_script_no_command_or_script(self, tmp_path):
        """Test _write_task_wrapper_script with neither command nor script."""
        task = Task(id="empty_task")
        script_path = tmp_path / "empty_task.sh"

        dag_exporter._write_task_wrapper_script(task, script_path)

        assert script_path.exists()
        assert os.access(script_path, os.X_OK)

        content = script_path.read_text()
        assert "#!/usr/bin/env bash" in content
        assert "echo 'No command defined'" in content

    def test_run_block_snakemake_parsing(self, tmp_path):
        """Test parsing of Snakemake run blocks."""
        snakefile = tmp_path / "run_block.smk"
        snakefile.write_text(
            textwrap.dedent("""
            configfile: "config.yaml"

            rule all:
                input: "final.txt"

            rule python_run_block:
                output: "final.txt"
                params:
                    greeting=config.get("greeting", "default_greeting")
                run:
                    print(f"Got greeting: {params.greeting}")
                    with open(output[0], "w") as f:
                        f.write(f"The greeting was: {params.greeting}")
        """)
        )

        # Create config file
        config_file = tmp_path / "config.yaml"
        config_file.write_text("greeting: Hello World")

        try:
            wf = snake_importer.to_workflow(snakefile, workdir=tmp_path)

            # Find the run block task
            run_task = None
            for task in wf.tasks.values():
                if "python_run_block" in task.id:
                    run_task = task
                    break

            assert run_task is not None, "python_run_block task not found"
            assert run_task.meta.get("is_run") is True
            assert run_task.meta.get("run_block_code") is not None
            assert (
                'print(f"Got greeting: {params.greeting}")'
                in run_task.meta["run_block_code"]
            )

        except RuntimeError as e:
            if "snakemake" in str(e):
                pytest.skip("Snakemake not available for integration test")
            else:
                raise


class TestRetryAndPriority:
    """Test retry and priority preservation and export."""

    def test_task_retry_attribute(self):
        """Test Task.retry attribute."""
        task = Task(id="retry_task", command="echo 'test'", retry=3)
        assert task.retry == 3

    def test_task_priority_attribute(self):
        """Test Task.priority attribute."""
        task = Task(id="priority_task", command="echo 'test'", priority=10)
        assert task.priority == 10

    def test_task_retry_and_priority(self):
        """Test Task with both retry and priority."""
        task = Task(
            id="retry_priority_task", command="echo 'test'", retry=2, priority=5
        )
        assert task.retry == 2
        assert task.priority == 5

    def test_dagman_exporter_retry_lines(self, tmp_path):
        """Test DAGMan exporter generates RETRY lines for tasks with retry > 0."""
        wf = Workflow(name="retry_test")

        # Task with retries
        task1 = Task(id="retry_task", command="echo 'may fail'", retry=3)
        wf.add_task(task1)

        # Task without retries
        task2 = Task(id="no_retry_task", command="echo 'always works'", retry=0)
        wf.add_task(task2)

        dag_path = tmp_path / "retry_test.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        dag_content = dag_path.read_text()

        # Should have RETRY line for retry_task
        assert "RETRY retry_task 3" in dag_content

        # Should NOT have RETRY line for no_retry_task
        assert "RETRY no_retry_task" not in dag_content

    def test_dagman_exporter_priority_classad(self, tmp_path):
        """Test DAGMan exporter generates PRIORITY directive for tasks with priority."""
        wf = Workflow(name="priority_test")

        # Task with priority
        task1 = Task(id="high_priority", command="echo 'important'", priority=10)
        wf.add_task(task1)

        # Task with default priority (0)
        task2 = Task(id="normal_priority", command="echo 'normal'", priority=0)
        wf.add_task(task2)

        dag_path = tmp_path / "priority_test.dag"
        scripts_dir = tmp_path / "scripts"
        dag_exporter.from_workflow(
            wf, dag_path, workdir=tmp_path, scripts_dir=scripts_dir
        )

        dag_content = dag_path.read_text()

        # Should have PRIORITY directive for high priority task
        assert "PRIORITY high_priority 10" in dag_content

        # Should NOT have PRIORITY directive for normal priority task (priority 0)
        lines_with_priority = [
            line
            for line in dag_content.split("\n")
            if "PRIORITY" in line and "normal_priority" in line
        ]
        assert (
            len(lines_with_priority) == 0
        )  # Normal priority task should not have PRIORITY directive

    def test_snakemake_retries_parsing(self, tmp_path):
        """Test parsing of Snakemake retries directive."""
        snakefile = tmp_path / "retries.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule all:
                input: "C.txt"

            rule A_will_fail_once:
                output: "A.txt"
                retries: 2
                shell:
                    '''
                    # This will fail the first time it's run
                    if [ ! -f {output}.tmp ]; then
                        touch {output}.tmp
                        echo "A is failing..."
                        exit 1
                    else
                        echo "A is succeeding on retry." > {output}
                        rm {output}.tmp
                    fi
                    '''

            rule B:
                input:  "A.txt"
                output: "B.txt"
                shell:  "cat {input} > {output}; echo 'B ran.' >> {output}"

            rule C_no_retry:
                input:  "B.txt"
                output: "C.txt"
                retries: 0
                shell:  "cat {input} > {output}; echo 'C ran.' >> {output}"
        """)
        )

        try:
            wf = snake_importer.to_workflow(snakefile, workdir=tmp_path)

            # Find tasks and check retry values
            retry_task = None
            no_retry_task = None

            for task in wf.tasks.values():
                if "A_will_fail_once" in task.id:
                    retry_task = task
                elif "C_no_retry" in task.id:
                    no_retry_task = task

            assert retry_task is not None, "A_will_fail_once task not found"
            assert retry_task.retry == 2

            assert no_retry_task is not None, "C_no_retry task not found"
            assert no_retry_task.retry == 0

            # Test DAG export includes retry lines
            dag_path = tmp_path / "retries.dag"
            scripts_dir = tmp_path / "scripts"
            dag_exporter.from_workflow(
                wf, dag_path, workdir=tmp_path, scripts_dir=scripts_dir
            )

            dag_content = dag_path.read_text()

            # Should have RETRY line for task with retries > 0
            retry_task_name = dag_exporter._sanitize_condor_job_name(retry_task.id)
            assert f"RETRY {retry_task_name} 2" in dag_content

            # Should NOT have RETRY line for task with retries = 0
            no_retry_task_name = dag_exporter._sanitize_condor_job_name(
                no_retry_task.id
            )
            assert f"RETRY {no_retry_task_name}" not in dag_content

        except RuntimeError as e:
            if "snakemake" in str(e):
                pytest.skip("Snakemake not available for integration test")
            else:
                raise


class TestIntegrationWorkflows:
    """Integration tests using complete example workflows."""

    def test_container_priority_workflow_end_to_end(self, tmp_path):
        """End-to-end test of container_priority.smk workflow."""
        # Create Snakefile
        snakefile = tmp_path / "container_priority.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule container_override:
                output: "container_test.txt"
                container: "docker://python:3.9-slim"
                conda: "environment.yaml"
                shell: "echo 'This job should run in python:3.9-slim' > {output}"

            rule all:
                input: "container_test.txt"
        """)
        )

        # Create environment file
        env_file = tmp_path / "environment.yaml"
        env_file.write_text("name: test\ndependencies:\n  - python=3.9")

        try:
            # Parse workflow
            wf = snake_importer.to_workflow(snakefile, workdir=tmp_path)

            # Export to DAG
            dag_path = tmp_path / "workflow.dag"
            scripts_dir = tmp_path / "scripts"
            dag_exporter.from_workflow(
                wf, dag_path, workdir=tmp_path, scripts_dir=scripts_dir, verbose=True
            )

            # Verify DAG file was created
            assert dag_path.exists()

            # Verify script files were created
            assert scripts_dir.exists()

            # Check submit files prioritize Docker
            submit_files = list(tmp_path.glob("*.sub"))
            assert len(submit_files) > 0, "No submit files found"

            # Find the submit file with Docker universe
            docker_found = False
            for submit_file in submit_files:
                content = submit_file.read_text()
                if (
                    "universe = docker" in content
                    and "docker_image = python:3.9-slim" in content
                ):
                    docker_found = True
                    break

            assert docker_found, "Docker universe not found in any submit file"

            # Verify generated scripts are executable
            for script_file in scripts_dir.glob("*.sh"):
                assert os.access(script_file, os.X_OK)

        except RuntimeError as e:
            if "snakemake" in str(e):
                pytest.skip("Snakemake not available for integration test")
            else:
                raise

    def test_conda_only_workflow(self, tmp_path):
        """Test workflow with only conda environment (no container)."""
        snakefile = tmp_path / "conda_only.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule analyze:
                output: "results.txt"
                conda: "analysis_env.yaml"
                shell: "python -c 'print(\\\"Analysis complete\\\")' > {output}"

            rule all:
                input: "results.txt"
        """)
        )

        env_file = tmp_path / "analysis_env.yaml"
        env_file.write_text(
            textwrap.dedent("""
            name: analysis
            dependencies:
              - python=3.9
              - pandas
              - numpy
        """)
        )

        try:
            wf = snake_importer.to_workflow(snakefile, workdir=tmp_path)

            dag_path = tmp_path / "conda_workflow.dag"
            scripts_dir = tmp_path / "scripts"
            dag_exporter.from_workflow(
                wf, dag_path, workdir=tmp_path, scripts_dir=scripts_dir
            )

            # Check submit files use vanilla universe for conda
            submit_files = list(tmp_path.glob("*.sub"))
            assert len(submit_files) > 0, "No submit files found"

            # All submit files should use vanilla universe for conda
            for submit_file in submit_files:
                content = submit_file.read_text()
                assert "universe = vanilla" in content
                assert "universe = docker" not in content

        except RuntimeError as e:
            if "snakemake" in str(e):
                pytest.skip("Snakemake not available for integration test")
            else:
                raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
