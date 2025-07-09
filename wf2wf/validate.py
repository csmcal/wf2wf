"""wf2wf.validate – JSON-Schema validation helper for Workflow IR."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from jsonschema import validate as _js_validate  # type: ignore

# Locate schema file relative to this module
_SCHEMA_FILE = Path(__file__).parent / "schemas" / "v0.1" / "wf.json"

if not _SCHEMA_FILE.exists():
    raise FileNotFoundError(f"Schema file missing: {_SCHEMA_FILE}")

_SCHEMA: dict[str, Any] = json.loads(_SCHEMA_FILE.read_text())

# Loss side-car schema
_LOSS_SCHEMA_FILE = Path(__file__).parent / "schemas" / "v0.1" / "loss.json"
if not _LOSS_SCHEMA_FILE.exists():
    raise FileNotFoundError(f"Schema file missing: {_LOSS_SCHEMA_FILE}")
_LOSS_SCHEMA: dict[str, Any] = json.loads(_LOSS_SCHEMA_FILE.read_text())

# Predefined execution environments (from core.py)
VALID_ENVIRONMENTS = {
    "shared_filesystem",
    "distributed_computing", 
    "cloud_native",
    "hybrid",
    "local"
}

# Resource validation rules
RESOURCE_VALIDATION_RULES = {
    "cpu": {"min": 1, "max": 1024, "type": int},
    "mem_mb": {"min": 1, "max": 1048576, "type": int},  # 1MB to 1TB
    "disk_mb": {"min": 1, "max": 1048576, "type": int},  # 1MB to 1TB
    "gpu": {"min": 0, "max": 128, "type": int},
    "gpu_mem_mb": {"min": 0, "max": 1048576, "type": int},  # 0MB to 1TB
    "time_s": {"min": 1, "max": 31536000, "type": int},  # 1s to 1 year
    "threads": {"min": 1, "max": 1024, "type": int},
    "retry_count": {"min": 0, "max": 100, "type": int},
    "retry_delay": {"min": 0, "max": 86400, "type": int},  # 0s to 1 day
    "max_runtime": {"min": 1, "max": 31536000, "type": int},  # 1s to 1 year
    "checkpoint_interval": {"min": 1, "max": 86400, "type": int},  # 1s to 1 day
    "parallel_transfers": {"min": 1, "max": 100, "type": int},
    "priority": {"min": -1000, "max": 1000, "type": int}
}

# File path validation patterns
FILE_PATH_PATTERNS = {
    "unix_path": r"^[^<>:\"|?*\x00-\x1f]+$",  # Unix-like path
    "windows_path": r"^[A-Za-z]:\\[^<>:\"|?*\x00-\x1f]*$|^[^<>:\"|?*\x00-\x1f]+$",  # Windows path with drive letter or relative
    "url": r"^https?://[^\s]+$",  # HTTP/HTTPS URL
    # Docker image: repo/name:tag or name:tag, only lowercase letters/numbers, must have tag
    "docker_image": r"^(?:[a-z0-9]+(?:[._-][a-z0-9]+)*/)?[a-z0-9]+(?:[._-][a-z0-9]+)*:[a-zA-Z0-9][a-zA-Z0-9._-]*$",
    "conda_env": r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$"  # Conda environment name
}


def validate_environment_name(environment: str) -> bool:
    """Validate that an environment name is from the predefined list.
    
    Args:
        environment: Environment name to validate
        
    Returns:
        True if valid, False otherwise
    """
    return environment in VALID_ENVIRONMENTS


def validate_resource_value(resource_name: str, value: Any) -> bool:
    """Validate a resource value against defined rules.
    
    Args:
        resource_name: Name of the resource (e.g., 'cpu', 'mem_mb')
        value: Value to validate
        
    Returns:
        True if valid, False otherwise
    """
    if resource_name not in RESOURCE_VALIDATION_RULES:
        return True  # Unknown resource, assume valid
    
    rules = RESOURCE_VALIDATION_RULES[resource_name]
    
    # Check type
    if not isinstance(value, rules["type"]):
        return False
    
    # Check range
    if value < rules["min"] or value > rules["max"]:
        return False
    
    return True


def validate_file_path(path: str, path_type: str = "unix_path") -> bool:
    """Validate a file path against defined patterns.
    
    Args:
        path: Path to validate
        path_type: Type of path ('unix_path', 'windows_path', 'url', 'docker_image', 'conda_env')
        
    Returns:
        True if valid, False otherwise
    """
    if path_type not in FILE_PATH_PATTERNS:
        return True  # Unknown path type, assume valid
    
    pattern = FILE_PATH_PATTERNS[path_type]
    return bool(re.match(pattern, path))


def validate_environment_specific_value(env_value: Dict[str, Any]) -> List[str]:
    """Validate an EnvironmentSpecificValue object and return any issues.
    
    Args:
        env_value: EnvironmentSpecificValue dictionary
        
    Returns:
        List of validation issues (empty if valid)
    """
    issues = []
    
    if not isinstance(env_value, dict):
        issues.append("EnvironmentSpecificValue must be a dictionary")
        return issues
    
    # Check required fields
    if "values" not in env_value:
        issues.append("EnvironmentSpecificValue must have 'values' field")
        return issues
    
    if not isinstance(env_value["values"], list):
        issues.append("EnvironmentSpecificValue 'values' must be a list")
        return issues
    
    # Validate each value entry
    for i, value_entry in enumerate(env_value["values"]):
        if not isinstance(value_entry, dict):
            issues.append(f"Value entry {i} must be a dictionary")
            continue
        
        if "value" not in value_entry:
            issues.append(f"Value entry {i} must have 'value' field")
            continue
        
        if "environments" not in value_entry:
            issues.append(f"Value entry {i} must have 'environments' field")
            continue
        
        # Validate environments
        environments = value_entry["environments"]
        if not isinstance(environments, list):
            issues.append(f"Value entry {i} 'environments' must be a list")
            continue
        
        for env in environments:
            if env is not None and not validate_environment_name(env):
                issues.append(f"Value entry {i} has invalid environment name: {env}")
    
    # Validate default_value if present
    if "default_value" in env_value and env_value["default_value"] is not None:
        # Could add type-specific validation here if needed
        pass
    
    return issues


def validate_workflow_enhanced(obj: Any) -> List[str]:
    """Enhanced workflow validation with additional checks.
    
    Args:
        obj: Workflow object or dictionary to validate
        
    Returns:
        List of validation issues (empty if valid)
    """
    issues = []
    
    try:
        # Basic JSON Schema validation
        validate_workflow(obj)
    except Exception as e:
        issues.append(f"JSON Schema validation failed: {str(e)}")
        return issues
    
    # Get workflow data
    if hasattr(obj, "to_dict"):
        data = obj.to_dict()
    else:
        data = obj
    
    # Enhanced validation checks
    issues.extend(_validate_workflow_structure(data))
    issues.extend(_validate_workflow_tasks(data))
    issues.extend(_validate_workflow_edges(data))
    issues.extend(_validate_workflow_resources(data))
    
    return issues


def _validate_workflow_structure(data: Dict[str, Any]) -> List[str]:
    """Validate workflow structure."""
    issues = []
    
    # Check required fields
    required_fields = ["name", "tasks", "edges"]
    for field in required_fields:
        if field not in data:
            issues.append(f"Workflow missing required field: {field}")
    
    # Validate name
    if "name" in data and not isinstance(data["name"], str):
        issues.append("Workflow name must be a string")
    
    # Validate tasks
    if "tasks" in data:
        if not isinstance(data["tasks"], dict):
            issues.append("Workflow tasks must be a dictionary")
        else:
            for task_id, task_data in data["tasks"].items():
                if not isinstance(task_id, str):
                    issues.append(f"Task ID must be a string: {task_id}")
                if not isinstance(task_data, dict):
                    issues.append(f"Task data must be a dictionary: {task_id}")
    
    # Validate edges
    if "edges" in data:
        if not isinstance(data["edges"], list):
            issues.append("Workflow edges must be a list")
        else:
            for i, edge in enumerate(data["edges"]):
                if not isinstance(edge, dict):
                    issues.append(f"Edge {i} must be a dictionary")
                    continue
                if "parent" not in edge or "child" not in edge:
                    issues.append(f"Edge {i} missing parent or child")
    
    return issues


def _validate_workflow_tasks(data: Dict[str, Any]) -> List[str]:
    """Validate workflow tasks."""
    issues = []
    
    if "tasks" not in data or not isinstance(data["tasks"], dict):
        return issues
    
    tasks = data["tasks"]
    task_ids = set()
    
    for task_id, task_data in tasks.items():
        if task_id in task_ids:
            issues.append(f"Duplicate task ID: {task_id}")
        task_ids.add(task_id)
        
        if not isinstance(task_data, dict):
            continue
        
        # Validate task structure
        if "id" not in task_data:
            issues.append(f"Task {task_id} missing 'id' field")
        
        # Validate environment-specific values
        for field_name, field_value in task_data.items():
            if isinstance(field_value, dict) and "values" in field_value:
                field_issues = validate_environment_specific_value(field_value)
                for issue in field_issues:
                    issues.append(f"Task {task_id} {field_name}: {issue}")
    
    return issues


def _validate_workflow_edges(data: Dict[str, Any]) -> List[str]:
    """Validate workflow edges."""
    issues = []
    
    if "edges" not in data or not isinstance(data["edges"], list):
        return issues
    
    if "tasks" not in data or not isinstance(data["tasks"], dict):
        return issues
    
    tasks = data["tasks"]
    edges = data["edges"]
    
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        
        parent = edge.get("parent")
        child = edge.get("child")
        
        if parent and parent not in tasks:
            issues.append(f"Edge {i} parent '{parent}' not found in tasks")
        
        if child and child not in tasks:
            issues.append(f"Edge {i} child '{child}' not found in tasks")
        
        if parent and child and parent == child:
            issues.append(f"Edge {i} has self-reference: {parent} -> {child}")
    
    return issues


def _validate_workflow_resources(data: Dict[str, Any]) -> List[str]:
    """Validate workflow resource specifications."""
    issues = []
    
    if "tasks" not in data or not isinstance(data["tasks"], dict):
        return issues
    
    for task_id, task_data in data["tasks"].items():
        if not isinstance(task_data, dict):
            continue
        
        # Check resource fields
        resource_fields = ["cpu", "mem_mb", "disk_mb", "gpu", "gpu_mem_mb", "time_s", "threads"]
        
        for field_name in resource_fields:
            if field_name in task_data:
                field_value = task_data[field_name]
                
                # Handle EnvironmentSpecificValue
                if isinstance(field_value, dict) and "values" in field_value:
                    for value_entry in field_value.get("values", []):
                        if isinstance(value_entry, dict) and "value" in value_entry:
                            value = value_entry["value"]
                            if value is not None and not validate_resource_value(field_name, value):
                                issues.append(f"Task {task_id} {field_name} has invalid value: {value}")
                # Handle direct values
                elif field_value is not None and not validate_resource_value(field_name, field_value):
                    issues.append(f"Task {task_id} {field_name} has invalid value: {field_value}")
    
    return issues


def validate_workflow(obj: Any) -> None:
    """Validate *obj* (Workflow or raw dict) against the v0.1 JSON schema.

    Raises
    ------
    jsonschema.ValidationError
        If the object does not conform to the schema.
    """
    if hasattr(obj, "to_dict"):
        data = obj.to_dict()  # type: ignore[arg-type]
    else:
        data = obj

    _js_validate(instance=data, schema=_SCHEMA)


def validate_workflow_with_enhanced_checks(obj: Any) -> None:
    """Validate workflow with both JSON Schema and enhanced checks.
    
    This function provides more comprehensive validation than the basic
    validate_workflow() function.
    
    Args:
        obj: Workflow object or dictionary to validate
        
    Raises
    ------
    jsonschema.ValidationError
        If the object does not conform to the JSON schema.
    ValueError
        If enhanced validation checks fail.
    """
    # First do JSON Schema validation
    validate_workflow(obj)
    
    # Then do enhanced validation
    issues = validate_workflow_enhanced(obj)
    
    if issues:
        raise ValueError(f"Enhanced validation failed:\n" + "\n".join(f"  - {issue}" for issue in issues))


# -----------------------------------------------------------------------------
# BioCompute Object validation (stand-alone, no env tooling required)
# -----------------------------------------------------------------------------

_BCO_SCHEMA_URL = "https://raw.githubusercontent.com/biocompute-objects/BCO_Specification/master/schema/2791object.json"


def validate_bco(bco_doc: Dict[str, Any]) -> None:
    """Validate *bco_doc* against the official IEEE 2791 JSON-Schema.

    Downloads the schema (cached per session) and raises :class:`jsonschema.ValidationError`
    on failure.
    """
    import urllib.request
    import json
    import functools

    @functools.lru_cache(maxsize=1)
    def _load_schema():
        with urllib.request.urlopen(_BCO_SCHEMA_URL, timeout=15) as fh:
            return json.loads(fh.read().decode())

    try:
        schema = _load_schema()
    except Exception:
        # Fallback: minimal schema requiring only mandatory fields
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["object_id", "spec_version", "provenance_domain"],
            "properties": {
                "object_id": {"type": "string"},
                "spec_version": {"type": "string"},
                "provenance_domain": {"type": "object"},
            },
        }

    _js_validate(instance=bco_doc, schema=schema)


# -----------------------------------------------------------------------------
# Loss side-car validation
# -----------------------------------------------------------------------------


def validate_loss(loss_doc: Dict[str, Any]) -> None:
    """Validate *loss_doc* against the loss.json schema."""
    _js_validate(instance=loss_doc, schema=_LOSS_SCHEMA)


# -----------------------------------------------------------------------------
# Utility functions for validation
# -----------------------------------------------------------------------------


def get_validation_summary(obj: Any) -> Dict[str, Any]:
    """Get a comprehensive validation summary for a workflow.
    
    Args:
        obj: Workflow object or dictionary to validate
        
    Returns:
        Dictionary with validation summary including:
        - valid: Boolean indicating if validation passed
        - issues: List of validation issues
        - warnings: List of validation warnings
        - stats: Dictionary with workflow statistics
    """
    summary = {
        "valid": True,
        "issues": [],
        "warnings": [],
        "stats": {}
    }
    
    try:
        # Get workflow data
        if hasattr(obj, "to_dict"):
            data = obj.to_dict()
        else:
            data = obj
        
        # Basic validation
        try:
            validate_workflow(obj)
        except Exception as e:
            summary["valid"] = False
            summary["issues"].append(f"JSON Schema validation failed: {str(e)}")
        
        # Enhanced validation
        enhanced_issues = validate_workflow_enhanced(obj)
        if enhanced_issues:
            summary["valid"] = False
            summary["issues"].extend(enhanced_issues)
        
        # Generate statistics
        summary["stats"] = _generate_workflow_stats(data)
        
        # Generate warnings for potential issues
        summary["warnings"] = _generate_validation_warnings(data)
        
    except Exception as e:
        summary["valid"] = False
        summary["issues"].append(f"Validation failed with exception: {str(e)}")
    
    return summary


def _generate_workflow_stats(data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate workflow statistics."""
    stats = {
        "task_count": 0,
        "edge_count": 0,
        "input_count": 0,
        "output_count": 0,
        "environment_count": 0,
        "resource_fields": set(),
        "environments_used": set()
    }
    
    # Count tasks and edges
    if "tasks" in data and isinstance(data["tasks"], dict):
        stats["task_count"] = len(data["tasks"])
        
        # Analyze task fields
        for task_data in data["tasks"].values():
            if isinstance(task_data, dict):
                # Count resource fields
                resource_fields = ["cpu", "mem_mb", "disk_mb", "gpu", "gpu_mem_mb", "time_s", "threads"]
                for field in resource_fields:
                    if field in task_data:
                        stats["resource_fields"].add(field)
                
                # Count environments used
                for field_name, field_value in task_data.items():
                    if isinstance(field_value, dict) and "values" in field_value:
                        for value_entry in field_value.get("values", []):
                            if isinstance(value_entry, dict) and "environments" in value_entry:
                                for env in value_entry["environments"]:
                                    if env is not None:
                                        stats["environments_used"].add(env)
    
    if "edges" in data and isinstance(data["edges"], list):
        stats["edge_count"] = len(data["edges"])
    
    if "inputs" in data and isinstance(data["inputs"], list):
        stats["input_count"] = len(data["inputs"])
    
    if "outputs" in data and isinstance(data["outputs"], list):
        stats["output_count"] = len(data["outputs"])
    
    stats["environment_count"] = len(stats["environments_used"])
    stats["resource_fields"] = list(stats["resource_fields"])
    stats["environments_used"] = list(stats["environments_used"])
    
    return stats


def _generate_validation_warnings(data: Dict[str, Any]) -> List[str]:
    """Generate validation warnings for potential issues."""
    warnings = []
    
    # Check for missing common fields
    if "tasks" in data and isinstance(data["tasks"], dict):
        for task_id, task_data in data["tasks"].items():
            if not isinstance(task_data, dict):
                continue
            
            # Check for tasks without commands or scripts
            if "command" not in task_data and "script" not in task_data:
                warnings.append(f"Task {task_id} has no command or script specified")
            
            # Check for tasks without resource specifications
            resource_fields = ["cpu", "mem_mb", "disk_mb"]
            has_resources = any(field in task_data for field in resource_fields)
            if not has_resources:
                warnings.append(f"Task {task_id} has no resource specifications")
    
    # Check for potential circular dependencies
    if "edges" in data and isinstance(data["edges"], list) and "tasks" in data:
        # Simple check for self-references
        for edge in data["edges"]:
            if isinstance(edge, dict) and edge.get("parent") == edge.get("child"):
                warnings.append(f"Self-reference detected: {edge.get('parent')} -> {edge.get('child')}")
    
    return warnings


__all__ = [
    "validate_workflow",
    "validate_workflow_enhanced", 
    "validate_workflow_with_enhanced_checks",
    "validate_loss",
    "validate_bco",
    "validate_environment_name",
    "validate_resource_value",
    "validate_file_path",
    "validate_environment_specific_value",
    "get_validation_summary",
    "VALID_ENVIRONMENTS",
    "RESOURCE_VALIDATION_RULES",
    "FILE_PATH_PATTERNS"
]
