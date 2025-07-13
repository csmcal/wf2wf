"""
Utility functions for environment adaptation.
"""

from typing import Any, Dict, List, Optional, Union
from wf2wf.core import Workflow, Task, EnvironmentSpecificValue


def copy_environment_value(source_value: EnvironmentSpecificValue, target_env: str) -> EnvironmentSpecificValue:
    """
    Copy an environment-specific value to a new environment.
    
    Args:
        source_value: Source environment-specific value
        target_env: Target environment name
        
    Returns:
        New environment-specific value with target environment
    """
    if source_value is None:
        return None
    
    # Get the first available value
    available_value = None
    for env_spec in source_value.values:
        if env_spec.get('environments') and env_spec['environments']:
            available_value = env_spec['value']
            break
    
    if available_value is None:
        # Fall back to universal value
        available_value = source_value.get_value_for("")
    
    if available_value is None:
        return None
    
    # Create new EnvironmentSpecificValue with target environment
    new_values = [{
        "environments": [target_env],
        "value": available_value
    }]
    
    return EnvironmentSpecificValue(new_values)


def merge_environment_values(value1: EnvironmentSpecificValue, value2: EnvironmentSpecificValue) -> EnvironmentSpecificValue:
    """
    Merge two environment-specific values.
    
    Args:
        value1: First environment-specific value
        value2: Second environment-specific value
        
    Returns:
        Merged environment-specific value
    """
    if value1 is None:
        return value2
    if value2 is None:
        return value1
    
    # Combine all values
    merged_values = []
    
    # Add values from first object
    if hasattr(value1, 'values'):
        merged_values.extend(value1.values)
    
    # Add values from second object
    if hasattr(value2, 'values'):
        merged_values.extend(value2.values)
    
    return EnvironmentSpecificValue(merged_values)


def get_first_available_value(env_value: EnvironmentSpecificValue) -> Any:
    """
    Get the first available value from an environment-specific value.
    
    Args:
        env_value: Environment-specific value
        
    Returns:
        First available value, or None if no values available
    """
    if env_value is None:
        return None
    
    # Look for environment-specific values first
    for env_spec in env_value.values:
        if env_spec.get('environments') and env_spec['environments']:
            return env_spec['value']
    
    # Fall back to universal value
    return env_value.get_value_for("")


def estimate_memory_from_cpu(cpu_count: int, base_memory_per_cpu: int = 2048) -> int:
    """
    Estimate memory requirements from CPU count.
    
    Args:
        cpu_count: Number of CPUs
        base_memory_per_cpu: Base memory per CPU in MB
        
    Returns:
        Estimated memory requirement in MB
    """
    return cpu_count * base_memory_per_cpu


def estimate_disk_from_data_size(input_files: List[str], output_files: List[str], 
                                overhead_factor: float = 2.0) -> int:
    """
    Estimate disk requirements from input/output file sizes.
    
    Args:
        input_files: List of input file paths
        output_files: List of output file paths
        overhead_factor: Factor to account for temporary files and overhead
        
    Returns:
        Estimated disk requirement in MB
    """
    total_size = 0
    
    # Calculate input file sizes
    for file_path in input_files:
        try:
            import os
            if os.path.exists(file_path):
                total_size += os.path.getsize(file_path)
        except (OSError, IOError):
            # Use default size if file doesn't exist or can't be accessed
            total_size += 1024 * 1024  # 1MB default
    
    # Calculate output file sizes (estimate based on input)
    output_size = total_size * 0.5  # Assume outputs are ~50% of inputs
    total_size += output_size
    
    # Apply overhead factor
    total_size = int(total_size * overhead_factor)
    
    # Convert to MB
    return total_size // (1024 * 1024)


def estimate_runtime_from_complexity(task_type: str, input_size: int, 
                                   complexity_factor: float = 1.0) -> int:
    """
    Estimate runtime from task complexity and input size.
    
    Args:
        task_type: Type of task (e.g., 'alignment', 'variant_calling', 'qc')
        input_size: Input data size in MB
        complexity_factor: Complexity factor for the task type
        
    Returns:
        Estimated runtime in seconds
    """
    # Base runtime estimates for different task types
    base_runtimes = {
        'alignment': 3600,      # 1 hour
        'variant_calling': 7200, # 2 hours
        'qc': 1800,             # 30 minutes
        'filtering': 900,       # 15 minutes
        'sorting': 1200,        # 20 minutes
        'indexing': 600,        # 10 minutes
        'default': 1800         # 30 minutes default
    }
    
    base_runtime = base_runtimes.get(task_type, base_runtimes['default'])
    
    # Scale by input size (assume linear scaling)
    size_factor = max(1.0, input_size / 1024)  # Normalize to 1GB
    
    # Apply complexity factor
    estimated_runtime = int(base_runtime * size_factor * complexity_factor)
    
    return estimated_runtime


def validate_resource_values(resources: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize resource values.
    
    Args:
        resources: Dictionary of resource values
        
    Returns:
        Validated and normalized resource values
    """
    validated = {}
    
    # Memory validation
    if 'mem_mb' in resources:
        mem_mb = resources['mem_mb']
        if isinstance(mem_mb, (int, float)) and mem_mb > 0:
            validated['mem_mb'] = int(mem_mb)
    
    # CPU validation
    if 'cpu' in resources:
        cpu = resources['cpu']
        if isinstance(cpu, (int, float)) and cpu > 0:
            validated['cpu'] = int(cpu)
    
    # Disk validation
    if 'disk_mb' in resources:
        disk_mb = resources['disk_mb']
        if isinstance(disk_mb, (int, float)) and disk_mb > 0:
            validated['disk_mb'] = int(disk_mb)
    
    # GPU validation
    if 'gpu' in resources:
        gpu = resources['gpu']
        if isinstance(gpu, (int, float)) and gpu >= 0:
            validated['gpu'] = int(gpu)
    
    # Runtime validation
    if 'time_s' in resources:
        time_s = resources['time_s']
        if isinstance(time_s, (int, float)) and time_s > 0:
            validated['time_s'] = int(time_s)
    
    return validated


def format_resource_summary(resources: Dict[str, Any]) -> str:
    """
    Format a human-readable summary of resource requirements.
    
    Args:
        resources: Dictionary of resource values
        
    Returns:
        Formatted resource summary string
    """
    parts = []
    
    if 'cpu' in resources:
        parts.append(f"{resources['cpu']} CPU(s)")
    
    if 'mem_mb' in resources:
        mem_gb = resources['mem_mb'] / 1024
        parts.append(f"{mem_gb:.1f}GB RAM")
    
    if 'disk_mb' in resources:
        disk_gb = resources['disk_mb'] / 1024
        parts.append(f"{disk_gb:.1f}GB disk")
    
    if 'gpu' in resources and resources['gpu'] > 0:
        parts.append(f"{resources['gpu']} GPU(s)")
    
    if 'time_s' in resources:
        hours = resources['time_s'] / 3600
        parts.append(f"{hours:.1f}h runtime")
    
    return ", ".join(parts) if parts else "No resources specified" 