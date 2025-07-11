# Understanding Loss Reports

When converting between workflow formats, wf2wf tracks information that cannot be represented in the target format and writes a `<output>.loss.json` side-car file. This ensures no information is silently lost during conversion.

## What is a Loss Side-car?

A loss side-car is a JSON file that accompanies your exported workflow, recording all information that could not be represented in the target format. This includes:

- **Environment-specific values** (e.g., different resource requirements for cloud vs. HPC)
- **Advanced features** (e.g., GPU specifications, retry policies, checkpointing)
- **Format-specific capabilities** (e.g., scatter operations, conditional execution)
- **Resource specifications** (e.g., memory, CPU, disk requirements)

## Anatomy of the Loss Side-car

```json
{
  "wf2wf_version": "0.3.0",
  "target_engine": "cwl",
  "source_checksum": "sha256:abc123...",
  "timestamp": "2024-01-15T10:30:00Z",
  "entries": [
    {
      "json_pointer": "/tasks/align/priority",
      "field": "priority",
      "lost_value": {
        "all_environment_values": {
          "shared_filesystem": 10,
          "distributed_computing": 5
        },
        "target_environment_value": 10,
        "default_value": 0,
        "environment_specific_value_type": "EnvironmentSpecificValue"
      },
      "reason": "CWL lacks job priority field",
      "origin": "wf2wf",
      "severity": "warn",
      "status": "lost",
      "category": "environment_specific",
      "environment_context": {
        "source_format": "snakemake",
        "target_format": "cwl",
        "target_environment": "shared_filesystem",
        "applicable_environments": ["shared_filesystem", "distributed_computing"],
        "has_target_environment_value": true
      },
      "recovery_suggestions": [
        "Use value from shared_filesystem environment: 10",
        "Use default value: 0",
        "Manually specify environment-specific values in target format"
      ]
    }
  ],
  "summary": {
    "total_entries": 1,
    "by_category": {
      "environment_specific": 1
    },
    "by_severity": {
      "warn": 1,
      "info": 0,
      "error": 0
    },
    "by_status": {
      "lost": 1,
      "lost_again": 0,
      "reapplied": 0,
      "adapted": 0
    }
  }
}
```

### Key Fields

- **`json_pointer`**: JSON pointer to the field in the workflow IR
- **`field`**: Name of the field that was lost
- **`lost_value`**: The value that could not be represented (may include environment-specific context)
- **`reason`**: Human-readable explanation of why the information was lost
- **`origin`**: Whether the loss came from user data (`"user"`) or wf2wf processing (`"wf2wf"`)
- **`severity`**: `info`, `warn`, or `error`
- **`status`**: `lost`, `lost_again`, `reapplied`, or `adapted`
- **`category`**: Type of lost information (e.g., `environment_specific`, `resource_specification`)
- **`environment_context`**: Format and environment information for context-aware restoration
- **`recovery_suggestions`**: Tips for recovering or working around the loss

## Loss Status Types

- **`lost`**: Information was lost during this conversion
- **`lost_again`**: Information was previously restored from a loss side-car but is lost again in this conversion
- **`reapplied`**: Information was successfully restored from a loss side-car
- **`adapted`**: Information was adapted rather than lost (e.g., environment-specific values converted to target environment)

## CLI Workflow

```bash
# Convert with loss tracking
wf2wf convert -i Snakefile -o workflow.cwl

# Check what was lost
cat workflow.cwl.loss.json

# Convert back with loss reinjection
wf2wf convert -i workflow.cwl -o restored.smk

# Abort conversion if there are critical losses
wf2wf convert -i Snakefile -o workflow.cwl --fail-on-loss error

# Validate the loss side-car
wf2wf validate workflow.cwl.loss.json
```

## Environment-Specific Loss Tracking

The new loss system provides enhanced tracking for environment-specific values:

- **Multi-environment support**: Tracks values for different execution environments (shared filesystem, distributed computing, cloud native)
- **Context-aware restoration**: When importing, the system can restore environment-specific values based on the target environment
- **Format capability detection**: Automatically detects which formats support which features

## Tips for Working with Loss Side-cars

1. **Keep the side-car with your workflow**: The `.loss.json` file contains information that can be restored when converting back to a more expressive format.

2. **Review losses before production**: Check the loss report to understand what information was lost and whether it's acceptable for your use case.

3. **Use richer target formats**: If you see critical losses, consider using a more expressive target format (e.g., DAGMan instead of CWL for advanced features).

4. **Environment-specific optimization**: The system can help you optimize workflows for specific execution environments by tracking environment-specific requirements.

5. **Recovery suggestions**: Follow the recovery suggestions in the loss entries to manually restore important information in your target format.

## Example: Round-trip Conversion

```bash
# Export Snakemake to CWL (some features lost)
wf2wf convert -i workflow.smk -o workflow.cwl

# Import CWL back to Snakemake (lost features restored)
wf2wf convert -i workflow.cwl -o restored.smk

# The restored workflow should have the original priority and retry settings
```

The loss system ensures that your workflow's intent and requirements are preserved across format conversions, even when the target format cannot directly represent all the original information.
