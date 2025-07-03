# Nextflow Examples

This directory contains example Nextflow workflows for testing and demonstration of wf2wf conversion capabilities.

## Files

### main.nf
Main Nextflow workflow file demonstrating:
- DSL2 syntax
- Process includes and modules
- Channel operations
- Workflow composition
- Parameter handling

### nextflow.config
Configuration file showcasing:
- Process resource specifications
- Container configurations
- Executor settings
- Profile definitions for different environments
- Monitoring and reporting options

### Modules (modules/)
- **prepare.nf**: Data preparation process with Python container
- **analyze.nf**: Analysis process with R container and GPU support
- **report.nf**: Report generation with Pandoc container

### Environments (environments/)
- **python.yml**: Conda environment for Python-based processes
- **r.yml**: Conda environment for R-based processes

### Data (data/)
- **raw_data.txt**: Sample input data for testing

## Features Demonstrated

### Process Features
- **Resource Specifications**: CPU, memory, disk, GPU requirements
- **Container Support**: Docker containers for reproducible environments
- **Conda Environments**: Language-specific package management
- **Error Handling**: Retry strategies and error recovery
- **Publishing**: Output file management and organization

### Workflow Features
- **Modular Design**: Separate modules for reusability
- **Channel Operations**: Data flow management
- **Parameter Configuration**: Flexible pipeline parameterization
- **Multiple Outputs**: Different output types per process

### Configuration Features
- **Executor Profiles**: Local, cluster, and cloud execution
- **Resource Monitoring**: Timeline, reports, and traces
- **Container Engines**: Docker and Singularity support
- **Queue Management**: Cluster job submission settings

## Usage

### Run the workflow locally:
```bash
cd examples/nextflow
nextflow run main.nf
```

### Run with custom parameters:
```bash
nextflow run main.nf --input_data custom_data.txt --output_dir custom_results
```

### Convert to wf2wf IR format:
```bash
wf2wf convert -i examples/nextflow/main.nf -o workflow.json
```

### Convert to other formats:
```bash
# Convert to Snakemake
wf2wf convert -i examples/nextflow/main.nf -o workflow.smk

# Convert to DAGMan
wf2wf convert -i examples/nextflow/main.nf -o workflow.dag
```

## Conversion Capabilities

This example demonstrates wf2wf's ability to convert:
- Process definitions → Tasks
- Resource specifications → ResourceSpec
- Container/conda settings → EnvironmentSpec
- Process dependencies → Edges
- Configuration parameters → Workflow config
- Error handling settings → Task retry/priority
