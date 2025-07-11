# Developer Guide – Loss Mapping

The wf2wf loss tracking system ensures that information is never silently dropped during format conversions. Instead, it provides a robust, extensible system for tracking, recording, validating, and reinjecting lost information.

## Architecture Overview

The loss system is organized into modular components:

```
wf2wf.loss/
├── __init__.py          # Public API
├── core.py              # Core tracking, recording, reinjection
├── context_detection.py # Format/environment-specific detection
├── export.py            # Format-specific export loss detection
├── import_.py           # Import validation and detection
└── README.md            # Detailed documentation
```

## Core Concepts

### LossEntry
A dictionary describing a single loss event:
```python
{
    "json_pointer": "/tasks/align/priority",
    "field": "priority",
    "lost_value": {...},  # May include environment-specific context
    "reason": "CWL lacks job priority field",
    "origin": "user",     # "user" or "wf2wf"
    "status": "lost",     # "lost", "lost_again", "reapplied", "adapted"
    "severity": "warn",   # "info", "warn", "error"
    "category": "environment_specific",
    "environment_context": {...},
    "recovery_suggestions": [...]
}
```

### Loss Side-car
A JSON file written alongside exported workflows containing:
- Loss entries with detailed context
- Summary statistics
- Source checksum for validation
- Timestamp and version information

## Integration Workflow

### For Exporters

1. **Detect losses**: Call format-specific loss detection
2. **Record losses**: Use the enhanced recording functions
3. **Write side-car**: Create the loss document

```python
from wf2wf.loss import detect_and_record_export_losses, write_loss_document

def export_workflow(workflow, output_path, target_format, target_environment):
    # Detect and record all losses for this format/environment
    detect_and_record_export_losses(workflow, target_format, target_environment)
    
    # ... export logic ...
    
    # Write loss side-car
    write_loss_document(
        output_path.with_suffix('.loss.json'),
        target_engine=target_format,
        source_checksum=compute_checksum(workflow)
    )
```

### For Importers

1. **Detect side-car**: Look for `.loss.json` file
2. **Validate side-car**: Check integrity and format
3. **Apply losses**: Reinject lost information

```python
from wf2wf.loss import detect_and_apply_loss_sidecar

def import_workflow(path):
    workflow = parse_workflow(path)
    
    # Apply loss side-car if available
    detect_and_apply_loss_sidecar(workflow, path)
    
    return workflow
```

## Extending the Loss System

### Adding Support for a New Format

1. **Add format detection** in `export.py`:
```python
def record_newformat_losses(workflow: Workflow, target_environment: str, verbose: bool = False) -> None:
    """Record losses when converting to NewFormat."""
    for task in workflow.tasks.values():
        # Check for unsupported features
        if task.gpu and isinstance(task.gpu, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/gpu",
                "gpu",
                task.gpu,
                "newformat",
                "newformat",
                target_environment,
                "NewFormat lacks GPU support"
            )
```

2. **Register the function** in `detect_and_record_export_losses()`:
```python
def detect_and_record_export_losses(workflow, target_format, target_environment, verbose=False):
    if target_format == "newformat":
        record_newformat_losses(workflow, target_environment, verbose)
    # ... other formats ...
```

### Custom Loss Detection

Use the provided classes for advanced scenarios:

```python
from wf2wf.loss import FormatLossDetector, EnvironmentLossRecorder

# Detect format-specific losses
detector = FormatLossDetector("source_format", "target_format")
losses = detector.detect_environment_specific_losses(workflow)

# Record with detailed context
recorder = EnvironmentLossRecorder("source_format", "target_format", "target_environment")
recorder.record_environment_specific_value_loss(
    json_pointer, field, env_value, reason
)
```

### Environment-Specific Value Handling

The system provides robust helpers for environment-specific values:

```python
from wf2wf.loss import (
    validate_environment_specific_value,
    restore_environment_specific_value
)

# Validate a value
is_valid = validate_environment_specific_value(value, "priority", int)

# Restore from loss data
restored = restore_environment_specific_value(
    lost_value, "priority", int, "shared_filesystem"
)
```

## Loss Categories

The system categorizes losses for better organization:

- **`environment_specific`**: Environment-specific values (e.g., different resource requirements)
- **`resource_specification`**: CPU, memory, disk, GPU specifications
- **`file_transfer`**: File transfer modes, staging requirements
- **`error_handling`**: Retry policies, error recovery
- **`execution_model`**: Execution model adaptations
- **`specification_class`**: Complex specification objects (LoggingSpec, SecuritySpec, etc.)
- **`advanced_features`**: Checkpointing, logging, security, networking

## Validation and Error Handling

### Side-car Validation
```python
from wf2wf.loss import validate_loss_sidecar, validate_loss_entry

# Validate entire side-car
is_valid = validate_loss_sidecar(loss_data, source_path)

# Validate individual entry
is_valid = validate_loss_entry(entry)
```

### Error Recovery
The system provides graceful error handling:
- Invalid side-cars are logged but don't crash the import
- Missing fields are handled with sensible defaults
- Type mismatches are detected and reported

## Best Practices

1. **Always record losses**: Never silently drop information
2. **Provide context**: Include environment and format information
3. **Give recovery suggestions**: Help users understand how to work around losses
4. **Validate side-cars**: Check integrity before applying
5. **Use appropriate categories**: Categorize losses for better organization
6. **Test round-trips**: Ensure losses can be properly restored

## CLI Integration

The loss system integrates with the CLI:

- `--fail-on-loss <severity>`: Abort conversion if losses exceed specified severity
- `wf2wf validate <file>.loss.json`: Validate loss side-car files
- Loss summaries are included in conversion output

## Future Enhancements

- **Import loss detection**: More granular detection of import-specific losses
- **Adaptation reporting**: Rich reporting of how information was adapted
- **User-facing summaries**: Human-readable loss summaries
- **Loss analytics**: Statistical analysis of common losses across formats
