"""
Environment mapping and characteristics.
"""

from typing import Dict, Any, List, Optional


class EnvironmentMapper:
    """
    Maps between execution environments and their characteristics.
    
    This class provides information about different execution environments
    to guide adaptation decisions.
    """
    
    # Environment characteristics that affect resource requirements
    ENVIRONMENT_CHARACTERISTICS = {
        "shared_filesystem": {
            "resource_overhead": 1.0,
            "memory_scaling": 1.0,
            "cpu_scaling": 1.0,
            "disk_scaling": 1.0,
            "gpu_scaling": 1.0,
            "supports_gpu": True,
            "supports_containers": True,
            "supports_modules": True,
            "file_access": "direct",
            "description": "HPC cluster with shared filesystem (NFS, Lustre)",
        },
        "distributed_computing": {
            "resource_overhead": 1.2,
            "memory_scaling": 1.1,
            "cpu_scaling": 1.0,
            "disk_scaling": 1.5,
            "gpu_scaling": 1.0,
            "supports_gpu": True,
            "supports_containers": True,
            "supports_modules": False,
            "file_access": "staging",
            "description": "Distributed computing (HTCondor, Grid, cloud batch)",
        },
        "hybrid": {
            "resource_overhead": 1.15,
            "memory_scaling": 1.05,
            "cpu_scaling": 1.0,
            "disk_scaling": 1.25,
            "gpu_scaling": 1.0,
            "supports_gpu": True,
            "supports_containers": True,
            "supports_modules": True,
            "file_access": "mixed",
            "description": "Hybrid environments (Nextflow, mixed cloud/HPC)",
        },
        "cloud_native": {
            "resource_overhead": 1.3,
            "memory_scaling": 1.2,
            "cpu_scaling": 1.1,
            "disk_scaling": 2.0,
            "gpu_scaling": 1.1,
            "supports_gpu": True,
            "supports_containers": True,
            "supports_modules": False,
            "file_access": "object_storage",
            "description": "Cloud-native (S3/GCS/Azure, serverless)",
        },
        "unknown": {
            "resource_overhead": 1.1,
            "memory_scaling": 1.05,
            "cpu_scaling": 1.0,
            "disk_scaling": 1.2,
            "gpu_scaling": 1.0,
            "supports_gpu": False,
            "supports_containers": False,
            "supports_modules": False,
            "file_access": "unknown",
            "description": "Unknown or unspecified environment",
        }
    }
    
    # Default resource values for each environment
    DEFAULT_RESOURCES = {
        "shared_filesystem": {
            "cpu": 1,
            "mem_mb": 2048,
            "disk_mb": 1024,
            "gpu": 0,
            "gpu_mem_mb": 0,
            "time_s": 3600,
            "threads": 1,
        },
        "distributed_computing": {
            "cpu": 1,
            "mem_mb": 4096,
            "disk_mb": 2048,
            "gpu": 0,
            "gpu_mem_mb": 0,
            "time_s": 7200,
            "threads": 1,
        },
        "hybrid": {
            "cpu": 1,
            "mem_mb": 3072,
            "disk_mb": 1536,
            "gpu": 0,
            "gpu_mem_mb": 0,
            "time_s": 5400,
            "threads": 1,
        },
        "cloud_native": {
            "cpu": 1,
            "mem_mb": 4096,
            "disk_mb": 4096,
            "gpu": 0,
            "gpu_mem_mb": 0,
            "time_s": 3600,
            "threads": 1,
        },
        "unknown": {
            "cpu": 1,
            "mem_mb": 2048,
            "disk_mb": 1024,
            "gpu": 0,
            "gpu_mem_mb": 0,
            "time_s": 3600,
            "threads": 1,
        }
    }
    
    def __init__(self):
        pass
    
    def get_characteristics(self, environment: str) -> Dict[str, Any]:
        """
        Get characteristics for a specific environment.
        
        Args:
            environment: Environment name
            
        Returns:
            Environment characteristics dictionary
        """
        return self.ENVIRONMENT_CHARACTERISTICS.get(environment, self.ENVIRONMENT_CHARACTERISTICS["unknown"])
    
    def get_default_resources(self, environment: str) -> Dict[str, Any]:
        """
        Get default resource values for a specific environment.
        
        Args:
            environment: Environment name
            
        Returns:
            Default resource values dictionary
        """
        return self.DEFAULT_RESOURCES.get(environment, self.DEFAULT_RESOURCES["unknown"])
    
    def get_scaling_factor(self, environment: str, resource_type: str) -> float:
        """
        Get scaling factor for a specific resource type in an environment.
        
        Args:
            environment: Environment name
            resource_type: Type of resource (memory, cpu, disk, gpu)
            
        Returns:
            Scaling factor
        """
        characteristics = self.get_characteristics(environment)
        
        scaling_map = {
            "memory": "memory_scaling",
            "mem_mb": "memory_scaling",
            "cpu": "cpu_scaling",
            "threads": "cpu_scaling",
            "disk": "disk_scaling",
            "disk_mb": "disk_scaling",
            "gpu": "gpu_scaling",
            "gpu_mem_mb": "gpu_scaling",
        }
        
        scaling_key = scaling_map.get(resource_type, "resource_overhead")
        return characteristics.get(scaling_key, 1.0)
    
    def supports_feature(self, environment: str, feature: str) -> bool:
        """
        Check if an environment supports a specific feature.
        
        Args:
            environment: Environment name
            feature: Feature name (gpu, containers, modules)
            
        Returns:
            True if feature is supported
        """
        characteristics = self.get_characteristics(environment)
        support_key = f"supports_{feature}"
        return characteristics.get(support_key, False)
    
    def get_file_access_method(self, environment: str) -> str:
        """
        Get the file access method for an environment.
        
        Args:
            environment: Environment name
            
        Returns:
            File access method description
        """
        characteristics = self.get_characteristics(environment)
        return characteristics.get("file_access", "unknown")
    
    def list_environments(self) -> List[str]:
        """
        Get list of all supported environments.
        
        Returns:
            List of environment names
        """
        return list(self.ENVIRONMENT_CHARACTERISTICS.keys())
    
    def get_environment_description(self, environment: str) -> str:
        """
        Get description for a specific environment.
        
        Args:
            environment: Environment name
            
        Returns:
            Environment description
        """
        characteristics = self.get_characteristics(environment)
        return characteristics.get("description", "Unknown environment")
    
    def calculate_adapted_resource(self, source_value: Any, source_env: str, target_env: str, resource_type: str) -> Any:
        """
        Calculate adapted resource value between environments.
        
        Args:
            source_value: Source environment value
            source_env: Source environment name
            target_env: Target environment name
            resource_type: Type of resource
            
        Returns:
            Adapted resource value
        """
        if source_value is None:
            return None
            
        # Get scaling factors
        source_scaling = self.get_scaling_factor(source_env, resource_type)
        target_scaling = self.get_scaling_factor(target_env, resource_type)
        
        # Calculate adaptation factor
        adaptation_factor = target_scaling / source_scaling if source_scaling > 0 else 1.0
        
        # Apply adaptation
        if isinstance(source_value, (int, float)):
            return int(source_value * adaptation_factor)
        else:
            return source_value  # Non-numeric values are passed through
    
    def validate_environment(self, environment: str) -> bool:
        """
        Validate that an environment is supported.
        
        Args:
            environment: Environment name to validate
            
        Returns:
            True if environment is supported
        """
        return environment in self.ENVIRONMENT_CHARACTERISTICS


# Global instance for easy access
environment_mapper = EnvironmentMapper() 