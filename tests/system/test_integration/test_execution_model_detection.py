import tempfile
from pathlib import Path
import pytest
from wf2wf.workflow_analysis import detect_execution_model_from_content


def test_shared_filesystem_workflow():
    """Test detection of shared filesystem workflow characteristics."""
    workflow_content = """
rule process_data:
    input: "/shared/data/input.txt"
    output: "/shared/results/output.txt"
    threads: 4
    resources: mem_mb=8000
    conda: "envs/python.yml"
    shell: "python process.py {input} {output}"

rule analyze_results:
    input: "/shared/results/output.txt"
    output: "/shared/results/analysis.txt"
    threads: 2
    resources: mem_mb=4000
    shell: "python analyze.py {input} > {output}"
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.smk', delete=False) as f:
        f.write(workflow_content)
        temp_file = Path(f.name)
    try:
        analysis = detect_execution_model_from_content(temp_file, "snakemake")
        assert analysis.execution_model == "shared_filesystem"
        assert analysis.confidence > 0.5
        assert len(analysis.indicators["shared_filesystem"]) > 0
    finally:
        temp_file.unlink()


def test_distributed_computing_workflow():
    """Test detection of distributed computing workflow characteristics."""
    workflow_content = """
JOB process_data process_data.sub
JOB analyze_results analyze_results.sub
PARENT process_data CHILD analyze_results
RETRY process_data 3
PRIORITY analyze_results 10
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.dag', delete=False) as f:
        f.write(workflow_content)
        temp_file = Path(f.name)
    submit_content = """
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
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sub', delete=False) as f:
        f.write(submit_content)
        submit_file = Path(f.name)
    try:
        analysis = detect_execution_model_from_content(temp_file, "dagman")
        assert analysis.execution_model == "distributed_computing"
        assert analysis.confidence > 0.5
        assert len(analysis.indicators["distributed_computing"]) > 0
    finally:
        temp_file.unlink()
        submit_file.unlink()


def test_hybrid_workflow():
    """Test detection of hybrid workflow characteristics."""
    workflow_content = """
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
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.nf', delete=False) as f:
        f.write(workflow_content)
        temp_file = Path(f.name)
    try:
        analysis = detect_execution_model_from_content(temp_file, "nextflow")
        assert analysis.execution_model == "hybrid"
        assert analysis.confidence > 0.4
        assert len(analysis.indicators["hybrid"]) > 0
    finally:
        temp_file.unlink()


def test_cloud_native_workflow():
    """Test detection of cloud-native workflow characteristics."""
    workflow_content = """
version 1.0

task process_data {
    input {
        String input_file
    }
    
    command <<<
        aws s3 cp ${input_file} /tmp/input.txt
        python process.py /tmp/input.txt > /tmp/output.txt
        aws s3 cp /tmp/output.txt s3://my-bucket/results/
    >>>
    
    output {
        String result = "s3://my-bucket/results/output.txt"
    }
    
    runtime {
        memory: "2 GB"
        cpu: 2
        docker: "python:3.9"
        region: "us-west-2"
        instance_type: "c5.large"
    }
}

workflow cloud_workflow {
    input {
        String input_data = "s3://my-bucket/input/data.txt"
    }
    
    call process_data {
        input: input_file = input_data
    }
    
    output {
        String result = process_data.result
    }
}
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.wdl', delete=False) as f:
        f.write(workflow_content)
        temp_file = Path(f.name)
    try:
        analysis = detect_execution_model_from_content(temp_file, "wdl")
        assert analysis.execution_model == "cloud_native"
        assert analysis.confidence > 0.5
        assert len(analysis.indicators["cloud_native"]) > 0
    finally:
        temp_file.unlink()


def test_unknown_content():
    """Test handling of unknown content."""
    workflow_content = "This is just some random text content with no workflow patterns."
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(workflow_content)
        temp_file = Path(f.name)
    try:
        analysis = detect_execution_model_from_content(temp_file, "snakemake")
        assert analysis.execution_model == "shared_filesystem"  # Default for snakemake
        assert analysis.confidence < 0.5  # Low confidence
        assert len(analysis.indicators["shared_filesystem"]) == 0
    finally:
        temp_file.unlink() 