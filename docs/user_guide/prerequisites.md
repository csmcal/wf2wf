# Pre-flight Checklist ✅

Make sure the following are in place **before** running `wf2wf` on a workflow.

| Item | Why it matters | How to verify |
|------|---------------|---------------|
| Python ≥ 3.9 | wf2wf targets modern Python | `python --version` |
| Source workflow parses cleanly | Importers need syntactically correct input | Run engine's own lint/dry-run (see below) |
| External binaries (if used) | `docker`, `micromamba`, `conda-lock`, `apptainer` | `which docker`, etc. |
| Network access to registries | Auto-env image pushes/pulls | `docker login <registry>` or firewalls |
| Write permission in working dir | Exporters create files and temp dirs | `touch test && rm test` |

## Recommended pre-checks for each engine

### Snakemake
```bash
snakemake --lint --snakefile Snakefile
snakemake --dag   --snakefile Snakefile | dot -Tpng > dag.png
```

### CWL
```bash
cwltool --validate workflow.cwl
```

### Nextflow
```bash
nextflow run -n -preview main.nf
```

### WDL
```bash
miniwdl check pipeline.wdl
```

If the native tool cannot parse the workflow, `wf2wf` will likely fail or lose information.

---

## Installing optional helpers

| Tool | Used for | Install |
|------|----------|---------|
| `conda-lock` | dependency locking | `pip install conda-lock` |
| `micromamba` | fast conda solves  | See <https://mamba.readthedocs.io/> |
| `docker buildx` | OCI builds       | Docker Desktop or `apt install docker-buildx-plugin` |
| `buildah` | rootless builds      | `dnf install buildah` |
| `apptainer` | HPC `.sif` images | <https://apptainer.org/> |
| `syft` & `grype` | SBOM & CVE scan | `brew install syft grype` |

All are optional – wf2wf falls back to stubs – but enable the full feature set. 