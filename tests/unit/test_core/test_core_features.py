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
from wf2wf.core import Workflow, Task
from wf2wf.exporters import dagman as dag_exporter
from wf2wf.importers import snakemake as snake_importer
from wf2wf.core import EnvironmentSpecificValue
from wf2wf.exporters.dagman import DAGManExporter


class TestContainersConda:
    """Test container and conda environment handling."""

    def test_environment_spec_container_docker(self):
        """Test Task with Docker container."""
        task = Task(id="docker_task")
        task.container.set_for_environment("docker://python:3.9-slim", "shared_filesystem")
        assert task.container.get_value_for("shared_filesystem") == "docker://python:3.9-slim"
        assert task.conda.get_value_for("shared_filesystem") is None

    def test_environment_spec_container_singularity(self):
        """Test Task with Singularity container."""
        task = Task(id="singularity_task")
        task.container.set_for_environment("/path/to/image.sif", "shared_filesystem")
        assert task.container.get_value_for("shared_filesystem") == "/path/to/image.sif"
        assert task.conda.get_value_for("shared_filesystem") is None

    def test_environment_spec_conda_file(self):
        """Test Task with conda YAML file."""
        task = Task(id="conda_task")
        task.conda.set_for_environment("environment.yaml", "shared_filesystem")
        assert task.conda.get_value_for("shared_filesystem") == "environment.yaml"
        assert task.container.get_value_for("shared_filesystem") is None

    def test_environment_spec_conda_name(self):
        """Test Task with conda environment name."""
        task = Task(id="conda_task")
        task.conda.set_for_environment("myenv", "shared_filesystem")
        assert task.conda.get_value_for("shared_filesystem") == "myenv"
        assert task.container.get_value_for("shared_filesystem") is None

    def test_container_priority_over_conda(self):
        """Test that container takes priority when both are specified."""
        task = Task(id="mixed_task")
        task.container.set_for_environment("docker://python:3.9-slim", "shared_filesystem")
        task.conda.set_for_environment("environment.yaml", "shared_filesystem")
        # Both should be preserved in the IR
        assert task.container.get_value_for("shared_filesystem") == "docker://python:3.9-slim"
        assert task.conda.get_value_for("shared_filesystem") == "environment.yaml"

    def test_dagman_exporter_docker_universe(self, tmp_path):
        """Test DAGMan exporter chooses docker universe for Docker containers."""
        wf = Workflow(name="docker_test")
        task = Task(id="docker_task")
        task.command.set_for_environment("echo 'hello from docker'", "distributed_computing")
        task.container.set_for_environment("docker://python:3.9-slim", "distributed_computing")
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
        task = Task(id="singularity_task")
        task.command.set_for_environment("echo 'hello from singularity'", "distributed_computing")
        task.container.set_for_environment("/path/to/image.sif", "distributed_computing")
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
        task = Task(id="conda_task")
        task.command.set_for_environment("echo 'hello from conda'", "distributed_computing")
        task.conda.set_for_environment("environment.yaml", "distributed_computing")
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
            # Check for container in shared_filesystem environment (original Snakemake directive)
            assert container_task.container.get_value_for("shared_filesystem") == "docker://python:3.9-slim"
            assert container_task.conda.get_value_for("shared_filesystem") == "environment.yaml"

            # Set container for distributed_computing to match shared_filesystem for export
            container_task.container.set_for_environment(
                container_task.container.get_value_for("shared_filesystem"),
                "distributed_computing"
            )

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
        task = Task(id="shell_task")
        task.command.set_for_environment("echo 'hello world'", "shared_filesystem")
        assert task.command.get_value_for("shared_filesystem") == "echo 'hello world'"
        assert task.script.get_value_for("shared_filesystem") is None

    def test_task_with_python_script(self):
        """Test task with Python script."""
        task = Task(id="python_task")
        task.script.set_for_environment("analyze.py", "shared_filesystem")
        assert task.script.get_value_for("shared_filesystem") == "analyze.py"
        assert task.command.get_value_for("shared_filesystem") is None

    def test_task_with_r_script(self):
        """Test task with R script."""
        task = Task(id="r_task")
        task.script.set_for_environment("plot.R", "shared_filesystem")
        assert task.script.get_value_for("shared_filesystem") == "plot.R"
        assert task.command.get_value_for("shared_filesystem") is None

    def test_write_task_wrapper_script_command(self, tmp_path):
        """Test _write_task_wrapper_script with shell command."""
        task = Task(id="shell_task")
        task.command.set_for_environment("echo 'hello world' > output.txt", "distributed_computing")
        script_path = tmp_path / "shell_task.sh"

        exporter = DAGManExporter(target_environment="distributed_computing")
        exporter._write_task_wrapper_script(task, script_path)

        assert script_path.exists()
        assert script_path.is_file()
        # Check file is executable
        assert os.access(script_path, os.X_OK)

        content = script_path.read_text()
        assert "#!/bin/bash" in content
        assert "set -euo pipefail" in content
        assert "echo 'hello world' > output.txt" in content

    def test_write_task_wrapper_script_python(self, tmp_path):
        """Test _write_task_wrapper_script with Python script."""
        task = Task(id="python_task", script=EnvironmentSpecificValue("analyze.py", ["distributed_computing"]))
        script_path = tmp_path / "python_task.sh"

        exporter = DAGManExporter(target_environment="distributed_computing")
        exporter._write_task_wrapper_script(task, script_path)

        assert script_path.exists()
        assert os.access(script_path, os.X_OK)

        content = script_path.read_text()
        assert "#!/bin/bash" in content
        assert "python analyze.py" in content

    def test_write_task_wrapper_script_r(self, tmp_path):
        """Test _write_task_wrapper_script with R script."""
        task = Task(id="r_task", script=EnvironmentSpecificValue("plot.R", ["distributed_computing"]))
        script_path = tmp_path / "r_task.sh"

        exporter = DAGManExporter(target_environment="distributed_computing")
        exporter._write_task_wrapper_script(task, script_path)

        assert script_path.exists()
        assert os.access(script_path, os.X_OK)

        content = script_path.read_text()
        assert "#!/bin/bash" in content
        assert "Rscript plot.R" in content

    def test_write_task_wrapper_script_unknown_extension(self, tmp_path):
        """Test _write_task_wrapper_script with unknown script extension."""
        task = Task(id="unknown_task", script=EnvironmentSpecificValue("process.xyz", ["distributed_computing"]))
        script_path = tmp_path / "unknown_task.sh"

        exporter = DAGManExporter(target_environment="distributed_computing")
        exporter._write_task_wrapper_script(task, script_path)

        assert script_path.exists()
        assert os.access(script_path, os.X_OK)

        content = script_path.read_text()
        assert "#!/bin/bash" in content
        assert "bash process.xyz" in content

    def test_write_task_wrapper_script_no_command_or_script(self, tmp_path):
        """Test _write_task_wrapper_script with neither command nor script."""
        task = Task(id="empty_task")
        script_path = tmp_path / "empty_task.sh"

        exporter = DAGManExporter(target_environment="distributed_computing")
        exporter._write_task_wrapper_script(task, script_path)

        assert script_path.exists()
        assert os.access(script_path, os.X_OK)

        content = script_path.read_text()
        assert "#!/bin/bash" in content
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
            # Note: meta field has been removed from Task class
            # Run block code is now stored in the script field as EnvironmentSpecificValue

        except RuntimeError as e:
            if "snakemake" in str(e):
                pytest.skip("Snakemake not available for integration test")
            else:
                raise


class TestRetryAndPriority:
    """Test retry and priority handling."""

    def test_task_retry_attribute(self):
        """Test task retry attribute."""
        task = Task(id="retry_task")
        task.retry_count.set_for_environment(3, "shared_filesystem")
        assert task.retry_count.get_value_for("shared_filesystem") == 3

    def test_task_priority_attribute(self):
        """Test task priority attribute."""
        task = Task(id="priority_task")
        task.priority.set_for_environment(10, "shared_filesystem")
        assert task.priority.get_value_for("shared_filesystem") == 10

    def test_task_retry_and_priority(self):
        """Test task with both retry and priority."""
        task = Task(id="retry_priority_task")
        task.retry_count.set_for_environment(2, "shared_filesystem")
        task.priority.set_for_environment(5, "shared_filesystem")
        assert task.retry_count.get_value_for("shared_filesystem") == 2
        assert task.priority.get_value_for("shared_filesystem") == 5

    def test_dagman_exporter_retry_lines(self, tmp_path):
        """Test DAGMan exporter generates RETRY lines for tasks with retry > 0."""
        wf = Workflow(name="retry_test")

        # Task with retries
        task1 = Task(id="retry_task")
        task1.retry_count.set_for_environment(3, "distributed_computing")
        wf.add_task(task1)

        # Task without retries
        task2 = Task(id="no_retry_task")
        task2.retry_count.set_for_environment(0, "distributed_computing")
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
        task1 = Task(id="high_priority")
        task1.priority.set_for_environment(10, "distributed_computing")
        wf.add_task(task1)

        # Task with default priority (0)
        task2 = Task(id="normal_priority")
        task2.priority.set_for_environment(0, "distributed_computing")
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
        assert len(lines_with_priority) == 0

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
            assert retry_task.retry_count.get_value_for("shared_filesystem") == 2

            assert no_retry_task is not None, "C_no_retry task not found"
            assert no_retry_task.retry_count.get_value_for("shared_filesystem") == 0

            # Set retry values for distributed_computing to match shared_filesystem for export
            retry_task.retry_count.set_for_environment(
                retry_task.retry_count.get_value_for("shared_filesystem"),
                "distributed_computing"
            )
            no_retry_task.retry_count.set_for_environment(
                no_retry_task.retry_count.get_value_for("shared_filesystem"),
                "distributed_computing"
            )

            # Test DAG export includes retry lines
            dag_path = tmp_path / "retries.dag"
            scripts_dir = tmp_path / "scripts"
            dag_exporter.from_workflow(
                wf, dag_path, workdir=tmp_path, scripts_dir=scripts_dir
            )

            dag_content = dag_path.read_text()

            # Create exporter instance for sanitize method
            exporter = DAGManExporter(target_environment="distributed_computing")
            
            # Should have RETRY line for task with retries > 0
            retry_task_name = exporter._sanitize_condor_job_name(retry_task.id)
            assert f"RETRY {retry_task_name} 2" in dag_content

            # Should NOT have RETRY line for task with retries = 0
            no_retry_task_name = exporter._sanitize_condor_job_name(
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

            # Set container for distributed_computing to match shared_filesystem for export
            for task in wf.tasks.values():
                if task.container.get_value_for("shared_filesystem"):
                    task.container.set_for_environment(
                        task.container.get_value_for("shared_filesystem"),
                        "distributed_computing"
                    )

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

            # Check that tasks with conda environments have universe = vanilla
            # and tasks without conda/container don't have universe = docker
            exporter = DAGManExporter(target_environment="distributed_computing")
            for submit_file in submit_files:
                content = submit_file.read_text()
                submit_name = submit_file.stem
                
                # Find corresponding task
                task = None
                for task_id, t in wf.tasks.items():
                    if exporter._sanitize_condor_job_name(task_id) == submit_name:
                        task = t
                        break
                
                if task:
                    conda_env = task.conda.get_value_for("distributed_computing")
                    container = task.container.get_value_for("distributed_computing")
                    
                    if conda_env and not container:
                        # Task has conda but no container - should have universe = vanilla
                        # Note: Conda environments are now handled through packaging and activation scripts
                        # rather than the +CondaEnv attribute for better portability
                        assert "universe = vanilla" in content, f"Task {task.id} has conda but no universe = vanilla"
                        
                        # Check that activation script was generated in scripts directory
                        script_files = list(scripts_dir.glob("*.sh"))
                        assert len(script_files) > 0, f"No script files found for task {task.id}"
                        
                        # Check that at least one script contains conda activation logic
                        activation_script_found = False
                        for script_file in script_files:
                            script_content = script_file.read_text()
                            if "conda-pack" in script_content or "conda activate" in script_content:
                                activation_script_found = True
                                break
                        assert activation_script_found, f"No conda activation script found for task {task.id}"
                        
                        # Check that conda environment tarball was created (if packaging succeeded)
                        env_tarballs = list(tmp_path.glob("*.tar.gz"))
                        if len(env_tarballs) > 0:
                            # Packaging succeeded - verify tarball exists
                            assert any("analysis" in tarball.name for tarball in env_tarballs), f"No environment tarball found for task {task.id}"
                        else:
                            # Packaging may have failed gracefully - check for fallback activation
                            conda_script_found = False
                            for script_file in script_files:
                                script_content = script_file.read_text()
                                if "conda activate analysis_env.yaml" in script_content:
                                    conda_script_found = True
                                    break
                            assert conda_script_found, f"No conda activation script found for task {task.id} (packaging failed)"
                        
                    elif not conda_env and not container:
                        # Task has no conda and no container - should not have universe = docker
                        assert "universe = docker" not in content, f"Task {task.id} has no container but has universe = docker"

        except RuntimeError as e:
            if "snakemake" in str(e):
                pytest.skip("Snakemake not available for integration test")
            else:
                raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
