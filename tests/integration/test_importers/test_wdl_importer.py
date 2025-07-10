"""Tests for WDL importer functionality."""

import pytest
from pathlib import Path
from wf2wf.importers import wdl


def test_wdl_importer_basic_task():
    """Test importing a basic WDL task."""

    wdl_content = """
version 1.0

task hello_world {
    input {
        String name
    }

    command <<<
        echo "Hello, ${name}!"
    >>>

    output {
        String greeting = stdout()
    }

    runtime {
        docker: "ubuntu:20.04"
        memory: "1 GB"
        cpu: 1
    }

    meta {
        description: "A simple hello world task"
        author: "Test Author"
    }
}

workflow hello_workflow {
    input {
        String input_name = "World"
    }

    call hello_world {
        input: name = input_name
    }

    output {
        String result = hello_world.greeting
    }

    meta {
        description: "Hello world workflow"
        version: "1.0"
    }
}
"""

    # Create temporary WDL file
    wdl_file = Path("test_hello.wdl")
    wdl_file.write_text(wdl_content)

    try:
        # Import the workflow
        workflow = wdl.to_workflow(wdl_file, verbose=True)

        # Verify workflow properties
        assert workflow.name == "hello_workflow"
        assert workflow.version == "1.0"
        assert len(workflow.tasks) == 1

        # Verify task properties
        task = list(workflow.tasks.values())[0]
        assert task.id == "hello_world"
        assert "echo" in task.command.get_value_for("shared_filesystem")
        assert task.cpu.get_value_for("shared_filesystem") == 1
        assert task.mem_mb.get_value_for("shared_filesystem") == 1024  # 1 GB converted to MB
        assert "docker://ubuntu:20.04" in task.container.get_value_for("shared_filesystem")

        # Verify inputs and outputs
        assert len(workflow.inputs) == 1
        assert workflow.inputs[0].id == "input_name"
        assert workflow.inputs[0].default == "World"

        assert len(workflow.outputs) == 1
        assert workflow.outputs[0].id == "result"

        # Verify metadata preservation
        if workflow.metadata and workflow.metadata.format_specific:
            assert workflow.metadata.format_specific.get("source_format") == "wdl"
            assert workflow.metadata.format_specific.get("wdl_version") == "1.0"

    finally:
        # Clean up
        if wdl_file.exists():
            wdl_file.unlink()


def test_wdl_importer_scatter():
    """Test importing a WDL workflow with scatter."""

    wdl_content = """
version 1.0

task process_file {
    input {
        File input_file
        String prefix
    }

    command <<<
        cp ${input_file} ${prefix}_output.txt
    >>>

    output {
        File output_file = "${prefix}_output.txt"
    }

    runtime {
        memory: "2 GB"
        cpu: 2
    }
}

workflow scatter_workflow {
    input {
        Array[File] input_files
        String output_prefix = "processed"
    }

    scatter (file in input_files) {
        call process_file {
            input:
                input_file = file,
                prefix = output_prefix
        }
    }

    output {
        Array[File] processed_files = process_file.output_file
    }
}
"""

    # Create temporary WDL file
    wdl_file = Path("test_scatter.wdl")
    wdl_file.write_text(wdl_content)

    try:
        # Import the workflow
        workflow = wdl.to_workflow(wdl_file, verbose=True)

        # Verify workflow properties
        assert workflow.name == "scatter_workflow"
        assert len(workflow.tasks) == 1

        # Verify scatter operation
        task = list(workflow.tasks.values())[0]
        scatter_spec = task.scatter.get_value_for("shared_filesystem")
        assert scatter_spec is not None
        assert scatter_spec.scatter_method == "dotproduct"

        # Verify resources
        assert task.cpu.get_value_for("shared_filesystem") == 2
        assert task.mem_mb.get_value_for("shared_filesystem") == 2048  # 2 GB converted to MB

    finally:
        # Clean up
        if wdl_file.exists():
            wdl_file.unlink()


def test_wdl_importer_multiple_tasks():
    """Test importing a WDL workflow with multiple tasks and dependencies."""

    wdl_content = """
version 1.0

task prepare_data {
    input {
        String input_data
    }

    command <<<
        echo "${input_data}" > prepared_data.txt
    >>>

    output {
        File prepared_file = "prepared_data.txt"
    }
}

task analyze_data {
    input {
        File data_file
    }

    command <<<
        wc -l ${data_file} > analysis_results.txt
    >>>

    output {
        File results = "analysis_results.txt"
    }
}

workflow multi_task_workflow {
    input {
        String input_data = "test data"
    }

    call prepare_data {
        input: input_data = input_data
    }

    call analyze_data {
        input: data_file = prepare_data.prepared_file
    }

    output {
        File final_results = analyze_data.results
    }
}
"""

    # Create temporary WDL file
    wdl_file = Path("test_multi_task.wdl")
    wdl_file.write_text(wdl_content)

    try:
        # Import the workflow
        workflow = wdl.to_workflow(wdl_file, verbose=True)

        # Verify workflow properties
        assert workflow.name == "multi_task_workflow"
        assert len(workflow.tasks) == 2

        # Verify tasks exist
        assert "prepare_data" in workflow.tasks
        assert "analyze_data" in workflow.tasks

        # Verify dependencies
        assert len(workflow.edges) == 1
        edge = workflow.edges[0]
        assert edge.parent == "prepare_data"
        assert edge.child == "analyze_data"

        # Verify task commands
        prepare_task = workflow.tasks["prepare_data"]
        analyze_task = workflow.tasks["analyze_data"]
        
        assert "echo" in prepare_task.command.get_value_for("shared_filesystem")
        assert "wc -l" in analyze_task.command.get_value_for("shared_filesystem")

    finally:
        # Clean up
        if wdl_file.exists():
            wdl_file.unlink()


def test_wdl_importer_error_handling():
    """Test WDL importer error handling."""

    # Test with invalid WDL content
    invalid_wdl = """
version 1.0

task invalid_task {
    input {
        String name
    }

    command <<<
        echo "Hello, ${name}!"
    >>>

    # Missing closing brace
"""

    wdl_file = Path("test_invalid.wdl")
    wdl_file.write_text(invalid_wdl)

    try:
        # Should handle parsing errors gracefully
        with pytest.raises(Exception):
            wdl.to_workflow(wdl_file, verbose=True)
    finally:
        if wdl_file.exists():
            wdl_file.unlink()


def test_wdl_type_conversion():
    """Test WDL type conversion to IR types."""

    wdl_content = """
version 1.0

task type_test {
    input {
        String string_input
        Int int_input
        Float float_input
        Boolean bool_input
        File file_input
        Array[String] array_input
    }

    command <<<
        echo "Processing inputs"
    >>>

    output {
        String result = "done"
    }
}

workflow type_workflow {
    input {
        String test_string = "test"
        Int test_int = 42
        Float test_float = 3.14
        Boolean test_bool = true
        File test_file = "input.txt"
        Array[String] test_array = ["a", "b", "c"]
    }

    call type_test {
        input:
            string_input = test_string,
            int_input = test_int,
            float_input = test_float,
            bool_input = test_bool,
            file_input = test_file,
            array_input = test_array
    }

    output {
        String result = type_test.result
    }
}
"""

    wdl_file = Path("test_types.wdl")
    wdl_file.write_text(wdl_content)

    try:
        workflow = wdl.to_workflow(wdl_file, verbose=True)

        # Verify type conversions
        assert len(workflow.inputs) == 6
        
        # Check that inputs have correct types
        input_ids = [input_spec.id for input_spec in workflow.inputs]
        assert "test_string" in input_ids
        assert "test_int" in input_ids
        assert "test_float" in input_ids
        assert "test_bool" in input_ids
        assert "test_file" in input_ids
        assert "test_array" in input_ids

    finally:
        if wdl_file.exists():
            wdl_file.unlink()


def test_wdl_memory_parsing():
    """Test WDL memory parsing with different units."""

    wdl_content = """
version 1.0

task memory_test {
    input {
        String input_data
    }

    command <<<
        echo "${input_data}" > output.txt
    >>>

    output {
        File output = "output.txt"
    }

    runtime {
        memory: "512 MB"
        cpu: 1
    }
}

workflow memory_workflow {
    input {
        String data = "test"
    }

    call memory_test {
        input: input_data = data
    }

    output {
        File result = memory_test.output
    }
}
"""

    wdl_file = Path("test_memory.wdl")
    wdl_file.write_text(wdl_content)

    try:
        workflow = wdl.to_workflow(wdl_file, verbose=True)
        
        task = list(workflow.tasks.values())[0]
        # Verify memory parsing (512 MB = 512 MB)
        assert task.mem_mb.get_value_for("shared_filesystem") == 512

    finally:
        if wdl_file.exists():
            wdl_file.unlink()


def test_wdl_disk_parsing():
    """Test WDL disk parsing with different units."""

    wdl_content = """
version 1.0

task disk_test {
    input {
        String input_data
    }

    command <<<
        echo "${input_data}" > output.txt
    >>>

    output {
        File output = "output.txt"
    }

    runtime {
        disk: "1 GB"
        memory: "256 MB"
        cpu: 1
    }
}

workflow disk_workflow {
    input {
        String data = "test"
    }

    call disk_test {
        input: input_data = data
    }

    output {
        File result = disk_test.output
    }
}
"""

    wdl_file = Path("test_disk.wdl")
    wdl_file.write_text(wdl_content)

    try:
        workflow = wdl.to_workflow(wdl_file, verbose=True)
        
        task = list(workflow.tasks.values())[0]
        # Verify disk parsing (1 GB = 1024 MB)
        assert task.disk_mb.get_value_for("shared_filesystem") == 1024

    finally:
        if wdl_file.exists():
            wdl_file.unlink()
