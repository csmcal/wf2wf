"""Shared utilities for loss-mapping during import/export cycles with comprehensive IR support."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import List, Dict, Any, TYPE_CHECKING, Union, Optional

if TYPE_CHECKING:
    from wf2wf.core import Workflow, EnvironmentSpecificValue

__all__ = [
    "LossEntry",
    "reset",
    "record",
    "as_list",
    "write",
    "apply",
    "prepare",
    "compute_checksum",
    "record_environment_adaptation",
    "record_spec_class_loss",
    "record_environment_specific_loss",
    "generate_summary",
    "create_loss_document",
    "write_loss_document",
]


class LossEntry(Dict[str, Any]):
    """Typed dict wrapper for a loss mapping entry with comprehensive IR support."""

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
    category: str = "advanced_features",
    environment_context: Optional[Dict[str, Any]] = None,
    adaptation_details: Optional[Dict[str, Any]] = None,
    recovery_suggestions: Optional[List[str]] = None,
) -> None:
    """Append a comprehensive loss entry describing that *field* at *json_pointer* was lost.

    Parameters
    ----------
    json_pointer : str
        JSON pointer to the field in the IR
    field : str
        Name of the field that was lost
    lost_value : Any
        The value that could not be represented in the target format
    reason : str
        Human-readable reason for the loss
    origin : str
        Whether the loss originated from user data or wf2wf processing
    severity : str
        Severity level: info, warn, error
    category : str
        Category of the lost information
    environment_context : Optional[Dict[str, Any]]
        Environment-specific context for the loss
    adaptation_details : Optional[Dict[str, Any]]
        Details about how the value was adapted
    recovery_suggestions : Optional[List[str]]
        Suggestions for recovering or working around the loss
    """
    if any(e["json_pointer"] == json_pointer and e["field"] == field for e in _LOSSES):
        return

    status = "lost"
    if any(
        e["json_pointer"] == json_pointer and e["field"] == field
        for e in _PREV_REAPPLIED
    ):
        status = "lost_again"

    entry = {
        "json_pointer": json_pointer,
        "field": field,
        "lost_value": lost_value,
        "reason": reason,
        "origin": origin,
        "status": status,
        "severity": severity,
        "category": category,
    }

    if environment_context:
        entry["environment_context"] = environment_context
    if adaptation_details:
        entry["adaptation_details"] = adaptation_details
    if recovery_suggestions:
        entry["recovery_suggestions"] = recovery_suggestions

    _LOSSES.append(entry)


def record_environment_adaptation(
    source_env: str,
    target_env: str,
    adaptation_type: str,
    details: Dict[str, Any],
    *,
    severity: str = "info"
) -> None:
    """Record environment adaptation information for loss tracking.
    
    Parameters
    ----------
    source_env : str
        The original execution environment
    target_env : str
        The target execution environment
    adaptation_type : str
        Type of adaptation: 'filesystem_to_distributed', 'distributed_to_filesystem', 
        'cloud_migration', 'hybrid_conversion', 'edge_adaptation'
    details : Dict[str, Any]
        Detailed information about what changed during the adaptation
    severity : str
        Severity level: info, warn, error
    """
    record(
        json_pointer="/execution_model",
        field="environment_adaptation",
        lost_value={
            "source_environment": source_env,
            "target_environment": target_env,
            "adaptation_type": adaptation_type,
            "details": details
        },
        reason=f"Environment adaptation from {source_env} to {target_env}",
        origin="wf2wf",
        severity=severity,
        category="execution_model",
        environment_context={
            "applicable_environments": [source_env, target_env],
            "target_environment": target_env
        }
    )


def record_environment_specific_loss(
    json_pointer: str,
    field: str,
    env_value: "EnvironmentSpecificValue",
    target_environment: str,
    reason: str,
    *,
    severity: str = "warn",
    category: str = "environment_specific"
) -> None:
    """Record loss of environment-specific values.
    
    Parameters
    ----------
    json_pointer : str
        JSON pointer to the field in the IR
    field : str
        Name of the field that was lost
    env_value : EnvironmentSpecificValue
        The environment-specific value that was lost
    target_environment : str
        The target environment where the loss occurred
    reason : str
        Reason for the loss
    severity : str
        Severity level: info, warn, error
    category : str
        Category of the lost information
    """
    applicable_envs = list(env_value.all_environments())
    
    record(
        json_pointer=json_pointer,
        field=field,
        lost_value=env_value.values,
        reason=reason,
        origin="user",
        severity=severity,
        category=category,
        environment_context={
            "applicable_environments": applicable_envs,
            "target_environment": target_environment
        },
        recovery_suggestions=[
            f"Consider adding {target_environment} support to the target format",
            f"Value was applicable to environments: {', '.join(applicable_envs)}"
        ]
    )


def record_spec_class_loss(
    json_pointer: str,
    field: str,
    spec_object: Any,
    spec_type: str,
    reason: str,
    *,
    severity: str = "warn"
) -> None:
    """Record loss of spec class objects (CheckpointSpec, LoggingSpec, etc.).
    
    Parameters
    ----------
    json_pointer : str
        JSON pointer to the field in the IR
    field : str
        Name of the field that was lost
    spec_object : Any
        The spec object that was lost
    spec_type : str
        Type of spec: 'checkpointing', 'logging', 'security', 'networking'
    reason : str
        Reason for the loss
    severity : str
        Severity level: info, warn, error
    """
    category_map = {
        'checkpointing': 'checkpointing',
        'logging': 'logging', 
        'security': 'security',
        'networking': 'networking'
    }
    
    record(
        json_pointer=json_pointer,
        field=field,
        lost_value=spec_object,
        reason=reason,
        origin="user",
        severity=severity,
        category=category_map.get(spec_type, 'advanced_features'),
        recovery_suggestions=[
            f"Target format does not support {spec_type} specifications",
            "Consider using format-specific extensions or hints",
            "Manual configuration may be required in target environment"
        ]
    )


def record_resource_specification_loss(
    task_id: str,
    resource_field: str,
    original_value: Any,
    target_environment: str,
    reason: str,
    *,
    severity: str = "warn"
) -> None:
    """Record loss of resource specifications.
    
    Parameters
    ----------
    task_id : str
        ID of the task
    resource_field : str
        Name of the resource field (cpu, mem_mb, disk_mb, gpu, etc.)
    original_value : Any
        Original resource value
    target_environment : str
        Target environment where the loss occurred
    reason : str
        Reason for the loss
    severity : str
        Severity level: info, warn, error
    """
    record(
        json_pointer=f"/tasks/{task_id}/{resource_field}",
        field=resource_field,
        lost_value=original_value,
        reason=reason,
        origin="user",
        severity=severity,
        category="resource_specification",
        environment_context={
            "target_environment": target_environment
        },
        recovery_suggestions=[
            f"Add {resource_field} support to target format",
            "Use format-specific resource extensions",
            "Configure resources manually in target environment"
        ]
    )


def record_file_transfer_loss(
    task_id: str,
    transfer_field: str,
    original_value: Any,
    target_environment: str,
    reason: str,
    *,
    severity: str = "warn"
) -> None:
    """Record loss of file transfer specifications.
    
    Parameters
    ----------
    task_id : str
        ID of the task
    transfer_field : str
        Name of the transfer field (file_transfer_mode, staging_required, etc.)
    original_value : Any
        Original transfer value
    target_environment : str
        Target environment where the loss occurred
    reason : str
        Reason for the loss
    severity : str
        Severity level: info, warn, error
    """
    record(
        json_pointer=f"/tasks/{task_id}/{transfer_field}",
        field=transfer_field,
        lost_value=original_value,
        reason=reason,
        origin="user",
        severity=severity,
        category="file_transfer",
        environment_context={
            "target_environment": target_environment
        },
        recovery_suggestions=[
            "Configure file transfer manually in target environment",
            "Use target format's native file handling mechanisms",
            "Consider environment-specific file transfer requirements"
        ]
    )


def record_error_handling_loss(
    task_id: str,
    error_field: str,
    original_value: Any,
    target_environment: str,
    reason: str,
    *,
    severity: str = "warn"
) -> None:
    """Record loss of error handling specifications.
    
    Parameters
    ----------
    task_id : str
        ID of the task
    error_field : str
        Name of the error handling field (retry_count, retry_delay, etc.)
    original_value : Any
        Original error handling value
    target_environment : str
        Target environment where the loss occurred
    reason : str
        Reason for the loss
    severity : str
        Severity level: info, warn, error
    """
    record(
        json_pointer=f"/tasks/{task_id}/{error_field}",
        field=error_field,
        lost_value=original_value,
        reason=reason,
        origin="user",
        severity=severity,
        category="error_handling",
        environment_context={
            "target_environment": target_environment
        },
        recovery_suggestions=[
            "Configure error handling manually in target environment",
            "Use target format's native error handling mechanisms",
            "Consider environment-specific error recovery strategies"
        ]
    )


def generate_summary() -> Dict[str, Any]:
    """Generate summary statistics for the current loss entries."""
    if not _LOSSES:
        return {
            "total_entries": 0,
            "by_category": {},
            "by_severity": {"info": 0, "warn": 0, "error": 0},
            "by_status": {"lost": 0, "lost_again": 0, "reapplied": 0, "adapted": 0},
            "by_origin": {"user": 0, "wf2wf": 0}
        }
    
    by_category = {}
    by_severity = {"info": 0, "warn": 0, "error": 0}
    by_status = {"lost": 0, "lost_again": 0, "reapplied": 0, "adapted": 0}
    by_origin = {"user": 0, "wf2wf": 0}
    
    for entry in _LOSSES:
        # Category
        category = entry.get("category", "advanced_features")
        by_category[category] = by_category.get(category, 0) + 1
        
        # Severity
        severity = entry.get("severity", "warn")
        by_severity[severity] = by_severity.get(severity, 0) + 1
        
        # Status
        status = entry.get("status", "lost")
        by_status[status] = by_status.get(status, 0) + 1
        
        # Origin
        origin = entry.get("origin", "user")
        by_origin[origin] = by_origin.get(origin, 0) + 1
    
    return {
        "total_entries": len(_LOSSES),
        "by_category": by_category,
        "by_severity": by_severity,
        "by_status": by_status,
        "by_origin": by_origin
    }


def as_list() -> List[LossEntry]:
    """Return the current loss entries as a list."""
    return _LOSSES.copy()


def write(doc: Dict[str, Any], path: Union[str, Path], **kwargs) -> None:
    """Write loss document to file."""
    _p = Path(path)
    _p.parent.mkdir(parents=True, exist_ok=True)
    _p.write_text(json.dumps(doc, indent=2, **kwargs))


def create_loss_document(
    target_engine: str, 
    source_checksum: str, 
    environment_adaptation: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Dict[str, Any]:
    """Create a comprehensive loss document with summary statistics."""
    import datetime
    
    doc = {
        "wf2wf_version": "0.3.0",  # Update as needed
        "target_engine": target_engine,
        "source_checksum": source_checksum,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "entries": as_list(),
        "summary": generate_summary()
    }
    
    if environment_adaptation:
        doc["environment_adaptation"] = environment_adaptation
    
    return doc


def write_loss_document(
    path: Union[str, Path], 
    target_engine: str, 
    source_checksum: str,
    environment_adaptation: Optional[Dict[str, Any]] = None,
    **kwargs
) -> None:
    """Write a comprehensive loss document to file."""
    doc = create_loss_document(target_engine, source_checksum, environment_adaptation, **kwargs)
    write(doc, path, **kwargs)


def apply(workflow: "Workflow", entries: List[LossEntry]) -> None:
    """Apply loss entries back to a workflow (reinjection).
    
    This function attempts to reinject lost information back into the workflow
    IR, marking entries as 'reapplied' if successful.
    """
    for entry in entries:
        if entry["status"] in ["reapplied", "adapted"]:
            continue
            
        try:
            # Parse JSON pointer to navigate to the target location
            pointer_parts = entry["json_pointer"].split("/")[1:]  # Skip empty first part
            current = workflow
            
            # Navigate to the parent of the target field
            for part in pointer_parts[:-1]:
                if part.isdigit():
                    # Array index
                    current = current[int(part)]
                else:
                    # Object property
                    if hasattr(current, part):
                        current = getattr(current, part)
                    elif isinstance(current, dict):
                        current = current[part]
                    else:
                        raise ValueError(f"Cannot navigate to {part} in {type(current)}")
            
            # Set the field value
            field_name = pointer_parts[-1]
            lost_value = entry["lost_value"]
            
            if hasattr(current, field_name):
                # Handle EnvironmentSpecificValue fields
                if hasattr(current, 'set_for_environment'):
                    # This is a Task or Workflow object
                    if isinstance(lost_value, dict) and "values" in lost_value:
                        # This is an EnvironmentSpecificValue
                        from wf2wf.core import EnvironmentSpecificValue
                        env_value = EnvironmentSpecificValue()
                        for value_entry in lost_value["values"]:
                            if isinstance(value_entry, dict) and "value" in value_entry:
                                value = value_entry["value"]
                                environments = value_entry.get("environments", [])
                                if environments:
                                    env_value.set_for_environment(value, environments[0])
                                    for env in environments[1:]:
                                        env_value.add_environment(env)
                        setattr(current, field_name, env_value)
                    else:
                        # Simple value
                        setattr(current, field_name, lost_value)
                else:
                    # Regular field
                    setattr(current, field_name, lost_value)
            elif isinstance(current, dict):
                current[field_name] = lost_value
            else:
                raise ValueError(f"Cannot set {field_name} on {type(current)}")
            
            # Mark as reapplied
            entry["status"] = "reapplied"
            
        except Exception as e:
            # Keep as lost if reinjection fails
            entry["status"] = "lost"
            print(f"Warning: Failed to reinject {entry['json_pointer']}: {e}")


def prepare(prev_entries: List[LossEntry]) -> None:
    """Prepare for a new export cycle by remembering previously reapplied entries."""
    _PREV_REAPPLIED.clear()
    for entry in prev_entries:
        if entry["status"] == "reapplied":
            _PREV_REAPPLIED.append(entry)


def compute_checksum(workflow: "Workflow") -> str:
    """Compute SHA-256 checksum of workflow IR for loss tracking."""
    # Use the workflow's built-in JSON serialization which handles all types
    json_str = workflow.to_json()
    
    # Compute SHA-256 hash
    hash_obj = hashlib.sha256()
    hash_obj.update(json_str.encode('utf-8'))
    
    return f"sha256:{hash_obj.hexdigest()}"
