# Troubleshooting 🐞

This page lists common errors, their cause, and how to fix them.

| Error message (excerpt) | Cause | Fix |
|-------------------------|-------|------|
| `snakemake --dag failed` | Snakefile has syntax or missing files | Run Snakemake dry-run; fix rule definitions |
| `ERROR: Unsupported format` | wf2wf couldn't auto-detect | Pass `--in-format` explicitly |
| `docker: command not found` | Docker not installed | Install Docker or use `--auto-env off` |
| `conda-lock not found` | Auto-env requested but binary missing | `pip install conda-lock` or `brew install conda-lock` |
| `push rejected: authentication required` | Registry push without login | `docker login <registry>` or use `--push-registry` with credentials |
| `Lost fields: retry` (during export) | Target engine can't express feature | Accept loss or choose richer format; use `.loss.json` side-car |
| `JSON schema validation failed` | IR or CWL invalid | File a bug if produced by wf2wf, otherwise inspect paths in error |

## Verbosity flags
Add `-v` / `--verbose` to see stack traces and subprocess output. Combine with `--debug` for maximal logging.

## Getting help
* Run `wf2wf info <file>` to inspect a workflow and ensure wf2wf can parse it.
* Open an issue with `--debug` logs attached. 