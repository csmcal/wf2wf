"""Tests for the Nextflow importer functionality."""

import pytest
from pathlib import Path
from wf2wf.core import Workflow
from wf2wf.importers.nextflow import to_workflow


class TestNextflowImporter:
    """Test the Nextflow importer."""

    def test_import_demo_workflow(self, examples_dir, persistent_test_output):
        """Test importing the demo Nextflow workflow."""
        nextflow_dir = examples_dir / "nextflow"

        if not (nextflow_dir / "main.nf").exists():
            pytest.skip("Demo Nextflow workflow not found")

        # Import the workflow
        wf = to_workflow(Path(nextflow_dir), verbose=True)

        # Test basic workflow properties
        assert wf.name == "nextflow"
        assert len(wf.tasks) == 3  # PREPARE_DATA, ANALYZE_DATA, GENERATE_REPORT
        assert len(wf.edges) == 2  # prepare->analyze->report

        # Test task names (should be uppercase in Nextflow)
        task_names = set(wf.tasks.keys())
        expected_names = {"PREPARE_DATA", "ANALYZE_DATA", "GENERATE_REPORT"}
        assert task_names == expected_names

        # Test dependencies
        deps = [(edge.parent, edge.child) for edge in wf.edges]
        expected_deps = [
            ("PREPARE_DATA", "ANALYZE_DATA"),
            ("ANALYZE_DATA", "GENERATE_REPORT"),
        ]
        assert set(deps) == set(expected_deps)

        # Test specific task properties using environment-specific values
        prep_task = wf.tasks["PREPARE_DATA"]
        assert prep_task.cpu.get_value_for("shared_filesystem") == 2
        assert prep_task.mem_mb.get_value_for("shared_filesystem") == 4096  # 4GB in MB
        assert prep_task.container.get_value_for("shared_filesystem") == "python:3.9-slim"
        assert prep_task.conda.get_value_for("shared_filesystem") == "environments/python.yml"

        analyze_task = wf.tasks["ANALYZE_DATA"]
        assert analyze_task.cpu.get_value_for("shared_filesystem") == 4
        assert analyze_task.mem_mb.get_value_for("shared_filesystem") == 8192  # 8GB in MB
        assert analyze_task.gpu.get_value_for("shared_filesystem") == 1
        assert analyze_task.retry_count.get_value_for("shared_filesystem") == 2
        assert analyze_task.container.get_value_for("shared_filesystem") == "rocker/r-ver:4.2.0"

        # Save converted workflow to test output
        output_file = persistent_test_output / "nextflow_workflow.json"
        wf.save_json(output_file)
        assert output_file.exists()

    def test_parse_nextflow_config(self, persistent_test_output):
        """Test parsing Nextflow configuration files."""
        # Create a test config file
        config_content = """
// Test nextflow.config
nextflow.enable.dsl = 2

params {
    input_data = "data/test.txt"
    output_dir = "results"
    threads = 8
    memory = "16.GB"
    analysis_threshold = 0.01
    debug = true
}

process {
    cpus = 2
    memory = '4.GB'
    time = '2h'

    withName: 'SPECIAL_PROCESS' {
        cpus = 8
        memory = '16.GB'
        container = 'special/image:latest'
    }
}

executor {
    name = 'slurm'
    queueSize = 100
}
"""

        config_file = persistent_test_output / "nextflow.config"
        config_file.write_text(config_content)

        # Test main.nf that references the config
        main_content = """
#!/usr/bin/env nextflow
nextflow.enable.dsl=2

process TEST_PROCESS {
    cpus 4
    memory '8.GB'

    input:
    path input_file

    output:
    path "output.txt"

    script:
    '''
    echo "Processing" > output.txt
    '''
}

workflow {
    input_ch = Channel.fromPath(params.input_data)
    TEST_PROCESS(input_ch)
}
"""

        main_file = persistent_test_output / "main.nf"
        main_file.write_text(main_content)

        # Import workflow
        wf = to_workflow(Path(main_file), verbose=True, debug=True)

        # Check configuration was parsed (now in metadata)
        assert wf.metadata is not None
        assert "nextflow_config" in wf.metadata.format_specific
        config = wf.metadata.format_specific["nextflow_config"]
        assert config["params"]["input_data"] == "data/test.txt"
        assert config["params"]["output_dir"] == "results"
        assert config["params"]["threads"] == 8
        assert config["params"]["analysis_threshold"] == 0.01
        assert config["params"]["debug"] is True

        # Check process was parsed
        assert len(wf.tasks) == 1
        task = wf.tasks["TEST_PROCESS"]
        assert task.cpu.get_value_for("shared_filesystem") == 4
        assert task.mem_mb.get_value_for("shared_filesystem") == 8192  # 8GB

    def test_parse_process_definitions(self, persistent_test_output):
        """Test parsing various process definition features."""
        # Create a comprehensive process definition
        main_content = """
#!/usr/bin/env nextflow
nextflow.enable.dsl=2

process COMPREHENSIVE_PROCESS {
    tag "sample_${input_file.baseName}"

    container 'biocontainers/fastqc:0.11.9'
    conda 'bioconda::fastqc=0.11.9'

    cpus 8
    memory '32.GB'
    disk '100.GB'
    time '4h'
    accelerator 2, type: 'nvidia-tesla-v100'

    publishDir "results/qc", mode: 'copy'

    errorStrategy 'retry'
    maxRetries 3

    input:
    path input_file
    path reference_db

    output:
    path "*.html", emit: reports
    path "*.zip", emit: data
    path "summary.txt", emit: summary

    script:
    '''
    echo "Running comprehensive analysis"
    fastqc !{input_file} --outdir .
    echo "Analysis complete" > summary.txt
    '''
}

process SIMPLE_PROCESS {
    input:
    val sample_id

    output:
    path "result.txt"

    script:
    '''
    echo "Sample: ${sample_id}" > result.txt
    '''
}

workflow {
    input_ch = Channel.fromPath("*.fastq")
    ref_ch = Channel.fromPath("reference.db")

    COMPREHENSIVE_PROCESS(input_ch, ref_ch)
    SIMPLE_PROCESS(Channel.value("test"))
}
"""

        main_file = persistent_test_output / "comprehensive.nf"
        main_file.write_text(main_content)

        # Import workflow
        wf = to_workflow(Path(main_file), verbose=True)

        # Check both processes were parsed
        assert len(wf.tasks) == 2

        # Check comprehensive process
        comp_task = wf.tasks["COMPREHENSIVE_PROCESS"]
        assert comp_task.cpu.get_value_for("shared_filesystem") == 8
        assert comp_task.mem_mb.get_value_for("shared_filesystem") == 32768  # 32GB
        assert comp_task.disk_mb.get_value_for("shared_filesystem") == 102400  # 100GB
        assert comp_task.time_s.get_value_for("shared_filesystem") == 14400  # 4h
        assert comp_task.gpu.get_value_for("shared_filesystem") == 2
        assert comp_task.container.get_value_for("shared_filesystem") == "biocontainers/fastqc:0.11.9"
        assert comp_task.conda.get_value_for("shared_filesystem") == "bioconda::fastqc=0.11.9"
        assert comp_task.retry_count.get_value_for("shared_filesystem") == 3

        # Check simple process
        simple_task = wf.tasks["SIMPLE_PROCESS"]
        assert simple_task.command.get_value_for("shared_filesystem") is not None

    def test_module_parsing(self, persistent_test_output):
        """Test parsing Nextflow modules."""
        # Create module file
        module_content = """
#!/usr/bin/env nextflow
nextflow.enable.dsl=2

process MODULE_PROCESS {
    tag "module_process"

    cpus 4
    memory '8.GB'

    input:
    path input_file

    output:
    path "module_output.txt"

    script:
    '''
    echo "Module processing" > module_output.txt
    '''
}
"""

        module_file = persistent_test_output / "modules" / "test_module.nf"
        module_file.parent.mkdir(exist_ok=True)
        module_file.write_text(module_content)

        # Create main workflow that imports module
        main_content = """
#!/usr/bin/env nextflow
nextflow.enable.dsl=2

include { MODULE_PROCESS } from './modules/test_module'

workflow {
    input_ch = Channel.fromPath("*.txt")
    MODULE_PROCESS(input_ch)
}
"""

        main_file = persistent_test_output / "modular_main.nf"
        main_file.write_text(main_content)

        # Import workflow
        wf = to_workflow(Path(main_file), verbose=True, debug=True)

        # Check module process was parsed
        assert len(wf.tasks) == 1  # Should include the module process
        assert "MODULE_PROCESS" in wf.tasks

        module_task = wf.tasks["MODULE_PROCESS"]
        assert module_task.cpu.get_value_for("shared_filesystem") == 4
        assert module_task.mem_mb.get_value_for("shared_filesystem") == 8192  # 8GB

    def test_resource_parsing(self, persistent_test_output):
        """Test parsing various resource specifications."""
        main_content = """
#!/usr/bin/env nextflow
nextflow.enable.dsl=2

process CPU_VARIANTS {
    cpus 2
    memory '4.GB'
    script: 'echo "CPU task"'
}

process MEMORY_VARIANTS {
    cpus 1
    memory '16.GB'
    script: 'echo "Memory task"'
}

process GPU_VARIANTS {
    cpus 4
    memory '32.GB'
    accelerator 1, type: 'nvidia-tesla-k80'
    script: 'echo "GPU task"'
}

workflow {
    CPU_VARIANTS()
    MEMORY_VARIANTS()
    GPU_VARIANTS()
}
"""

        main_file = persistent_test_output / "resources.nf"
        main_file.write_text(main_content)

        # Import workflow
        wf = to_workflow(Path(main_file), verbose=True)

        # Check resource parsing
        assert len(wf.tasks) == 3

        cpu_task = wf.tasks["CPU_VARIANTS"]
        assert cpu_task.cpu.get_value_for("shared_filesystem") == 2
        assert cpu_task.mem_mb.get_value_for("shared_filesystem") == 4096

        mem_task = wf.tasks["MEMORY_VARIANTS"]
        assert mem_task.cpu.get_value_for("shared_filesystem") == 1
        assert mem_task.mem_mb.get_value_for("shared_filesystem") == 16384

        gpu_task = wf.tasks["GPU_VARIANTS"]
        assert gpu_task.cpu.get_value_for("shared_filesystem") == 4
        assert gpu_task.mem_mb.get_value_for("shared_filesystem") == 32768
        assert gpu_task.gpu.get_value_for("shared_filesystem") == 1

    def test_dependency_extraction(self, persistent_test_output):
        """Test extracting dependencies between processes."""
        main_content = """
#!/usr/bin/env nextflow
nextflow.enable.dsl=2

process step1 {
    input: path input_file
    output: path "step1_output.txt"
    script: 'echo "Step 1" > step1_output.txt'
}

process step2 {
    input: path step1_output
    output: path "step2_output.txt"
    script: 'echo "Step 2" > step2_output.txt'
}

process step3 {
    input: path step2_output
    output: path "step3_output.txt"
    script: 'echo "Step 3" > step3_output.txt'
}

process step4 {
    input: path step3_output
    output: path "final_output.txt"
    script: 'echo "Final step" > final_output.txt'
}

workflow {
    input_ch = Channel.fromPath("input.txt")
    
    step1_ch = step1(input_ch)
    step2_ch = step2(step1_ch)
    step3_ch = step3(step2_ch)
    step4_ch = step4(step3_ch)
}
"""

        main_file = persistent_test_output / "dependencies.nf"
        main_file.write_text(main_content)

        # Import workflow
        wf = to_workflow(Path(main_file), verbose=True)

        # Check all processes were parsed
        assert len(wf.tasks) == 4

        # Check dependencies
        deps = [(edge.parent, edge.child) for edge in wf.edges]
        expected_deps = [
            ("step1", "step2"),
            ("step2", "step3"),
            ("step3", "step4"),
        ]
        assert set(deps) == set(expected_deps)

    def test_error_handling(self, persistent_test_output):
        """Test error handling for invalid Nextflow files."""
        # Test with non-existent file
        with pytest.raises(ImportError):
            to_workflow("nonexistent.nf")

        # Test with invalid Nextflow syntax
        invalid_content = """
#!/usr/bin/env nextflow
invalid syntax here
process INVALID {
    this is not valid nextflow
}
"""

        invalid_file = persistent_test_output / "invalid.nf"
        invalid_file.write_text(invalid_content)

        # Should handle gracefully or raise appropriate error
        try:
            wf = to_workflow(Path(invalid_file), verbose=True)
            # If it doesn't raise an error, at least it should create a workflow
            assert isinstance(wf, Workflow)
        except Exception as e:
            # Should be a specific error, not a generic one
            assert "nextflow" in str(e).lower() or "syntax" in str(e).lower()
