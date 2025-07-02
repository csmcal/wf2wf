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

```{tableofcontents}
```

---

## Sections

* **User Guide** – step-by-step tutorials and best practices.
* **CLI Reference** – exhaustive help for every command.
* **Developer Guide** – IR schema, environment pipeline, contributor tips.
* **Changelog** – project history. 