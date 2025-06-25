"""Tests for WDL importer functionality."""

import pytest
from pathlib import Path
from wf2wf.importers import wdl
from wf2wf.core import Workflow, Task


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
        assert "echo" in task.command
        assert task.resources.cpu == 1
        assert task.resources.mem_mb == 1024  # 1 GB converted to MB
        assert "docker://ubuntu:20.04" in task.environment.container
        
        # Verify inputs and outputs
        assert len(workflow.inputs) == 1
        assert workflow.inputs[0].id == "input_name"
        assert workflow.inputs[0].default == "World"
        
        assert len(workflow.outputs) == 1
        assert workflow.outputs[0].id == "result"
        
        # Verify metadata preservation
        assert workflow.meta['source_format'] == 'wdl'
        assert workflow.meta['wdl_version'] == '1.0'
        
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
        assert task.scatter is not None
        assert task.scatter.scatter_method == "dotproduct"
        
        # Verify resources
        assert task.resources.cpu == 2
        assert task.resources.mem_mb == 2048  # 2 GB converted to MB
        
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
    
    runtime {
        memory: "4 GB"
        cpu: 4
        disks: "local-disk 10 HDD"
    }
}

workflow analysis_workflow {
    input {
        String raw_data = "sample data"
    }
    
    call prepare_data {
        input: input_data = raw_data
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
    wdl_file = Path("test_analysis.wdl")
    wdl_file.write_text(wdl_content)
    
    try:
        # Import the workflow
        workflow = wdl.to_workflow(wdl_file, verbose=True)
        
        # Verify workflow properties
        assert workflow.name == "analysis_workflow"
        assert len(workflow.tasks) == 2
        
        # Verify task names
        task_ids = [task.id for task in workflow.tasks.values()]
        assert "prepare_data" in task_ids
        assert "analyze_data" in task_ids
        
        # Verify dependencies
        assert len(workflow.edges) == 1
        edge = workflow.edges[0]
        assert edge.parent == "prepare_data"
        assert edge.child == "analyze_data"
        
        # Verify resource specifications
        analyze_task = None
        for task in workflow.tasks.values():
            if task.id == "analyze_data":
                analyze_task = task
                break
        
        assert analyze_task is not None
        assert analyze_task.resources.cpu == 4
        assert analyze_task.resources.mem_mb == 4096  # 4 GB
        assert analyze_task.resources.disk_mb == 10240  # 10 GB
        
    finally:
        # Clean up
        if wdl_file.exists():
            wdl_file.unlink()


def test_wdl_importer_error_handling():
    """Test error handling for invalid WDL files."""
    
    # Test with non-existent file
    with pytest.raises(FileNotFoundError):
        wdl.to_workflow("nonexistent.wdl")
    
    # Test with invalid WDL content
    invalid_wdl = Path("invalid.wdl")
    invalid_wdl.write_text("this is not valid WDL content")
    
    try:
        with pytest.raises(RuntimeError):
            wdl.to_workflow(invalid_wdl)
    finally:
        if invalid_wdl.exists():
            invalid_wdl.unlink()


def test_wdl_type_conversion():
    """Test WDL type conversion to IR types."""
    
    from wf2wf.importers.wdl import _convert_wdl_type
    
    # Basic types
    assert _convert_wdl_type("String") == "string"
    assert _convert_wdl_type("Int") == "int"
    assert _convert_wdl_type("Float") == "float"
    assert _convert_wdl_type("Boolean") == "boolean"
    assert _convert_wdl_type("File") == "File"
    
    # Optional types
    assert _convert_wdl_type("String?") == "string?"
    assert _convert_wdl_type("Int?") == "int?"
    
    # Array types
    assert _convert_wdl_type("Array[String]") == "array<string>"
    assert _convert_wdl_type("Array[File]") == "array<File>"


def test_wdl_memory_parsing():
    """Test WDL memory string parsing."""
    
    from wf2wf.importers.wdl import _parse_memory_string
    
    # Test various memory formats
    assert _parse_memory_string("1 GB") == 1024
    assert _parse_memory_string("2 GB") == 2048
    assert _parse_memory_string("512 MB") == 512
    assert _parse_memory_string("1024 MB") == 1024
    assert _parse_memory_string("4 GB") == 4096
    
    # Test invalid formats
    assert _parse_memory_string("invalid") is None
    assert _parse_memory_string("") is None


def test_wdl_disk_parsing():
    """Test WDL disk string parsing."""
    
    from wf2wf.importers.wdl import _parse_disk_string
    
    # Test disk format parsing
    assert _parse_disk_string("local-disk 10 HDD") == 10240  # 10 GB to MB
    assert _parse_disk_string("local-disk 5 SSD") == 5120   # 5 GB to MB
    
    # Test invalid formats
    assert _parse_disk_string("invalid") is None
    assert _parse_disk_string("") is None 