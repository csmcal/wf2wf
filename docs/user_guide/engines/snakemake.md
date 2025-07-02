# Snakemake Cheat-Sheet

| Feature | Status |
|---------|--------|
| `shell:` / `script:` | ✅ |
| Python `run:` blocks | ✅ auto-script |
| Wildcards | ✅ |
| `resources:` cpu/mem/disk | ✅ mapped |
| GPU resources | ✅ mapped |
| `conda:` | ✅ builds or reuse |
| `container:` | ✅ Docker/Singularity |
| Checkpoints | 🚧 partial (static graph only) |
| Dynamic rules | ❌ unsupported |

## Supported directives
* `threads`, `resources`, `envmodules`, `params`, `input`/`output`, `benchmark`, `log`.

## Unsupported
* `pipe()`, `dynamic()`, `shadow`, modules. 