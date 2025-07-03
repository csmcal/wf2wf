# DAGMan Examples

This directory contains example HTCondor DAGMan workflows for testing and demonstration.

## Files

### test_demo.dag
A simple linear workflow demonstrating basic DAGMan features:
- 3 jobs: prepare_data → analyze_data → generate_report
- Resource specifications (CPU, memory, disk)
- Container usage (Docker)
- Retry and priority settings
- Job variables

### Submit Files
- **prepare_data.sub**: Data preparation job (1 CPU, 2GB RAM)
- **analyze_data.sub**: Analysis job with container (4 CPU, 8GB RAM)
- **generate_report.sub**: Report generation job (2 CPU, 4GB RAM)

## Usage

Convert to wf2wf IR format:
```bash
wf2wf convert -i examples/dagman/test_demo.dag -o workflow.json
```

Convert directly to Snakemake:
```bash
wf2wf convert -i examples/dagman/test_demo.dag -o workflow.smk
```

## Features Demonstrated

- **Dependencies**: PARENT/CHILD relationships
- **Resources**: request_cpus, request_memory, request_disk
- **Containers**: Docker container specifications
- **File Transfer**: Input/output file specifications
- **Retry Logic**: RETRY directives for fault tolerance
- **Priority**: Job priority settings
- **Variables**: VARS for parameterization
