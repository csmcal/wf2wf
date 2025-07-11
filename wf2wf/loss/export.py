"""Export loss detection and recording for different workflow formats."""

from __future__ import annotations

from typing import Any, Dict, List

from wf2wf.core import Workflow, Task, EnvironmentSpecificValue
from .core import record as loss_record
from .context_detection import record_environment_specific_value_loss


def detect_and_record_export_losses(workflow: Workflow, target_format: str, target_environment: str = "shared_filesystem", verbose: bool = False) -> None:
    """Detect and record losses when converting to target format for specific environment."""
    
    if target_format == "cwl":
        record_cwl_losses(workflow, target_environment, verbose)
    elif target_format == "dagman":
        record_dagman_losses(workflow, target_environment, verbose)
    elif target_format == "snakemake":
        record_snakemake_losses(workflow, target_environment, verbose)
    elif target_format == "nextflow":
        record_nextflow_losses(workflow, target_environment, verbose)
    elif target_format == "wdl":
        record_wdl_losses(workflow, target_environment, verbose)
    elif target_format == "galaxy":
        record_galaxy_losses(workflow, target_environment, verbose)
    else:
        if verbose:
            print(f"Warning: No loss detection rules for format '{target_format}'")


def record_cwl_losses(workflow: Workflow, target_environment: str, verbose: bool = False) -> None:
    """Record losses when converting to CWL format."""
    
    for task in workflow.tasks.values():
        # GPU resources not fully supported in CWL ResourceRequirement
        if task.gpu and isinstance(task.gpu, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/gpu",
                "gpu",
                task.gpu,
                "cwl",
                "cwl",
                target_environment,
                "CWL ResourceRequirement lacks GPU fields"
            )
        
        if task.gpu_mem_mb and isinstance(task.gpu_mem_mb, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/gpu_mem_mb",
                "gpu_mem_mb",
                task.gpu_mem_mb,
                "cwl",
                "cwl",
                target_environment,
                "CWL ResourceRequirement lacks GPU memory fields"
            )
        
        # Priority and retry not part of CWL core spec
        if task.priority and isinstance(task.priority, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/priority",
                "priority",
                task.priority,
                "cwl",
                "cwl",
                target_environment,
                "CWL lacks job priority field"
            )
        
        if task.retry_count and isinstance(task.retry_count, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/retry_count",
                "retry_count",
                task.retry_count,
                "cwl",
                "cwl",
                target_environment,
                "CWL lacks retry mechanism; use engine hints instead"
            )
        
        # Advanced features not supported in CWL
        if task.checkpointing and isinstance(task.checkpointing, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/checkpointing",
                "checkpointing",
                task.checkpointing,
                "cwl",
                "cwl",
                target_environment,
                "CWL lacks checkpointing support"
            )
        
        if task.logging and isinstance(task.logging, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/logging",
                "logging",
                task.logging,
                "cwl",
                "cwl",
                target_environment,
                "CWL lacks structured logging support"
            )
        
        if task.security and isinstance(task.security, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/security",
                "security",
                task.security,
                "cwl",
                "cwl",
                target_environment,
                "CWL lacks security specification support"
            )
        
        if task.networking and isinstance(task.networking, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/networking",
                "networking",
                task.networking,
                "cwl",
                "cwl",
                target_environment,
                "CWL lacks networking specification support"
            )


def record_dagman_losses(workflow: Workflow, target_environment: str, verbose: bool = False) -> None:
    """Record losses when converting to DAGMan format."""
    
    for task in workflow.tasks.values():
        # Scatter operations not supported in DAGMan
        if task.scatter and isinstance(task.scatter, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/scatter",
                "scatter",
                task.scatter,
                "dagman",
                "dagman",
                target_environment,
                "DAGMan has no scatter primitive"
            )
        
        # Conditional execution not supported
        if task.when and isinstance(task.when, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/when",
                "when",
                task.when,
                "dagman",
                "dagman",
                target_environment,
                "Conditional when lost in DAGMan"
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
        if task.checkpointing and isinstance(task.checkpointing, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/checkpointing",
                "checkpointing",
                task.checkpointing,
                "dagman",
                "dagman",
                target_environment,
                "DAGMan lacks checkpointing support"
            )
        
        if task.logging and isinstance(task.logging, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/logging",
                "logging",
                task.logging,
                "dagman",
                "dagman",
                target_environment,
                "DAGMan lacks structured logging support"
            )
        
        if task.security and isinstance(task.security, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/security",
                "security",
                task.security,
                "dagman",
                "dagman",
                target_environment,
                "DAGMan lacks security specification support"
            )
        
        if task.networking and isinstance(task.networking, EnvironmentSpecificValue):
            record_environment_specific_value_loss(
                f"/tasks/{task.id}/networking",
                "networking",
                task.networking,
                "dagman",
                "dagman",
                target_environment,
                "DAGMan lacks networking specification support"
            )


def record_snakemake_losses(workflow: Workflow, target_environment: str, verbose: bool = False) -> None:
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
        # GPU resources not supported in Snakemake
        gpu_value = _get_env_value(task.gpu, target_environment)
        if gpu_value:
            loss_record(
                f"/tasks/{task.id}/gpu",
                "gpu",
                gpu_value,
                "GPU resources not supported in Snakemake",
                "user"
            )
        
        # Retry policies not supported
        retry_value = _get_env_value(task.retry_count, target_environment)
        if retry_value:
            loss_record(
                f"/tasks/{task.id}/retry_count",
                "retry_count",
                retry_value,
                "Retry policies not supported in Snakemake",
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


def record_nextflow_losses(workflow: Workflow, target_environment: str, verbose: bool = False) -> None:
    """Record losses when converting to Nextflow format."""
    
    for task in workflow.tasks.values():
        # Advanced features not supported
        checkpointing = _get_env_value(task.checkpointing, target_environment)
        if checkpointing:
            loss_record(
                f"/tasks/{task.id}/checkpointing",
                "checkpointing",
                checkpointing,
                "Nextflow lacks checkpointing support",
                "user"
            )
        
        logging = _get_env_value(task.logging, target_environment)
        if logging:
            loss_record(
                f"/tasks/{task.id}/logging",
                "logging",
                logging,
                "Nextflow lacks structured logging support",
                "user"
            )
        
        security = _get_env_value(task.security, target_environment)
        if security:
            loss_record(
                f"/tasks/{task.id}/security",
                "security",
                security,
                "Nextflow lacks security specification support",
                "user"
            )
        
        networking = _get_env_value(task.networking, target_environment)
        if networking:
            loss_record(
                f"/tasks/{task.id}/networking",
                "networking",
                networking,
                "Nextflow lacks networking specification support",
                "user"
            )


def record_wdl_losses(workflow: Workflow, target_environment: str, verbose: bool = False) -> None:
    """Record losses when converting to WDL format."""
    
    for task in workflow.tasks.values():
        # GPU resources not fully supported in WDL
        gpu_value = _get_env_value(task.gpu, target_environment)
        if gpu_value:
            loss_record(
                f"/tasks/{task.id}/gpu",
                "gpu",
                gpu_value,
                "WDL lacks GPU resource specification",
                "user"
            )
        
        gpu_mem_value = _get_env_value(task.gpu_mem_mb, target_environment)
        if gpu_mem_value:
            loss_record(
                f"/tasks/{task.id}/gpu_mem_mb",
                "gpu_mem_mb",
                gpu_mem_value,
                "WDL lacks GPU memory specification",
                "user"
            )
        
        # Priority not supported in WDL
        priority_value = _get_env_value(task.priority, target_environment)
        if priority_value:
            loss_record(
                f"/tasks/{task.id}/priority",
                "priority",
                priority_value,
                "WDL lacks job priority field",
                "user"
            )
        
        # Advanced features not supported
        checkpointing = _get_env_value(task.checkpointing, target_environment)
        if checkpointing:
            loss_record(
                f"/tasks/{task.id}/checkpointing",
                "checkpointing",
                checkpointing,
                "WDL lacks checkpointing support",
                "user"
            )
        
        logging = _get_env_value(task.logging, target_environment)
        if logging:
            loss_record(
                f"/tasks/{task.id}/logging",
                "logging",
                logging,
                "WDL lacks structured logging support",
                "user"
            )
        
        security = _get_env_value(task.security, target_environment)
        if security:
            loss_record(
                f"/tasks/{task.id}/security",
                "security",
                security,
                "WDL lacks security specification support",
                "user"
            )
        
        networking = _get_env_value(task.networking, target_environment)
        if networking:
            loss_record(
                f"/tasks/{task.id}/networking",
                "networking",
                networking,
                "WDL lacks networking specification support",
                "user"
            )


def record_galaxy_losses(workflow: Workflow, target_environment: str, verbose: bool = False) -> None:
    """Record losses when converting to Galaxy format."""
    
    for task in workflow.tasks.values():
        # GPU resources not supported in Galaxy
        gpu_value = _get_env_value(task.gpu, target_environment)
        if gpu_value:
            loss_record(
                f"/tasks/{task.id}/gpu",
                "gpu",
                gpu_value,
                "Galaxy lacks GPU resource specification",
                "user"
            )
        
        gpu_mem_value = _get_env_value(task.gpu_mem_mb, target_environment)
        if gpu_mem_value:
            loss_record(
                f"/tasks/{task.id}/gpu_mem_mb",
                "gpu_mem_mb",
                gpu_mem_value,
                "Galaxy lacks GPU memory specification",
                "user"
            )
        
        # Priority not supported in Galaxy
        priority_value = _get_env_value(task.priority, target_environment)
        if priority_value:
            loss_record(
                f"/tasks/{task.id}/priority",
                "priority",
                priority_value,
                "Galaxy lacks job priority field",
                "user"
            )
        
        # Retry policies not supported
        retry_value = _get_env_value(task.retry_count, target_environment)
        if retry_value:
            loss_record(
                f"/tasks/{task.id}/retry_count",
                "retry_count",
                retry_value,
                "Galaxy lacks retry mechanism",
                "user"
            )
        
        # Advanced features not supported
        checkpointing = _get_env_value(task.checkpointing, target_environment)
        if checkpointing:
            loss_record(
                f"/tasks/{task.id}/checkpointing",
                "checkpointing",
                checkpointing,
                "Galaxy lacks checkpointing support",
                "user"
            )
        
        logging = _get_env_value(task.logging, target_environment)
        if logging:
            loss_record(
                f"/tasks/{task.id}/logging",
                "logging",
                logging,
                "Galaxy lacks structured logging support",
                "user"
            )
        
        security = _get_env_value(task.security, target_environment)
        if security:
            loss_record(
                f"/tasks/{task.id}/security",
                "security",
                security,
                "Galaxy lacks security specification support",
                "user"
            )
        
        networking = _get_env_value(task.networking, target_environment)
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