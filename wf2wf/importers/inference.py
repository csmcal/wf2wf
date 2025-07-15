"""
wf2wf.importers.inference – Intelligent inference of missing workflow information.

This module provides intelligent inference capabilities for filling in missing
workflow information based on context, patterns, and best practices.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

from wf2wf.core import (
    Task, Workflow, EnvironmentSpecificValue, CheckpointSpec, 
    LoggingSpec, SecuritySpec, NetworkingSpec
)
from wf2wf.environ import EnvironmentManager

logger = logging.getLogger(__name__)


def infer_environment_specific_values(
    workflow: Workflow, 
    source_format: str,
    execution_model: str = None
) -> None:
    """
    Infer environment-specific values for all tasks in the workflow.
    
    This function analyzes each task and infers appropriate values for different
    execution environments based on the source format and task characteristics.
    
    Args:
        workflow: Workflow to process
        source_format: Source format name
        execution_model: Detected execution model (if None, infers for all target environments)
    """
    # Get target environments for the source format
    target_environments = _get_target_environments_for_format(source_format)
    
    # If execution model is specified, focus on that environment
    if execution_model and execution_model in target_environments:
        target_environments = {execution_model}
    
    # Get the original execution environment from metadata
    original_env = None
    if workflow.metadata and workflow.metadata.original_execution_environment:
        original_env = workflow.metadata.original_execution_environment
    
    # Process each task
    for task in workflow.tasks.values():
        for environment in target_environments:
            _infer_task_environment_values(task, environment, source_format)


def _get_target_environments_for_format(source_format: str) -> Set[str]:
    """
    Get target environments for a given source format.
    
    Args:
        source_format: Source format name
        
    Returns:
        Set of target environment names
    """
    # Map source formats to target environments
    format_environment_map = {
        'snakemake': {'shared_filesystem', 'distributed_computing', 'cloud_native'},
        'cwl': {'shared_filesystem', 'cloud_native'},
        'wdl': {'shared_filesystem', 'cloud_native'},
        'nextflow': {'shared_filesystem', 'distributed_computing', 'cloud_native'},
        'dagman': {'distributed_computing'},
        'galaxy': {'shared_filesystem', 'cloud_native'}
    }
    
    return format_environment_map.get(source_format.lower(), {'shared_filesystem'})


def _infer_task_environment_values(task: Task, environment: str, source_format: str):
    """
    Infer environment-specific values for a single task.
    
    Args:
        task: Task to process
        environment: Target environment name
        source_format: Source format name
    """
    # Debug: Check the type of retry_count
    import logging
    logger = logging.getLogger(__name__)
    logger.debug(f"Task {task.id}: retry_count type is {type(task.retry_count)}, value is {task.retry_count}")
    
    # Infer resource requirements - only if not already set
    if task.cpu.get_value_for(environment) is None:
        cpu = _infer_cpu_from_command(task.command.get_value_for('shared_filesystem'), environment, source_format)
        if cpu is not None:
            task.cpu.set_for_environment(cpu, environment)
    
    if task.mem_mb.get_value_for(environment) is None:
        memory = _infer_memory_from_command(task.command.get_value_for('shared_filesystem'), environment, source_format)
        if memory is not None:
            task.mem_mb.set_for_environment(memory, environment)
    
    if task.disk_mb.get_value_for(environment) is None:
        disk = _infer_disk_from_command(task.command.get_value_for('shared_filesystem'), environment, source_format)
        if disk is not None:
            task.disk_mb.set_for_environment(disk, environment)
    
    if task.gpu.get_value_for(environment) is None:
        gpu = _infer_gpu_from_command(task.command.get_value_for('shared_filesystem'), environment, source_format)
        if gpu is not None:
            task.gpu.set_for_environment(gpu, environment)
    
    # Infer environment isolation - only if not already set
    if task.conda.get_value_for(environment) is None:
        _infer_environment_isolation(task, environment, source_format)
    
    # Infer error handling - only if not already set
    if not isinstance(task.retry_count, EnvironmentSpecificValue):
        logger.warning(f"Task {task.id}: retry_count is not EnvironmentSpecificValue, it's {type(task.retry_count)}")
        # Convert to EnvironmentSpecificValue if it's not already
        task.retry_count = EnvironmentSpecificValue(task.retry_count if task.retry_count is not None else 0)
    
    if task.retry_count.get_value_for(environment) is None:
        _infer_error_handling(task, environment, source_format)
    
    # Infer file transfer behavior - only if not already set
    if task.file_transfer_mode.get_value_for(environment) is None:
        _infer_file_transfer_behavior(task, environment, source_format)
    
    # Infer advanced features - only if not already set
    if task.logging.get_value_for(environment) is None:
        _infer_advanced_features(task, environment, source_format)


def _infer_resource_requirements(task: Task, environment: str, source_format: str):
    """
    Infer resource requirements for a task.
    
    Args:
        task: Task to process
        environment: Target environment name
        source_format: Source format name
    """
    # Infer CPU requirements
    if task.cpu.get_value_for(environment) is None:
        command = task.command.get_value_for('shared_filesystem')
        cpu = _infer_cpu_from_command(command, environment, source_format)
        if cpu is not None:
            task.cpu.set_for_environment(cpu, environment)
    
    # Infer memory requirements
    if task.mem_mb.get_value_for(environment) is None:
        command = task.command.get_value_for('shared_filesystem')
        memory = _infer_memory_from_command(command, environment, source_format)
        if memory is not None:
            task.mem_mb.set_for_environment(memory, environment)
    
    # Infer disk requirements
    if task.disk_mb.get_value_for(environment) is None:
        command = task.command.get_value_for('shared_filesystem')
        disk = _infer_disk_from_command(command, environment, source_format)
        if disk is not None:
            task.disk_mb.set_for_environment(disk, environment)
    
    # Infer GPU requirements
    if task.gpu.get_value_for(environment) is None:
        command = task.command.get_value_for('shared_filesystem')
        gpu = _infer_gpu_from_command(command, environment, source_format)
        if gpu is not None:
            task.gpu.set_for_environment(gpu, environment)


def _infer_cpu_from_command(command: Optional[str], environment: str, source_format: str) -> Optional[int]:
    """
    Infer CPU requirements from command string.
    
    Args:
        command: Command string to analyze
        environment: Target environment name
        source_format: Source format name
        
    Returns:
        Inferred CPU count or None
    """
    if not command:
        return _get_default_cpu_for_environment(environment)
    
    command_lower = command.lower()
    
    # Check for explicit CPU indicators
    cpu_patterns = [
        r'--cpus?\s+(\d+)',
        r'-c\s+(\d+)',
        r'--threads?\s+(\d+)',
        r'-t\s+(\d+)',
        r'--processes?\s+(\d+)',
        r'-p\s+(\d+)'
    ]
    
    for pattern in cpu_patterns:
        match = re.search(pattern, command_lower)
        if match:
            return int(match.group(1))
    
    # Check for tool-specific indicators
    if any(tool in command_lower for tool in ['blast', 'hmmer', 'bowtie', 'bwa']):
        return 4  # Bioinformatics tools typically benefit from multiple cores
    
    if any(tool in command_lower for tool in ['samtools', 'bcftools', 'fastqc']):
        return 2  # Moderate parallelization
    
    if any(tool in command_lower for tool in ['python', 'rscript', 'julia']):
        return 1  # Scripting languages often single-threaded
    
    # Default based on environment
    return _get_default_cpu_for_environment(environment)


def _get_default_cpu_for_environment(environment: str) -> int:
    """
    Get default CPU count for environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Default CPU count
    """
    defaults = {
        'shared_filesystem': 1,
        'distributed_computing': 2,
        'cloud_native': 1,
        'hybrid': 2,
        'edge': 1
    }
    return defaults.get(environment, 1)


def _infer_memory_from_command(command: Optional[str], environment: str, source_format: str) -> Optional[int]:
    """
    Infer memory requirements from command string.
    
    Args:
        command: Command string to analyze
        environment: Target environment name
        source_format: Source format name
        
    Returns:
        Inferred memory in MB or None
    """
    if not command:
        return _get_default_memory_for_environment(environment)
    
    command_lower = command.lower()
    
    # Check for explicit memory indicators
    memory_patterns = [
        r'--memory?\s+(\d+)',
        r'-m\s+(\d+)',
        r'--mem\s+(\d+)',
        r'--ram\s+(\d+)'
    ]
    
    for pattern in memory_patterns:
        match = re.search(pattern, command_lower)
        if match:
            value = int(match.group(1))
            # Assume MB if value is reasonable, otherwise assume GB
            if value < 1000:
                return value * 1024  # Convert GB to MB
            return value
    
    # Check for tool-specific memory requirements
    if any(tool in command_lower for tool in ['blast', 'hmmer']):
        return _get_high_memory_for_environment(environment)
    
    if any(tool in command_lower for tool in ['bowtie', 'bwa', 'samtools']):
        return _get_moderate_memory_for_environment(environment)
    
    if any(tool in command_lower for tool in ['python', 'rscript', 'julia']):
        return _get_low_memory_for_environment(environment)
    
    # Default based on environment
    return _get_default_memory_for_environment(environment)


def _get_default_memory_for_environment(environment: str) -> int:
    """
    Get default memory for environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Default memory in MB
    """
    defaults = {
        'shared_filesystem': 2048,
        'distributed_computing': 4096,
        'cloud_native': 2048,
        'hybrid': 4096,
        'edge': 1024
    }
    return defaults.get(environment, 2048)


def _get_high_memory_for_environment(environment: str) -> int:
    """
    Get high memory requirement for environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        High memory in MB
    """
    defaults = {
        'shared_filesystem': 8192,
        'distributed_computing': 16384,
        'cloud_native': 8192,
        'hybrid': 16384,
        'edge': 4096
    }
    return defaults.get(environment, 8192)


def _get_moderate_memory_for_environment(environment: str) -> int:
    """
    Get moderate memory requirement for environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Moderate memory in MB
    """
    defaults = {
        'shared_filesystem': 4096,
        'distributed_computing': 8192,
        'cloud_native': 4096,
        'hybrid': 8192,
        'edge': 2048
    }
    return defaults.get(environment, 4096)


def _get_low_memory_for_environment(environment: str) -> int:
    """
    Get low memory requirement for environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Low memory in MB
    """
    defaults = {
        'shared_filesystem': 1024,
        'distributed_computing': 2048,
        'cloud_native': 1024,
        'hybrid': 2048,
        'edge': 512
    }
    return defaults.get(environment, 1024)


def _infer_disk_from_command(command: Optional[str], environment: str, source_format: str) -> Optional[int]:
    """
    Infer disk requirements from command string.
    
    Args:
        command: Command string to analyze
        environment: Target environment name
        source_format: Source format name
        
    Returns:
        Inferred disk space in MB or None
    """
    if not command:
        return _get_default_disk_for_environment(environment)
    
    command_lower = command.lower()
    
    # Check for tool-specific disk requirements
    if any(tool in command_lower for tool in ['blast', 'hmmer', 'bowtie', 'bwa']):
        return _get_high_disk_for_environment(environment)
    
    if any(tool in command_lower for tool in ['samtools', 'bcftools', 'fastqc']):
        return _get_moderate_disk_for_environment(environment)
    
    # Default based on environment
    return _get_default_disk_for_environment(environment)


def _get_default_disk_for_environment(environment: str) -> int:
    """
    Get default disk space for environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Default disk space in MB
    """
    defaults = {
        'shared_filesystem': 2048,
        'distributed_computing': 4096,
        'cloud_native': 2048,
        'hybrid': 4096,
        'edge': 1024
    }
    return defaults.get(environment, 2048)


def _get_high_disk_for_environment(environment: str) -> int:
    """
    Get high disk requirement for environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        High disk space in MB
    """
    defaults = {
        'shared_filesystem': 8192,
        'distributed_computing': 16384,
        'cloud_native': 8192,
        'hybrid': 16384,
        'edge': 4096
    }
    return defaults.get(environment, 8192)


def _get_moderate_disk_for_environment(environment: str) -> int:
    """
    Get moderate disk requirement for environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Moderate disk space in MB
    """
    defaults = {
        'shared_filesystem': 4096,
        'distributed_computing': 8192,
        'cloud_native': 4096,
        'hybrid': 8192,
        'edge': 2048
    }
    return defaults.get(environment, 4096)


def _infer_gpu_from_command(command: Optional[str], environment: str, source_format: str) -> Optional[int]:
    """
    Infer GPU requirements from command string.
    
    Args:
        command: Command string to analyze
        environment: Target environment name
        source_format: Source format name
        
    Returns:
        Inferred GPU count or None
    """
    if not command:
        return 0  # Default to no GPU
    
    command_lower = command.lower()
    
    # Check for GPU indicators
    gpu_patterns = [
        r'--gpu\s+(\d+)',
        r'--gpus?\s+(\d+)',
        r'-g\s+(\d+)'
    ]
    
    for pattern in gpu_patterns:
        match = re.search(pattern, command_lower)
        if match:
            return int(match.group(1))
    
    # Check for GPU-accelerated tools
    gpu_tools = ['tensorflow', 'pytorch', 'keras', 'cuda', 'gpu', 'nvidia']
    if any(tool in command_lower for tool in gpu_tools):
        return 1  # Default to 1 GPU for GPU-accelerated tools
    
    return 0


def _infer_environment_isolation(task: Task, environment: str, source_format: str):
    """
    Infer environment isolation requirements.
    
    Args:
        task: Task to infer environment isolation for
        environment: Target environment name
        source_format: Source format name
    """
    # Check if container is already specified
    if task.container.get_value_for(environment) is not None:
        return
    
    # Check if conda environment is already specified
    if task.conda.get_value_for(environment) is not None:
        return
    
    # Use environment manager for inference
    env_manager = EnvironmentManager()
    command = task.command.get_value_for('shared_filesystem')
    
    if command:
        container = env_manager._infer_container_from_command(command)
        if container:
            task.container.set_for_environment(container, environment)


def _infer_error_handling(task: Task, environment: str, source_format: str):
    """
    Infer error handling requirements.
    
    Args:
        task: Task to infer error handling for
        environment: Target environment name
        source_format: Source format name
    """
    # Infer retry count
    if task.retry_count.get_value_for(environment) is None:
        retry_count = _infer_retry_count_from_environment(environment)
        task.set_retry_inferred(retry_count, environment)
    
    # Infer retry delay
    if task.retry_delay.get_value_for(environment) is None:
        retry_delay = _infer_retry_delay_from_environment(environment)
        task.retry_delay.set_for_environment(retry_delay, environment)
    
    # Infer max runtime
    if task.max_runtime.get_value_for(environment) is None:
        max_runtime = _infer_max_runtime_from_environment(environment)
        task.max_runtime.set_for_environment(max_runtime, environment)


def _infer_retry_count_from_environment(environment: str) -> int:
    """
    Infer retry count from environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Inferred retry count
    """
    defaults = {
        'shared_filesystem': 0,
        'distributed_computing': 2,
        'cloud_native': 3,
        'hybrid': 2,
        'edge': 1
    }
    return defaults.get(environment, 0)


def _infer_retry_delay_from_environment(environment: str) -> int:
    """
    Infer retry delay from environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Inferred retry delay in seconds
    """
    defaults = {
        'shared_filesystem': 0,
        'distributed_computing': 60,
        'cloud_native': 30,
        'hybrid': 60,
        'edge': 120
    }
    return defaults.get(environment, 0)


def _infer_max_runtime_from_environment(environment: str) -> Optional[int]:
    """
    Infer max runtime from environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Inferred max runtime in seconds or None
    """
    defaults = {
        'shared_filesystem': None,
        'distributed_computing': 3600,  # 1 hour
        'cloud_native': 7200,  # 2 hours
        'hybrid': 3600,  # 1 hour
        'edge': 1800  # 30 minutes
    }
    return defaults.get(environment, None)


def _infer_file_transfer_behavior(task: Task, environment: str, source_format: str):
    """
    Infer file transfer behavior.
    
    Args:
        task: Task to infer file transfer behavior for
        environment: Target environment name
        source_format: Source format name
    """
    # Infer file transfer mode
    if task.file_transfer_mode.get_value_for(environment) is None:
        transfer_mode = _infer_transfer_mode_from_environment(environment)
        task.file_transfer_mode.set_for_environment(transfer_mode, environment)
    
    # Infer staging requirements
    if task.staging_required.get_value_for(environment) is None:
        staging_required = _infer_staging_from_environment(environment)
        task.staging_required.set_for_environment(staging_required, environment)
    
    # Infer cleanup behavior
    if task.cleanup_after.get_value_for(environment) is None:
        cleanup_after = _infer_cleanup_from_environment(environment)
        task.cleanup_after.set_for_environment(cleanup_after, environment)


def _infer_transfer_mode_from_environment(environment: str) -> str:
    """
    Infer transfer mode from environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Inferred transfer mode
    """
    defaults = {
        'shared_filesystem': 'never',
        'distributed_computing': 'explicit',
        'cloud_native': 'cloud_storage',
        'hybrid': 'adaptive',
        'edge': 'minimal'
    }
    return defaults.get(environment, 'auto')


def _infer_staging_from_environment(environment: str) -> bool:
    """
    Infer staging requirements from environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Inferred staging requirement
    """
    defaults = {
        'shared_filesystem': False,
        'distributed_computing': True,
        'cloud_native': True,
        'hybrid': True,
        'edge': False
    }
    return defaults.get(environment, False)


def _infer_cleanup_from_environment(environment: str) -> bool:
    """
    Infer cleanup behavior from environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Inferred cleanup behavior
    """
    defaults = {
        'shared_filesystem': False,
        'distributed_computing': True,
        'cloud_native': True,
        'hybrid': True,
        'edge': True
    }
    return defaults.get(environment, False)


def _infer_advanced_features(task: Task, environment: str, source_format: str):
    """
    Infer advanced features for a task.
    
    Args:
        task: Task to infer advanced features for
        environment: Target environment name
        source_format: Source format name
    """
    # Infer checkpointing
    if task.checkpointing.get_value_for(environment) is None:
        checkpointing = _infer_checkpointing_from_environment(environment)
        if checkpointing:
            task.checkpointing.set_for_environment(checkpointing, environment)
    
    # Infer logging
    if task.logging.get_value_for(environment) is None:
        logging_spec = _infer_logging_from_environment(environment)
        if logging_spec:
            task.logging.set_for_environment(logging_spec, environment)
    
    # Infer security
    if task.security.get_value_for(environment) is None:
        security_spec = _infer_security_from_environment(environment)
        if security_spec:
            task.security.set_for_environment(security_spec, environment)
    
    # Infer networking
    if task.networking.get_value_for(environment) is None:
        networking_spec = _infer_networking_from_environment(environment)
        if networking_spec:
            task.networking.set_for_environment(networking_spec, environment)


def _infer_checkpointing_from_environment(environment: str) -> Optional[CheckpointSpec]:
    """
    Infer checkpointing from environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Inferred checkpointing specification or None
    """
    if environment in ['distributed_computing', 'hybrid']:
        return CheckpointSpec(
            strategy="filesystem",
            interval=300,  # 5 minutes
            storage_location="/tmp/checkpoints",
            enabled=True,
            notes="Auto-inferred checkpointing for distributed environment"
        )
    return None


def _infer_logging_from_environment(environment: str) -> Optional[LoggingSpec]:
    """
    Infer logging from environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Inferred logging specification or None
    """
    if environment in ['distributed_computing', 'cloud_native', 'hybrid']:
        return LoggingSpec(
            log_level="INFO",
            log_format="json",
            log_destination="/tmp/logs",
            aggregation="syslog",
            notes="Auto-inferred logging for distributed/cloud environment"
        )
    return None


def _infer_security_from_environment(environment: str) -> Optional[SecuritySpec]:
    """
    Infer security from environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Inferred security specification or None
    """
    if environment in ['cloud_native', 'hybrid']:
        return SecuritySpec(
            encryption="AES256",
            access_policies="least-privilege",
            secrets={},
            authentication="oauth",
            notes="Auto-inferred security for cloud environment"
        )
    return None


def _infer_networking_from_environment(environment: str) -> Optional[NetworkingSpec]:
    """
    Infer networking from environment.
    
    Args:
        environment: Target environment name
        
    Returns:
        Inferred networking specification or None
    """
    if environment in ['cloud_native', 'hybrid']:
        return NetworkingSpec(
            network_mode="bridge",
            allowed_ports=[80, 443],
            egress_rules=["0.0.0.0/0"],
            ingress_rules=["10.0.0.0/8"],
            notes="Auto-inferred networking for cloud environment"
        )
    return None


def infer_execution_model(workflow: Workflow, source_format: str) -> str:
    """
    Infer execution model from workflow characteristics.
    
    Args:
        workflow: Workflow to analyze
        source_format: Source format name
        
    Returns:
        Inferred execution model
    """
    # Analyze workflow characteristics
    total_tasks = len(workflow.tasks)
    has_parallel_tasks = len(workflow.edges) < total_tasks * (total_tasks - 1) / 2
    
    # Check for distributed computing indicators
    has_gpu_tasks = any(task.gpu.get_value_for('shared_filesystem') or 0 > 0 for task in workflow.tasks.values())
    has_high_memory_tasks = any(task.mem_mb.get_value_for('shared_filesystem') or 0 > 8192 for task in workflow.tasks.values())
    
    # Determine execution model based on workflow characteristics
    if has_gpu_tasks or has_high_memory_tasks:
        return "parallel"
    elif has_parallel_tasks and total_tasks > 5:
        return "parallel"
    elif source_format in ['dagman', 'nextflow']:
        return "parallel"
    elif source_format in ['cwl', 'wdl']:
        return "pipeline"
    elif total_tasks == 1:
        return "sequential"
    else:
        return "pipeline" 


def infer_condor_attributes(workflow: Workflow, target_environment: str = "distributed_computing") -> None:
    """Infer Condor-specific attributes from Snakemake metadata and task properties.
    
    This function analyzes tasks and their metadata to generate appropriate
    Condor-specific attributes for distributed computing environments.
    """
    for task in workflow.tasks.values():
        # Skip if no metadata or no Snakemake-specific data
        if not task.metadata or "snakemake_rule" not in task.metadata.format_specific:
            continue
            
        rule_data = task.metadata.format_specific["snakemake_rule"]
        
        # Infer Condor requirements based on resources and environment
        requirements = []
        
        # GPU requirements
        gpu_value = task.gpu.get_value_for("shared_filesystem")
        if gpu_value and gpu_value > 0:
            requirements.append("(HasGPU == True)")
            # Add GPU memory requirement if specified
            gpu_mem = task.gpu_mem_mb.get_value_for("shared_filesystem")
            if gpu_mem and gpu_mem > 0:
                requirements.append(f"(GPUMemory >= {gpu_mem})")
        
        # Memory requirements
        mem_value = task.mem_mb.get_value_for("shared_filesystem")
        if mem_value and mem_value > 0:
            requirements.append(f"(Memory >= {mem_value})")
        
        # CPU requirements
        cpu_value = task.cpu.get_value_for("shared_filesystem")
        if cpu_value and cpu_value > 1:
            requirements.append(f"(Cpus >= {cpu_value})")
        
        # Disk requirements
        disk_value = task.disk_mb.get_value_for("shared_filesystem")
        if disk_value and disk_value > 0:
            requirements.append(f"(Disk >= {disk_value})")
        
        # Add requirements to task if any were found
        if requirements:
            requirements_str = " && ".join(requirements)
            task.extra["requirements"] = EnvironmentSpecificValue(requirements_str, [target_environment])
        
        # Infer Condor rank based on priority
        priority_value = task.priority.get_value_for("shared_filesystem")
        if priority_value and priority_value > 0:
            task.extra["rank"] = EnvironmentSpecificValue(f"({priority_value} * 1000)", [target_environment])
        
        # Infer GPU lab preference based on GPU usage
        if gpu_value and gpu_value > 0:
            task.extra["+WantGPULab"] = EnvironmentSpecificValue("true", [target_environment])
        
        # Infer universe based on container usage
        container_value = task.container.get_value_for("shared_filesystem")
        if container_value:
            task.extra["universe"] = EnvironmentSpecificValue("docker", [target_environment])
            task.extra["docker_image"] = EnvironmentSpecificValue(container_value, [target_environment])
        
        # Infer job class based on resource usage
        if gpu_value and gpu_value > 0:
            task.extra["+JobClass"] = EnvironmentSpecificValue("gpu", [target_environment])
        elif mem_value and mem_value > 8192:  # 8GB
            task.extra["+JobClass"] = EnvironmentSpecificValue("highmem", [target_environment])
        elif cpu_value and cpu_value > 4:
            task.extra["+JobClass"] = EnvironmentSpecificValue("multicore", [target_environment])
        else:
            task.extra["+JobClass"] = EnvironmentSpecificValue("standard", [target_environment]) 