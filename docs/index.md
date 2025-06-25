# wf2wf Documentation

Welcome to **wf2wf** – the universal workflow-format converter.

This site contains user guides, API reference and design notes.

```{tableofcontents}
```

---

## Getting started

1. `pip install wf2wf` (or `conda install -c conda-forge wf2wf` once released)
2. Run your first conversion:

```bash
wf2wf convert -i Snakefile -o pipeline.dag --report-md
```

See the [Quick CLI tour](../README.md) for more examples.

## Sections

* **User Guide** – end-to-end tutorials and how-to's.
* **CLI Reference** – detailed help for each command.
* **Developer Guide** – architecture, IR schema, loss-mapping.
* **Changelog** – project history. 