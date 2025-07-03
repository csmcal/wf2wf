"""Shared utilities for loss-mapping during import/export cycles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from wf2wf.core import Workflow

__all__ = [
    "LossEntry",
    "reset",
    "record",
    "as_list",
    "write",
    "apply",
    "prepare",
    "compute_checksum",
]


class LossEntry(Dict[str, Any]):
    """Typed dict wrapper for a loss mapping entry."""

    # No custom behaviour – keeping simple for now.


_LOSSES: List[LossEntry] = []

# Entries from previous workflow instance (e.g. after reinjection)
_PREV_REAPPLIED: List[LossEntry] = []


def reset() -> None:
    """Clear the in-memory loss buffer."""
    _LOSSES.clear()


def record(
    json_pointer: str,
    field: str,
    lost_value: Any,
    reason: str,
    origin: str = "user",
    *,
    severity: str = "warn",
) -> None:
    """Append a loss entry describing that *field* at *json_pointer* was lost.

    • Entries are deduplicated within the current export cycle.
    • If the same pointer/field previously had *status == reapplied*, the new
      entry is marked as ``lost_again`` to aid diagnostics.
    """
    if any(e["json_pointer"] == json_pointer and e["field"] == field for e in _LOSSES):
        return

    status = "lost"
    if any(
        e["json_pointer"] == json_pointer and e["field"] == field
        for e in _PREV_REAPPLIED
    ):
        status = "lost_again"

    _LOSSES.append(
        {
            "json_pointer": json_pointer,
            "field": field,
            "lost_value": lost_value,
            "reason": reason,
            "origin": origin,
            "status": status,
            "severity": severity,
        }
    )


def as_list() -> List[LossEntry]:
    return list(_LOSSES)


def write(
    path: Path,
    *,
    wf2wf_version: str = "0.3.0",
    target_engine: str | None = None,
    source_checksum: str | None = None,
) -> None:
    if not _LOSSES:
        return
    doc = {
        "wf2wf_version": wf2wf_version,
        "target_engine": target_engine,
        "source_checksum": source_checksum,
        "entries": _LOSSES,
    }
    path.write_text(json.dumps(doc, indent=2))


# -----------------------------------------------------------------------------
# Re-injection helpers (best-effort for common paths – extensible).
# -----------------------------------------------------------------------------


def apply(workflow: "Workflow", entries: List[LossEntry]) -> None:  # type: ignore[name-defined]
    """Best-effort reapply *entries* onto *workflow* in-place."""
    for e in entries:
        ptr = e.get("json_pointer", "")
        field = e.get("field")
        value = e.get("lost_value")
        if not ptr or not field:
            continue

        # Very limited mapping for now
        parts = ptr.strip("/").split("/")
        if not parts:
            continue

        if parts[0] == "tasks" and len(parts) >= 2:
            task_id = parts[1]
            task = workflow.tasks.get(task_id)
            if not task:
                continue
            if field == "retry":
                task.retry = value
            elif field == "priority":
                task.priority = value
            elif field == "when":
                task.when = value
            elif field == "scatter":
                try:
                    from wf2wf.core import ScatterSpec  # type: ignore

                    task.scatter = ScatterSpec(
                        scatter=value if isinstance(value, list) else [value]
                    )
                except Exception:
                    task.scatter = None
            elif field == "gpu":
                task.resources.gpu = value
            elif field == "gpu_mem_mb":
                task.resources.gpu_mem_mb = value
            elif field == "gpu_capability":
                setattr(task.resources, "gpu_capability", value)
            elif field == "cpu":
                task.resources.cpu = value
            elif field == "mem_mb":
                task.resources.mem_mb = value
            elif field == "disk_mb":
                task.resources.disk_mb = value
            elif field == "time_s":
                task.resources.time_s = value
            # any additional resources fields can be set generically
            elif field in ("resources",):
                for k, v in (value or {}).items():
                    setattr(task.resources, k, v)

            # Parameters within task inputs/outputs
            if (
                parts[0] == "tasks"
                and len(parts) >= 4
                and parts[2] in ("inputs", "outputs")
            ):
                io_type = parts[2]  # inputs / outputs
                param_id = parts[3]
                if io_type == "inputs":
                    params = task.inputs
                else:
                    params = task.outputs
                for p in params:
                    if getattr(p, "id", None) == param_id:
                        setattr(p, field, value)
                        if field == "secondary_files":
                            p.secondary_files = value
                        break

        # Workflow-level inputs / outputs (not in task scope)
        if parts[0] in ("inputs", "outputs") and len(parts) >= 2:
            param_id = parts[1]
            params = workflow.inputs if parts[0] == "inputs" else workflow.outputs
            for p in params:
                if getattr(p, "id", None) == param_id:
                    setattr(p, field, value)
                    break

        # Workflow-level simple attributes
        if parts[0] == "intent":
            workflow.intent = value if isinstance(value, list) else [value]
        elif parts[0] in ("label", "doc", "version"):
            setattr(workflow, parts[0], value)
        elif parts[0] == "provenance_domain":
            # crude mapping for BCO provenance
            workflow.provenance = value
        elif parts[0] == "meta":
            if isinstance(value, dict):
                workflow.meta.update(value)

        # Task environment fields, e.g. /tasks/<id>/environment/container
        if parts[0] == "tasks" and len(parts) >= 3 and parts[2] == "environment":
            task_id = parts[1]
            task = workflow.tasks.get(task_id)
            if task:
                if len(parts) == 4:
                    env_field = parts[3]
                    if env_field in ("container", "conda"):
                        setattr(task.environment, env_field, value)
                    elif env_field == "env_vars" and isinstance(value, dict):
                        task.environment.env_vars.update(value)
                elif len(parts) >= 5 and parts[3] == "env_vars":
                    # Pointer to a specific env var key
                    var_key = parts[4]
                    task.environment.env_vars[var_key] = value

        # Mark entry as reapplied on success
        e["status"] = "reapplied"


def prepare(prev_entries: List[LossEntry]) -> None:
    """Save previously *reapplied* loss entries so we can detect repeat losses.

    Should be invoked by exporters *before* they start recording new losses.
    """
    global _PREV_REAPPLIED
    _PREV_REAPPLIED = [e for e in prev_entries if e.get("status") == "reapplied"]


def compute_checksum(workflow: "Workflow") -> str:  # type: ignore[name-defined]
    """Return sha256 checksum of canonical JSON representation of *workflow*."""
    import hashlib
    import json

    j = json.dumps(workflow.to_dict(), sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(j).hexdigest()
