# Quickstart

Follow these steps to convert your first workflow.

## Basic Conversion

### Example: Snakemake → DAGMan
```bash
wf2wf convert -i Snakefile -o pipeline.dag --report-md
```

* `-i` / `--input` – source workflow
* `-o` / `--output` – destination file
* `--report-md` – generate a Markdown conversion report

### Example: CWL → Nextflow with loss check
```bash
wf2wf convert -i analysis.cwl -o main.nf \
             --out-format nextflow \
             --fail-on-loss
```

## Interactive Conversion

### Interactive Resource Specification
```bash
# Convert with interactive mode for guided assistance
wf2wf convert -i workflow.smk -o workflow.dag --interactive

# This will prompt you for:
# - Missing resource specifications (CPU, memory, disk)
# - Container/environment requirements
# - Error handling configurations
# - File transfer mode optimization
```

### Example Interactive Session
```bash
$ wf2wf convert -i workflow.smk -o workflow.dag --interactive

Found 3 tasks without explicit resource requirements.
Distributed systems require explicit resource allocation.
Add default resource specifications? [Y/n]: Y

Applied default resources: CPU=1, Memory=2048MB, Disk=4096MB

Found 2 tasks without container specifications.
Distributed systems typically require explicit environment isolation.
Add container specifications? [Y/n]: Y

Enable --auto-env to automatically build containers for these tasks.
```

## Advanced Features

### Resource Processing
```bash
# Convert with automatic resource inference and validation
wf2wf convert -i workflow.smk -o workflow.dag \
    --infer-resources \
    --validate-resources \
    --resource-profile cluster
```

### Comprehensive Conversion
```bash
# Full-featured conversion with all enhancements
wf2wf convert -i workflow.smk -o workflow.dag \
    --interactive \
    --infer-resources \
    --validate-resources \
    --resource-profile cluster \
    --target-env distributed \
    --report-md \
    --verbose
```

## Next Steps

1. **Try Interactive Mode**: Use `--interactive` for guided conversions
2. **Explore Resource Features**: Use `--infer-resources` and `--validate-resources`
3. **Review Loss Reports**: Use `--report-md` to understand conversion implications
4. **Check Documentation**: See [Shared Infrastructure](shared_infrastructure.md) for detailed features

See the [Commands](../cli/commands.md) page for full CLI reference.
