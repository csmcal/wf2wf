# Developer Guide – Architecture

This page gives a high-level overview of the internal design.

## Intermediate Representation (IR)
All conversions flow through a dataclass-based IR:
* `Workflow` → `Task` → `ParameterSpec`, `RequirementSpec`, etc.
* Versioned JSON schema under `wf2wf/schemas/v0.1/wf.json`
* Validation via `jsonschema`

### Why IR?
* Decouples importers/exporters
* Enables round-trip testing
* Central place for metadata handling and loss mapping

## Code layout
```text
wf2wf/
  core.py           # IR dataclasses & utils
  importers/        # Format → IR
  exporters/        # IR → Format
  environ.py        # Conda → OCI pipeline
  loss.py           # Loss mapping helpers
  cli.py            # Typer/Click CLI
```

## Adding a new engine
1. Implement `importers/<engine>.py` returning a `Workflow` instance.
2. Implement `exporters/<engine>.py` consuming a `Workflow`.
3. Register entry-points if distributing externally.
4. Add tests & docs.
