# Developer Guide – Loss Mapping

When a target engine cannot express an IR field, we *never* drop it silently.

## Loss-mapping workflow
1. Exporter calls `loss.record(json_pointer, field, value, reason, origin)`
2. At the end, `loss.write()` creates `output.loss.json` side-car.
3. Importer reads side-car and tries to reinject data; status becomes `reapplied`.

## Schema excerpt
```json
{
  "json_pointer": "/tasks/align/resources/gpu",
  "lost_value": 1,
  "reason": "CWL ResourceRequirement has no GPU fields",
  "severity": "warn",
  "status": "lost"
}
```

## CLI integration
* `--fail-on-loss` aborts if unresolved losses ≥ given severity.
* `wf2wf validate` checks `.loss.json` files. 