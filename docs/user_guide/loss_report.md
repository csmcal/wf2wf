# Understanding Loss Reports

When converting to a less expressive engine wf2wf writes a `<output>.loss.json` side-car.

## Anatomy of the file
```json
{
  "target_engine": "cwl",
  "entries": [
    {
      "json_pointer": "/tasks/align/retry",
      "field": "retry",
      "lost_value": 3,
      "reason": "CWL has no retry field",
      "severity": "warn",
      "status": "lost"
    }
  ]
}
```

* **severity** – `info`, `warn`, `error` (future use)
* **status** – `lost`, `lost_again`, `reapplied`

## CLI workflow
```bash
# Convert but abort on any brand-new loss
wf2wf convert -i Snakefile -o workflow.cwl --fail-on-loss

# Validate later
wf2wf validate workflow.cwl            # checks embedded schema
wf2wf validate workflow.cwl.loss.json   # checks that losses are allowed
```

## Tips
* Use a richer target (e.g. DAGMan) if you see critical losses.
* Keep the `.loss.json` with the workflow so information can be re-applied when converting back.
