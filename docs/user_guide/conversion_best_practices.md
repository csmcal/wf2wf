# Workflow Conversion Best Practices

This guide provides best practices for converting workflows between different execution environments using wf2wf.

## Understanding Execution Environment Differences

### Shared Filesystem vs Distributed Computing

Workflow engines make different assumptions about their execution environment:

| Aspect | Shared Filesystem | Distributed Computing |
|--------|------------------|---------------------|
| **File Access** | All files accessible via shared filesystem | Files must be explicitly transferred |
| **Resources** | Minimal specifications, system defaults | Explicit CPU, memory, disk allocation |
| **Environment** | System-wide software or conda | Container specifications required |
| **Error Handling** | Basic retry mechanisms | Sophisticated retry policies |
| **Parallelization** | Implicit (wildcards) | Explicit scatter/gather |

## Pre-Conversion Analysis

### 1. Understand Your Source Workflow

Before converting, analyze your source workflow:

```bash
# Get detailed information about your workflow
wf2wf info workflow.smk

# Check for potential issues
wf2wf validate workflow.smk

# Preview conversion with dry-run mode
wf2wf convert -i workflow.smk -o workflow.dag --dry-run
```

### 2. Identify Target Environment Requirements

Understand what your target environment needs:

- **HTCondor/DAGMan**: Explicit resources, containers, file transfers
- **Nextflow**: Container specifications, resource limits
- **CWL**: Resource requirements, software requirements
- **Snakemake**: Conda environments, resource specifications

## Interactive Conversion Workflow

### Step 1: Initial Conversion with Analysis

```bash
# Convert with interactive mode for guided assistance
wf2wf convert -i workflow.smk -o workflow.dag --interactive --verbose

# This enables:
# - Interactive resource specification
# - Guided environment configuration
# - Error handling setup
# - File transfer optimization
```

### Step 2: Review Configuration Analysis

The conversion report will show:

```markdown
## Configuration Analysis

### Resource Analysis
* **Memory**: 2 tasks without explicit memory requirements
* **CPU**: 1 task without CPU specifications
* **Disk**: 3 tasks without disk requirements

### Environment Analysis
* **Containers**: 3 tasks without container/conda specifications
* **Software**: 2 tasks with system dependencies

### Error Handling Analysis
* **Retry Policies**: 3 tasks without retry specifications
* **Error Recovery**: 1 task without error handling

### File Transfer Analysis
* **Transfer Modes**: 6 files with auto-detected transfer modes
* **Dependencies**: 2 files with missing dependency specifications

**Recommendations:**
* Add explicit resource requirements for all tasks
* Specify container images or conda environments for environment isolation
* Configure retry policies for fault tolerance
* Use `--infer-resources` to automatically detect resource requirements
* Use `--resource-profile cluster` for standard cluster specifications
* Enable `--auto-env` for automatic container generation
* Review file transfer modes for distributed execution
```

### Step 3: Address Issues with Interactive Assistance

Use the interactive prompts to:
- Add default resource specifications
- Specify container environments
- Configure retry policies
- Review file transfer modes

```bash
# Interactive resource specification
Found 3 tasks without explicit resource requirements.
Distributed systems require explicit resource allocation.
Add default resource specifications? [Y/n]: Y

Applied default resources: CPU=1, Memory=2048MB, Disk=4096MB

# Interactive environment specification
Found 2 tasks without container specifications.
Distributed systems typically require explicit environment isolation.
Add container specifications or conda environments? [Y/n]: Y

Enable --auto-env to automatically build containers for these tasks.

# Interactive error handling
Found 3 tasks without retry specifications.
Distributed systems benefit from explicit error handling.
Add retry specifications for failed tasks? [Y/n]: Y

Applied default retry settings (2 retries)
```

## Best Practices by Conversion Type

### Snakemake → DAGMan

**Before Conversion:**
```python
# Add resource specifications to your Snakefile
rule process_data:
    input: "data/{sample}.txt"
    output: "processed/{sample}.txt"
    resources:
        mem_mb=4096,
        disk_mb=4096
    shell: "python process.py {input} > {output}"
```

**Enhanced Conversion:**
```bash
# Convert with all enhanced features
wf2wf convert -i workflow.smk -o workflow.dag \
    --interactive \
    --infer-resources \
    --validate-resources \
    --resource-profile cluster \
    --target-env distributed \
    --report-md
```

**After Conversion:**
```bash
# Review generated DAGMan files
cat workflow.dag
cat process_data_*.sub

# Check conversion report for any issues
cat conversion_report.md
```

### CWL → Nextflow

**Before Conversion:**
```yaml
# Ensure resource requirements are specified
requirements:
  - class: ResourceRequirement
    coresMin: 4
    ramMin: 8192
    tmpdirMin: 4096
```

**Enhanced Conversion:**
```bash
# Convert with enhanced CWL processing
wf2wf convert -i workflow.cwl -o main.nf \
    --interactive \
    --infer-resources \
    --validate-resources \
    --resource-profile cloud \
    --target-env distributed
```

**After Conversion:**
```groovy
// Review generated Nextflow process
process PROCESS_DATA {
    cpus 4
    memory 8.GB
    disk 4.GB
    
    input:
    path input_file
    
    output:
    path output_file
    
    script:
    """
    python process.py ${input_file} > ${output_file}
    """
}
```

### DAGMan → Snakemake

**Before Conversion:**
```bash
# Review submit file specifications
cat job.sub
# Look for: request_cpus, request_memory, transfer_input_files
```

**Enhanced Conversion:**
```bash
# Convert with enhanced DAGMan processing
wf2wf convert -i workflow.dag -o workflow.smk \
    --interactive \
    --infer-resources \
    --validate-resources \
    --resource-profile shared \
    --target-env distributed
```

**After Conversion:**
```python
# Review generated Snakefile
# Ensure resource specifications are preserved
rule job:
    input: "input.txt"
    output: "output.txt"
    resources:
        mem_mb=4096,
        disk_mb=4096
    shell: "python job.py {input} > {output}"
```

## Loss Detection and Reporting

### Comprehensive Loss Analysis

```bash
# Generate detailed loss report
wf2wf convert -i workflow.smk -o workflow.dag --report-md

# The report includes:
# - Information preservation analysis
# - Potential loss identification
# - Conversion recommendations
# - Quality metrics
```

### Loss Report Example

```markdown
# Enhanced Conversion Report

## Information Loss Analysis

### Preserved Information (100%)
- ✅ Task definitions and dependencies
- ✅ Resource specifications (enhanced)
- ✅ Container/environment specifications
- ✅ Input/output file specifications
- ✅ Error handling configurations

### Potential Loss (Minimal)
- ⚠️ Snakemake wildcards → DAGMan parameter substitution
- ⚠️ Snakemake conda environments → DAGMan container specifications

### Quality Metrics
- **Compliance Score**: 95/100
- **Resource Coverage**: 100%
- **Environment Coverage**: 100%
- **Error Handling Coverage**: 100%

### Recommendations
- Review wildcard substitutions for correctness
- Verify container specifications match conda environments
- All resource specifications are properly converted
```

## Enhanced Troubleshooting

### Common Issues and Solutions

1. **Resource Validation Failures**
   ```bash
   # Adjust resource specifications
   wf2wf convert -i workflow.smk -o workflow.dag --resource-profile shared
   
   # Or use interactive mode to adjust manually
   wf2wf convert -i workflow.smk -o workflow.dag --interactive
   ```

2. **Container Generation Issues**
   ```bash
   # Enable automatic container generation
   wf2wf convert -i workflow.smk -o workflow.dag --auto-env
   
   # Or specify containers manually
   wf2wf convert -i workflow.smk -o workflow.dag --interactive
   ```

3. **File Transfer Problems**
   ```bash
   # Review file transfer modes
   wf2wf convert -i workflow.smk -o workflow.dag --interactive
   
   # Optimize for distributed computing
   wf2wf convert -i workflow.smk -o workflow.dag --target-env distributed
   ```

### Getting Enhanced Help

```bash
# Get detailed information about your workflow
wf2wf info workflow.smk

# Validate workflow with enhanced checks
wf2wf validate workflow.smk

# Preview conversion with all enhancements
wf2wf convert -i workflow.smk -o workflow.dag --dry-run --verbose

# Check for potential issues
wf2wf convert -i workflow.smk -o workflow.dag --interactive
```

## Resource Specification Guidelines

### Automatic Resource Inference

The enhanced system can automatically infer resource requirements:

```bash
# Enable automatic resource inference
wf2wf convert -i workflow.smk -o workflow.dag --infer-resources

# Inference examples:
# - "bwa mem" → 8GB memory, 4 CPU
# - "samtools sort" → 4GB memory, 2 CPU
# - "python script.py" → 1GB memory, 1 CPU
# - "Rscript analysis.R" → 2GB memory, 1 CPU
```

### Resource Profiles

Use predefined resource profiles for different environments:

```bash
# Apply specific resource profile
wf2wf convert -i workflow.smk -o workflow.dag --resource-profile cluster

# Available profiles:
# - shared: Light resources (1 CPU, 512MB RAM, 1GB disk)
# - cluster: Standard cluster (1 CPU, 2GB RAM, 4GB disk)
# - cloud: Cloud-optimized (2 CPU, 4GB RAM, 8GB disk)
# - hpc: High-performance (4 CPU, 8GB RAM, 16GB disk)
# - gpu: GPU-enabled (4 CPU, 16GB RAM, 32GB disk)
```

### Memory Requirements

| Task Type | Recommended Memory | Notes |
|-----------|-------------------|-------|
| Light processing | 1-2 GB | Text processing, simple scripts |
| Medium analysis | 4-8 GB | Data analysis, moderate datasets |
| Heavy computation | 16-32 GB | Machine learning, large datasets |
| Genomics | 32-64 GB | Sequence alignment, variant calling |

### Disk Requirements

| Task Type | Recommended Disk | Notes |
|-----------|------------------|-------|
| Text processing | 1-2 GB | Small input/output files |
| Data analysis | 4-8 GB | Moderate datasets |
| Genomics | 10-50 GB | Large sequence files |
| Machine learning | 5-20 GB | Model files and datasets |

### CPU Requirements

| Task Type | Recommended CPUs | Notes |
|-----------|-----------------|-------|
| Single-threaded | 1 | Simple scripts, basic processing |
| Multi-threaded | 4-8 | Data analysis, moderate parallelism |
| High-performance | 16-32 | Machine learning, genomics |

## Container and Environment Best Practices

### Automatic Container Generation

```bash
# Enable automatic container generation
wf2wf convert -i workflow.smk -o workflow.dag --auto-env

# This will:
# - Analyze software dependencies
# - Generate appropriate container specifications
# - Create conda environment files
# - Optimize for target environment
```

### Container Specifications

```python
# Snakemake with container
rule process:
    container: "docker://python:3.9-slim"
    shell: "python process.py"

# CWL with Docker requirement
requirements:
  - class: DockerRequirement
    dockerPull: python:3.9-slim
```

### Conda Environments

```python
# Snakemake with conda
rule process:
    conda: "environment.yaml"
    shell: "python process.py"
```

```yaml
# environment.yaml
name: analysis
channels:
  - conda-forge
  - bioconda
dependencies:
  - python=3.9
  - pandas
  - numpy
  - biopython
```

## Error Handling and Retry Policies

### Retry Specifications

```python
# Snakemake with retries
rule process:
    retries: 3
    shell: "python process.py"
```

```bash
# DAGMan with retry
RETRY process_job 3
```

### Interactive Error Handling Configuration

```bash
# Enable automatic error handling setup
wf2wf convert -i workflow.smk -o workflow.dag --interactive

# The system will:
# - Detect tasks without retry specifications
# - Suggest appropriate retry policies
# - Configure error recovery mechanisms
# - Optimize for target environment
```

### Error Strategies

- **Transient failures**: 2-3 retries with exponential backoff
- **Resource failures**: Retry with different resource specifications
- **Data corruption**: Validate inputs before processing
- **Network issues**: Retry with longer timeouts

### Error Handling Examples

# Snakemake with enhanced error handling
rule process:
    input: "data.txt"
    output: "result.txt"
    retries: 3  # Auto-configured
    shell: "python process.py {input} > {output}"
```

```bash
# DAGMan with enhanced error handling
# Auto-generated submit file includes:
# retry = 3
# on_exit_remove = (ExitCode != 0)
# max_retries = 3
```

## File Transfer Optimization

### Transfer Mode Selection

```python
from wf2wf.core import ParameterSpec

# Input files - always transfer
input_file = ParameterSpec(
    id="data/input.txt",
    type="File",
    transfer_mode="always"
)

# Reference data - shared storage
reference = ParameterSpec(
    id="/shared/genomes/hg38.fa",
    type="File",
    transfer_mode="shared"
)

# Temporary files - never transfer
temp_file = ParameterSpec(
    id="temp.log",
    type="File",
    transfer_mode="never"
)
```

### Transfer Optimization Tips

1. **Minimize transfers**: Use `shared` mode for large reference files
2. **Batch transfers**: Group related files together
3. **Compress data**: Use compressed formats when possible
4. **Local processing**: Use `never` mode for temporary files

## Validation and Testing

### Post-Conversion Validation

```bash
# Validate the converted workflow
wf2wf validate workflow.dag

# Check for any unresolved losses
cat workflow.loss.json

# Test with a small dataset
condor_submit_dag workflow.dag
```

### Testing Checklist

- [ ] All tasks have appropriate resource specifications
- [ ] Container/environment specifications are correct
- [ ] File transfer modes are appropriate
- [ ] Retry policies are configured
- [ ] Dependencies are correctly specified
- [ ] Output files are properly defined

## Troubleshooting Common Issues

### Resource Issues

**Problem**: Jobs fail due to insufficient memory
**Solution**: Increase memory specifications or optimize memory usage

**Problem**: Jobs fail due to insufficient disk space
**Solution**: Increase disk specifications or clean up temporary files

### Container Issues

**Problem**: Container not found
**Solution**: Ensure container image exists and is accessible

**Problem**: Container permissions issues
**Solution**: Check container user and file permissions

### File Transfer Issues

**Problem**: Files not found on compute nodes
**Solution**: Check transfer modes and ensure files are in transfer lists

**Problem**: Unnecessary large file transfers
**Solution**: Mark reference data as `shared` mode

## Advanced Configuration

### Custom Resource Patterns

```python
# Custom resource detection patterns
def custom_resource_detection(task):
    if "alignment" in task.id:
        return ResourceSpec(mem_mb=16384, cpu=8)
    elif "qc" in task.id:
        return ResourceSpec(mem_mb=2048, cpu=2)
    else:
        return ResourceSpec(mem_mb=4096, cpu=4)
```

### Environment-Specific Configurations

```bash
# Different configurations for different environments
wf2wf convert -i workflow.smk -o workflow.dag \
    --default-memory 8GB \
    --default-disk 10GB \
    --default-cpus 4
```

## Performance Optimization

### Resource Optimization

1. **Profile your workflows**: Measure actual resource usage
2. **Right-size resources**: Match specifications to actual needs
3. **Use resource limits**: Prevent runaway jobs
4. **Monitor usage**: Track resource utilization over time

### Transfer Optimization

1. **Use shared storage**: Minimize data movement
2. **Compress data**: Reduce transfer sizes
3. **Batch operations**: Group related transfers
4. **Cache frequently used data**: Store on shared storage

## Related Documentation

- [File Transfer Handling](file_transfers.md) - Detailed file transfer guide
- [Installation Guide](installation.md) - Setting up wf2wf
- [Engine Overview](engines/overview.md) - Understanding workflow engines
- [Troubleshooting](troubleshooting.md) - Common issues and solutions 