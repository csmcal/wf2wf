"""Format-specific loss detection and environment-specific value handling."""

from __future__ import annotations

import logging
from typing import List, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from wf2wf.core import Workflow, EnvironmentSpecificValue

logger = logging.getLogger(__name__)


@dataclass
class FormatLossDetector:
    """Detects format-specific losses during import/export cycles."""
    
    source_format: str
    target_format: str
    
    def detect_environment_specific_losses(self, workflow: "Workflow") -> List[Dict[str, Any]]:
        """Detect environment-specific value losses between formats."""
        losses = []
        
        for task in workflow.tasks:
            # Check all EnvironmentSpecificValue fields
            for field_name, field_value in task.__dict__.items():
                if isinstance(field_value, EnvironmentSpecificValue):
                    if self._will_lose_environment_specific_info(field_value, field_name):
                        losses.append({
                            "task_id": task.id,
                            "field": field_name,
                            "value": field_value,
                            "reason": f"{self.source_format} environment-specific values not supported in {self.target_format}"
                        })
        
        return losses
    
    def _will_lose_environment_specific_info(self, env_value: "EnvironmentSpecificValue", field_name: str) -> bool:
        """Check if environment-specific information will be lost in target format."""
        # Different formats have different capabilities
        if self.target_format == "cwl":
            # CWL has limited environment-specific support
            return len(env_value.all_environments()) > 1
        elif self.target_format == "dagman":
            # DAGMan primarily supports distributed_computing environment
            return "shared_filesystem" in env_value.all_environments()
        elif self.target_format == "snakemake":
            # Snakemake has good environment support
            return False
        elif self.target_format == "nextflow":
            # Nextflow has good environment support
            return False
        elif self.target_format == "wdl":
            # WDL has limited environment-specific support
            return len(env_value.all_environments()) > 1
        elif self.target_format == "galaxy":
            # Galaxy has limited environment-specific support
            return len(env_value.all_environments()) > 1
        
        return True


@dataclass
class EnvironmentLossRecorder:
    """Records environment-specific losses with detailed context."""
    
    source_format: str
    target_format: str
    target_environment: str
    
    def record_environment_specific_value_loss(
        self,
        json_pointer: str,
        field: str,
        env_value: "EnvironmentSpecificValue",
        reason: str,
        *,
        severity: str = "warn"
    ) -> None:
        """Record loss of environment-specific value with detailed context."""
        # Extract all environment values
        all_values = {}
        for env in env_value.all_environments():
            all_values[env] = env_value.get_value_for(env)
        
        # Get the most relevant value for the target environment
        target_value = env_value.get_value_for(self.target_environment)
        if target_value is None:
            # Fall back to default value
            target_value = env_value.default_value
        
        from .core import record
        record(
            json_pointer=json_pointer,
            field=field,
            lost_value={
                "all_environment_values": all_values,
                "target_environment_value": target_value,
                "default_value": env_value.default_value,
                "environment_specific_value_type": "EnvironmentSpecificValue"
            },
            reason=reason,
            origin="wf2wf",
            severity=severity,
            category="environment_specific",
            environment_context={
                "source_format": self.source_format,
                "target_format": self.target_format,
                "target_environment": self.target_environment,
                "applicable_environments": list(env_value.all_environments()),
                "has_target_environment_value": target_value is not None
            },
            recovery_suggestions=[
                f"Use value from {self.target_environment} environment: {target_value}",
                f"Use default value: {env_value.default_value}",
                "Manually specify environment-specific values in target format"
            ]
        )


def detect_format_specific_losses(
    workflow: "Workflow",
    source_format: str,
    target_format: str
) -> List[Dict[str, Any]]:
    """Detect format-specific losses in a workflow."""
    detector = FormatLossDetector(source_format, target_format)
    return detector.detect_environment_specific_losses(workflow)


def record_environment_specific_value_loss(
    json_pointer: str,
    field: str,
    env_value: "EnvironmentSpecificValue",
    source_format: str,
    target_format: str,
    target_environment: str,
    reason: str,
    *,
    severity: str = "warn"
) -> None:
    """Record loss of environment-specific value with format context."""
    recorder = EnvironmentLossRecorder(source_format, target_format, target_environment)
    recorder.record_environment_specific_value_loss(json_pointer, field, env_value, reason, severity=severity)


def validate_environment_specific_value(
    value: Any,
    field_name: str,
    expected_type: type
) -> bool:
    """Validate that a value is a proper EnvironmentSpecificValue."""
    if not isinstance(value, EnvironmentSpecificValue):
        logger.warning(f"Field {field_name} is not an EnvironmentSpecificValue: {type(value)}")
        return False
    
    # Check that the value type matches expected type
    if not isinstance(value.default_value, expected_type):
        logger.warning(f"Field {field_name} default value type mismatch: expected {expected_type}, got {type(value.default_value)}")
        return False
    
    return True


def restore_environment_specific_value(
    lost_value: Any,
    field_name: str,
    expected_type: type,
    target_environment: str
) -> "EnvironmentSpecificValue":
    """Restore an EnvironmentSpecificValue from lost data."""
    from wf2wf.core import EnvironmentSpecificValue
    
    if isinstance(lost_value, dict) and "environment_specific_value_type" in lost_value:
        # This is a properly recorded environment-specific value
        if "all_environment_values" in lost_value:
            # Reconstruct from all environment values
            env_values = lost_value["all_environment_values"]
            default_value = lost_value.get("default_value", lost_value.get("target_environment_value"))
            
            # Create new EnvironmentSpecificValue
            restored = EnvironmentSpecificValue(default_value)
            
            # Set values for each environment
            for env, value in env_values.items():
                if value is not None:
                    restored.set_for_environment(value, env)
            
            return restored
        elif "target_environment_value" in lost_value:
            # Use target environment value as default
            target_value = lost_value["target_environment_value"]
            restored = EnvironmentSpecificValue(target_value)
            if target_value is not None:
                restored.set_for_environment(target_value, target_environment)
            return restored
    
    # Fallback: treat as simple value and create EnvironmentSpecificValue
    if isinstance(lost_value, expected_type):
        restored = EnvironmentSpecificValue(lost_value)
        restored.set_for_environment(lost_value, target_environment)
        return restored
    
    # Last resort: use default value for the type
    if expected_type == int:
        default_val = 0
    elif expected_type == float:
        default_val = 0.0
    elif expected_type == str:
        default_val = ""
    elif expected_type == bool:
        default_val = False
    else:
        default_val = None
    
    restored = EnvironmentSpecificValue(default_val)
    logger.warning(f"Could not restore {field_name} from {lost_value}, using default: {default_val}")
    return restored 