"""
wf2wf.importers.loss_integration – Enhanced loss side-car integration.

This module provides comprehensive loss side-car integration for importers,
including detection, application, and summary generation.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from wf2wf.core import Workflow, Task, EnvironmentSpecificValue

logger = logging.getLogger(__name__)


def detect_and_apply_loss_sidecar(
    workflow: Workflow, 
    source_path: Path, 
    verbose: bool = False
) -> bool:
    """
    Detect and apply loss side-car during import.
    
    This function looks for a loss side-car file next to the source file
    and applies any loss information to the workflow. It handles validation
    of the side-car file and provides detailed logging of the application process.
    
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
        # Load and validate loss data
        loss_data = json.loads(loss_path.read_text())
        
        # Validate the loss side-car
        if not _validate_loss_sidecar(loss_data, source_path, verbose):
            logger.warning(f"Invalid loss side-car: {loss_path}")
            return False
        
        # Apply loss information to workflow
        applied_count = _apply_loss_data(workflow, loss_data, verbose)
        
        if verbose:
            logger.info(f"Applied {applied_count} loss entries from {loss_path}")
        
        # Create summary
        summary = create_loss_sidecar_summary(workflow, source_path)
        if verbose:
            logger.info(f"Loss side-car summary: {summary}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to apply loss side-car {loss_path}: {e}")
        return False


def _validate_loss_sidecar(
    loss_data: Dict[str, Any], 
    source_path: Path, 
    verbose: bool = False
) -> bool:
    """
    Validate loss side-car data.
    
    Args:
        loss_data: Dictionary containing loss data
        source_path: Path to the source workflow file
        verbose: Enable verbose logging
        
    Returns:
        True if the loss side-car is valid, False otherwise
    """
    # Check required fields
    required_fields = ['wf2wf_version', 'target_engine', 'entries']
    for field in required_fields:
        if field not in loss_data:
            if verbose:
                logger.warning(f"Missing required field in loss side-car: {field}")
            return False
    
    # Check source checksum if present
    if 'source_checksum' in loss_data:
        expected_checksum = _compute_source_checksum(source_path)
        actual_checksum = loss_data['source_checksum']
        
        if not actual_checksum.startswith('sha256:'):
            if verbose:
                logger.warning(f"Invalid checksum format: {actual_checksum}")
            return False
        
        if actual_checksum != expected_checksum:
            if verbose:
                logger.warning(f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}")
            return False
    
    # Validate entries
    entries = loss_data.get('entries', [])
    if not isinstance(entries, list):
        if verbose:
            logger.warning("Entries field must be a list")
        return False
    
    for i, entry in enumerate(entries):
        if not _validate_loss_entry(entry, verbose):
            if verbose:
                logger.warning(f"Invalid loss entry at index {i}: {entry}")
            return False
    
    return True


def _validate_loss_entry(entry: Dict[str, Any], verbose: bool = False) -> bool:
    """
    Validate a single loss entry.
    
    Args:
        entry: Dictionary containing loss entry
        verbose: Enable verbose logging
        
    Returns:
        True if the entry is valid, False otherwise
    """
    # Check required fields
    required_fields = ['json_pointer', 'field', 'lost_value', 'reason', 'origin']
    for field in required_fields:
        if field not in entry:
            if verbose:
                logger.warning(f"Missing required field in loss entry: {field}")
            return False
    
    # Validate field types
    if not isinstance(entry['json_pointer'], str):
        if verbose:
            logger.warning("json_pointer must be a string")
        return False
    
    if not isinstance(entry['field'], str):
        if verbose:
            logger.warning("field must be a string")
        return False
    
    if not isinstance(entry['reason'], str):
        if verbose:
            logger.warning("reason must be a string")
        return False
    
    if entry['origin'] not in ['user', 'wf2wf']:
        if verbose:
            logger.warning("origin must be 'user' or 'wf2wf'")
        return False
    
    # Validate optional fields
    if 'severity' in entry:
        if entry['severity'] not in ['info', 'warn', 'error']:
            if verbose:
                logger.warning("severity must be 'info', 'warn', or 'error'")
            return False
    
    if 'status' in entry:
        if entry['status'] not in ['lost', 'lost_again', 'reapplied']:
            if verbose:
                logger.warning("status must be 'lost', 'lost_again', or 'reapplied'")
            return False
    
    return True


def _compute_source_checksum(source_path: Path) -> str:
    """
    Compute SHA-256 checksum of source file.
    
    Args:
        source_path: Path to the source file
        
    Returns:
        SHA-256 checksum in the format 'sha256:<hex>'
    """
    if not source_path.exists():
        return f"sha256:{'0' * 64}"
    
    sha256_hash = hashlib.sha256()
    with open(source_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    
    return f"sha256:{sha256_hash.hexdigest()}"


def _apply_loss_data(
    workflow: Workflow, 
    loss_data: Dict[str, Any], 
    verbose: bool = False
) -> int:
    """
    Apply loss data to workflow.
    
    Args:
        workflow: Workflow object to apply loss information to
        loss_data: Dictionary containing loss information
        verbose: Enable verbose logging
        
    Returns:
        Number of loss entries successfully applied
    """
    entries = loss_data.get('entries', [])
    applied_count = 0
    
    for entry in entries:
        try:
            if _apply_loss_entry(workflow, entry, verbose):
                applied_count += 1
        except Exception as e:
            if verbose:
                logger.warning(f"Failed to apply loss entry {entry}: {e}")
    
    return applied_count


def _apply_loss_entry(
    workflow: Workflow, 
    entry: Dict[str, Any], 
    verbose: bool = False
) -> bool:
    """
    Apply a single loss entry to the workflow.
    
    Args:
        workflow: Workflow object to apply loss information to
        entry: Dictionary containing loss entry information
        verbose: Enable verbose logging
        
    Returns:
        True if the entry was successfully applied, False otherwise
    """
    json_pointer = entry.get('json_pointer', '')
    lost_value = entry.get('lost_value')
    field = entry.get('field')
    status = entry.get('status', 'lost')
    
    if status == 'reapplied':
        if verbose:
            logger.debug(f"Skipping already reapplied entry: {json_pointer}")
        return False
    
    if verbose:
        logger.debug(f"Applying loss entry: {json_pointer} -> {field} = {lost_value}")
    
    # Parse JSON pointer to find the target location
    target = _resolve_json_pointer(workflow, json_pointer)
    
    if target is None:
        if verbose:
            logger.debug(f"Could not resolve JSON pointer: {json_pointer}")
        return False
    
    if lost_value is None:
        if verbose:
            logger.debug(f"Lost value is None for: {json_pointer}")
        return False
    
    # Try to restore the lost value
    success = _restore_lost_value(target, field, lost_value, verbose)
    
    if success:
        # Mark as reapplied
        entry['status'] = 'reapplied'
        if verbose:
            logger.debug(f"Successfully restored {field} at {json_pointer}")
    
    return success


def _resolve_json_pointer(obj: Any, json_pointer: str) -> Any:
    """
    Resolve a JSON pointer to find the target object.
    
    Args:
        obj: Object to search in (usually the workflow)
        json_pointer: JSON pointer string (e.g., "/tasks/task1/cpu")
        
    Returns:
        Target object or None if not found
    """
    if not json_pointer.startswith('/'):
        return None
    
    parts = json_pointer.split('/')[1:]  # Skip empty first part
    
    current = obj
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return None
    
    return current


def _restore_lost_value(
    target: Any, 
    field: str, 
    lost_value: Any, 
    verbose: bool = False
) -> bool:
    """
    Restore a lost value to the target object.
    
    Args:
        target: Target object to restore value to
        field: Field name to restore
        lost_value: Value to restore
        verbose: Enable verbose logging
        
    Returns:
        True if the value was successfully restored, False otherwise
    """
    try:
        # Handle environment-specific fields
        if hasattr(target, 'set_for_environment'):
            # This is a Task or Workflow with environment-specific values
            target.set_for_environment(field, lost_value, 'shared_filesystem')
            return True
        
        # Handle regular fields
        if hasattr(target, field):
            setattr(target, field, lost_value)
            return True
        
        # Handle extra dict for unknown fields
        if hasattr(target, 'extra'):
            target.extra[field] = EnvironmentSpecificValue(lost_value, ['shared_filesystem'])
            return True
        
        # Handle dict-like objects
        if isinstance(target, dict):
            target[field] = lost_value
            return True
        
        if verbose:
            logger.debug(f"Cannot restore {field} to {type(target).__name__}")
        
        return False
        
    except Exception as e:
        if verbose:
            logger.debug(f"Failed to restore {field}: {e}")
        return False


def create_loss_sidecar_summary(
    workflow: Workflow, 
    source_path: Path
) -> Dict[str, Any]:
    """
    Create summary of loss side-car application.
    
    Args:
        workflow: Workflow object that had loss side-car applied
        source_path: Path to the source workflow file
        
    Returns:
        Dictionary containing summary information
    """
    loss_path = source_path.with_suffix('.loss.json')
    
    if not loss_path.exists():
        return {
            'loss_sidecar_found': False,
            'total_entries': 0,
            'applied_entries': 0,
            'failed_entries': 0,
            'by_severity': {},
            'by_origin': {}
        }
    
    try:
        loss_data = json.loads(loss_path.read_text())
        entries = loss_data.get('entries', [])
        
        # Count entries by status
        total_entries = len(entries)
        applied_entries = len([e for e in entries if e.get('status') == 'reapplied'])
        failed_entries = total_entries - applied_entries
        
        # Count by severity
        by_severity = {}
        for entry in entries:
            severity = entry.get('severity', 'info')
            by_severity[severity] = by_severity.get(severity, 0) + 1
        
        # Count by origin
        by_origin = {}
        for entry in entries:
            origin = entry.get('origin', 'unknown')
            by_origin[origin] = by_origin.get(origin, 0) + 1
        
        return {
            'loss_sidecar_found': True,
            'loss_sidecar_path': str(loss_path),
            'total_entries': total_entries,
            'applied_entries': applied_entries,
            'failed_entries': failed_entries,
            'by_severity': by_severity,
            'by_origin': by_origin,
            'wf2wf_version': loss_data.get('wf2wf_version'),
            'target_engine': loss_data.get('target_engine'),
            'timestamp': loss_data.get('timestamp')
        }
        
    except Exception as e:
        logger.warning(f"Failed to create loss side-car summary: {e}")
        return {
            'loss_sidecar_found': True,
            'loss_sidecar_path': str(loss_path),
            'error': str(e),
            'total_entries': 0,
            'applied_entries': 0,
            'failed_entries': 0,
            'by_severity': {},
            'by_origin': {}
        }


def get_loss_sidecar_path(source_path: Path) -> Optional[Path]:
    """
    Get the path to the loss side-car file for a source file.
    
    Args:
        source_path: Path to the source workflow file
        
    Returns:
        Path to the loss side-car file, or None if it doesn't exist
    """
    loss_path = source_path.with_suffix('.loss.json')
    return loss_path if loss_path.exists() else None


def validate_loss_sidecar_compatibility(
    loss_data: Dict[str, Any], 
    source_path: Path
) -> Dict[str, Any]:
    """
    Validate loss side-car compatibility with current workflow.
    
    Args:
        loss_data: Dictionary containing loss data
        source_path: Path to the source workflow file
        
    Returns:
        Dictionary containing validation results
    """
    results = {
        'compatible': True,
        'warnings': [],
        'errors': []
    }
    
    # Check wf2wf version compatibility
    loss_version = loss_data.get('wf2wf_version')
    if loss_version:
        # Simple version check - could be enhanced with proper semver parsing
        if not loss_version.startswith('0.'):
            results['warnings'].append(f"Loss side-car version {loss_version} may not be compatible")
    
    # Check source checksum
    if 'source_checksum' in loss_data:
        expected_checksum = _compute_source_checksum(source_path)
        actual_checksum = loss_data['source_checksum']
        
        if actual_checksum != expected_checksum:
            results['errors'].append(f"Source checksum mismatch: expected {expected_checksum}, got {actual_checksum}")
            results['compatible'] = False
    
    # Check for invalid entries
    entries = loss_data.get('entries', [])
    for i, entry in enumerate(entries):
        if not _validate_loss_entry(entry):
            results['errors'].append(f"Invalid loss entry at index {i}")
            results['compatible'] = False
    
    return results


def create_loss_application_report(
    workflow: Workflow, 
    source_path: Path, 
    verbose: bool = False
) -> str:
    """
    Create a human-readable report of loss side-car application.
    
    Args:
        workflow: Workflow object that had loss side-car applied
        source_path: Path to the source workflow file
        verbose: Enable verbose logging
        
    Returns:
        Human-readable report string
    """
    summary = create_loss_sidecar_summary(workflow, source_path)
    
    if not summary['loss_sidecar_found']:
        return "No loss side-car found."
    
    report_lines = [
        f"Loss side-car application report for {source_path.name}:",
        f"  Side-car file: {summary['loss_sidecar_path']}",
        f"  Total entries: {summary['total_entries']}",
        f"  Successfully applied: {summary['applied_entries']}",
        f"  Failed to apply: {summary['failed_entries']}",
    ]
    
    # Add severity breakdown
    if summary['by_severity']:
        report_lines.append("  By severity:")
        for severity, count in summary['by_severity'].items():
            report_lines.append(f"    {severity}: {count}")
    
    # Add origin breakdown
    if summary['by_origin']:
        report_lines.append("  By origin:")
        for origin, count in summary['by_origin'].items():
            report_lines.append(f"    {origin}: {count}")
    
    # Add warnings if any
    if summary.get('warnings'):
        report_lines.append("  Warnings:")
        for warning in summary['warnings']:
            report_lines.append(f"    - {warning}")
    
    # Add errors if any
    if summary.get('errors'):
        report_lines.append("  Errors:")
        for error in summary['errors']:
            report_lines.append(f"    - {error}")
    
    return "\n".join(report_lines) 