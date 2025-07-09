# wf2wf Documentation

Welcome to **wf2wf** – the universal workflow-format converter.

```{admonition} Docs in progress
This documentation site is still growing.  If something is missing, please [open an issue](https://github.com/csmcal/wf2wf/issues) or contribute a pull request!
```

---

## Overview 🌐

`wf2wf` converts workflows between *any* supported engines via a loss-preserving **Intermediate Representation (IR)**.  Supported today:

• Snakemake • CWL • Nextflow • WDL • Galaxy • HTCondor DAGMan (+ BioCompute Objects)

Key features:

* 🔄 **Universal conversion** – always *A → IR → B* for maximum fidelity.
* 🧠 **Intelligent inference** – automatically fills in missing resource specifications and configurations.
* 💬 **Interactive prompting** – guided assistance for complex conversions and missing information.
* 🧬 **Loss mapping** – records unexpressed fields in side-cars so nothing vanishes.
* 🐳 **Environment automation** – Conda → OCI → Apptainer with SBOM generation.
* ⚖ **Regulatory support** – Emits BioCompute Objects and provenance metadata.

---

## Quick install

```bash
pip install wf2wf            # or: conda install -c conda-forge wf2wf
```

---

## Quick CLI tour 🚀

```bash
# Convert Snakemake → DAGMan and build container images
wf2wf convert -i Snakefile -o pipeline.dag --auto-env build --interactive

# Convert CWL → Nextflow, aborting on information loss
wf2wf convert -i analysis.cwl -o main.nf --out-format nextflow --fail-on-loss

# Enhanced conversion with interactive resource specification
wf2wf convert -i Snakefile -o pipeline.dag --interactive --infer-resources

# Convert CWL → Nextflow with resource validation and loss detection
wf2wf convert -i analysis.cwl -o main.nf --out-format nextflow --fail-on-loss --validate-resources

# Comprehensive conversion with all enhanced features
wf2wf convert -i workflow.smk -o workflow.dag \
    --interactive \
    --infer-resources \
    --validate-resources \
    --resource-profile cluster \
    --target-env distributed \
    --report-md
```

---

## Enhanced Features 🆕

### Intelligent Resource Inference
Automatically detect and specify resource requirements based on command analysis:
```bash
wf2wf convert -i workflow.smk -o workflow.dag --infer-resources
# Analyzes: "bwa mem" → 8GB memory, 4 CPU
# Analyzes: "samtools sort" → 4GB memory, 2 CPU
```

### Interactive Conversion Mode
Get guided assistance for complex conversions:
```bash
wf2wf convert -i workflow.smk -o workflow.dag --interactive
# Prompts for: missing resources, containers, error handling, file transfers
```

### Resource Processing
Validate and optimize resource specifications:
```bash
wf2wf convert -i workflow.smk -o workflow.dag --validate-resources --resource-profile cluster
```

---

```{toctree}
:hidden:
:maxdepth: 2
:caption: User Guide

user_guide/installation
user_guide/prerequisites
user_guide/quickstart
user_guide/shared_infrastructure
user_guide/environments
user_guide/registry_auth
user_guide/examples
user_guide/faq
user_guide/file_transfers
user_guide/conversion_best_practices
user_guide/troubleshooting
user_guide/loss_report
```

```{toctree}
:hidden:
:maxdepth: 2
:caption: Tutorials

user_guide/tutorials/snakemake_to_dagman
user_guide/tutorials/cwl_to_nextflow
```

```{toctree}
:hidden:
:maxdepth: 2
:caption: Engines

user_guide/engines/overview
user_guide/engines/snakemake
user_guide/engines/cwl
user_guide/engines/nextflow
user_guide/engines/dagman
user_guide/engines/wdl
user_guide/engines/galaxy
```

```{toctree}
:hidden:
:maxdepth: 2
:caption: CLI Reference

cli/cli_reference
cli/commands
cli/convert
cli/validate
cli/info
cli/bco
cli/cache
```

```{toctree}
:hidden:
:maxdepth: 2
:caption: Developer Guide

developer/architecture
developer/loss_mapping
developer/contributing
developer/versioning
api/index
```

```{toctree}
:hidden:
:maxdepth: 1
:caption: Project

CHANGELOG <https://github.com/csmcal/wf2wf/blob/main/CHANGELOG.md>
```

---

## Sections

* **User Guide** – step-by-step tutorials and best practices.
* **Shared Infrastructure** – comprehensive guide to intelligent inference and interactive features.
* **CLI Reference** – exhaustive help for every command.
* **Developer Guide** – IR schema, environment pipeline, contributor tips.
* **Changelog** – project history and release notes.
