# wf2wf Loss Tracking System

The `wf2wf.loss` package provides a robust, extensible, and centralized system for tracking, recording, validating, and reinjecting information loss during workflow format conversions. It is designed to support both importers and exporters, and to handle format- and environment-specific loss scenarios in a unified way.

## Architecture Overview

The loss system is organized into several submodules:

- **core.py**: Core loss tracking, recording, reinjection, and summary logic. Handles the in-memory loss buffer, writing/reading sidecars, and reinjecting lost values into workflows.
- **context_detection.py**: Format- and environment-specific loss detection, helpers for environment-specific values, and robust restoration logic.
- **export.py**: Format-specific loss detection for exporters (e.g., what is lost when exporting to CWL, Snakemake, DAGMan, etc.).
- **import_.py**: (Planned) Import-specific loss detection and validation helpers, including sidecar validation.
- **__init__.py**: Exposes the public API for the loss system, aggregating all main functions and classes.

## Key Concepts

- **LossEntry**: A dictionary describing a single loss event, including the field, value, reason, environment context, and status (lost, lost_again, reapplied, etc.).
- **Loss Sidecar**: A JSON file written alongside exported workflows, recording all information that could not be represented in the target format.
- **Reinjection**: When importing a workflow, the loss sidecar can be used to restore lost information, where possible, into the IR.
- **Format/Environment Detection**: The system can detect which fields will be lost for a given format/environment and record them with detailed context.

## Usage

### Exporters
- Use `detect_and_record_export_losses(workflow, target_format, target_environment)` to record all losses before exporting.
- Write the loss sidecar with `write_loss_document(...)` after export.

### Importers
- Use `detect_and_apply_loss_sidecar(workflow, source_path)` to reinject lost information from a sidecar during import.
- Validate sidecars with `validate_loss_sidecar(...)`.

### Helpers
- Use `record_environment_specific_value_loss(...)` to record loss of environment-specific values with full context.
- Use `restore_environment_specific_value(...)` to robustly reconstruct environment-specific values from loss entries.

## Extension Points

- **Adding a new format**: Implement a new `record_<format>_losses` function in `export.py` and add it to the dispatcher in `detect_and_record_export_losses`.
- **Custom loss detection**: Use or extend `FormatLossDetector` and `EnvironmentLossRecorder` in `context_detection.py` for advanced scenarios.
- **Import loss detection**: Extend `import_.py` to add import-specific loss detection or validation logic.

## Example: Exporter Integration

```python
from wf2wf.loss import detect_and_record_export_losses, write_loss_document

def export_workflow(workflow, output_path, target_format, target_environment):
    detect_and_record_export_losses(workflow, target_format, target_environment)
    # ... export logic ...
    write_loss_document(output_path.with_suffix('.loss.json'), target_format, compute_checksum(workflow))
```

## Example: Importer Integration

```python
from wf2wf.loss import detect_and_apply_loss_sidecar

def import_workflow(path):
    workflow = ... # parse workflow
    detect_and_apply_loss_sidecar(workflow, path)
    return workflow
```

## Status and Future Work
- The loss system is now robust, modular, and extensible.
- Future enhancements may include more granular import loss detection, richer adaptation reporting, and user-facing loss summaries.

---

For more details, see the docstrings in each submodule or the main [wf2wf documentation](../docs/). 