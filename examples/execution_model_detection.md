# Content-Based Execution Model Detection

This document demonstrates how wf2wf detects whether a workflow is designed for shared filesystem or distributed computing execution by analyzing the actual content of the workflow file.

## Overview

wf2wf can analyze workflow content to determine the execution model, regardless of file extension. This is particularly useful when:

- Files have incorrect extensions
- Workflows are designed for one environment but need to run in another
- You want to understand the execution characteristics before conversion

## Detection Indicators

### Shared Filesystem Indicators

Workflows designed for shared filesystem execution typically show:

- **File path patterns**: `/shared/`, `/nfs/`, `/lustre/`, `/data/`, `/project/`
- **Cloud storage**: `gs://`, `s3://`, `azure://`
- **Minimal resource specs**: Basic `threads:`, `mem_mb:`, `resources:` specifications
- **System-wide environments**: `conda:`, `container:`, `env:` specifications
- **Simple file operations**: `cp`, `mv`, `ln` commands
- **Basic error handling**: Simple `retry` mechanisms

### Distributed Computing Indicators

Workflows designed for distributed computing typically show:

- **Explicit resource specs**: `request_cpus`, `request_memory`, `request_disk`, `request_gpus`
- **File transfer specs**: `transfer_input_files`, `transfer_output_files`, `should_transfer_files`
- **Job management**: `universe =`, `executable =`, `queue`, `priority`, `retry`
- **Environment isolation**: `docker_image`, `singularity_image`, `apptainer_image`
- **HPC features**: `requirements =`, `rank =`, `+ClassAd`, `+WantGPULab`

### Hybrid Indicators

Some workflows show characteristics of both:

- **Nextflow patterns**: `publishDir`, `stash`, `stageInMode`, `stageOutMode`
- **Cloud integration**: Cloud storage with distributed features
- **Advanced resource management**: `accelerator`, `resource_labels`

## Examples

### Example 1: Shared Filesystem Workflow (Snakemake)

```bash
# Create a shared filesystem workflow
cat > shared_workflow.smk << 'EOF'
rule process_data:
    input: "/shared/data/input.txt"
    output: "/shared/results/output.txt"
    threads: 4
    resources: mem_mb=8000
    conda: "envs/python.yml"
    shell: "python process.py {input} {output}"
EOF

# Analyze the execution model
wf2wf convert -i shared_workflow.smk -o workflow.json --verbose
```

Expected output:
```
Converting shared_workflow.smk → workflow.json

Analyzing workflow execution model...
Detected execution model: shared_filesystem (confidence: 0.85)
Evidence:
  shared_filesystem: 4 indicators
    - Uses shared directory paths
    - Uses basic resource specifications
    - Uses conda environments
    - Uses simple file copy operations
Recommendations:
  - Workflow appears designed for shared filesystem execution
  - Consider adding explicit resource specifications for distributed environments
  - Review file transfer requirements for distributed computing
```

### Example 2: Distributed Computing Workflow (DAGMan)

```bash
# Create a distributed computing workflow
cat > distributed_workflow.dag << 'EOF'
JOB process_data process_data.sub
JOB analyze_results analyze_results.sub
PARENT process_data CHILD analyze_results
RETRY process_data 3
PRIORITY analyze_results 10
EOF

cat > process_data.sub << 'EOF'
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
EOF

# Analyze the execution model
wf2wf convert -i distributed_workflow.dag -o workflow.json --verbose
```

Expected output:
```
Converting distributed_workflow.dag → workflow.json

Analyzing workflow execution model...
Detected execution model: distributed_computing (confidence: 0.92)
Evidence:
  distributed_computing: 8 indicators
    - Explicit CPU requirements
    - Explicit memory requirements
    - Explicit disk requirements
    - Explicit GPU requirements
    - Job universe specification
    - Docker container specification
    - Job placement requirements
    - GPU lab requirements
Recommendations:
  - Workflow appears designed for distributed computing
  - Resource specifications are well-defined
  - File transfer mechanisms are explicitly configured
```

### Example 3: Hybrid Workflow (Nextflow)

```bash
# Create a hybrid workflow
cat > hybrid_workflow.nf << 'EOF'
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
EOF

# Analyze the execution model
wf2wf convert -i hybrid_workflow.nf -o workflow.json --verbose
```

Expected output:
```
Converting hybrid_workflow.nf → workflow.json

Analyzing workflow execution model...
Detected execution model: hybrid (confidence: 0.75)
Evidence:
  hybrid: 2 indicators
    - Uses Nextflow publishDir for output staging
    - Uses Nextflow stash for file management
Recommendations:
  - Workflow shows characteristics of both shared and distributed execution
  - May require careful configuration for target environment
  - Review both resource and file transfer specifications
```

## Use Cases

### 1. Environment Migration

When moving workflows between environments:

```bash
# Analyze before converting to distributed environment
wf2wf convert -i shared_workflow.smk -o distributed_workflow.dag --verbose

# The analysis will show what needs to be added for distributed execution
```

### 2. Workflow Validation

Check if a workflow is properly configured for its target environment:

```bash
# Validate a workflow for HPC execution
wf2wf convert -i workflow.smk --validate-resources --target-environment hpc --verbose
```

### 3. Documentation Generation

Generate reports about workflow characteristics:

```bash
# Generate detailed analysis report
wf2wf convert -i workflow.smk -o workflow.json --report-md analysis.md --verbose
```

## Confidence Levels

The detection provides confidence scores:

- **0.8-1.0**: High confidence, clear indicators
- **0.5-0.8**: Medium confidence, some indicators
- **0.3-0.5**: Low confidence, few indicators
- **0.1-0.3**: Very low confidence, using format defaults

## Limitations

- **Binary files**: Cannot analyze binary workflow files
- **Encrypted content**: Cannot analyze encrypted workflows
- **Complex patterns**: May miss sophisticated execution patterns
- **Format-specific features**: Some format-specific features may not be detected

## Integration with Conversion

The execution model detection is automatically integrated into the conversion process when using `--verbose`. The detected model can influence:

- Resource profile selection
- File transfer mode detection
- Environment configuration
- Conversion warnings and recommendations 