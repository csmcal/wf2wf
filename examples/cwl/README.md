# CWL Example Workflow

This directory contains a demonstration CWL (Common Workflow Language) workflow for testing the wf2wf converter.

## Files

- `workflow.cwl` - Main workflow definition
- `tools/` - Individual tool definitions
  - `prepare_data.cwl` - Data preparation tool
  - `analyze_data.cwl` - Data analysis tool
  - `generate_report.cwl` - Report generation tool
- `data/input_data.txt` - Sample input data
- `job.yml` - Job input parameters

## Workflow Structure

The workflow consists of three sequential steps:

1. **Data Preparation** (`prepare_data`)
   - Processes raw input data
   - Resources: 2 CPU cores, 4GB RAM
   - Container: python:3.9-slim

2. **Data Analysis** (`analyze_data`)
   - Analyzes processed data with statistical methods
   - Resources: 4 CPU cores, 8GB RAM
   - Container: python:3.9-slim

3. **Report Generation** (`generate_report`)
   - Creates final HTML report
   - Resources: 1 CPU core, 2GB RAM
   - Container: python:3.9-slim

## Dependencies

```
prepare_data → analyze_data → generate_report
```

## Features Demonstrated

- **Resource Requirements**: CPU, memory, and temporary disk specifications
- **Container Support**: Docker containers for reproducible execution
- **Parameter Passing**: Workflow inputs and step-to-step data flow
- **File Handling**: Input/output file management
- **Documentation**: Comprehensive metadata and descriptions

## Running with CWL

If you have `cwltool` installed:

```bash
cwl-runner workflow.cwl job.yml
```

## Conversion with wf2wf

Convert to other formats:

```bash
# CWL to JSON IR
wf2wf convert -i workflow.cwl -o workflow.json

# CWL to Nextflow
wf2wf convert -i workflow.cwl -o workflow.nf

# CWL to Snakemake
wf2wf convert -i workflow.cwl -o Snakefile

# CWL to DAGMan
wf2wf convert -i workflow.cwl -o workflow.dag
```
