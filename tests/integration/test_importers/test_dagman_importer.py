"""Tests for the DAGMan importer functionality."""

import pytest
from textwrap import dedent
from wf2wf.importers import dagman as dag_importer
from pathlib import Path
from wf2wf.core import EnvironmentSpecificValue


class TestDAGManImporter:
    """Test the DAGMan importer."""

    def test_import_demo_workflow(self, dagman_examples, persistent_test_output):
        """Test importing the demo DAGMan workflow."""
        dag_file = dagman_examples / "test_demo.dag"

        if not dag_file.exists():
            pytest.skip("Demo DAGMan file not found")

        # Import the workflow
        wf = dag_importer.to_workflow(dag_file, verbose=True)

        # Test basic workflow properties
        assert wf.name == "test_demo"
        assert len(wf.tasks) == 3
        assert len(wf.edges) == 2

        # Test task names
        task_names = set(wf.tasks.keys())
        expected_names = {"prepare_data", "analyze_data", "generate_report"}
        assert task_names == expected_names

        # Test dependencies
        deps = [(edge.parent, edge.child) for edge in wf.edges]
        expected_deps = [
            ("prepare_data", "analyze_data"),
            ("analyze_data", "generate_report"),
        ]
        assert set(deps) == set(expected_deps)

        # Test specific task properties
        prep_task = wf.tasks["prepare_data"]
        assert prep_task.retry_count.get_value_for("distributed_computing") == 2
        assert prep_task.cpu.get_value_for("distributed_computing") == 2048  # 2GB in MB
        assert prep_task.disk_mb.get_value_for("distributed_computing") == 1024  # 1GB in MB

        analyze_task = wf.tasks["analyze_data"]
        assert analyze_task.retry_count.get_value_for("distributed_computing") == 1
        assert analyze_task.priority.get_value_for("distributed_computing") == 10
        assert analyze_task.cpu.get_value_for("distributed_computing") == 4
        assert analyze_task.mem_mb.get_value_for("distributed_computing") == 8192  # 8GB in MB
        assert analyze_task.container.get_value_for("distributed_computing") == "docker://python:3.9-slim"

        # Save converted workflow to test output
        output_file = persistent_test_output / "demo_workflow.json"
        wf.save_json(output_file)
        assert output_file.exists()

    def test_dag_file_parsing(self, persistent_test_output):
        """Test DAG file parsing with various features."""
        # Create a test DAG file
        dag_content = """
# Test DAG file
JOB task1 task1.sub
JOB task2 task2.sub NOOP
JOB task3 task3.sub

PARENT task1 CHILD task2 task3
RETRY task1 3
PRIORITY task2 -5
VARS task1 input="data.txt" output="result.txt"
SET_ENV PYTHONPATH=/opt/tools
"""

        dag_file = persistent_test_output / "test.dag"
        dag_file.write_text(dag_content)

        # Create minimal submit files
        for task in ["task1", "task2", "task3"]:
            sub_file = persistent_test_output / f"{task}.sub"
            sub_content = f"""
universe = vanilla
executable = /bin/echo
arguments = "{task} executed"
request_cpus = 1
request_memory = 1GB
queue
"""
            sub_file.write_text(sub_content)

        # Import the workflow
        wf = dag_importer.to_workflow(dag_file)

        assert len(wf.tasks) == 3
        assert len(wf.edges) == 2

        # Check task1 properties
        task1 = wf.tasks["task1"]
        assert task1.retry_count.get_value_for("distributed_computing") == 3
        assert "dag_vars" in task1.metadata.format_specific
        assert task1.metadata.format_specific["dag_vars"]["input"] == "data.txt"

        # Check task2 properties
        task2 = wf.tasks["task2"]
        assert task2.priority.get_value_for("distributed_computing") == -5

        # Check environment variables
        assert "dag_variables" in wf.metadata.format_specific
        assert wf.metadata.format_specific["dag_variables"]["PYTHONPATH"] == "/opt/tools"

    def test_submit_file_parsing(self, persistent_test_output):
        """Test submit file parsing with various features."""
        # Create a comprehensive submit file
        sub_content = """
# Test submit file
universe = vanilla
executable = /usr/bin/python3
arguments = script.py --input $(inputfile) --output $(outputfile)

request_cpus = 8
request_memory = 16GB
request_disk = 10GB
request_gpus = 2

container_image = docker://tensorflow/tensorflow:latest

transfer_input_files = script.py, input.dat
transfer_output_files = results.txt, plots.png

environment = "OMP_NUM_THREADS=8 CUDA_VISIBLE_DEVICES=0,1"

output = job.out
error = job.err
log = job.log

requirements = (Target.HasGPU == True)

queue
"""

        dag_content = """
JOB gpu_job gpu_job.sub
"""

        # Write files
        dag_file = persistent_test_output / "gpu_test.dag"
        sub_file = persistent_test_output / "gpu_job.sub"

        dag_file.write_text(dag_content)
        sub_file.write_text(sub_content)

        # Import workflow
        wf = dag_importer.to_workflow(dag_file)

        assert len(wf.tasks) == 1
        task = wf.tasks["gpu_job"]

        # Check resource specifications
        assert task.cpu.get_value_for("distributed_computing") == 8
        assert task.mem_mb.get_value_for("distributed_computing") == 16384  # 16GB in MB
        assert task.disk_mb.get_value_for("distributed_computing") == 10240  # 10GB in MB
        assert task.gpu.get_value_for("distributed_computing") == 2

        # Check container
        assert task.container.get_value_for("distributed_computing") == "docker://tensorflow/tensorflow:latest"

        # Check environment variables
        env_vars = task.env_vars.get_value_for("distributed_computing") or {}
        assert "OMP_NUM_THREADS" in env_vars
        assert env_vars["OMP_NUM_THREADS"] == "8"

        # Check file transfers - now using ParameterSpec objects
        input_ids = [inp.id if hasattr(inp, 'id') else inp for inp in task.inputs]
        output_ids = [out.id if hasattr(out, 'id') else out for out in task.outputs]
        
        assert "script.py" in input_ids
        assert "input.dat" in input_ids
        assert "results.txt" in output_ids
        assert "plots.png" in output_ids
        
        # Check that transfer_mode is set to "always" for transferred files
        for inp in task.inputs:
            if hasattr(inp, 'transfer_mode'):
                assert inp.transfer_mode.get_value_with_default("distributed_computing") == "always"
        for out in task.outputs:
            if hasattr(out, 'transfer_mode'):
                assert out.transfer_mode.get_value_with_default("distributed_computing") == "always"

        # Check metadata
        assert task.metadata.format_specific["requirements"] == "(Target.HasGPU == True)"
        assert task.metadata.format_specific["condor_log"] == "job.log"

    def test_memory_unit_parsing(self):
        """Test parsing of different memory units."""
        from wf2wf.importers.dagman import _parse_memory_value

        assert _parse_memory_value("1024") == 1024  # Default MB
        assert _parse_memory_value("1024MB") == 1024
        assert _parse_memory_value("1GB") == 1024
        assert _parse_memory_value("2GB") == 2048
        assert _parse_memory_value("1024KB") == 1
        assert _parse_memory_value("1TB") == 1024 * 1024

        # Test with spaces and case variations
        assert _parse_memory_value("2 GB") == 2048
        assert _parse_memory_value("512 mb") == 512

    def test_error_handling(self, persistent_test_output):
        """Test error handling for invalid files."""
        # Test non-existent file
        with pytest.raises(ImportError):
            dag_importer.to_workflow(Path("nonexistent.dag"))

        # Test empty DAG file
        empty_dag = persistent_test_output / "empty.dag"
        empty_dag.write_text("")

        with pytest.raises(ImportError, match="No jobs found"):
            dag_importer.to_workflow(empty_dag)

        # Test DAG with missing submit file
        dag_with_missing_sub = persistent_test_output / "missing_sub.dag"
        dag_with_missing_sub.write_text("JOB test nonexistent.sub")

        # Should not raise an error, but should warn
        wf = dag_importer.to_workflow(dag_with_missing_sub, verbose=True)
        assert len(wf.tasks) == 1


class TestDAGManImporterInlineSubmit:
    """Test suite for importing DAGMan inline submit descriptions."""

    def test_import_inline_submit_basic(self, persistent_test_output):
        """Test importing basic inline submit descriptions."""
        dag_content = dedent("""
            JOB simple_task {
                executable = /path/to/script.sh
                request_cpus = 2
                request_memory = 4096MB
                request_disk = 5120MB
                universe = vanilla
                output = logs/simple_task.out
                error = logs/simple_task.err
                log = logs/simple_task.log
                queue
            }
        """).strip()

        dag_path = persistent_test_output / "simple.dag"
        dag_path.write_text(dag_content)

        wf = dag_importer.to_workflow(dag_path)

        # Check workflow structure
        assert len(wf.tasks) == 1
        assert "simple_task" in wf.tasks

        # Check task properties
        task = wf.tasks["simple_task"]
        assert task.cpu.get_value_for("distributed_computing") == 2
        assert task.mem_mb.get_value_for("distributed_computing") == 4096
        assert task.disk_mb.get_value_for("distributed_computing") == 5120
        assert task.metadata.format_specific.get("universe") == "vanilla"

    def test_import_inline_submit_with_custom_attributes(self, persistent_test_output):
        """Test importing inline submit descriptions with custom HTCondor attributes."""
        dag_content = dedent("""
            JOB gpu_task {
                executable = /path/to/gpu_script.sh
                request_cpus = 4
                request_memory = 8192MB
                request_gpus = 2
                requirements = (Memory > 8000) && (HasGPU == True)
                +WantGPULab = true
                +ProjectName = "Special Project"
                universe = vanilla
                queue
            }
        """).strip()

        dag_path = persistent_test_output / "gpu.dag"
        dag_path.write_text(dag_content)

        wf = dag_importer.to_workflow(dag_path)

        task = wf.tasks["gpu_task"]
        assert task.cpu.get_value_for("distributed_computing") == 4
        assert task.mem_mb.get_value_for("distributed_computing") == 8192
        assert task.gpu.get_value_for("distributed_computing") == 2

        # Check custom attributes - requirements goes to meta, others to extra
        assert task.metadata.format_specific["requirements"] == "(Memory > 8000) && (HasGPU == True)"
        # Note: extra attributes are now stored in task.extra
        extra_attrs = task.extra.get("+wantgpulab", EnvironmentSpecificValue()).get_value_for("distributed_computing")
        assert extra_attrs == "true"
        extra_attrs = task.extra.get("+projectname", EnvironmentSpecificValue()).get_value_for("distributed_computing")
        assert extra_attrs == "Special Project"

    def test_import_inline_submit_container_types(self, persistent_test_output):
        """Test importing inline submit descriptions with different container types."""
        dag_content = dedent("""
            JOB docker_task {
                executable = /path/to/script.sh
                request_cpus = 2
                request_memory = 4096MB
                universe = docker
                docker_image = python:3.9
                queue
            }

            JOB singularity_task {
                executable = /path/to/script.sh
                request_cpus = 1
                request_memory = 2048MB
                universe = vanilla
                +SingularityImage = "/path/to/container.sif"
                queue
            }
        """).strip()

        dag_path = persistent_test_output / "containers.dag"
        dag_path.write_text(dag_content)

        wf = dag_importer.to_workflow(dag_path)

        # Check Docker task
        docker_task = wf.tasks["docker_task"]
        assert docker_task.container.get_value_for("distributed_computing") == "docker://python:3.9"
        assert docker_task.metadata.format_specific["universe"] == "docker"

        # Check Singularity task
        singularity_task = wf.tasks["singularity_task"]
        assert singularity_task.container.get_value_for("distributed_computing") == "/path/to/container.sif"
        assert singularity_task.metadata.format_specific["universe"] == "vanilla"

    def test_import_inline_submit_with_retry_priority(self, persistent_test_output):
        """Test importing inline submit descriptions with retry and priority settings."""
        dag_content = dedent("""
            JOB important_task {
                executable = /path/to/script.sh
                request_cpus = 2
                request_memory = 4096MB
                universe = vanilla
                queue
            }

            RETRY important_task 3
            PRIORITY important_task 20
        """).strip()

        dag_path = persistent_test_output / "retry_priority.dag"
        dag_path.write_text(dag_content)

        wf = dag_importer.to_workflow(dag_path)

        task = wf.tasks["important_task"]
        assert task.retry_count.get_value_for("distributed_computing") == 3
        assert task.priority.get_value_for("distributed_computing") == 20

    def test_import_mixed_inline_and_external_submit(self, persistent_test_output):
        """Test importing DAG files with mixed inline and external submit descriptions."""
        # Create external submit file
        submit_content = dedent("""
            executable = /path/to/external_script.sh
            request_cpus = 1
            request_memory = 2048MB
            universe = vanilla
            queue
        """).strip()

        submit_path = persistent_test_output / "external_task.sub"
        submit_path.write_text(submit_content)

        # Create DAG with both inline and external
        dag_content = dedent("""
            JOB inline_task {
                executable = /path/to/inline_script.sh
                request_cpus = 2
                request_memory = 4096MB
                universe = vanilla
                queue
            }

            JOB external_task external_task.sub

            PARENT inline_task CHILD external_task
        """).strip()

        dag_path = persistent_test_output / "mixed.dag"
        dag_path.write_text(dag_content)

        wf = dag_importer.to_workflow(dag_path)

        # Check both tasks were imported correctly
        assert len(wf.tasks) == 2

        inline_task = wf.tasks["inline_task"]
        assert inline_task.cpu.get_value_for("distributed_computing") == 2
        assert inline_task.mem_mb.get_value_for("distributed_computing") == 4096

        external_task = wf.tasks["external_task"]
        assert external_task.cpu.get_value_for("distributed_computing") == 1
        assert external_task.mem_mb.get_value_for("distributed_computing") == 2048

        # Check dependency
        assert len(wf.edges) == 1
        assert wf.edges[0].parent == "inline_task"
        assert wf.edges[0].child == "external_task"

    def test_import_inline_submit_multiline_format(self, persistent_test_output):
        """Test importing inline submit descriptions with proper multiline formatting."""
        dag_content = dedent("""
            JOB complex_task {
                # Submit description for complex_task
                executable = /path/to/complex_script.sh
                arguments = --input data.txt --output results.txt

                # Resource requirements
                request_cpus = 4
                request_memory = 8192MB
                request_disk = 10240MB
                request_gpus = 2

                # Custom requirements
                requirements = (Memory > 8000) && (HasGPU == True)
                +WantGPULab = true

                # I/O and logging
                output = logs/complex_task.out
                error = logs/complex_task.err
                log = logs/complex_task.log

                # Job settings
                universe = docker
                docker_image = tensorflow/tensorflow:latest-gpu
                should_transfer_files = YES
                when_to_transfer_output = ON_EXIT

                # Submit the job
                queue
            }
        """).strip()

        dag_path = persistent_test_output / "complex.dag"
        dag_path.write_text(dag_content)

        wf = dag_importer.to_workflow(dag_path)

        task = wf.tasks["complex_task"]
        assert task.cpu.get_value_for("distributed_computing") == 4
        assert task.mem_mb.get_value_for("distributed_computing") == 8192
        assert task.disk_mb.get_value_for("distributed_computing") == 10240
        assert task.gpu.get_value_for("distributed_computing") == 2
        assert task.container.get_value_for("distributed_computing") == "docker://tensorflow/tensorflow:latest-gpu"

        # Check custom attributes
        assert task.metadata.format_specific["requirements"] == "(Memory > 8000) && (HasGPU == True)"
        assert task.extra["+wantgpulab"].get_value_for("distributed_computing") == "true"

    def test_import_inline_submit_error_handling(self, persistent_test_output):
        """Test error handling for malformed inline submit descriptions."""
        # Test missing closing brace
        dag_content_missing_brace = dedent("""
            JOB bad_task {
                executable = /path/to/script.sh
                request_cpus = 2
                # Missing closing brace
        """).strip()

        dag_path = persistent_test_output / "bad.dag"
        dag_path.write_text(dag_content_missing_brace)

        # Should still import what it can parse
        wf = dag_importer.to_workflow(dag_path)

        # Should have created the task with what was parsed
        assert "bad_task" in wf.tasks
        task = wf.tasks["bad_task"]
        assert task.cpu.get_value_for("distributed_computing") == 2

    def test_import_inline_submit_empty_content(self):
        """Test importing DAGMan file with empty inline submit content."""
        dag_content = """
JOB step1 step1.sub
JOB step2 step2.sub
PARENT step1 CHILD step2
"""
        dag_file = Path("test_empty_inline.dag")
        dag_file.write_text(dag_content)

        try:
            wf = dag_importer.to_workflow(dag_file)
            assert len(wf.tasks) == 2
            assert "step1" in wf.tasks
            assert "step2" in wf.tasks
            
            # Check that resources are default (not specified)
            assert wf.tasks["step1"].cpu.get_value_for("distributed_computing") == 1
            assert wf.tasks["step1"].mem_mb.get_value_for("distributed_computing") == 4096
            assert wf.tasks["step2"].cpu.get_value_for("distributed_computing") == 1
            assert wf.tasks["step2"].mem_mb.get_value_for("distributed_computing") == 4096

        finally:
            dag_file.unlink(missing_ok=True)

    def test_import_inline_submit_workflow_metadata_preservation(
        self, persistent_test_output
    ):
        """Test that workflow metadata is preserved when importing inline submit descriptions."""
        dag_content = dedent("""
            # HTCondor DAGMan file generated by wf2wf
            # Original workflow name: metadata_test
            # Original workflow version: 2.5
            # Workflow metadata: {"description": "Test workflow with metadata", "author": "wf2wf"}

            JOB test_task {
                executable = /path/to/script.sh
                request_cpus = 1
                request_memory = 2048MB
                universe = vanilla
                queue
            }
        """).strip()

        dag_path = persistent_test_output / "metadata.dag"
        dag_path.write_text(dag_content)

        wf = dag_importer.to_workflow(dag_path)

        # Check metadata preservation
        assert wf.name == "metadata_test"
        assert wf.version == "2.5"
        assert wf.metadata.format_specific["workflow_metadata"]["description"] == "Test workflow with metadata"
        assert wf.metadata.format_specific["workflow_metadata"]["author"] == "wf2wf"


class TestDAGManImporterCompatibility:
    """Test compatibility between inline and external submit file formats."""

    def test_equivalent_import_results(self, persistent_test_output):
        """Test that inline and external submit descriptions produce equivalent import results."""
        # Create external submit file
        submit_content = dedent("""
            executable = /path/to/script.sh
            request_cpus = 4
            request_memory = 8192MB
            request_gpus = 1
            universe = docker
            docker_image = tensorflow/tensorflow:latest
            output = logs/task.out
            error = logs/task.err
            log = logs/task.log
            queue
        """).strip()

        submit_path = persistent_test_output / "task.sub"
        submit_path.write_text(submit_content)

        # Create DAG with external submit file
        dag_external_content = dedent("""
            JOB test_task task.sub
        """).strip()

        dag_external_path = persistent_test_output / "external.dag"
        dag_external_path.write_text(dag_external_content)

        # Create DAG with inline submit description
        dag_inline_content = dedent("""
            JOB test_task {
                executable = /path/to/script.sh
                request_cpus = 4
                request_memory = 8192MB
                request_gpus = 1
                universe = docker
                docker_image = tensorflow/tensorflow:latest
                output = logs/task.out
                error = logs/task.err
                log = logs/task.log
                queue
            }
        """).strip()

        dag_inline_path = persistent_test_output / "inline.dag"
        dag_inline_path.write_text(dag_inline_content)

        # Import both versions
        wf_external = dag_importer.to_workflow(dag_external_path)
        wf_inline = dag_importer.to_workflow(dag_inline_path)

        # Compare results - should be functionally equivalent
        assert len(wf_external.tasks) == len(wf_inline.tasks) == 1

        task_external = wf_external.tasks["test_task"]
        task_inline = wf_inline.tasks["test_task"]

        # Core attributes should match
        assert task_external.cpu.get_value_for("distributed_computing") == task_inline.cpu.get_value_for("distributed_computing") == 4
        assert task_external.mem_mb.get_value_for("distributed_computing") == task_inline.mem_mb.get_value_for("distributed_computing") == 8192
        assert task_external.gpu.get_value_for("distributed_computing") == task_inline.gpu.get_value_for("distributed_computing") == 1
        assert (
            task_external.container.get_value_for("distributed_computing")
            == task_inline.container.get_value_for("distributed_computing")
            == "docker://tensorflow/tensorflow:latest"
        )
