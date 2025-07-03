# Environment Automation

`wf2wf` can build reproducible software stacks from Conda YAML files and attach them to your workflow.

## Workflow
1. Conda YAML → lock-file via **conda-lock**
2. Locked environment realised with **micromamba**
3. Packed with **conda-pack** → tarball
4. Tarball baked into OCI image via **docker buildx** (or Buildah)
5. Optional: convert OCI → `.sif` via Apptainer
6. SBOM generated with **Syft**

## CLI flags
| Flag | Purpose |
|------|---------|
| `--auto-env build` | Build images if not cached |
| `--auto-env reuse` | Reuse existing images only |
| `--push-registry URL` | Push to remote registry |
| `--apptainer` | Produce `.sif` images |
| `--fail-on-loss` | Abort if environment info would be lost |

## Caching & pruning
Environment artefacts are content-addressed by the SHA-256 of the lock file. Use `wf2wf cache prune` to clear old images.
