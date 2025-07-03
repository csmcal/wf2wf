# Tutorial: Snakemake → DAGMan

In this tutorial we'll convert a simple Snakemake workflow to HTCondor DAGMan, build its environments and validate the result.

## Prerequisites
* Docker daemon running (for image builds)
* HTCondor client tools (optional – for submitting)

## 1. Clone the example workflow
```bash
git clone https://github.com/csmcal/wf2wf-examples.git
cd wf2wf-examples/snake/basic
```

## 2. Inspect the workflow
```bash
snakemake --dag --snakefile linear.smk | dot -Tpng > dag.png && open dag.png
```

## 3. Dry-run wf2wf
```bash
wf2wf info linear.smk
```

## 4. Convert with auto-env
```bash
wf2wf convert -i linear.smk -o linear.dag \
              --out-format dagman \
              --auto-env build \
              --push-registry ghcr.io/$USER/wf2wf-demo \
              --report-md
```

Outputs:
* `linear.dag` – DAGMan workflow
* `linear.dag.md` – conversion report
* `*.sub` files – HTCondor submit descriptions
* Images pushed with digest-tags

## 5. Validate
```bash
wf2wf validate linear.dag
wf2wf validate linear.dag.loss.json
```

## 6. Submit (optional)
```bash
condor_submit_dag -f linear.dag
```

That's it! You can re-import the DAG back to Snakemake later.
