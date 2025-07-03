# Advanced Examples

This directory contains examples demonstrating advanced features and complex workflow patterns in snake2dagman.

## Examples

### advanced.smk
A comprehensive example combining multiple features:
- Container usage (Docker/Singularity)
- Conda environment management
- Resource allocation
- Complex rule dependencies

### checkpoint.smk
Demonstrates Snakemake checkpoint functionality:
- Dynamic file determination
- Checkpoint rule definition
- Handling checkpoint outputs

### notebook.smk
Shows Jupyter notebook integration:
- Running notebooks as rules
- Parameter passing
- Output handling

### run_block.smk
Examples of Python run blocks:
- Complex Python logic in rules
- Parameter handling
- File operations

### scatter_gather.smk
Demonstrates scatter-gather pattern:
- Parallel processing
- Result aggregation
- Resource management

### container_priority.smk
Shows container priority handling:
- Multiple container definitions
- Priority resolution
- Container selection logic

### gpu.smk
Demonstrates GPU resource allocation:
- GPU request specification
- GPU memory allocation
- GPU-specific attributes

### localrules.smk
Shows local rule usage:
- Submit-node execution
- Rule localization
- Performance optimization

### retries.smk
Demonstrates retry functionality:
- Error handling with retries
- Retry count specification
- Retry conditions

## Usage

Run any example with:
```bash
snake2dagman --snakefile examples/advanced/[example].smk
```

These examples demonstrate more complex use cases and integration of multiple features.
