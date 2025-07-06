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

from wf2wf.core import ResourceSpec, ResourceProfile, ResourceField


# Predefined resource profiles for different environments
DEFAULT_PROFILES = {
    "shared": ResourceProfile(
        name="shared",
        description="Shared filesystem environment (minimal resources)",
        environment="shared",
        priority="low",
        resources=ResourceSpec(
            cpu=ResourceField(value=1, source_method="default"),
            mem_mb=ResourceField(value=512, source_method="default"),
            disk_mb=ResourceField(value=1024, source_method="default"),
        )
    ),
    "cluster": ResourceProfile(
        name="cluster",
        description="HTCondor/SGE cluster environment",
        environment="cluster",
        priority="normal",
        resources=ResourceSpec(
            cpu=ResourceField(value=1, source_method="default"),
            mem_mb=ResourceField(value=2048, source_method="default"),  # 2GB
            disk_mb=ResourceField(value=4096, source_method="default"),  # 4GB
        )
    ),
    "cloud": ResourceProfile(
        name="cloud",
        description="Cloud computing environment (AWS, GCP, Azure)",
        environment="cloud",
        priority="normal",
        resources=ResourceSpec(
            cpu=ResourceField(value=2, source_method="default"),
            mem_mb=ResourceField(value=4096, source_method="default"),  # 4GB
            disk_mb=ResourceField(value=8192, source_method="default"),  # 8GB
        )
    ),
    "hpc": ResourceProfile(
        name="hpc",
        description="High Performance Computing environment",
        environment="hpc",
        priority="normal",
        resources=ResourceSpec(
            cpu=ResourceField(value=4, source_method="default"),
            mem_mb=ResourceField(value=8192, source_method="default"),  # 8GB
            disk_mb=ResourceField(value=16384, source_method="default"),  # 16GB
        )
    ),
    "gpu": ResourceProfile(
        name="gpu",
        description="GPU-enabled environment",
        environment="gpu",
        priority="high",
        resources=ResourceSpec(
            cpu=ResourceField(value=4, source_method="default"),
            mem_mb=ResourceField(value=16384, source_method="default"),  # 16GB
            disk_mb=ResourceField(value=32768, source_method="default"),  # 32GB
            gpu=ResourceField(value=1, source_method="default"),
            gpu_mem_mb=ResourceField(value=8192, source_method="default"),  # 8GB
        )
    ),
    "memory_intensive": ResourceProfile(
        name="memory_intensive",
        description="Memory-intensive computing environment",
        environment="hpc",
        priority="high",
        resources=ResourceSpec(
            cpu=ResourceField(value=8, source_method="default"),
            mem_mb=ResourceField(value=65536, source_method="default"),  # 64GB
            disk_mb=ResourceField(value=16384, source_method="default"),  # 16GB
        )
    ),
    "io_intensive": ResourceProfile(
        name="io_intensive",
        description="I/O-intensive computing environment",
        environment="hpc",
        priority="normal",
        resources=ResourceSpec(
            cpu=ResourceField(value=4, source_method="default"),
            mem_mb=ResourceField(value=8192, source_method="default"),  # 8GB
            disk_mb=ResourceField(value=131072, source_method="default"),  # 128GB
        )
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


def infer_resources_from_command(command: str, script: Optional[str] = None) -> ResourceSpec:
    """Infer resource requirements from command or script content."""
    resources = ResourceSpec()
    # All inferred fields get source_method="inferred"
    if not command and not script:
        resources.cpu.value = 1
        resources.cpu.source_method = "inferred"
        resources.threads.value = 1
        resources.threads.source_method = "inferred"
        return resources
    content = (command or "") + " " + (script or "")
    content = content.lower()
    # Infer CPU requirements
    if any(tool in content for tool in ["bwa", "bowtie", "star", "hisat2", "salmon", "kallisto"]):
        resources.cpu.value = 4
        resources.cpu.source_method = "inferred"
    elif any(tool in content for tool in ["samtools", "bcftools", "bedtools", "awk", "sed", "grep"]):
        resources.cpu.value = 1
        resources.cpu.source_method = "inferred"
    elif any(tool in content for tool in ["gatk", "freebayes", "mutect", "varscan"]):
        resources.cpu.value = 2
        resources.cpu.source_method = "inferred"
    elif any(tool in content for tool in ["fastqc", "multiqc", "qualimap"]):
        resources.cpu.value = 1
        resources.cpu.source_method = "inferred"
    elif any(tool in content for tool in ["rscript", "python", "perl", "bash"]):
        resources.cpu.value = 1
        resources.cpu.source_method = "inferred"
    else:
        resources.cpu.value = 1
        resources.cpu.source_method = "inferred"
    # Infer memory requirements
    if any(tool in content for tool in ["gatk", "freebayes", "mutect", "varscan"]):
        resources.mem_mb.value = 8192
        resources.mem_mb.source_method = "inferred"
    elif any(tool in content for tool in ["star", "hisat2", "salmon", "kallisto"]):
        resources.mem_mb.value = 4096
        resources.mem_mb.source_method = "inferred"
    elif any(tool in content for tool in ["bwa", "bowtie", "samtools", "bcftools"]):
        resources.mem_mb.value = 2048
        resources.mem_mb.source_method = "inferred"
    elif any(tool in content for tool in ["fastqc", "multiqc", "qualimap"]):
        resources.mem_mb.value = 1024
        resources.mem_mb.source_method = "inferred"
    # Infer disk requirements
    if any(ext in content for ext in [".bam", ".sam", ".vcf", ".fastq", ".fq"]):
        resources.disk_mb.value = 4096
        resources.disk_mb.source_method = "inferred"
    elif any(ext in content for ext in [".txt", ".csv", ".tsv", ".json", ".yaml"]):
        resources.disk_mb.value = 1024
        resources.disk_mb.source_method = "inferred"
    # Infer GPU requirements
    if any(tool in content for tool in ["gpu", "cuda", "tensorflow", "pytorch", "nvidia"]):
        resources.gpu.value = 1
        resources.gpu.source_method = "inferred"
        resources.gpu_mem_mb.value = 4096
        resources.gpu_mem_mb.source_method = "inferred"
    # Set default threads if not specified
    if resources.threads.value is None:
        resources.threads.value = 1
        resources.threads.source_method = "inferred"
    return resources


def apply_resource_profile(resources, profile):
    """Apply a resource profile to existing resources, filling in missing values."""
    if isinstance(profile, str):
        if profile not in DEFAULT_PROFILES:
            raise ValueError(f"Unknown resource profile: {profile}. Available: {list(DEFAULT_PROFILES.keys())}")
        profile = DEFAULT_PROFILES[profile]
    # For each field, fill missing value and set source_method
    def fill(field, profile_field):
        if field.value is None and profile_field.value is not None:
            field.value = profile_field.value
            field.source_method = "template"
        return field
    result = ResourceSpec(
        cpu=fill(resources.cpu, profile.resources.cpu),
        mem_mb=fill(resources.mem_mb, profile.resources.mem_mb),
        disk_mb=fill(resources.disk_mb, profile.resources.disk_mb),
        gpu=fill(resources.gpu, profile.resources.gpu),
        gpu_mem_mb=fill(resources.gpu_mem_mb, profile.resources.gpu_mem_mb),
        time_s=fill(resources.time_s, profile.resources.time_s),
        threads=fill(resources.threads, profile.resources.threads),
        extra=getattr(resources, 'extra', {}).copy() if hasattr(resources, 'extra') else {}
    )
    return result


def validate_resources(resources: ResourceSpec, target_environment: str = "cluster") -> List[str]:
    """Validate resource specifications and return warnings/errors."""
    issues = []
    
    # Check for missing critical resources
    if resources.cpu.value is None:
        issues.append("Missing CPU specification")
    elif resources.cpu.value < 1:
        issues.append("CPU must be at least 1")
    elif resources.cpu.value > 64:
        issues.append("CPU count seems unusually high (>64)")
    
    if resources.mem_mb.value is None:
        issues.append("Missing memory specification")
    elif resources.mem_mb.value < 128:
        issues.append("Memory specification seems too low (<128MB)")
    elif resources.mem_mb.value > 1024 * 1024:  # 1TB
        issues.append("Memory specification seems unusually high (>1TB)")
    
    if resources.disk_mb.value is None:
        issues.append("Missing disk specification")
    elif resources.disk_mb.value < 256:
        issues.append("Disk specification seems too low (<256MB)")
    elif resources.disk_mb.value > 1024 * 1024 * 100:  # 100TB
        issues.append("Disk specification seems unusually high (>100TB)")
    
    # Note: Time is not typically a resource specification in workflow engines
    # It's usually handled by the scheduler or execution environment
    # So we don't validate time_s here
    
    # Environment-specific validations
    if target_environment == "cluster":
        if resources.cpu.value and resources.cpu.value > 32:
            issues.append("High CPU count may exceed cluster limits")
        if resources.mem_mb.value and resources.mem_mb.value > 1024 * 64:  # 64GB
            issues.append("High memory requirement may exceed cluster limits")
    
    elif target_environment == "cloud":
        if resources.gpu.value and resources.gpu.value > 8:
            issues.append("High GPU count may exceed cloud instance limits")
    
    elif target_environment == "shared":
        if resources.cpu.value and resources.cpu.value > 8:
            issues.append("High CPU count may impact shared system performance")
        if resources.mem_mb.value and resources.mem_mb.value > 1024 * 16:  # 16GB
            issues.append("High memory requirement may impact shared system performance")
    
    return issues


def suggest_resource_profile(resources: ResourceSpec, target_environment: str = "cluster") -> str:
    """Suggest an appropriate resource profile based on current resources and target environment."""
    if resources.gpu.value and resources.gpu.value > 0:
        return "gpu"
    
    if resources.mem_mb.value and resources.mem_mb.value > 16384:  # 16GB
        return "memory_intensive"
    
    if resources.disk_mb.value and resources.disk_mb.value > 32768:  # 32GB
        return "io_intensive"
    
    # Default based on environment
    return target_environment


def load_custom_profile(profile_path: Union[str, Path]) -> ResourceProfile:
    """Load a custom resource profile from a YAML file."""
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required to load custom resource profiles")
    
    profile_path = Path(profile_path)
    if not profile_path.exists():
        raise FileNotFoundError(f"Resource profile not found: {profile_path}")
    
    with open(profile_path, 'r') as f:
        data = yaml.safe_load(f)
    
    # Handle both old ResourceSpec format and new ResourceProfile format
    if "resources" in data:
        # New format with metadata
        resources_data = data.pop("resources", {})
        resources = ResourceSpec(**resources_data)
        return ResourceProfile(resources=resources, **data)
    else:
        # Old format - assume it's just resource data
        resources = ResourceSpec(**data)
        return ResourceProfile(
            name="custom",
            description="Custom profile",
            resources=resources
        )


def save_custom_profile(profile: ResourceProfile, profile_path: Union[str, Path]) -> None:
    """Save a custom resource profile to a YAML file."""
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required to save custom resource profiles")
    
    profile_path = Path(profile_path)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to dict for YAML serialization
    data = {
        "name": profile.name,
        "description": profile.description,
        "environment": profile.environment,
        "priority": profile.priority,
        "resources": {
            "cpu": profile.resources.cpu,
            "mem_mb": profile.resources.mem_mb,
            "disk_mb": profile.resources.disk_mb,
            "gpu": profile.resources.gpu,
            "gpu_mem_mb": profile.resources.gpu_mem_mb,
            "time_s": profile.resources.time_s,
            "threads": profile.resources.threads,
            "extra": profile.resources.extra
        }
    }
    
    with open(profile_path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, indent=2)


def get_available_profiles() -> Dict[str, ResourceProfile]:
    """Get all available resource profiles."""
    return DEFAULT_PROFILES.copy()


def create_profile_from_existing(resources, name, description):
    """Create a new resource profile from existing ResourceSpec."""
    return ResourceProfile(
        name=name,
        description=description,
        resources=ResourceSpec(
            cpu=resources.cpu,
            mem_mb=resources.mem_mb,
            disk_mb=resources.disk_mb,
            gpu=resources.gpu,
            gpu_mem_mb=resources.gpu_mem_mb,
            time_s=resources.time_s,
            threads=resources.threads
        )
    ) 