"""
Resource-specific adaptation strategies.
"""

import logging
from typing import Any, Optional
from .base import EnvironmentAdapter
from .environments import environment_mapper

logger = logging.getLogger(__name__)


class ResourceAdapter(EnvironmentAdapter):
    """
    Handles resource requirement adaptations between environments.
    
    This adapter implements intelligent resource adaptation strategies
    based on environment characteristics and resource types.
    """
    
    def _adapt_resource_value(self, field_name: str, source_value: Any, **opts) -> Optional[Any]:
        """
        Adapt a resource value from source to target environment.
        
        Args:
            field_name: Name of the resource field
            source_value: Source environment value
            **opts: Additional adaptation options
            
        Returns:
            Adapted value for target environment, or None if no adaptation needed
        """
        logger.debug(f"ResourceAdapter._adapt_resource_value called with field_name={field_name}, source_value={source_value}")
        
        if source_value is None:
            logger.debug(f"source_value is None, returning None")
            return None
        
        # Apply environment-specific adaptation
        adapted_value = environment_mapper.calculate_adapted_resource(
            source_value, self.source_env, self.target_env, field_name
        )
        logger.debug(f"environment_mapper.calculate_adapted_resource returned: {adapted_value}")
        
        # Apply field-specific adaptation logic
        if field_name == "mem_mb":
            adapted_value = self._adapt_memory(source_value, adapted_value, **opts)
        elif field_name == "cpu":
            adapted_value = self._adapt_cpu(source_value, adapted_value, **opts)
        elif field_name == "disk_mb":
            adapted_value = self._adapt_disk(source_value, adapted_value, **opts)
        elif field_name == "gpu":
            adapted_value = self._adapt_gpu(source_value, adapted_value, **opts)
        elif field_name == "gpu_mem_mb":
            adapted_value = self._adapt_gpu_memory(source_value, adapted_value, **opts)
        elif field_name == "time_s":
            adapted_value = self._adapt_runtime(source_value, adapted_value, **opts)
        elif field_name == "threads":
            adapted_value = self._adapt_threads(source_value, adapted_value, **opts)
        
        # Log adaptation if value changed
        if adapted_value != source_value:
            reason = self._get_adaptation_reason(field_name, source_value, adapted_value)
            self.log_adaptation(field_name, source_value, adapted_value, reason)
        
        return adapted_value
    
    def _adapt_memory(self, source_value: int, scaled_value: int, **opts) -> int:
        """
        Adapt memory requirements between environments.
        
        Args:
            source_value: Source memory value in MB
            scaled_value: Environment-scaled memory value
            **opts: Additional options
            
        Returns:
            Adapted memory value in MB
        """
        # Apply minimum memory constraints
        min_memory = opts.get("min_memory_mb", 512)
        if scaled_value < min_memory:
            scaled_value = min_memory
        
        # Apply maximum memory constraints
        max_memory = opts.get("max_memory_mb", 131072)  # 128GB
        if scaled_value > max_memory:
            scaled_value = max_memory
        
        # Round to nearest 512MB for better resource allocation
        scaled_value = ((scaled_value + 255) // 512) * 512
        
        return scaled_value
    
    def _adapt_cpu(self, source_value: int, scaled_value: int, **opts) -> int:
        """
        Adapt CPU requirements between environments.
        
        Args:
            source_value: Source CPU value
            scaled_value: Environment-scaled CPU value
            **opts: Additional options
            
        Returns:
            Adapted CPU value
        """
        # Apply minimum CPU constraints
        min_cpu = opts.get("min_cpu", 1)
        if scaled_value < min_cpu:
            scaled_value = min_cpu
        
        # Apply maximum CPU constraints
        max_cpu = opts.get("max_cpu", 64)
        if scaled_value > max_cpu:
            scaled_value = max_cpu
        
        return scaled_value
    
    def _adapt_disk(self, source_value: int, scaled_value: int, **opts) -> int:
        """
        Adapt disk requirements between environments.
        
        Args:
            source_value: Source disk value in MB
            scaled_value: Environment-scaled disk value
            **opts: Additional options
            
        Returns:
            Adapted disk value in MB
        """
        # Apply minimum disk constraints
        min_disk = opts.get("min_disk_mb", 1024)  # 1GB
        if scaled_value < min_disk:
            scaled_value = min_disk
        
        # Apply maximum disk constraints
        max_disk = opts.get("max_disk_mb", 1048576)  # 1TB
        if scaled_value > max_disk:
            scaled_value = max_disk
        
        # Round to nearest 1GB for better resource allocation
        scaled_value = ((scaled_value + 511) // 1024) * 1024
        
        return scaled_value
    
    def _adapt_gpu(self, source_value: int, scaled_value: int, **opts) -> int:
        """
        Adapt GPU requirements between environments.
        
        Args:
            source_value: Source GPU value
            scaled_value: Environment-scaled GPU value
            **opts: Additional options
            
        Returns:
            Adapted GPU value
        """
        # Check if target environment supports GPU
        if not environment_mapper.supports_feature(self.target_env, "gpu"):
            # Fall back to CPU-only execution
            return 0
        
        # Apply minimum GPU constraints
        min_gpu = opts.get("min_gpu", 0)
        if scaled_value < min_gpu:
            scaled_value = min_gpu
        
        # Apply maximum GPU constraints
        max_gpu = opts.get("max_gpu", 8)
        if scaled_value > max_gpu:
            scaled_value = max_gpu
        
        return scaled_value
    
    def _adapt_gpu_memory(self, source_value: int, scaled_value: int, **opts) -> int:
        """
        Adapt GPU memory requirements between environments.
        
        Args:
            source_value: Source GPU memory value in MB
            scaled_value: Environment-scaled GPU memory value
            **opts: Additional options
            
        Returns:
            Adapted GPU memory value in MB
        """
        # Check if target environment supports GPU
        if not environment_mapper.supports_feature(self.target_env, "gpu"):
            return 0
        
        # Apply minimum GPU memory constraints
        min_gpu_memory = opts.get("min_gpu_memory_mb", 1024)  # 1GB
        if scaled_value < min_gpu_memory:
            scaled_value = min_gpu_memory
        
        # Apply maximum GPU memory constraints
        max_gpu_memory = opts.get("max_gpu_memory_mb", 32768)  # 32GB
        if scaled_value > max_gpu_memory:
            scaled_value = max_gpu_memory
        
        # Round to nearest 1GB
        scaled_value = ((scaled_value + 511) // 1024) * 1024
        
        return scaled_value
    
    def _adapt_runtime(self, source_value: int, scaled_value: int, **opts) -> int:
        """
        Adapt runtime requirements between environments.
        
        Args:
            source_value: Source runtime value in seconds
            scaled_value: Environment-scaled runtime value
            **opts: Additional options
            
        Returns:
            Adapted runtime value in seconds
        """
        # Apply minimum runtime constraints
        min_runtime = opts.get("min_runtime_s", 300)  # 5 minutes
        if scaled_value < min_runtime:
            scaled_value = min_runtime
        
        # Apply maximum runtime constraints
        max_runtime = opts.get("max_runtime_s", 604800)  # 1 week
        if scaled_value > max_runtime:
            scaled_value = max_runtime
        
        # Round to nearest hour for better scheduling
        scaled_value = ((scaled_value + 1799) // 3600) * 3600
        
        return scaled_value
    
    def _adapt_threads(self, source_value: int, scaled_value: int, **opts) -> int:
        """
        Adapt thread requirements between environments.
        
        Args:
            source_value: Source thread value
            scaled_value: Environment-scaled thread value
            **opts: Additional options
            
        Returns:
            Adapted thread value
        """
        # Apply minimum thread constraints
        min_threads = opts.get("min_threads", 1)
        if scaled_value < min_threads:
            scaled_value = min_threads
        
        # Apply maximum thread constraints
        max_threads = opts.get("max_threads", 32)
        if scaled_value > max_threads:
            scaled_value = max_threads
        
        return scaled_value
    
    def _get_adaptation_reason(self, field_name: str, source_value: Any, adapted_value: Any) -> str:
        """
        Generate a human-readable reason for the adaptation.
        
        Args:
            field_name: Name of the resource field
            source_value: Original value
            adapted_value: Adapted value
            
        Returns:
            Reason string
        """
        if field_name == "gpu" and adapted_value == 0:
            return f"GPU not supported in {self.target_env} environment"
        
        if field_name in ["mem_mb", "disk_mb"]:
            scaling_factor = adapted_value / source_value if source_value > 0 else 1.0
            return f"Applied {scaling_factor:.2f}x scaling for {self.target_env} environment"
        
        if field_name == "time_s":
            scaling_factor = adapted_value / source_value if source_value > 0 else 1.0
            return f"Applied {scaling_factor:.2f}x runtime scaling for {self.target_env} environment"
        
        return f"Adapted for {self.target_env} environment characteristics" 