# Basic Examples

This directory contains basic examples demonstrating core features of snake2dagman.

## Examples

### linear.smk
A simple linear workflow demonstrating basic rule dependencies:
```
A -> B -> C
```

### wildcards.smk
Demonstrates wildcard usage in Snakemake rules, showing how to:
- Use wildcards in input/output patterns
- Access wildcard values in shell commands
- Handle multiple wildcards in a single rule

### resources.smk
Shows how to specify resource requirements:
- Memory allocation
- CPU/thread usage
- Disk space requirements
- Custom resource definitions

## Usage

Run any example with:
```bash
snake2dagman --snakefile examples/basic/[example].smk
```

These examples are designed to be simple and educational, focusing on one feature at a time.
