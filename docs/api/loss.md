# Loss System API Reference

The `wf2wf.loss` package provides a comprehensive system for tracking, recording, validating, and reinjecting information loss during workflow format conversions.

## Core Loss Functions

### Basic Loss Recording

```{automodule} wf2wf.loss.core
:members: record, reset, as_list, generate_summary
:undoc-members:
```

### Loss Document Management

```{automodule} wf2wf.loss.core
:members: create_loss_document, write_loss_document, write
:undoc-members:
```

### Loss Reinjection

```{automodule} wf2wf.loss.core
:members: apply, prepare, detect_and_apply_loss_sidecar
:undoc-members:
```

### Checksum and Validation

```{automodule} wf2wf.loss.core
:members: compute_checksum, create_loss_sidecar_summary
:undoc-members:
```

## Context Detection

### Format-Specific Loss Detection

```{automodule} wf2wf.loss.context_detection
:members: detect_format_specific_losses, FormatLossDetector
:undoc-members:
```

### Environment-Specific Value Handling

```{automodule} wf2wf.loss.context_detection
:members: record_environment_specific_value_loss, EnvironmentLossRecorder, validate_environment_specific_value, restore_environment_specific_value
:undoc-members:
```

## Export Loss Detection

### Format-Specific Export Losses

```{automodule} wf2wf.loss.export
:members: detect_and_record_export_losses
:undoc-members:
```

### Individual Format Loss Functions

```{automodule} wf2wf.loss.export
:members: record_cwl_losses, record_dagman_losses, record_snakemake_losses, record_nextflow_losses, record_wdl_losses, record_galaxy_losses
:undoc-members:
```

## Import Loss Detection

### Side-car Validation

```{automodule} wf2wf.loss.import_
:members: validate_loss_sidecar, validate_loss_entry
:undoc-members:
```

### Import Loss Detection

```{automodule} wf2wf.loss.import_
:members: detect_and_record_import_losses
:undoc-members:
```

## Data Structures

### LossEntry

A typed dictionary wrapper for loss entries:

```python
class LossEntry(Dict[str, Any]):
    """Typed dict wrapper for a loss mapping entry with comprehensive IR support."""
```

### Loss Entry Schema

Each loss entry contains:

- `json_pointer`: JSON pointer to the field in the IR
- `field`: Name of the field that was lost
- `lost_value`: The value that could not be represented
- `reason`: Human-readable reason for the loss
- `origin`: Whether the loss came from user data or wf2wf processing
- `status`: Current status (`lost`, `lost_again`, `reapplied`, `adapted`)
- `severity`: Severity level (`info`, `warn`, `error`)
- `category`: Category of lost information
- `environment_context`: Environment-specific context (optional)
- `recovery_suggestions`: Suggestions for recovery (optional)

## Usage Examples

### Basic Loss Recording

```python
from wf2wf.loss import record, reset, as_list

# Record a simple loss
record(
    json_pointer="/tasks/align/priority",
    field="priority",
    lost_value=10,
    reason="CWL lacks job priority field",
    origin="user",
    severity="warn"
)

# Get all recorded losses
losses = as_list()
```

### Environment-Specific Loss Recording

```python
from wf2wf.loss import record_environment_specific_value_loss

# Record loss of environment-specific value
record_environment_specific_value_loss(
    json_pointer="/tasks/align/cpu",
    field="cpu",
    env_value=task.cpu,  # EnvironmentSpecificValue object
    source_format="snakemake",
    target_format="cwl",
    target_environment="shared_filesystem",
    reason="CWL has limited resource specification"
)
```

### Export Loss Detection

```python
from wf2wf.loss import detect_and_record_export_losses

# Detect and record all losses for a format
detect_and_record_export_losses(
    workflow=workflow,
    target_format="cwl",
    target_environment="shared_filesystem",
    verbose=True
)
```

### Loss Reinjection

```python
from wf2wf.loss import detect_and_apply_loss_sidecar

# Apply loss side-car during import
workflow = parse_workflow(path)
detect_and_apply_loss_sidecar(workflow, path, verbose=True)
```

### Custom Loss Detection

```python
from wf2wf.loss import FormatLossDetector, EnvironmentLossRecorder

# Create custom detector
detector = FormatLossDetector("snakemake", "cwl")
losses = detector.detect_environment_specific_losses(workflow)

# Create custom recorder
recorder = EnvironmentLossRecorder("snakemake", "cwl", "shared_filesystem")
recorder.record_environment_specific_value_loss(
    json_pointer="/tasks/align/gpu",
    field="gpu",
    env_value=task.gpu,
    reason="CWL lacks GPU support"
)
```

### Loss Document Creation

```python
from wf2wf.loss import create_loss_document, write_loss_document, compute_checksum

# Create loss document
doc = create_loss_document(
    target_engine="cwl",
    source_checksum=compute_checksum(workflow),
    environment_adaptation={
        "source_environment": "shared_filesystem",
        "target_environment": "distributed_computing"
    }
)

# Write to file
write_loss_document(
    path="workflow.loss.json",
    target_engine="cwl",
    source_checksum=compute_checksum(workflow)
)
```

### Side-car Validation

```python
from wf2wf.loss import validate_loss_sidecar, validate_loss_entry

# Validate entire side-car
with open("workflow.loss.json") as f:
    loss_data = json.load(f)
is_valid = validate_loss_sidecar(loss_data, Path("workflow.cwl"))

# Validate individual entry
is_valid = validate_loss_entry(loss_data["entries"][0])
```

## Error Handling

The loss system provides comprehensive error handling:

- **Invalid side-cars**: Logged but don't crash imports
- **Missing fields**: Handled with sensible defaults
- **Type mismatches**: Detected and reported
- **Validation failures**: Detailed error messages

## Performance Considerations

- Loss detection is performed once per export
- Side-car validation is lightweight
- Reinjection is optimized for common cases
- Memory usage scales with number of loss entries

## Extension Points

The loss system is designed to be extensible:

1. **New formats**: Add format-specific loss detection functions
2. **Custom categories**: Define new loss categories
3. **Enhanced validation**: Extend validation logic
4. **Custom restoration**: Implement format-specific restoration logic 