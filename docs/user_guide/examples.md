# Working with the Example Workflows

The repo ships with a rich `examples/` folder covering every supported engine. Use them for quick testing and demos.

## Snakemake
```bash
wf2wf convert -i examples/snake/basic/linear.smk \
              -o linear.dag \
              --out-format dagman
```

Generate a graph image:
```bash
snakemake --dag --snakefile examples/snake/basic/linear.smk | dot -Tpng > dag.png
```

## Nextflow
```bash
wf2wf convert -i examples/nextflow/main.nf -o pipeline.cwl --out-format cwl
```

## Batch testing
A simple script to convert every example and ensure none crash:
```bash
for f in examples/**/*.{smk,cwl,nf,wdl,ga}; do
    wf2wf info "$f" >/dev/null
done
```
