"""Tests for the Nextflow importer functionality."""

import pytest
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
        wf = to_workflow(nextflow_dir, verbose=True)

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

        # Test specific task properties
        prep_task = wf.tasks["PREPARE_DATA"]
        assert prep_task.resources.cpu == 2
        assert prep_task.resources.mem_mb == 4096  # 4GB in MB
        assert prep_task.environment.container == "python:3.9-slim"
        assert prep_task.environment.conda == "environments/python.yml"

        analyze_task = wf.tasks["ANALYZE_DATA"]
        assert analyze_task.resources.cpu == 4
        assert analyze_task.resources.mem_mb == 8192  # 8GB in MB
        assert analyze_task.resources.gpu == 1
        assert analyze_task.retry == 2
        assert analyze_task.environment.container == "rocker/r-ver:4.2.0"

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

        config_file = persistent_test_output / "test.config"
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
        wf = to_workflow(main_file, verbose=True)

        # Check configuration was parsed
        assert wf.config["input_data"] == "data/test.txt"
        assert wf.config["output_dir"] == "results"
        assert wf.config["threads"] == 8
        assert wf.config["analysis_threshold"] == 0.01
        assert wf.config["debug"] is True

        # Check process was parsed
        assert len(wf.tasks) == 1
        task = wf.tasks["TEST_PROCESS"]
        assert task.resources.cpu == 4
        assert task.resources.mem_mb == 8192  # 8GB

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
        wf = to_workflow(main_file, verbose=True)

        assert len(wf.tasks) == 2

        # Test comprehensive process
        comp_task = wf.tasks["COMPREHENSIVE_PROCESS"]
        assert comp_task.resources.cpu == 8
        assert comp_task.resources.mem_mb == 32768  # 32GB
        assert comp_task.resources.disk_mb == 102400  # 100GB
        assert comp_task.resources.time_s == 14400  # 4 hours
        assert comp_task.resources.gpu == 2
        assert comp_task.retry == 3
        assert comp_task.environment.container == "biocontainers/fastqc:0.11.9"
        assert comp_task.environment.conda == "bioconda::fastqc=0.11.9"
        assert comp_task.meta["tag"] == "sample_${input_file.baseName}"
        assert comp_task.meta["publishDir"] == "results/qc"
        assert comp_task.meta["errorStrategy"] == "retry"

        # Check inputs and outputs
        assert len(comp_task.inputs) == 2  # input_file, reference_db
        assert len(comp_task.outputs) == 3  # reports, data, summary

        # Test simple process
        simple_task = wf.tasks["SIMPLE_PROCESS"]
        assert len(simple_task.inputs) == 1  # sample_id (val)
        assert len(simple_task.outputs) == 1  # result.txt

    def test_module_parsing(self, persistent_test_output):
        """Test parsing workflows with included modules."""
        # Create module files
        modules_dir = persistent_test_output / "modules"
        modules_dir.mkdir()

        # Create a module file
        module_content = """
process ALIGN_READS {
    container 'biocontainers/bwa:0.7.17'

    cpus 4
    memory '16.GB'

    input:
    path reads
    path reference

    output:
    path "aligned.bam", emit: bam

    script:
    '''
    bwa mem !{reference} !{reads} | samtools sort -o aligned.bam
    '''
}
"""

        module_file = modules_dir / "align.nf"
        module_file.write_text(module_content)

        # Create main workflow that includes the module
        main_content = """
#!/usr/bin/env nextflow
nextflow.enable.dsl=2

include { ALIGN_READS } from './modules/align'

process CALL_VARIANTS {
    input:
    path bam_file

    output:
    path "variants.vcf"

    script:
    '''
    echo "Calling variants from ${bam_file}" > variants.vcf
    '''
}

workflow {
    reads_ch = Channel.fromPath("*.fastq")
    ref_ch = Channel.fromPath("reference.fa")

    ALIGN_READS(reads_ch, ref_ch)
    CALL_VARIANTS(ALIGN_READS.out.bam)
}
"""

        main_file = persistent_test_output / "modular_main.nf"
        main_file.write_text(main_content)

        # Import workflow
        wf = to_workflow(main_file, verbose=True)

        # Should have both processes
        assert len(wf.tasks) == 2
        assert "ALIGN_READS" in wf.tasks
        assert "CALL_VARIANTS" in wf.tasks

        # Check dependency
        deps = [(edge.parent, edge.child) for edge in wf.edges]
        assert ("ALIGN_READS", "CALL_VARIANTS") in deps

        # Check module process properties
        align_task = wf.tasks["ALIGN_READS"]
        assert align_task.resources.cpu == 4
        assert align_task.resources.mem_mb == 16384  # 16GB
        assert align_task.environment.container == "biocontainers/bwa:0.7.17"

    def test_resource_parsing(self, persistent_test_output):
        """Test parsing different resource specifications."""
        main_content = """
#!/usr/bin/env nextflow
nextflow.enable.dsl=2

process MEMORY_VARIANTS {
    memory '512.MB'
    script: 'echo "small memory"'
}

process TIME_VARIANTS {
    time '30m'
    script: 'echo "30 minutes"'
}

process DISK_VARIANTS {
    disk '5.TB'
    script: 'echo "large disk"'
}

workflow {
    MEMORY_VARIANTS()
    TIME_VARIANTS()
    DISK_VARIANTS()
}
"""

        main_file = persistent_test_output / "resources.nf"
        main_file.write_text(main_content)

        wf = to_workflow(main_file)

        # Test memory conversion
        mem_task = wf.tasks["MEMORY_VARIANTS"]
        assert mem_task.resources.mem_mb == 512

        # Test time conversion
        time_task = wf.tasks["TIME_VARIANTS"]
        assert time_task.resources.time_s == 1800  # 30 minutes

        # Test disk conversion
        disk_task = wf.tasks["DISK_VARIANTS"]
        assert disk_task.resources.disk_mb == 5242880  # 5TB in MB

    def test_dependency_extraction(self, persistent_test_output):
        """Test extraction of process dependencies from workflow definition."""
        main_content = """
#!/usr/bin/env nextflow
nextflow.enable.dsl=2

process STEP_A {
    output: path "a.txt"
    script: 'echo "A" > a.txt'
}

process STEP_B {
    input: path input_a
    output: path "b.txt"
    script: 'echo "B" > b.txt'
}

process STEP_C {
    input: path input_b
    output: path "c.txt"
    script: 'echo "C" > c.txt'
}

process STEP_D {
    input:
    path input_b
    path input_c
    output: path "d.txt"
    script: 'echo "D" > d.txt'
}

workflow {
    STEP_A()
    STEP_B(STEP_A.out)
    STEP_C(STEP_B.out)
    STEP_D(STEP_B.out, STEP_C.out)
}
"""

        main_file = persistent_test_output / "dependencies.nf"
        main_file.write_text(main_content)

        wf = to_workflow(main_file, verbose=True)

        # Check all processes are present
        assert len(wf.tasks) == 4

        # Check dependencies
        deps = [(edge.parent, edge.child) for edge in wf.edges]
        expected_deps = [
            ("STEP_A", "STEP_B"),
            ("STEP_B", "STEP_C"),
            ("STEP_B", "STEP_D"),
            ("STEP_C", "STEP_D"),
        ]

        for dep in expected_deps:
            assert dep in deps

    def test_error_handling(self, persistent_test_output):
        """Test error handling for invalid files."""
        # Test non-existent file
        with pytest.raises(FileNotFoundError):
            to_workflow("nonexistent.nf")

        # Test directory without main.nf
        empty_dir = persistent_test_output / "empty_dir"
        empty_dir.mkdir()

        with pytest.raises(FileNotFoundError):
            to_workflow(empty_dir)

        # Test invalid Nextflow syntax (should not crash)
        invalid_content = """
        This is not valid Nextflow syntax
        process {
            invalid syntax here
        """

        invalid_file = persistent_test_output / "invalid.nf"
        invalid_file.write_text(invalid_content)

        # Should handle gracefully
        wf = to_workflow(invalid_file, verbose=True)
        # Should at least create an empty workflow
        assert isinstance(wf, Workflow)
