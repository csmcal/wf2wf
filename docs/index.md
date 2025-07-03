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
```

---

```{toctree}
:hidden:
:maxdepth: 2
:caption: User Guide

user_guide/installation
user_guide/prerequisites
user_guide/quickstart
user_guide/environments
user_guide/registry_auth
user_guide/examples
user_guide/faq
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
api/index
```

---

## Sections

* **User Guide** – step-by-step tutorials and best practices.
* **CLI Reference** – exhaustive help for every command.
* **Developer Guide** – IR schema, environment pipeline, contributor tips.
* **Changelog** – project history.
