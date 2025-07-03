# `wf2wf convert`

Convert workflows between formats via the Intermediate Representation.

```console
wf2wf convert [OPTIONS] -i <input> -o <output>

Options:
  -i, --input PATH               Input workflow (file or directory)
  -o, --output PATH              Output path
  -f, --out-format [cwl|dagman|nextflow|snakemake|wdl|galaxy]
  --auto-env [off|build|reuse]   Conda/OCI environment handling
  --push-registry TEXT           Push built images to registry
  --apptainer                    Produce .sif images alongside OCI
  --fail-on-loss                 Abort if conversion loses information
  --report-md                    Emit Markdown report
  -v, --verbose                  Increase verbosity
  -q, --quiet                    Reduce output
  --help                         Show this message and exit.
```
