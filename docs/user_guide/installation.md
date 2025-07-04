# Installation

```{contents} Table of Contents
:depth: 1
```

## PyPI (recommended)
```bash
pip install wf2wf
```

## Conda
```bash
# Coming soon - conda-forge feedstock in progress
# conda install -c conda-forge wf2wf
```

```{note}
The conda-forge package is currently under review. For now, use the PyPI installation method.
```

## Development install
```bash
git clone https://github.com/csmcal/wf2wf.git && cd wf2wf
pip install -e .[dev]
pre-commit install
pytest -q
```

### Optional extras
* `.[docs]` – build documentation
* `.[html]` – Markdown → HTML report generation

## External Workflow Engines

`wf2wf` does not include workflow engines as dependencies. You need to install the specific workflow engines you want to convert from or to:

### Snakemake
```bash
# PyPI
pip install snakemake

# Conda (recommended for Snakemake)
conda install -c conda-forge snakemake
```

### CWL
```bash
pip install cwltool
```

### Nextflow
```bash
# Download and install from https://www.nextflow.io/
curl -s https://get.nextflow.io | bash
```

### HTCondor/DAGMan
Install from your system package manager or download from [HTCondor website](https://htcondor.org/downloads/).

```{note}
Only install the workflow engines you actually need for conversion. For example, if you only need to convert Snakemake to DAGMan, you only need to install Snakemake, or potentially nothing.
```
