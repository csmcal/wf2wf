"""Core loss tracking and management functionality."""

from __future__ import annotations

import json
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, TYPE_CHECKING, Union, Optional

if TYPE_CHECKING:
    from wf2wf.core import Workflow, EnvironmentSpecificValue

logger = logging.getLogger(__name__)


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
            "target_environment": target_environment,
            "applicable_environments": applicable_envs
        },
        recovery_suggestions=[
            f"Use value from {target_environment} environment",
            "Use default value",
            "Manually specify environment-specific values in target format"
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
    """Record loss of specification class objects.
    
    Parameters
    ----------
    json_pointer : str
        JSON pointer to the field in the IR
    field : str
        Name of the field that was lost
    spec_object : Any
        The specification object that was lost
    spec_type : str
        Type of specification (LoggingSpec, SecuritySpec, etc.)
    reason : str
        Reason for the loss
    severity : str
        Severity level: info, warn, error
    """
    record(
        json_pointer=json_pointer,
        field=field,
        lost_value=spec_object.__dict__ if hasattr(spec_object, '__dict__') else str(spec_object),
        reason=reason,
        origin="user",
        severity=severity,
        category="specification_class",
        recovery_suggestions=[
            f"Recreate {spec_type} manually in target format",
            "Use target format's native specification mechanisms",
            "Consider environment-specific {spec_type} requirements"
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
    from wf2wf.core import WF2WFJSONEncoder
    
    _p = Path(path)
    _p.parent.mkdir(parents=True, exist_ok=True)
    _p.write_text(json.dumps(doc, indent=2, cls=WF2WFJSONEncoder, **kwargs))


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
    """Write a loss document to file."""
    doc = create_loss_document(target_engine, source_checksum, environment_adaptation, **kwargs)
    write(doc, path, **kwargs)


def apply(workflow: "Workflow", entries: List[LossEntry]) -> int:
    """Apply loss entries back to a workflow (reinjection).
    
    This function attempts to reinject lost information back into the workflow
    IR, marking entries as 'reapplied' if successful.
    
    Returns:
        Number of successfully applied entries
    """
    from wf2wf.core import EnvironmentSpecificValue
    
    applied_count = 0
    
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
                # Get the current field value to determine its type
                current_field_value = getattr(current, field_name)
                
                # Check if this is an EnvironmentSpecificValue field
                if isinstance(current_field_value, EnvironmentSpecificValue):
                    # Use enhanced restoration for environment-specific values
                    target_environment = entry.get("environment_context", {}).get("target_environment", "shared_filesystem")
                    
                    # Determine the expected type from the current field
                    expected_type = type(current_field_value.default_value)
                    
                    # Restore the environment-specific value
                    from .context_detection import restore_environment_specific_value
                    restored_value = restore_environment_specific_value(
                        lost_value, field_name, expected_type, target_environment
                    )
                    
                    setattr(current, field_name, restored_value)
                    logger.debug(f"Restored {field_name} as EnvironmentSpecificValue: {restored_value}")
                    
                else:
                    # Regular field - set directly
                    setattr(current, field_name, lost_value)
                    logger.debug(f"Restored {field_name} as regular field: {lost_value}")
                    
            elif isinstance(current, dict):
                current[field_name] = lost_value
            else:
                raise ValueError(f"Cannot set {field_name} on {type(current)}")
            
            # Mark as reapplied
            entry["status"] = "reapplied"
            applied_count += 1
            
        except Exception as e:
            # Keep as lost if reinjection fails
            entry["status"] = "lost"
            logger.warning(f"Failed to reinject {entry['json_pointer']}: {e}")
    
    return applied_count


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


def detect_and_apply_loss_sidecar(workflow: "Workflow", source_path: Path, verbose: bool = False) -> bool:
    """
    Detect and apply loss side-car during import.
    
    This function looks for a loss side-car file next to the source file
    and applies any loss information to the workflow.
    
    Args:
        workflow: Workflow object to apply loss information to
        source_path: Path to the source workflow file
        verbose: Enable verbose logging
        
    Returns:
        True if a loss side-car was found and applied, False otherwise
    """
    loss_path = source_path.with_suffix('.loss.json')
    
    if not loss_path.exists():
        if verbose:
            logger.debug(f"No loss side-car found at {loss_path}")
        return False
    
    if verbose:
        logger.info(f"Found loss side-car: {loss_path}")
    
    try:
        # Load loss data
        loss_data = json.loads(loss_path.read_text())
        
        # Validate the loss side-car (pass workflow IR for checksum)
        from .import_ import validate_loss_sidecar
        if not validate_loss_sidecar(loss_data, workflow, verbose):
            logger.warning(f"Invalid loss side-car: {loss_path}")
            return False
        
        # Apply loss information to workflow
        entries = loss_data.get('entries', [])
        applied_count = apply(workflow, entries)
        
        # Store the loss map in the workflow
        workflow.loss_map = entries
        
        if verbose:
            logger.info(f"Applied {applied_count} loss entries from {loss_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to apply loss side-car {loss_path}: {e}")
        return False


def create_loss_sidecar_summary(workflow: "Workflow", source_path: Path) -> Dict[str, Any]:
    """
    Create a summary of loss side-car information for a workflow.
    
    Args:
        workflow: Workflow object
        source_path: Path to the source workflow file
        
    Returns:
        Dictionary containing loss side-car summary information
    """
    loss_path = source_path.with_suffix('.loss.json')
    
    if not loss_path.exists():
        return {
            "has_loss_sidecar": False,
            "loss_path": str(loss_path),
            "entries_count": 0,
            "summary": None
        }
    
    try:
        loss_data = json.loads(loss_path.read_text())
        entries = loss_data.get('entries', [])
        summary = loss_data.get('summary', {})
        
        return {
            "has_loss_sidecar": True,
            "loss_path": str(loss_path),
            "entries_count": len(entries),
            "summary": summary,
            "target_engine": loss_data.get('target_engine'),
            "source_checksum": loss_data.get('source_checksum'),
            "timestamp": loss_data.get('timestamp')
        }
        
    except Exception as e:
        logger.error(f"Failed to read loss side-car {loss_path}: {e}")
        return {
            "has_loss_sidecar": True,
            "loss_path": str(loss_path),
            "entries_count": 0,
            "summary": None,
            "error": str(e)
        } 