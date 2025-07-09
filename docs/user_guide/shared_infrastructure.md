# Shared Infrastructure Features

wf2wf provides a comprehensive shared infrastructure that enhances all workflow importers with intelligent inference, interactive prompting, and resource management capabilities.

## Overview

The shared infrastructure consists of several key components that work together to provide a consistent and enhanced user experience across all supported workflow formats:

- **Intelligent Inference**: Automatically fills in missing information
- **Interactive Prompting**: Guides users through configuration decisions
- **Resource Processing**: Validates and optimizes resource specifications
- **Loss Integration**: Detects and reports information loss during conversion
- **Environment Management**: Adapts workflows for different execution environments

## Intelligent Inference

### What It Does

The intelligent inference system analyzes your workflow and automatically fills in missing information based on:

- **Command Analysis**: Infers resource requirements from command content
- **Format Patterns**: Applies format-specific best practices
- **Execution Environment**: Adapts to target environment requirements
- **Content Analysis**: Detects execution models and patterns

### How It Works

```bash
# Automatic inference is enabled by default
wf2wf convert -i workflow.smk -o workflow.dag

# The system will automatically:
# - Infer missing resource requirements
# - Detect execution models
# - Apply environment-specific optimizations
# - Suggest improvements
```

### Inference Examples

**Resource Inference:**
```python
# Before inference
rule process:
    input: "data.txt"
    output: "result.txt"
    shell: "python heavy_analysis.py {input} > {output}"

# After inference (automatic)
rule process:
    input: "data.txt"
    output: "result.txt"
    resources:
        mem_mb=8192,  # Inferred from "heavy_analysis"
        cpu=4,        # Inferred from analysis type
        disk_mb=4096  # Inferred from file operations
    shell: "python heavy_analysis.py {input} > {output}"
```

**Execution Model Detection:**
```bash
# Automatic detection of execution model
wf2wf info workflow.smk

# Output:
# Execution Model: distributed_computing
# Detection Method: content_analysis
# Confidence: 0.85
# Indicators: 
#   - Multiple resource specifications
#   - Container requirements
#   - File transfer modes
```

## Interactive Prompting

### When It's Useful

Interactive mode is particularly helpful when:

- Converting between different execution environments
- Workflows have missing resource specifications
- Container/environment specifications are incomplete
- Error handling needs to be configured
- File transfer modes need optimization

### Enabling Interactive Mode

```bash
# Enable interactive mode
wf2wf convert -i workflow.smk -o workflow.dag --interactive

# Interactive mode with verbose output
wf2wf convert -i workflow.smk -o workflow.dag --interactive --verbose
```

### Interactive Session Examples

**Resource Specification:**
```
Found 3 tasks without explicit resource requirements.
Distributed systems require explicit resource allocation.
Add default resource specifications? [Y/n]: Y

Applied default resources: CPU=1, Memory=2048MB, Disk=4096MB
```

**Container Specification:**
```
Found 2 tasks without container or conda specifications.
Distributed systems typically require explicit environment isolation.
Add container specifications or conda environments? [Y/n]: Y

Enable --auto-env to automatically build containers for these tasks.
```

**Error Handling:**
```
Found 4 tasks without retry specifications.
Distributed systems benefit from explicit error handling.
Add retry specifications for failed tasks? [Y/n]: Y

Applied default retry settings (2 retries)
```

## Resource Processing

### Resource Validation

The resource processor validates specifications against target environments:

```bash
# Validate resources for cluster environment
wf2wf convert -i workflow.smk -o workflow.dag --validate-resources

# Output:
# ⚠ Resource validation found 2 issues:
#   • task_1: Memory specification (16384MB) exceeds cluster limit (8192MB)
#   • task_2: CPU specification (16) exceeds cluster limit (8)
```

### Resource Profiles

Apply predefined resource profiles for different environments:

```bash
# Apply cluster profile
wf2wf convert -i workflow.smk -o workflow.dag --resource-profile cluster

# Available profiles:
# - shared: Light resources for shared filesystem
# - cluster: Standard cluster resources
# - cloud: Cloud-optimized resources
# - hpc: High-performance computing resources
# - gpu: GPU-enabled resources
```

### Resource Inference

Automatically infer resource requirements from command analysis:

```bash
# Enable resource inference
wf2wf convert -i workflow.smk -o workflow.dag --infer-resources

# The system analyzes commands like:
# - "bwa mem" → High memory, moderate CPU
# - "samtools sort" → High memory, moderate CPU
# - "python script.py" → Low memory, low CPU
# - "Rscript analysis.R" → Moderate memory, low CPU
```

## Loss Integration

### Loss Detection

The loss integration system automatically detects information that may be lost during conversion:

```bash
# Convert with loss detection
wf2wf convert -i workflow.smk -o workflow.dag --fail-on-loss

# Generate detailed loss report
wf2wf convert -i workflow.smk -o workflow.dag --report-md
```

### Loss Report Example

```markdown
# Conversion Report

## Information Loss Summary

### Preserved Information
- ✅ Task definitions and dependencies
- ✅ Resource specifications
- ✅ Container/environment specifications
- ✅ Input/output file specifications

### Potential Loss
- ⚠️ Snakemake wildcards → DAGMan parameter substitution
- ⚠️ Snakemake conda environments → DAGMan container specifications
- ⚠️ Snakemake threads specification → DAGMan CPU requirements

### Recommendations
- Review wildcard substitutions for correctness
- Verify container specifications match conda environments
- Confirm CPU requirements match thread specifications
```

## Environment Management

### Execution Environment Adaptation

The system automatically adapts workflows for different execution environments:

```bash
# Convert for shared filesystem
wf2wf convert -i workflow.smk -o workflow.dag --target-env shared

# Convert for distributed computing
wf2wf convert -i workflow.smk -o workflow.dag --target-env distributed

# Convert for cloud computing
wf2wf convert -i workflow.smk -o workflow.dag --target-env cloud
```

### Environment-Specific Optimizations

**Shared Filesystem:**
- Minimal resource specifications
- System-wide software dependencies
- Basic error handling

**Distributed Computing:**
- Explicit resource requirements
- Container specifications
- Sophisticated retry policies
- File transfer mode optimization

**Cloud Computing:**
- Cloud-optimized resource profiles
- Container-based execution
- Cost-optimized configurations

## Best Practices

### Using Shared Infrastructure

1. **Always use interactive mode** for complex conversions
2. **Enable resource inference** for workflows without explicit specifications
3. **Validate resources** against your target environment
4. **Review loss reports** to understand conversion implications
5. **Use appropriate resource profiles** for your target environment

### Configuration Examples

```bash
# Comprehensive conversion with all features
wf2wf convert -i workflow.smk -o workflow.dag \
    --interactive \
    --infer-resources \
    --validate-resources \
    --resource-profile cluster \
    --target-env distributed \
    --report-md \
    --verbose
```

### Troubleshooting

**Common Issues:**
1. **Resource validation failures**: Adjust specifications or use different profile
2. **Interactive prompts not appearing**: Ensure `--interactive` flag is used
3. **Loss detection warnings**: Review and address potential information loss
4. **Inference not working**: Check command content for analysis

**Getting Help:**
```bash
# Get detailed information about your workflow
wf2wf info workflow.smk

# Validate workflow before conversion
wf2wf validate workflow.smk

# Check for potential issues
wf2wf convert -i workflow.smk -o workflow.dag --dry-run
```

## Compliance and Quality

All importers now achieve **85-95% compliance** with the shared infrastructure specification:

- **DAGMan**: 95/100 (Reference implementation)
- **CWL**: 95/100 (Enhanced with resource processing)
- **Snakemake**: 90/100 (Complex format, excellent compliance)
- **Nextflow**: 90/100 (Fully compliant)
- **WDL**: 85/100 (Good compliance)
- **Galaxy**: 85/100 (Good compliance)

This ensures consistent behavior and enhanced functionality across all supported workflow formats. 