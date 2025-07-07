"""
wf2wf.exporters.loss_integration – Loss detection and recording for exporters.

This module provides utilities for detecting and recording information loss
when converting from the IR to target workflow formats.
"""

from __future__ import annotations

from typing import Any, Dict, List

from wf2wf.core import Workflow, Task, EnvironmentSpecificValue
from wf2wf.loss import record as loss_record


def detect_and_record_losses(workflow: Workflow, target_format: str, target_environment: str = "shared_filesystem", verbose: bool = False) -> None:
    """Detect and record losses when converting to target format for specific environment."""
    
    if target_format == "cwl":
        _record_cwl_losses(workflow, target_environment, verbose)
    elif target_format == "dagman":
        _record_dagman_losses(workflow, target_environment, verbose)
    elif target_format == "snakemake":
        _record_snakemake_losses(workflow, target_environment, verbose)
    elif target_format == "nextflow":
        _record_nextflow_losses(workflow, target_environment, verbose)
    elif target_format == "wdl":
        _record_wdl_losses(workflow, target_environment, verbose)
    elif target_format == "galaxy":
        _record_galaxy_losses(workflow, target_environment, verbose)
    else:
        if verbose:
            print(f"Warning: No loss detection rules for format '{target_format}'")


def _record_cwl_losses(workflow: Workflow, target_environment: str, verbose: bool = False) -> None:
    """Record losses when converting to CWL format."""
    
    for task in workflow.tasks.values():
        # GPU resources not fully supported in CWL ResourceRequirement
        gpu_value = _get_env_value(task.gpu, target_environment)
        if gpu_value:
            loss_record(
                f"/tasks/{task.id}/gpu",
                "gpu",
                gpu_value,
                "CWL ResourceRequirement lacks GPU fields",
                "user"
            )
        
        gpu_mem_value = _get_env_value(task.gpu_mem_mb, target_environment)
        if gpu_mem_value:
            loss_record(
                f"/tasks/{task.id}/gpu_mem_mb",
                "gpu_mem_mb",
                gpu_mem_value,
                "CWL ResourceRequirement lacks GPU memory fields",
                "user"
            )
        
        # Priority and retry not part of CWL core spec
        priority_value = _get_env_value(task.priority, target_environment)
        if priority_value:
            loss_record(
                f"/tasks/{task.id}/priority",
                "priority",
                priority_value,
                "CWL lacks job priority field",
                "user"
            )
        
        retry_value = _get_env_value(task.retry_count, target_environment)
        if retry_value:
            loss_record(
                f"/tasks/{task.id}/retry_count",
                "retry",
                retry_value,
                "CWL lacks retry mechanism; use engine hints instead",
                "user"
            )
        
        # Advanced features not supported in CWL
        checkpointing = _get_env_value(task.checkpointing, target_environment)
        if checkpointing:
            loss_record(
                f"/tasks/{task.id}/checkpointing",
                "checkpointing",
                checkpointing,
                "CWL lacks checkpointing support",
                "user"
            )
        
        logging = _get_env_value(task.logging, target_environment)
        if logging:
            loss_record(
                f"/tasks/{task.id}/logging",
                "logging",
                logging,
                "CWL lacks structured logging support",
                "user"
            )
        
        security = _get_env_value(task.security, target_environment)
        if security:
            loss_record(
                f"/tasks/{task.id}/security",
                "security",
                security,
                "CWL lacks security specification support",
                "user"
            )
        
        networking = _get_env_value(task.networking, target_environment)
        if networking:
            loss_record(
                f"/tasks/{task.id}/networking",
                "networking",
                networking,
                "CWL lacks networking specification support",
                "user"
            )


def _record_dagman_losses(workflow: Workflow, target_environment: str, verbose: bool = False) -> None:
    """Record losses when converting to DAGMan format."""
    
    for task in workflow.tasks.values():
        # Scatter operations not supported in DAGMan
        scatter_value = _get_env_value(task.scatter, target_environment)
        if scatter_value:
            loss_record(
                f"/tasks/{task.id}/scatter",
                "scatter",
                scatter_value.scatter,
                "DAGMan has no scatter primitive",
                "user"
            )
        
        # Conditional execution not supported
        when_value = _get_env_value(task.when, target_environment)
        if when_value:
            loss_record(
                f"/tasks/{task.id}/when",
                "when",
                when_value,
                "Conditional when lost in DAGMan",
                "user"
            )
        
        # Secondary files not preserved
        for param_list in (task.inputs, task.outputs):
            for p in param_list:
                if hasattr(p, 'secondary_files') and p.secondary_files:
                    loss_record(
                        f"/tasks/{task.id}/{'inputs' if param_list is task.inputs else 'outputs'}/{p.id}/secondary_files",
                        "secondary_files",
                        p.secondary_files,
                        "HTCondor DAGMan has no concept of secondary files",
                        "user"
                    )
        
        # Advanced features not supported
        checkpointing = _get_env_value(task.checkpointing, target_environment)
        if checkpointing:
            loss_record(
                f"/tasks/{task.id}/checkpointing",
                "checkpointing",
                checkpointing,
                "DAGMan lacks checkpointing support",
                "user"
            )
        
        logging = _get_env_value(task.logging, target_environment)
        if logging:
            loss_record(
                f"/tasks/{task.id}/logging",
                "logging",
                logging,
                "DAGMan lacks structured logging support",
                "user"
            )
        
        security = _get_env_value(task.security, target_environment)
        if security:
            loss_record(
                f"/tasks/{task.id}/security",
                "security",
                security,
                "DAGMan lacks security specification support",
                "user"
            )
        
        networking = _get_env_value(task.networking, target_environment)
        if networking:
            loss_record(
                f"/tasks/{task.id}/networking",
                "networking",
                networking,
                "DAGMan lacks networking specification support",
                "user"
            )


def _record_snakemake_losses(workflow: Workflow, target_environment: str, verbose: bool = False) -> None:
    """Record losses when converting to Snakemake format."""
    
    # Workflow-level intent not representable
    if workflow.intent:
        loss_record(
            "/intent",
            "intent",
            workflow.intent,
            "Snakemake has no ontology intent field",
            "user"
        )
    
    for task in workflow.tasks.values():
        # Scatter operations not natively supported
        scatter_value = _get_env_value(task.scatter, target_environment)
        if scatter_value:
            loss_record(
                f"/tasks/{task.id}/scatter",
                "scatter",
                scatter_value.scatter,
                "Native scatter not supported in Snakemake",
                "user"
            )
        
        # Conditional execution not directly supported
        when_value = _get_env_value(task.when, target_environment)
        if when_value:
            loss_record(
                f"/tasks/{task.id}/when",
                "when",
                when_value,
                "Conditional execution not directly supported in Snakemake",
                "user"
            )
        
        # GPU scheduling not expressible
        gpu_value = _get_env_value(task.gpu, target_environment)
        if gpu_value:
            loss_record(
                f"/tasks/{task.id}/gpu",
                "gpu",
                gpu_value,
                "GPU scheduling not expressible in Snakemake",
                "user"
            )
        
        # Secondary files concept missing
        for p in task.outputs:
            if hasattr(p, 'secondary_files') and p.secondary_files:
                loss_record(
                    f"/tasks/{task.id}/outputs/{p.id}/secondary_files",
                    "secondary_files",
                    p.secondary_files,
                    "Secondary files concept missing in Snakemake",
                    "user"
                )
        
        # Advanced features not supported
        checkpointing = _get_env_value(task.checkpointing, target_environment)
        if checkpointing:
            loss_record(
                f"/tasks/{task.id}/checkpointing",
                "checkpointing",
                checkpointing,
                "Snakemake lacks checkpointing support",
                "user"
            )
        
        logging = _get_env_value(task.logging, target_environment)
        if logging:
            loss_record(
                f"/tasks/{task.id}/logging",
                "logging",
                logging,
                "Snakemake lacks structured logging support",
                "user"
            )
        
        security = _get_env_value(task.security, target_environment)
        if security:
            loss_record(
                f"/tasks/{task.id}/security",
                "security",
                security,
                "Snakemake lacks security specification support",
                "user"
            )
        
        networking = _get_env_value(task.networking, target_environment)
        if networking:
            loss_record(
                f"/tasks/{task.id}/networking",
                "networking",
                networking,
                "Snakemake lacks networking specification support",
                "user"
            )


def _record_nextflow_losses(workflow: Workflow, target_environment: str, verbose: bool = False) -> None:
    """Record losses when converting to Nextflow format."""
    
    for task in workflow.tasks.values():
        # Advanced features not fully supported
        checkpointing = _get_env_value(task.checkpointing, "cloud_native")
        if checkpointing:
            loss_record(
                f"/tasks/{task.id}/checkpointing",
                "checkpointing",
                checkpointing,
                "Nextflow lacks checkpointing support",
                "user"
            )
        
        security = _get_env_value(task.security, "cloud_native")
        if security:
            loss_record(
                f"/tasks/{task.id}/security",
                "security",
                security,
                "Nextflow lacks security specification support",
                "user"
            )
        
        networking = _get_env_value(task.networking, "cloud_native")
        if networking:
            loss_record(
                f"/tasks/{task.id}/networking",
                "networking",
                networking,
                "Nextflow lacks networking specification support",
                "user"
            )


def _record_wdl_losses(workflow: Workflow, target_environment: str, verbose: bool = False) -> None:
    """Record losses when converting to WDL format."""
    
    for task in workflow.tasks.values():
        # Advanced features not supported
        checkpointing = _get_env_value(task.checkpointing, "shared_filesystem")
        if checkpointing:
            loss_record(
                f"/tasks/{task.id}/checkpointing",
                "checkpointing",
                checkpointing,
                "WDL lacks checkpointing support",
                "user"
            )
        
        logging = _get_env_value(task.logging, "shared_filesystem")
        if logging:
            loss_record(
                f"/tasks/{task.id}/logging",
                "logging",
                logging,
                "WDL lacks structured logging support",
                "user"
            )
        
        security = _get_env_value(task.security, "shared_filesystem")
        if security:
            loss_record(
                f"/tasks/{task.id}/security",
                "security",
                security,
                "WDL lacks security specification support",
                "user"
            )
        
        networking = _get_env_value(task.networking, "shared_filesystem")
        if networking:
            loss_record(
                f"/tasks/{task.id}/networking",
                "networking",
                networking,
                "WDL lacks networking specification support",
                "user"
            )


def _record_galaxy_losses(workflow: Workflow, target_environment: str, verbose: bool = False) -> None:
    """Record losses when converting to Galaxy format."""
    
    for task in workflow.tasks.values():
        # Many advanced features not supported in Galaxy
        scatter_value = _get_env_value(task.scatter, "shared_filesystem")
        if scatter_value:
            loss_record(
                f"/tasks/{task.id}/scatter",
                "scatter",
                scatter_value.scatter,
                "Galaxy lacks scatter support",
                "user"
            )
        
        when_value = _get_env_value(task.when, "shared_filesystem")
        if when_value:
            loss_record(
                f"/tasks/{task.id}/when",
                "when",
                when_value,
                "Galaxy lacks conditional execution support",
                "user"
            )
        
        # Advanced features not supported
        checkpointing = _get_env_value(task.checkpointing, "shared_filesystem")
        if checkpointing:
            loss_record(
                f"/tasks/{task.id}/checkpointing",
                "checkpointing",
                checkpointing,
                "Galaxy lacks checkpointing support",
                "user"
            )
        
        logging = _get_env_value(task.logging, "shared_filesystem")
        if logging:
            loss_record(
                f"/tasks/{task.id}/logging",
                "logging",
                logging,
                "Galaxy lacks structured logging support",
                "user"
            )
        
        security = _get_env_value(task.security, "shared_filesystem")
        if security:
            loss_record(
                f"/tasks/{task.id}/security",
                "security",
                security,
                "Galaxy lacks security specification support",
                "user"
            )
        
        networking = _get_env_value(task.networking, "shared_filesystem")
        if networking:
            loss_record(
                f"/tasks/{task.id}/networking",
                "networking",
                networking,
                "Galaxy lacks networking specification support",
                "user"
            )


def _get_env_value(env_value: EnvironmentSpecificValue, environment: str) -> Any:
    """Get value for specific environment from EnvironmentSpecificValue."""
    if env_value is None:
        return None
    
    # Try to get environment-specific value
    value = env_value.get_value_for(environment)
    if value is not None:
        return value
    
    # Fallback to universal value (empty environments list)
    return env_value.get_value_for("") 