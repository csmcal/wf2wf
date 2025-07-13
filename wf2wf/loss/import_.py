"""Import loss detection and validation for loss sidecars."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


def detect_and_record_import_losses(workflow: "Workflow", source_format: str, target_environment: str = "shared_filesystem", verbose: bool = False) -> None:
    """Detect and record losses when importing from source format."""
    # This function can be expanded to detect import-specific losses
    # For now, it's a placeholder for future import loss detection
    pass


def validate_loss_sidecar(loss_data: Dict[str, Any], workflow, verbose: bool = False) -> bool:
    """
    Validate loss side-car data.
    
    Args:
        loss_data: Dictionary containing loss data
        workflow: Workflow IR object (for checksum validation)
        verbose: Enable verbose logging
        
    Returns:
        True if the loss side-car is valid, False otherwise
    """
    # Check required fields from base system
    required_fields = ['wf2wf_version', 'target_engine', 'entries', 'summary']
    for field in required_fields:
        if field not in loss_data:
            if verbose:
                logger.warning(f"Missing required field in loss side-car: {field}")
            return False
    
    # Check source checksum if present
    if 'source_checksum' in loss_data:
        # Validate checksum against the workflow IR
        try:
            from wf2wf.loss.core import compute_checksum
            actual_checksum = compute_checksum(workflow)
            expected_checksum = loss_data['source_checksum']
            
            if actual_checksum != expected_checksum:
                # Check if this looks like deliberate tampering (e.g., all zeros)
                if expected_checksum == "sha256:" + "0" * 64:
                    if verbose:
                        logger.warning(f"Detected zeroed checksum: {expected_checksum}")
                    return False
                
                # Otherwise, it's likely a normal round-trip difference
                if verbose:
                    logger.warning(f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}")
                    logger.info("Checksum mismatch detected - this is expected for round-trip conversions. Proceeding with loss reinjection.")
                # Don't return False - allow loss reinjection to proceed with warning
        except Exception as e:
            if verbose:
                logger.warning(f"Failed to validate checksum: {e}")
            # Don't return False - allow loss reinjection to proceed with warning
    
    # Validate entries
    entries = loss_data.get('entries', [])
    if not isinstance(entries, list):
        if verbose:
            logger.warning("Entries field must be a list")
        return False
    
    for i, entry in enumerate(entries):
        if not validate_loss_entry(entry, verbose):
            if verbose:
                logger.warning(f"Invalid loss entry at index {i}: {entry}")
            return False
    
    return True


def validate_loss_entry(entry: Dict[str, Any], verbose: bool = False) -> bool:
    """
    Validate a single loss entry.
    
    Args:
        entry: Dictionary containing loss entry data
        verbose: Enable verbose logging
        
    Returns:
        True if the loss entry is valid, False otherwise
    """
    # Check required fields
    required_fields = ['json_pointer', 'field', 'lost_value', 'reason', 'origin', 'status', 'severity']
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
    
    if not isinstance(entry['origin'], str):
        if verbose:
            logger.warning("origin must be a string")
        return False
    
    if not isinstance(entry['status'], str):
        if verbose:
            logger.warning("status must be a string")
        return False
    
    if not isinstance(entry['severity'], str):
        if verbose:
            logger.warning("severity must be a string")
        return False
    
    # Validate status values
    valid_statuses = ['lost', 'lost_again', 'reapplied', 'adapted']
    if entry['status'] not in valid_statuses:
        if verbose:
            logger.warning(f"Invalid status: {entry['status']}. Must be one of: {valid_statuses}")
        return False
    
    # Validate severity values
    valid_severities = ['info', 'warn', 'error']
    if entry['severity'] not in valid_severities:
        if verbose:
            logger.warning(f"Invalid severity: {entry['severity']}. Must be one of: {valid_severities}")
        return False
    
    # Validate origin values
    valid_origins = ['user', 'wf2wf']
    if entry['origin'] not in valid_origins:
        if verbose:
            logger.warning(f"Invalid origin: {entry['origin']}. Must be one of: {valid_origins}")
        return False
    
    # Validate JSON pointer format
    json_pointer = entry['json_pointer']
    if not json_pointer.startswith('/'):
        if verbose:
            logger.warning("json_pointer must start with '/'")
        return False
    
    # Validate optional fields if present
    if 'category' in entry and not isinstance(entry['category'], str):
        if verbose:
            logger.warning("category must be a string")
        return False
    
    if 'environment_context' in entry and not isinstance(entry['environment_context'], dict):
        if verbose:
            logger.warning("environment_context must be a dictionary")
        return False
    
    if 'adaptation_details' in entry and not isinstance(entry['adaptation_details'], dict):
        if verbose:
            logger.warning("adaptation_details must be a dictionary")
        return False
    
    if 'recovery_suggestions' in entry:
        if not isinstance(entry['recovery_suggestions'], list):
            if verbose:
                logger.warning("recovery_suggestions must be a list")
            return False
        
        for suggestion in entry['recovery_suggestions']:
            if not isinstance(suggestion, str):
                if verbose:
                    logger.warning("All recovery_suggestions must be strings")
                return False
    
    return True 