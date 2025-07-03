# Quickstart

Follow these steps to convert your first workflow.

## Example: Snakemake → DAGMan
```bash
wf2wf convert -i Snakefile -o pipeline.dag --report-md
```

* `-i` / `--input` – source workflow
* `-o` / `--output` – destination file
* `--report-md` – generate a Markdown conversion report

## Example: CWL → Nextflow with loss check
```bash
wf2wf convert -i analysis.cwl -o main.nf \
             --out-format nextflow \
             --fail-on-loss
```

See the [Commands](../cli/commands.md) page for full CLI reference.
