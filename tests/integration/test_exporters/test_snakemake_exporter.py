"""Tests for the Snakemake exporter functionality."""

from wf2wf.core import Workflow, Task, ParameterSpec, EnvironmentSpecificValue
from wf2wf.exporters.snakemake import from_workflow
import os


class TestSnakemakeExporter:
    """Test the Snakemake exporter."""

    def test_export_simple_workflow(self, persistent_test_output):
        """Test exporting a simple linear workflow."""
        # Create a simple workflow
        wf = Workflow(name="simple_workflow")

        task1 = Task(
            id="prepare_data",
            command=EnvironmentSpecificValue("python prepare.py input.txt output.txt"),
            inputs=[ParameterSpec(id="input.txt", type="File")],
            outputs=[ParameterSpec(id="output.txt", type="File")],
        )
        # Set resources using environment-specific values
        task1.cpu.set_for_environment(2, "shared_filesystem")
        task1.mem_mb.set_for_environment(4096, "shared_filesystem")

        task2 = Task(
            id="analyze_data",
            command=EnvironmentSpecificValue("python analyze.py output.txt results.txt"),
            inputs=[ParameterSpec(id="output.txt", type="File")],
            outputs=[ParameterSpec(id="results.txt", type="File")],
        )
        # Set resources and environment using environment-specific values
        task2.cpu.set_for_environment(4, "shared_filesystem")
        task2.mem_mb.set_for_environment(8192, "shared_filesystem")
        task2.conda.set_for_environment("envs/analysis.yaml", "shared_filesystem")

        wf.add_task(task1)
        wf.add_task(task2)
        wf.add_edge("prepare_data", "analyze_data")

        # Export to Snakemake
        output_file = persistent_test_output / "simple_workflow.smk"
        from_workflow(wf, output_file, verbose=True)

        # Check that file was created
        assert output_file.exists()

        # Read and verify content
        content = output_file.read_text()

        # Check header
        assert "# Snakefile generated by wf2wf" in content
        assert "simple_workflow" in content

        # Check rules
        assert "rule all:" in content
        assert "rule prepare_data:" in content
        assert "rule analyze_data:" in content

        # Check inputs/outputs
        assert 'input:\n        "input.txt",' in content
        assert 'output:\n        "output.txt",' in content
        assert 'output:\n        "results.txt",' in content

        # Check resources
        assert "cpu=2" in content
        assert "mem_mb=4096" in content
        assert "cpu=4" in content
        assert "mem_mb=8192" in content

        # Check conda environment
        assert "conda: 'envs/analysis.yaml'" in content

        # Check commands
        assert "python prepare.py input.txt output.txt" in content
        assert "python analyze.py output.txt results.txt" in content

    def test_export_with_config(self, persistent_test_output):
        """Test exporting workflow with configuration."""
        wf = Workflow(
            name="config_workflow",
        )
        # Add config to metadata
        if wf.metadata is None:
            from wf2wf.core import MetadataSpec
            wf.metadata = MetadataSpec()
        wf.metadata.add_format_specific("config", {
            "analysis_params": {"threshold": 0.05, "iterations": 1000},
            "data_source": "/path/to/data",
        })

        task = Task(
            id="analyze",
            command=EnvironmentSpecificValue("python analyze.py --threshold {config[analysis_params][threshold]}"),
            inputs=[ParameterSpec(id="data.txt", type="File")],
            outputs=[ParameterSpec(id="results.txt", type="File")],
        )
        wf.add_task(task)

        # Export with embedded config
        output_file = persistent_test_output / "config_workflow.smk"
        from_workflow(wf, output_file)

        content = output_file.read_text()

        # Check config is embedded
        assert "config:" in content
        assert "analysis_params:" in content
        assert "threshold: 0.05" in content
        assert "iterations: 1000" in content
        assert "data_source" in content and "/path/to/data" in content

    def test_export_with_separate_config(self, persistent_test_output):
        """Test exporting workflow with separate config file."""
        wf = Workflow(name="separate_config_workflow")
        # Add config to metadata
        if wf.metadata is None:
            from wf2wf.core import MetadataSpec
            wf.metadata = MetadataSpec()
        wf.metadata.add_format_specific("config", {"param1": "value1", "param2": 42})

        task = Task(id="test_task", command=EnvironmentSpecificValue("echo test"))
        wf.add_task(task)

        # Export with separate config file
        output_file = persistent_test_output / "separate_config.smk"
        config_file = persistent_test_output / "config.yaml"

        from_workflow(wf, output_file, config_file=config_file)

        # Check Snakefile references config
        snakefile_content = output_file.read_text()
        assert "configfile:" in snakefile_content
        assert "config.yaml" in snakefile_content

        # Check config file was created
        assert config_file.exists()
        config_content = config_file.read_text()
        assert "param1: value1" in config_content
        assert "param2: 42" in config_content

    def test_export_with_containers(self, persistent_test_output):
        """Test exporting workflow with container specifications."""
        wf = Workflow(name="container_workflow")

        # Task with Docker container
        docker_task = Task(
            id="docker_task",
            command=EnvironmentSpecificValue("python script.py"),
        )
        docker_task.container.set_for_environment("docker://python:3.9-slim", "shared_filesystem")

        # Task with direct container reference
        container_task = Task(
            id="container_task",
            command=EnvironmentSpecificValue("R script.R"),
        )
        container_task.container.set_for_environment("bioconductor/release_core2", "shared_filesystem")

        wf.add_task(docker_task)
        wf.add_task(container_task)

        output_file = persistent_test_output / "container_workflow.smk"
        from_workflow(wf, output_file)

        content = output_file.read_text()

        # Check container specifications
        assert "container:" in content  # Just check for presence
        assert "docker://python:3.9-slim" in content
        assert "bioconductor/release_core2" in content

    def test_export_with_resources(self, persistent_test_output):
        """Test exporting workflow with comprehensive resource specifications."""
        wf = Workflow(name="resource_workflow")

        task = Task(
            id="resource_intensive_task",
            command=EnvironmentSpecificValue("python compute.py"),
        )
        # Set comprehensive resources using environment-specific values
        task.cpu.set_for_environment(16, "shared_filesystem")
        task.mem_mb.set_for_environment(32768, "shared_filesystem")  # 32GB
        task.disk_mb.set_for_environment(102400, "shared_filesystem")  # 100GB
        task.gpu.set_for_environment(2, "shared_filesystem")
        task.time_s.set_for_environment(7200, "shared_filesystem")  # 2 hours
        task.threads.set_for_environment(8, "shared_filesystem")
        
        wf.add_task(task)

        output_file = persistent_test_output / "resource_workflow.smk"
        from_workflow(wf, output_file)

        content = output_file.read_text()

        # Check resource conversion
        assert "cpu=16" in content
        assert "mem_mb=32768" in content
        assert "disk_mb=102400" in content
        assert "threads=8" in content

    def test_export_with_retry_priority(self, persistent_test_output):
        """Test exporting workflow with retry and priority settings."""
        wf = Workflow(name="retry_priority_workflow")

        task1 = Task(
            id="high_priority_task", 
            command=EnvironmentSpecificValue("python important.py")
        )
        task1.priority.set_for_environment(10, "shared_filesystem")
        task1.retry_count.set_for_environment(3, "shared_filesystem")

        task2 = Task(
            id="low_priority_task", 
            command=EnvironmentSpecificValue("python background.py")
        )
        task2.priority.set_for_environment(-5, "shared_filesystem")
        task2.retry_count.set_for_environment(1, "shared_filesystem")

        wf.add_task(task1)
        wf.add_task(task2)

        output_file = persistent_test_output / "retry_priority_workflow.smk"
        from_workflow(wf, output_file)

        content = output_file.read_text()

        # Check that rules are generated (priority and retry are not directly exported in Snakemake)
        assert "rule high_priority_task:" in content
        assert "rule low_priority_task:" in content
        assert "python important.py" in content
        assert "python background.py" in content

    def test_export_with_scripts(self, persistent_test_output):
        """Test exporting workflow with script files."""
        wf = Workflow(name="script_workflow")

        # Create script directory
        script_dir = persistent_test_output / "scripts"
        script_dir.mkdir(exist_ok=True)
        script_file = script_dir / "process_data.py"
        script_file.write_text("print('Processing data...')")

        task = Task(
            id="process_data",
            script=EnvironmentSpecificValue("scripts/process_data.py"),
            inputs=[ParameterSpec(id="input.txt", type="File")],
            outputs=[ParameterSpec(id="output.txt", type="File")],
        )

        wf.add_task(task)

        output_file = persistent_test_output / "script_workflow.smk"
        from_workflow(wf, output_file, script_dir="scripts")

        content = output_file.read_text()

        # Check script reference
        assert "script:" in content  # Just check for presence
        assert "scripts/process_data.py" in content
        assert "rule process_data:" in content

    def test_topological_ordering(self, persistent_test_output):
        """Test that tasks are generated in topological order."""
        wf = Workflow(name="topological_workflow")

        # Create tasks with dependencies: A -> B -> C
        task_a = Task(id="task_a", command=EnvironmentSpecificValue("echo A"))
        task_b = Task(id="task_b", command=EnvironmentSpecificValue("echo B"))
        task_c = Task(id="task_c", command=EnvironmentSpecificValue("echo C"))

        wf.add_task(task_a)
        wf.add_task(task_b)
        wf.add_task(task_c)
        wf.add_edge("task_a", "task_b")
        wf.add_edge("task_b", "task_c")

        output_file = persistent_test_output / "topological_workflow.smk"
        from_workflow(wf, output_file)

        content = output_file.read_text()

        # Check that all rules are present
        assert "rule task_a:" in content
        assert "rule task_b:" in content
        assert "rule task_c:" in content

        # Check that the order is reasonable (topological sort should put A first)
        lines = content.split('\n')
        task_a_line = next(i for i, line in enumerate(lines) if "rule task_a:" in line)
        task_b_line = next(i for i, line in enumerate(lines) if "rule task_b:" in line)
        task_c_line = next(i for i, line in enumerate(lines) if "rule task_c:" in line)

        # A should come before B and C
        assert task_a_line < task_b_line
        assert task_a_line < task_c_line

    def test_rule_name_sanitization(self, persistent_test_output):
        """Test that rule names are properly sanitized."""
        wf = Workflow(name="sanitization_workflow")

        # Task with problematic name
        task = Task(
            id="task with spaces and special chars!@#",
            command=EnvironmentSpecificValue("echo test")
        )
        wf.add_task(task)

        output_file = persistent_test_output / "sanitization_workflow.smk"
        from_workflow(wf, output_file)

        content = output_file.read_text()

        # Check that rule name is sanitized
        assert "rule task_with_spaces_and_special_chars___:" in content
        assert "task with spaces and special chars!@#" not in content

    def test_complex_workflow_from_json(
        self, sample_workflow_json, persistent_test_output
    ):
        """Test exporting a complex workflow from JSON."""
        # Load workflow from JSON
        wf = Workflow.from_json(sample_workflow_json.read_text())

        output_file = persistent_test_output / "complex_workflow.smk"
        from_workflow(wf, output_file)

        # Check that file was created
        assert output_file.exists()

        content = output_file.read_text()

        # Check basic structure
        assert "# Snakefile generated by wf2wf" in content
        assert "rule all:" in content

        # Check that all tasks are present
        for task_id in wf.tasks:
            assert f"rule {task_id}:" in content
