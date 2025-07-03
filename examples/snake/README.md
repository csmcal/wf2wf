# snake2dagman Examples

This directory contains example Snakefiles demonstrating various features and use cases of snake2dagman.

## Directory Structure

- `basic/` - Basic workflow examples demonstrating core features
  - `linear.smk` - Simple linear workflow
  - `wildcards.smk` - Wildcard usage examples
  - `resources.smk` - Resource allocation examples

- `advanced/` - Advanced workflow features
  - `advanced.smk` - Complex workflow with multiple features
  - `checkpoint.smk` - Checkpoint usage examples
  - `notebook.smk` - Jupyter notebook integration
  - `run_block.smk` - Python run blocks
  - `scatter_gather.smk` - Scatter-gather pattern

- `error_handling/` - Error cases and edge conditions
  - `error.smk` - Error handling examples
  - `circular_dep.smk` - Circular dependency detection
  - `unsupported.smk` - Unsupported feature examples

- `data/` - Example data files and environment specifications
  - `environment.yaml` - Example conda environment
  - Sample data files for testing

- `full_workflow/` - Complete example workflow
  - Full working example with scripts, environments, and data
  - Demonstrates integration of multiple features

## Usage

Each example can be run with:

```bash
snake2dagman --snakefile examples/[category]/[example].smk
```

See the individual example files for specific usage instructions and requirements.
