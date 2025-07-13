"""
Logging utilities for environment adaptation.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime


class AdaptationLogger:
    """
    Logger for tracking adaptation decisions and their rationale.
    """
    
    def __init__(self, name: str = "adaptation"):
        self.logger = logging.getLogger(name)
        self.adaptations = []
        self.start_time = datetime.now()
    
    def log_adaptation(self, field: str, old_value: Any, new_value: Any, 
                      reason: str, source_env: str, target_env: str, 
                      level: str = "INFO"):
        """
        Log an adaptation decision.
        
        Args:
            field: Name of the field being adapted
            old_value: Original value
            new_value: New value after adaptation
            reason: Reason for the adaptation
            source_env: Source environment
            target_env: Target environment
            level: Log level (INFO, WARNING, ERROR)
        """
        adaptation_record = {
            "timestamp": datetime.now().isoformat(),
            "field": field,
            "old_value": old_value,
            "new_value": new_value,
            "reason": reason,
            "source_env": source_env,
            "target_env": target_env,
            "level": level
        }
        
        self.adaptations.append(adaptation_record)
        
        # Log to standard logger
        log_message = (
            f"Adaptation: {field} = {old_value} → {new_value} "
            f"({source_env} → {target_env}): {reason}"
        )
        
        if level == "WARNING":
            self.logger.warning(log_message)
        elif level == "ERROR":
            self.logger.error(log_message)
        else:
            self.logger.info(log_message)
    
    def log_environment_mismatch(self, field: str, source_env: str, target_env: str):
        """
        Log when a field is missing for the target environment.
        
        Args:
            field: Name of the field
            source_env: Source environment
            target_env: Target environment
        """
        self.log_adaptation(
            field, None, None,
            f"Field not available for {target_env} environment",
            source_env, target_env, "WARNING"
        )
    
    def log_fallback_used(self, field: str, fallback_value: Any, 
                         source_env: str, target_env: str):
        """
        Log when a fallback value is used.
        
        Args:
            field: Name of the field
            fallback_value: Fallback value used
            source_env: Source environment
            target_env: Target environment
        """
        self.log_adaptation(
            field, None, fallback_value,
            f"Using fallback value for {target_env} environment",
            source_env, target_env, "INFO"
        )
    
    def log_scaling_applied(self, field: str, original_value: Any, scaled_value: Any,
                           scaling_factor: float, source_env: str, target_env: str):
        """
        Log when resource scaling is applied.
        
        Args:
            field: Name of the field
            original_value: Original value
            scaled_value: Scaled value
            scaling_factor: Scaling factor applied
            source_env: Source environment
            target_env: Target environment
        """
        self.log_adaptation(
            field, original_value, scaled_value,
            f"Applied {scaling_factor:.2f}x scaling for {target_env} environment",
            source_env, target_env, "INFO"
        )
    
    def get_adaptation_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all adaptations performed.
        
        Returns:
            Dictionary containing adaptation summary
        """
        if not self.adaptations:
            return {
                "total_adaptations": 0,
                "adaptations": [],
                "duration": 0,
                "warnings": 0,
                "errors": 0
            }
        
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        warnings = sum(1 for a in self.adaptations if a["level"] == "WARNING")
        errors = sum(1 for a in self.adaptations if a["level"] == "ERROR")
        
        return {
            "total_adaptations": len(self.adaptations),
            "adaptations": self.adaptations,
            "duration": duration,
            "warnings": warnings,
            "errors": errors,
            "start_time": self.start_time.isoformat(),
            "end_time": end_time.isoformat()
        }
    
    def print_summary(self):
        """Print a human-readable summary of adaptations."""
        summary = self.get_adaptation_summary()
        
        print(f"\n=== Adaptation Summary ===")
        print(f"Total adaptations: {summary['total_adaptations']}")
        print(f"Duration: {summary['duration']:.2f}s")
        print(f"Warnings: {summary['warnings']}")
        print(f"Errors: {summary['errors']}")
        
        if summary['adaptations']:
            print(f"\nAdaptations:")
            for adaptation in summary['adaptations']:
                level_icon = {
                    "INFO": "ℹ️",
                    "WARNING": "⚠️", 
                    "ERROR": "❌"
                }.get(adaptation["level"], "ℹ️")
                
                print(f"  {level_icon} {adaptation['field']}: "
                      f"{adaptation['old_value']} → {adaptation['new_value']}")
                print(f"     Reason: {adaptation['reason']}")
    
    def export_report(self, format: str = "json") -> str:
        """
        Export adaptation report in specified format.
        
        Args:
            format: Report format ("json", "yaml", "text")
            
        Returns:
            Formatted report string
        """
        summary = self.get_adaptation_summary()
        
        if format == "json":
            import json
            return json.dumps(summary, indent=2)
        
        elif format == "yaml":
            import yaml
            return yaml.dump(summary, default_flow_style=False)
        
        elif format == "text":
            lines = []
            lines.append("Environment Adaptation Report")
            lines.append("=" * 40)
            lines.append(f"Total adaptations: {summary['total_adaptations']}")
            lines.append(f"Duration: {summary['duration']:.2f}s")
            lines.append(f"Warnings: {summary['warnings']}")
            lines.append(f"Errors: {summary['errors']}")
            lines.append("")
            
            if summary['adaptations']:
                lines.append("Detailed Adaptations:")
                lines.append("-" * 20)
                for adaptation in summary['adaptations']:
                    lines.append(f"Field: {adaptation['field']}")
                    lines.append(f"  Old: {adaptation['old_value']}")
                    lines.append(f"  New: {adaptation['new_value']}")
                    lines.append(f"  Reason: {adaptation['reason']}")
                    lines.append(f"  Level: {adaptation['level']}")
                    lines.append("")
            
            return "\n".join(lines)
        
        else:
            raise ValueError(f"Unsupported format: {format}")


# Global adaptation logger instance
adaptation_logger = AdaptationLogger()


def log_adaptation(field: str, old_value: Any, new_value: Any, 
                  reason: str, source_env: str, target_env: str, 
                  level: str = "INFO"):
    """
    Convenience function to log an adaptation using the global logger.
    
    Args:
        field: Name of the field being adapted
        old_value: Original value
        new_value: New value after adaptation
        reason: Reason for the adaptation
        source_env: Source environment
        target_env: Target environment
        level: Log level (INFO, WARNING, ERROR)
    """
    adaptation_logger.log_adaptation(
        field, old_value, new_value, reason, source_env, target_env, level
    )


def get_adaptation_summary() -> Dict[str, Any]:
    """
    Get adaptation summary from the global logger.
    
    Returns:
        Dictionary containing adaptation summary
    """
    return adaptation_logger.get_adaptation_summary()


def print_adaptation_summary():
    """Print adaptation summary from the global logger."""
    adaptation_logger.print_summary()


def export_adaptation_report(format: str = "json") -> str:
    """
    Export adaptation report from the global logger.
    
    Args:
        format: Report format ("json", "yaml", "text")
        
    Returns:
        Formatted report string
    """
    return adaptation_logger.export_report(format) 