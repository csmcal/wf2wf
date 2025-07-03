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
