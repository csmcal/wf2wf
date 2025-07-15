"""Integration tests for new WDL and Galaxy format support."""

import pytest
from pathlib import Path
from wf2wf.importers import load as load_importer
from wf2wf.exporters import load as load_exporter


def test_wdl_importer_registration():
    """Test that WDL importer is properly registered."""

    # Test that WDL importer can be loaded
    wdl_importer = load_importer("wdl")
    assert wdl_importer is not None
    assert hasattr(wdl_importer, "to_workflow")


def test_wdl_exporter_registration():
    """Test that WDL exporter is properly registered."""

    # Test that WDL exporter can be loaded
    wdl_exporter = load_exporter("wdl")
    assert wdl_exporter is not None
    # The exporter class should have export_workflow method, not from_workflow
    assert hasattr(wdl_exporter, "export_workflow")


def test_galaxy_importer_registration():
    """Test that Galaxy importer is properly registered."""

    # Test that Galaxy importer can be loaded
    galaxy_importer = load_importer("galaxy")
    assert galaxy_importer is not None
    assert hasattr(galaxy_importer, "to_workflow")


def test_galaxy_exporter_registration():
    """Test that Galaxy exporter is properly registered."""

    # Test that Galaxy exporter can be loaded
    galaxy_exporter = load_exporter("galaxy")
    assert galaxy_exporter is not None
    # The exporter class should have export_workflow method, not from_workflow
    assert hasattr(galaxy_exporter, "export_workflow")


def test_all_supported_formats():
    """Test that all expected formats are supported."""

    # Test importers
    expected_importers = ["snakemake", "dagman", "nextflow", "cwl", "wdl", "galaxy"]
    for fmt in expected_importers:
        try:
            importer = load_importer(fmt)
            assert importer is not None, f"Importer for {fmt} should be available"
        except ValueError as e:
            pytest.fail(f"Importer for {fmt} should be registered: {e}")

    # Test exporters
    expected_exporters = ["snakemake", "dagman", "nextflow", "cwl", "wdl", "galaxy"]
    for fmt in expected_exporters:
        try:
            exporter = load_exporter(fmt)
            assert exporter is not None, f"Exporter for {fmt} should be available"
        except ValueError as e:
            pytest.fail(f"Exporter for {fmt} should be registered: {e}")


def test_format_error_handling():
    """Test error handling for unsupported formats."""

    # Test unsupported importer format
    with pytest.raises(ValueError, match="Unsupported importer format"):
        load_importer("unsupported_format")

    # Test unsupported exporter format
    with pytest.raises(ValueError, match="Unsupported export format"):
        load_exporter("unsupported_format")


def test_content_based_execution_model_detection(tmp_path):
    """Test content-based execution model detection."""
    from wf2wf.workflow_analysis import detect_execution_model_from_content
    
    # Test shared filesystem workflow (Snakemake)
    shared_workflow = tmp_path / "shared_workflow.smk"
    shared_workflow.write_text("""
rule process_data:
    input: "/shared/data/input.txt"
    output: "/shared/results/output.txt"
    threads: 4
    resources: mem_mb=8000
    conda: "envs/python.yml"
    shell: "python process.py {input} {output}"
""")
    
    analysis = detect_execution_model_from_content(shared_workflow, "snakemake")
    assert analysis.execution_model == "shared_filesystem"
    assert analysis.confidence > 0.5
    assert len(analysis.indicators["shared_filesystem"]) > 0
    
    # Test distributed computing workflow (DAGMan)
    distributed_workflow = tmp_path / "distributed_workflow.dag"
    distributed_workflow.write_text("""
JOB process_data process_data.sub
JOB analyze_results analyze_results.sub
PARENT process_data CHILD analyze_results
RETRY process_data 3
PRIORITY analyze_results 10
""")
    
    # Create the submit file referenced
    submit_file = tmp_path / "process_data.sub"
    submit_file.write_text("""
executable = /path/to/script.sh
request_cpus = 8
request_memory = 16384MB
request_disk = 10240MB
request_gpus = 1
universe = docker
docker_image = tensorflow/tensorflow:latest
requirements = (Memory > 16000) && (HasGPU == True)
+WantGPULab = true
+ProjectName = "DistributedWorkflow"
transfer_input_files = input_data.txt
transfer_output_files = results.txt
should_transfer_files = YES
when_to_transfer_output = ON_EXIT
queue
""")
    
    analysis = detect_execution_model_from_content(distributed_workflow, "dagman")
    assert analysis.execution_model == "distributed_computing"
    assert analysis.confidence > 0.5
    assert len(analysis.indicators["distributed_computing"]) > 0
    
    # Test hybrid workflow (Nextflow)
    hybrid_workflow = tmp_path / "hybrid_workflow.nf"
    hybrid_workflow.write_text("""
process process_data {
    input:
    path input_file
    output:
    path output_file
    publishDir "results/", mode: 'copy'
    stash "processed_data"
    
    script:
    '''
    python process.py $input_file > $output_file
    '''
}

workflow {
    channel.fromPath("data/*.txt")
        .map { file -> tuple(file, file.name) }
        .set { input_ch }
    
    process_data(input_ch)
}
""")
    
    analysis = detect_execution_model_from_content(hybrid_workflow, "nextflow")
    assert analysis.execution_model == "hybrid"
    assert analysis.confidence > 0.4
    assert len(analysis.indicators["hybrid"]) > 0
    
    # Test unknown content
    unknown_workflow = tmp_path / "unknown_workflow.txt"
    unknown_workflow.write_text("This is just some random text content.")
    
    analysis = detect_execution_model_from_content(unknown_workflow, "snakemake")
    assert analysis.execution_model == "shared_filesystem"  # Default for snakemake
    assert analysis.confidence < 0.5  # Low confidence
    assert len(analysis.indicators["shared_filesystem"]) == 0


def test_wdl_round_trip_basic():
    """Test basic round-trip conversion: WDL -> IR -> WDL."""

    # Simple WDL workflow
    wdl_content = """
version 1.0

task hello {
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
        memory: "1 GB"
        cpu: 1
    }
}

workflow hello_workflow {
    input {
        String input_name = "World"
    }

    call hello {
        input: name = input_name
    }

    output {
        String result = hello.greeting
    }
}
"""

    # Create temporary files
    input_wdl = Path("test_input.wdl")
    output_wdl = Path("test_output.wdl")

    try:
        # Write input WDL
        input_wdl.write_text(wdl_content)

        # Import WDL to IR
        wdl_importer = load_importer("wdl")
        workflow = wdl_importer.to_workflow(input_wdl)

        # Verify basic import
        assert workflow.name == "hello_workflow"
        assert len(workflow.tasks) == 1

        # Export IR back to WDL using the module-level from_workflow function
        from wf2wf.exporters.wdl import from_workflow
        from_workflow(workflow, output_wdl)

        # Verify output file was created
        assert output_wdl.exists()
        output_content = output_wdl.read_text()

        # Basic verification of output content
        assert "version 1.0" in output_content
        assert "import \"tasks/*.wdl\"" in output_content
        assert "workflow hello_workflow" in output_content
        
        # Check if task file was created
        task_file = output_wdl.parent / "tasks" / "hello.wdl"
        assert task_file.exists(), f"Task file {task_file} should be created"
        
        task_content = task_file.read_text()
        assert "task hello" in task_content

    finally:
        # Clean up
        for file in [input_wdl, output_wdl]:
            if file.exists():
                file.unlink()


def test_galaxy_round_trip_basic():
    """Test basic round-trip conversion: Galaxy -> IR -> Galaxy."""

    import json

    # Simple Galaxy workflow with an actual tool step
    galaxy_workflow = {
        "a_galaxy_workflow": "true",
        "annotation": "Test workflow",
        "format-version": "0.1",
        "name": "Test Workflow",
        "steps": {
            "0": {
                "annotation": "Input data",
                "content_id": None,
                "id": 0,
                "input_connections": {},
                "inputs": [{"description": "Input dataset", "name": "input_data"}],
                "label": "Input Data",
                "name": "Input dataset",
                "outputs": [{"name": "output", "type": "data"}],
                "tool_id": None,
                "tool_state": "{}",
                "tool_version": None,
                "type": "data_input",
                "uuid": "input-uuid",
                "workflow_outputs": [],
            },
            "1": {
                "annotation": "Process data",
                "content_id": None,
                "id": 1,
                "input_connections": {
                    "input": {"id": 0, "output_name": "output"}
                },
                "inputs": [{"description": "Input dataset", "name": "input"}],
                "label": "Process Data",
                "name": "Process data",
                "outputs": [{"name": "output", "type": "data"}],
                "tool_id": "toolshed.g2.bx.psu.edu/repos/devteam/cat/cat/1.0.0",
                "tool_state": "{\"input\": \"null\", \"lines\": \"1\", \"__page__\": 0, \"__rerun_remap_job_id__\": null}",
                "tool_version": "1.0.0",
                "type": "tool",
                "uuid": "tool-uuid",
                "workflow_outputs": [{"output_name": "output", "label": "Processed Data"}],
            }
        },
        "tags": ["test"],
        "uuid": "workflow-uuid",
        "version": "1.0",
    }

    # Create temporary files
    input_galaxy = Path("test_input.ga")
    output_galaxy = Path("test_output.ga")

    try:
        # Write input Galaxy workflow
        with open(input_galaxy, "w") as f:
            json.dump(galaxy_workflow, f)

        # Import Galaxy to IR
        galaxy_importer = load_importer("galaxy")
        workflow = galaxy_importer.to_workflow(input_galaxy)

        # Verify basic import
        assert workflow.name == "Test Workflow"
        assert len(workflow.tasks) == 1  # Should have one task from the tool step
        assert len(workflow.inputs) == 1

        # Export IR back to Galaxy using the module-level from_workflow function
        from wf2wf.exporters.galaxy import from_workflow
        from_workflow(workflow, output_galaxy)

        # Verify output file was created
        assert output_galaxy.exists()

        # Load and verify output content
        with open(output_galaxy, "r") as f:
            output_data = json.load(f)

        assert output_data["a_galaxy_workflow"] == "true"
        assert output_data["name"] == "Test Workflow"
        assert "steps" in output_data

    finally:
        # Clean up
        for file in [input_galaxy, output_galaxy]:
            if file.exists():
                file.unlink()
