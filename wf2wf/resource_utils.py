"""
wf2wf.resource_utils – Resource Requirements & Scheduling Utilities

This module provides utilities for resource inference, normalization, and validation
when converting between shared filesystem and distributed computing workflows.

Features:
- Resource inference for workflows with missing specifications
- Unit normalization across different formats
- Resource validation and best practices checking
- Default resource profiles for different compute environments
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from wf2wf.core import Task, EnvironmentSpecificValue


@dataclass
class ResourceProfile:
    """Resource profile for different compute environments."""
    name: str
    description: str
    environment: str
    priority: str
    cpu: int
    mem_mb: int
    disk_mb: int
    gpu: Optional[int] = None
    gpu_mem_mb: Optional[int] = None
    time_s: Optional[int] = None


# Predefined resource profiles for different environments
DEFAULT_PROFILES = {
    "shared": ResourceProfile(
        name="shared",
        description="Shared filesystem environment (minimal resources)",
        environment="shared",
        priority="low",
        cpu=1,
        mem_mb=512,
        disk_mb=1024,
    ),
    "cluster": ResourceProfile(
        name="cluster",
        description="HTCondor/SGE cluster environment",
        environment="cluster",
        priority="normal",
        cpu=1,
        mem_mb=2048,  # 2GB
        disk_mb=4096,  # 4GB
    ),
    "cloud": ResourceProfile(
        name="cloud",
        description="Cloud computing environment (AWS, GCP, Azure)",
        environment="cloud",
        priority="normal",
        cpu=2,
        mem_mb=4096,  # 4GB
        disk_mb=8192,  # 8GB
    ),
    "hpc": ResourceProfile(
        name="hpc",
        description="High Performance Computing environment",
        environment="hpc",
        priority="normal",
        cpu=4,
        mem_mb=8192,  # 8GB
        disk_mb=16384,  # 16GB
    ),
    "gpu": ResourceProfile(
        name="gpu",
        description="GPU-enabled environment",
        environment="gpu",
        priority="high",
        cpu=4,
        mem_mb=16384,  # 16GB
        disk_mb=32768,  # 32GB
        gpu=1,
        gpu_mem_mb=8192,  # 8GB
    ),
    "memory_intensive": ResourceProfile(
        name="memory_intensive",
        description="Memory-intensive computing environment",
        environment="hpc",
        priority="high",
        cpu=8,
        mem_mb=65536,  # 64GB
        disk_mb=16384,  # 16GB
    ),
    "io_intensive": ResourceProfile(
        name="io_intensive",
        description="I/O-intensive computing environment",
        environment="hpc",
        priority="normal",
        cpu=4,
        mem_mb=8192,  # 8GB
        disk_mb=131072,  # 128GB
    ),
}


def normalize_memory(value: Union[str, int, float]) -> int:
    """Normalize memory value to MB."""
    if isinstance(value, (int, float)):
        return int(value)
    
    if isinstance(value, str):
        value = value.strip().upper()
        
        # Handle common memory formats
        patterns = [
            (r'(\d+(?:\.\d+)?)\s*KB', lambda m: int(float(m.group(1)) / 1024)),
            (r'(\d+(?:\.\d+)?)\s*MB', lambda m: int(float(m.group(1)))),
            (r'(\d+(?:\.\d+)?)\s*GB', lambda m: int(float(m.group(1)) * 1024)),
            (r'(\d+(?:\.\d+)?)\s*TB', lambda m: int(float(m.group(1)) * 1024 * 1024)),
            (r'(\d+(?:\.\d+)?)\s*G', lambda m: int(float(m.group(1)) * 1024)),
            (r'(\d+(?:\.\d+)?)\s*M', lambda m: int(float(m.group(1)))),
            (r'(\d+(?:\.\d+)?)\s*K', lambda m: int(float(m.group(1)) / 1024)),
        ]
        
        for pattern, converter in patterns:
            match = re.match(pattern, value)
            if match:
                return converter(match)
        
        # Try to parse as plain number (assume MB)
        try:
            return int(float(value))
        except ValueError:
            raise ValueError(f"Could not parse memory value: {value}")
    
    raise ValueError(f"Unsupported memory value type: {type(value)}")


def normalize_time(value: Union[str, int, float]) -> int:
    """Normalize time value to seconds."""
    if isinstance(value, (int, float)):
        return int(value)
    
    if isinstance(value, str):
        value = value.strip().lower()
        
        # Handle common time formats
        patterns = [
            (r'(\d+(?:\.\d+)?)\s*s(?:ec(?:onds?)?)?', lambda m: int(float(m.group(1)))),
            (r'(\d+(?:\.\d+)?)\s*m(?:in(?:utes?)?)?', lambda m: int(float(m.group(1)) * 60)),
            (r'(\d+(?:\.\d+)?)\s*h(?:ours?)?', lambda m: int(float(m.group(1)) * 3600)),
            (r'(\d+(?:\.\d+)?)\s*d(?:ays?)?', lambda m: int(float(m.group(1)) * 86400)),
        ]
        
        for pattern, converter in patterns:
            match = re.match(pattern, value)
            if match:
                return converter(match)
        
        # Try to parse as plain number (assume seconds)
        try:
            return int(float(value))
        except ValueError:
            raise ValueError(f"Could not parse time value: {value}")
    
    raise ValueError(f"Unsupported time value type: {type(value)}")


def infer_resources_from_command(command: Optional[EnvironmentSpecificValue], script: Optional[EnvironmentSpecificValue] = None, environment: str = "shared_filesystem") -> Dict[str, Any]:
    """Infer resource requirements from command or script content for a specific environment.
    Args:
        command: EnvironmentSpecificValue for the command
        script: EnvironmentSpecificValue for the script (optional)
        environment: The environment to extract the value for (default: 'shared_filesystem')
    Returns:
        Dict of inferred resources
    """
    resources = {}
    
    command_str = command.get_value_for(environment) if command else ""
    script_str = script.get_value_for(environment) if script else ""
    
    # Convert None to empty string to avoid concatenation errors
    command_str = command_str or ""
    script_str = script_str or ""
    
    if not command_str and not script_str:
        resources["cpu"] = 1
        resources["threads"] = 1
        return resources
    
    content = command_str + " " + script_str
    content = content.lower()
    
    # Infer CPU requirements
    if any(tool in content for tool in ["bwa", "bowtie", "star", "hisat2", "salmon", "kallisto"]):
        resources["cpu"] = 4
    elif any(tool in content for tool in ["samtools", "bcftools", "bedtools", "awk", "sed", "grep"]):
        resources["cpu"] = 1
    elif any(tool in content for tool in ["gatk", "freebayes", "mutect", "varscan"]):
        resources["cpu"] = 2
    elif any(tool in content for tool in ["fastqc", "multiqc", "qualimap"]):
        resources["cpu"] = 1
    elif any(tool in content for tool in ["rscript", "python", "perl", "bash"]):
        resources["cpu"] = 1
    else:
        resources["cpu"] = 1
    
    # Infer memory requirements
    if any(tool in content for tool in ["bwa", "bowtie", "star", "hisat2"]):
        resources["mem_mb"] = 4096  # 4GB for alignment tools
    elif any(tool in content for tool in ["gatk", "freebayes", "mutect", "varscan"]):
        resources["mem_mb"] = 8192  # 8GB for variant calling
    elif any(tool in content for tool in ["samtools", "bcftools", "bedtools"]):
        resources["mem_mb"] = 2048  # 2GB for sequence manipulation
    elif any(tool in content for tool in ["fastqc", "multiqc", "qualimap"]):
        resources["mem_mb"] = 1024  # 1GB for quality control
    elif any(tool in content for tool in ["rscript", "python", "perl"]):
        resources["mem_mb"] = 1024  # 1GB for scripting
    else:
        resources["mem_mb"] = 1024  # Default 1GB
    
    # Infer disk requirements
    if any(tool in content for tool in ["bwa", "bowtie", "star", "hisat2", "samtools", "bcftools"]):
        resources["disk_mb"] = 8192  # 8GB for sequence data
    elif any(tool in content for tool in ["gatk", "freebayes", "mutect", "varscan"]):
        resources["disk_mb"] = 4096  # 4GB for variant data
    else:
        resources["disk_mb"] = 2048  # Default 2GB
    
    # Infer GPU requirements
    if any(tool in content for tool in ["cuda", "gpu", "tensorflow", "pytorch", "nvidia"]):
        resources["gpu"] = 1
        resources["gpu_mem_mb"] = 4096  # 4GB GPU memory
    
    # Infer time requirements
    if any(tool in content for tool in ["bwa", "bowtie", "star", "hisat2"]):
        resources["time_s"] = 7200  # 2 hours for alignment
    elif any(tool in content for tool in ["gatk", "freebayes", "mutect", "varscan"]):
        resources["time_s"] = 3600  # 1 hour for variant calling
    else:
        resources["time_s"] = 1800  # Default 30 minutes
    
    return resources


def apply_resource_profile(task: Task, profile: ResourceProfile) -> Task:
    """Apply a resource profile to a task."""
    def fill(field_name: str, profile_value: Optional[int]):
        if profile_value is not None:
            current_value = getattr(task, field_name, None)
            if current_value is None or not hasattr(current_value, 'get_value_with_default'):
                # Create new EnvironmentSpecificValue if needed
                env_value = EnvironmentSpecificValue(profile_value, [profile.environment])
                setattr(task, field_name, env_value)
            else:
                # Add to existing EnvironmentSpecificValue
                current_value.set_for_environment(profile_value, profile.environment)
    
    fill("cpu", profile.cpu)
    fill("mem_mb", profile.mem_mb)
    fill("disk_mb", profile.disk_mb)
    fill("gpu", profile.gpu)
    fill("gpu_mem_mb", profile.gpu_mem_mb)
    fill("time_s", profile.time_s)
    
    return task


def validate_resources(task: Task, target_environment: str = "cluster") -> List[str]:
    """Validate resource specifications for a task."""
    issues = []
    
    # Get resource values for the target environment
    cpu = task.cpu.get_value_with_default(target_environment) if task.cpu else None
    mem_mb = task.mem_mb.get_value_with_default(target_environment) if task.mem_mb else None
    disk_mb = task.disk_mb.get_value_with_default(target_environment) if task.disk_mb else None
    gpu = task.gpu.get_value_with_default(target_environment) if task.gpu else None
    gpu_mem_mb = task.gpu_mem_mb.get_value_with_default(target_environment) if task.gpu_mem_mb else None
    
    # Check for missing CPU
    if cpu is None or cpu <= 0:
        issues.append("CPU specification is missing or invalid")
    
    # Check for missing memory
    if mem_mb is None or mem_mb <= 0:
        issues.append("Memory specification is missing or invalid")
    
    # Check for excessive CPU
    if cpu and cpu > 64:
        issues.append(f"CPU requirement ({cpu}) is excessive for {target_environment}")
    
    # Check for excessive memory
    if mem_mb and mem_mb > 131072:  # 128GB
        issues.append(f"Memory requirement ({mem_mb}MB) is excessive for {target_environment}")
    
    # Check for excessive disk
    if disk_mb and disk_mb > 1048576:  # 1TB
        issues.append(f"Disk requirement ({disk_mb}MB) is excessive for {target_environment}")
    
    # Check GPU requirements
    if gpu and gpu > 8:
        issues.append(f"GPU requirement ({gpu}) is excessive")
    
    if gpu_mem_mb and gpu_mem_mb > 32768:  # 32GB
        issues.append(f"GPU memory requirement ({gpu_mem_mb}MB) is excessive")
    
    # Environment-specific checks
    if target_environment in ["shared", "shared_filesystem"]:
        if cpu and cpu > 4:
            issues.append("CPU requirement too high for shared filesystem environment")
        if mem_mb and mem_mb > 8192:  # 8GB
            issues.append("Memory requirement too high for shared filesystem environment")
    
    elif target_environment == "cluster":
        if cpu and cpu > 32:
            issues.append("CPU requirement too high for cluster environment")
        if mem_mb and mem_mb > 65536:  # 64GB
            issues.append("Memory requirement too high for cluster environment")
    
    return issues


def suggest_resource_profile(task: Task, target_environment: str = "cluster") -> str:
    """Suggest a resource profile based on task requirements."""
    # Get current resource values
    cpu = task.cpu.get_value_with_default(target_environment) if task.cpu else 1
    mem_mb = task.mem_mb.get_value_with_default(target_environment) if task.mem_mb else 1024
    gpu = task.gpu.get_value_with_default(target_environment) if task.gpu else 0
    
    # Suggest based on requirements
    if gpu > 0:
        return "gpu"
    elif mem_mb > 32768:  # 32GB
        return "memory_intensive"
    elif task.disk_mb and task.disk_mb.get_value_with_default(target_environment) > 65536:  # 64GB
        return "io_intensive"
    elif cpu > 8:
        return "hpc"
    elif target_environment == "cloud":
        return "cloud"
    elif target_environment == "cluster":
        return "cluster"
    else:
        return "shared"


def load_custom_profile(profile_path: Union[str, Path]) -> ResourceProfile:
    """Load a custom resource profile from file."""
    import json
    
    profile_path = Path(profile_path)
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile file not found: {profile_path}")
    
    with open(profile_path, 'r') as f:
        data = json.load(f)
    
        return ResourceProfile(
        name=data.get("name", "custom"),
        description=data.get("description", "Custom resource profile"),
        environment=data.get("environment", "shared"),
        priority=data.get("priority", "normal"),
        cpu=data.get("cpu", 1),
        mem_mb=data.get("mem_mb", 1024),
        disk_mb=data.get("disk_mb", 2048),
        gpu=data.get("gpu"),
        gpu_mem_mb=data.get("gpu_mem_mb"),
        time_s=data.get("time_s")
        )


def save_custom_profile(profile: ResourceProfile, profile_path: Union[str, Path]) -> None:
    """Save a custom resource profile to file."""
    import json
    
    profile_path = Path(profile_path)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {
        "name": profile.name,
        "description": profile.description,
        "environment": profile.environment,
        "priority": profile.priority,
        "cpu": profile.cpu,
        "mem_mb": profile.mem_mb,
        "disk_mb": profile.disk_mb,
    }
    
    if profile.gpu is not None:
        data["gpu"] = profile.gpu
    if profile.gpu_mem_mb is not None:
        data["gpu_mem_mb"] = profile.gpu_mem_mb
    if profile.time_s is not None:
        data["time_s"] = profile.time_s
    
    with open(profile_path, 'w') as f:
        json.dump(data, f, indent=2)


def get_available_profiles() -> Dict[str, ResourceProfile]:
    """Get all available resource profiles."""
    return DEFAULT_PROFILES.copy()


def create_profile_from_existing(task: Task, name: str, description: str, environment: str = "shared_filesystem") -> ResourceProfile:
    """Create a resource profile from an existing task for a specific environment."""
    # Get values from the task for the specified environment
    cpu = task.cpu.get_value_with_default(environment) if task.cpu else None
    mem_mb = task.mem_mb.get_value_with_default(environment) if task.mem_mb else None
    disk_mb = task.disk_mb.get_value_with_default(environment) if task.disk_mb else None
    gpu = task.gpu.get_value_with_default(environment) if task.gpu else None
    gpu_mem_mb = task.gpu_mem_mb.get_value_with_default(environment) if task.gpu_mem_mb else None
    time_s = task.time_s.get_value_with_default(environment) if task.time_s else None
    
    return ResourceProfile(
        name=name,
        description=description,
        environment=environment,
        priority="normal",
        cpu=cpu or 1,
        mem_mb=mem_mb or 1024,
        disk_mb=disk_mb or 2048,
        gpu=gpu,
        gpu_mem_mb=gpu_mem_mb,
        time_s=time_s
    ) 