# File Transfer Handling for Distributed Computing

## Overview

One of the critical challenges in workflow conversion is handling the fundamental difference between **shared filesystem workflows** (like Snakemake, CWL) and **distributed computing workflows** (like HTCondor/DAGMan). This document explains how wf2wf addresses this challenge.

## The Problem

Different workflow systems make different assumptions about file accessibility:

### Shared Filesystem Workflows (Snakemake, CWL, Nextflow)
- **Assumption**: All compute nodes share the same filesystem
- **File Handling**: Files can be left in place between tasks
- **Intermediate Files**: Can be accessed directly by path
- **Reference Data**: Assumed to be accessible from all nodes

### Distributed Computing Workflows (HTCondor/DAGMan)
- **Assumption**: Compute nodes may not share filesystems
- **File Handling**: Files must be explicitly transferred to/from compute nodes
- **Intermediate Files**: Must be transferred between dependent tasks
- **Reference Data**: May need to be on shared storage or transferred

## wf2wf's Solution: Transfer Modes

wf2wf introduces **transfer modes** in the intermediate representation to capture file transfer requirements:

### Transfer Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `auto` | Automatically determine transfer need (default) | Most regular files |
| `always` | Always transfer, regardless of environment | Critical files that must be local |
| `never` | Never transfer, local only | Temporary/log files |
| `shared` | On shared storage, accessible to all nodes | Reference genomes, large databases |

## Conversion Behavior

### Snakemake → DAGMan
When converting from Snakemake to DAGMan, wf2wf:

1. **Analyzes file paths** to detect likely shared storage locations
2. **Applies heuristics** to determine appropriate transfer modes:
   - `/shared/`, `/nfs/`, `/data/` → `shared`
   - `.tmp`, `/tmp/`, `.log` → `never`
   - Reference file extensions (`.fa`, `.bam`, `.gtf`) → `shared`
   - Regular files → `auto` (will be transferred)

### DAGMan → Snakemake
When converting from DAGMan to Snakemake:

1. **Preserves transfer specifications** from HTCondor submit files
2. **Maps transfer directives** to appropriate transfer modes
3. **Removes transfer specifications** in Snakemake output (not needed)

## Examples

### Basic Usage

```python
from wf2wf.core import ParameterSpec

# Regular file - will be transferred (auto mode)
input_file = "data.txt"

# Reference on shared storage - no transfer needed
reference = ParameterSpec(
    id="/shared/genomes/hg38.fa",
    type="File",
    transfer_mode="shared"
)

# Critical config file - always transfer
config = ParameterSpec(
    id="analysis.conf",
    type="File", 
    transfer_mode="always"
)

# Temporary file - local only
temp = ParameterSpec(
    id="temp.log",
    type="File",
    transfer_mode="never"
)
```

### DAGMan Output

When exported to DAGMan, only `auto` and `always` files appear in transfer lists:

```bash
# In generated .sub file:
transfer_input_files = data.txt,analysis.conf
# /shared/genomes/hg38.fa and temp.log are excluded
```

## Automatic Detection

### Snakemake Import
wf2wf automatically detects transfer modes based on file path patterns:

**Shared Storage Patterns:**
- `/nfs/`, `/shared/`, `/data/`, `/storage/`
- `/lustre/`, `/gpfs/`, `/beegfs/`
- Cloud URLs: `gs://`, `s3://`, `https://`

**Local/Temporary Patterns:**
- `/tmp/`, `.tmp`, `temp_`
- `.log`, `.err`, `.out`
- `/dev/`, `/proc/`, `/sys/`

**Reference Data Patterns:**
- `.fa`, `.fasta`, `.genome`, `.gtf`, `.gff`
- `.bam`, `.sam`, `.bed`
- Directories: `reference/`, `genome/`, `annotation/`

### Example Automatic Detection

```python
# Input: /shared/data/genome.fa
# → Detected as transfer_mode="shared"

# Input: temp_analysis.tmp  
# → Detected as transfer_mode="never"

# Input: sample_data.txt
# → Detected as transfer_mode="auto"
```

## Best Practices

### For Workflow Authors

1. **Be Explicit**: Use `ParameterSpec` with explicit `transfer_mode` for clarity
2. **Consider Environment**: Think about where files will be stored
3. **Reference Data**: Mark large reference files as `shared`
4. **Temporary Files**: Mark temp/log files as `never`

### For System Administrators

1. **Shared Storage**: Ensure shared paths are consistently mounted
2. **Reference Data**: Place large datasets on shared storage
3. **Transfer Optimization**: Use appropriate transfer modes to minimize data movement

## Troubleshooting

### Common Issues

**Problem**: Files not found on compute nodes
- **Solution**: Check transfer modes, ensure `auto` or `always` for required files

**Problem**: Unnecessary large file transfers
- **Solution**: Mark reference data as `shared` mode

**Problem**: Log files filling transfer directories
- **Solution**: Mark log files as `never` mode

### Debugging Transfer Specifications

Use verbose output to see transfer decisions:

```bash
wf2wf convert -i workflow.smk --out-format dagman --verbose
```

Examine generated `.sub` files to verify transfer specifications:

```bash
grep "transfer_.*_files" *.sub
```

## Advanced Configuration

### Custom Patterns

You can extend the automatic detection by modifying the patterns in:
- `wf2wf/importers/snakemake.py` → `_detect_transfer_mode()`

### Engine-Specific Handling

Different engines may interpret transfer modes differently:
- **DAGMan**: Generates `transfer_input_files`/`transfer_output_files`
- **Snakemake**: Ignores transfer modes (assumes shared filesystem)
- **CWL**: Could map to staging directives (future enhancement)

## Related Documentation

- [Installation Guide](installation.md) - Setting up shared storage
- [Engine Overview](engines/overview.md) - Understanding different workflow engines
- [Troubleshooting](troubleshooting.md) - Common conversion issues

---

## Workflow Conversion: Shared Filesystem vs Distributed Computing

This section demonstrates the key differences between shared filesystem workflows (like Snakemake) and distributed computing workflows (like HTCondor DAGMan), and how wf2wf handles these conversions.

### Key Differences

#### 1. File Transfer Assumptions

**Shared Filesystem (Snakemake)**
- Assumes all files are accessible on a shared filesystem
- No explicit file transfer needed
- Files referenced by relative paths

**Distributed Computing (HTCondor)**
- Jobs run on different machines
- Files must be explicitly transferred to/from execution nodes
- Requires `transfer_input_files` and `transfer_output_files` directives

#### 2. Resource Requirements

**Shared Filesystem**
- Often minimal or implicit resource specifications
- Relies on system defaults or queue limits

**Distributed Computing**
- Explicit resource allocation required
- `request_cpus`, `request_memory`, `request_disk` must be specified
- GPU resources need explicit allocation

#### 3. Environment Isolation

**Shared Filesystem**
- Often uses system-wide installations or conda environments
- Environment setup handled outside workflow

**Distributed Computing**
- Requires explicit container specifications
- Environment must be portable across execution nodes
- Docker/Singularity containers preferred

#### 4. Error Handling

**Shared Filesystem**
- Basic retry mechanisms
- Often relies on external monitoring

**Distributed Computing**
- Sophisticated retry policies
- Job-level error handling and recovery
- Priority and preemption support

#### 5. Scatter/Gather Patterns

**Shared Filesystem**
- Implicit parallelization through wildcards
- Dynamic job generation

**Distributed Computing**
- Explicit scatter specifications needed
- Static job definitions

### Example: Snakemake to DAGMan Conversion

#### Input: Snakemake Workflow

```python
# Snakefile
rule all:
    input: "results/final_report.txt"

rule process_data:
    input: "data/{sample}.txt"
    output: "processed/{sample}.txt"
    shell: "python process.py {input} > {output}"

rule analyze:
    input: "processed/{sample}.txt"
    output: "results/{sample}_analysis.txt"
    shell: "python analyze.py {input} > {output}"

rule report:
    input: expand("results/{sample}_analysis.txt", sample=["A", "B", "C"])
    output: "results/final_report.txt"
    shell: "python report.py {input} > {output}"
```

#### Output: DAGMan Workflow

```text
# HTCondor DAGMan file
JOB process_data_A process_data_A.sub
JOB process_data_B process_data_B.sub
JOB process_data_C process_data_C.sub
JOB analyze_A analyze_A.sub
JOB analyze_B analyze_B.sub
JOB analyze_C analyze_C.sub
JOB report report.sub

PARENT process_data_A CHILD analyze_A
PARENT process_data_B CHILD analyze_B
PARENT process_data_C CHILD analyze_C
PARENT analyze_A analyze_B analyze_C CHILD report
```

```bash
# process_data_A.sub
executable = scripts/process_data_A.sh
request_cpus = 1
request_memory = 4096MB
request_disk = 4096MB
transfer_input_files = data/A.txt
transfer_output_files = processed/A.txt
universe = vanilla
queue
```

### Configuration Issues and Solutions

#### 1. Missing Resource Requirements

**Problem**: Snakemake workflow has no explicit resource specifications.

**Solution**: wf2wf prompts user to add default resources:

```bash
$ wf2wf convert -i Snakefile -o workflow.dag --interactive

Found 3 tasks without explicit resource requirements. 
Distributed systems require explicit resource allocation. 
Add default resource specifications? (y)es/(n)o/(a)lways/(q)uit: y
```

#### 2. Missing Container Specifications

**Problem**: No environment isolation specified.

**Solution**: wf2wf prompts for container specifications:

```bash
Found 3 tasks without container or conda specifications. 
Distributed systems typically require explicit environment isolation. 
Add container specifications or conda environments? (y)es/(n)o/(a)lways/(q)uit: y
```

#### 3. Missing Error Handling

**Problem**: No retry specifications for fault tolerance.

**Solution**: wf2wf adds default retry policies:

```bash
Found 3 tasks without retry specifications. 
Distributed systems benefit from explicit error handling. 
Add retry specifications for failed tasks? (y)es/(n)o/(a)lways/(q)uit: y
```

#### 4. File Transfer Modes

**Problem**: Files need explicit transfer specifications.

**Solution**: wf2wf automatically detects and sets transfer modes:

```python
# Auto-detected transfer modes
ParameterSpec(id="data/A.txt", type="File", transfer_mode="always")  # Input file
ParameterSpec(id="processed/A.txt", type="File", transfer_mode="always")  # Output file
ParameterSpec(id="/shared/reference.fa", type="File", transfer_mode="shared")  # Shared reference
```

### Interactive Mode Features

#### Automatic Configuration Detection

When using `--interactive`, wf2wf automatically detects:

1. **Resource Gaps**: Tasks without memory/disk specifications
2. **Environment Issues**: Tasks without container/conda specifications  
3. **Error Handling**: Tasks without retry policies
4. **File Transfer**: Files with auto-detected transfer modes

#### Smart Defaults

wf2wf applies intelligent defaults:

- **Memory**: 4GB default for compute tasks
- **Disk**: 4GB default for data processing tasks
- **Retry**: 2 retries for fault tolerance
- **Transfer Mode**: Auto-detected based on file paths

#### Configuration Validation

The conversion report includes a "Configuration Analysis" section:

```markdown
## Configuration Analysis

### Potential Issues for Distributed Computing

* **Memory**: 2 tasks without explicit memory requirements
* **Containers**: 3 tasks without container/conda specifications
* **Error Handling**: 3 tasks without retry specifications
* **File Transfer**: 6 files with auto-detected transfer modes

**Recommendations:**
* Add explicit resource requirements for all tasks
* Specify container images or conda environments for environment isolation
* Configure retry policies for fault tolerance
* Review file transfer modes for distributed execution
```

### Best Practices

#### For Shared Filesystem Workflows

1. **Add Resource Specifications**: Even if not required, specify memory/disk needs
2. **Use Containers**: Specify conda environments or container images
3. **Add Retry Logic**: Include retry specifications for robustness
4. **Document Dependencies**: Make file dependencies explicit

#### For Distributed Computing Workflows

1. **Explicit Resources**: Always specify CPU, memory, and disk requirements
2. **Container Isolation**: Use Docker or Singularity containers
3. **Error Handling**: Configure retry policies and error strategies
4. **File Transfer**: Review and optimize file transfer patterns
5. **Monitoring**: Set up proper logging and monitoring

#### Conversion Workflow

1. **Analyze Source**: Understand the source workflow's assumptions
2. **Interactive Review**: Use `--interactive` to review configuration gaps
3. **Apply Defaults**: Let wf2wf apply intelligent defaults
4. **Customize**: Adjust configurations based on your infrastructure
5. **Validate**: Test the converted workflow thoroughly

### Example Commands

```bash
# Basic conversion with warnings
wf2wf convert -i Snakefile -o workflow.dag

# Interactive conversion with configuration prompts
wf2wf convert -i Snakefile -o workflow.dag --interactive

# Automatic environment handling
wf2wf convert -i Snakefile -o workflow.dag --auto-env build

# Generate detailed report
wf2wf convert -i Snakefile -o workflow.dag --report-md conversion_report.md

# Validate the conversion
wf2wf validate workflow.dag
```

This comprehensive approach ensures that workflows converted between different execution environments maintain their functionality while adapting to the target system's requirements. 