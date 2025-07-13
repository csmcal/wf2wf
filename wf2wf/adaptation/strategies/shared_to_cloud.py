"""
Specialized adapter for shared filesystem to cloud native conversions.
"""

from typing import Any, Optional
from ..base import EnvironmentAdapter
from ..resources import ResourceAdapter


class SharedToCloudAdapter(ResourceAdapter):
    """
    Specialized adapter for converting from shared filesystem to cloud native.
    
    This adapter handles the specific challenges of converting workflows designed
    for HPC clusters with shared filesystems to cloud-native environments
    like AWS Batch, Google Cloud Run, or Azure Container Instances.
    """
    
    def __init__(self, source_env: str, target_env: str):
        super().__init__(source_env, target_env)
        
        # Validate that this adapter is used for the correct environment pair
        if source_env != "shared_filesystem" or target_env != "cloud_native":
            raise ValueError(
                f"This adapter is specifically for shared_filesystem → cloud_native, "
                f"got {source_env} → {target_env}"
            )
    
    def _adapt_task_environment(self, task, **opts):
        """Override to handle cloud native specific adaptations."""
        super()._adapt_task_environment(task, **opts)
        
        # Add cloud native specific adaptations
        self._adapt_container_requirements(task, **opts)
        self._adapt_object_storage_requirements(task, **opts)
    
    def _adapt_container_requirements(self, task, **opts):
        """Adapt container requirements for cloud native."""
        # Cloud native environments typically require containerization
        # This could involve ensuring container specifications are present
        # For now, we'll just log that this adaptation is needed
        self.log_adaptation(
            "container_required",
            False,
            True,
            "Cloud native environments require containerization"
        )
    
    def _adapt_object_storage_requirements(self, task, **opts):
        """Adapt storage requirements for cloud native."""
        # Cloud native environments typically use object storage (S3, GCS, etc.)
        # This could involve setting up object storage access patterns
        # For now, we'll just log that this adaptation is needed
        self.log_adaptation(
            "file_access",
            "direct",
            "object_storage",
            "Cloud native uses object storage instead of direct file access"
        )
    
    def _adapt_memory(self, source_value: int, scaled_value: int, **opts) -> int:
        """Override with cloud native specific memory adaptation."""
        # Cloud native environments often have higher memory overhead due to:
        # - Container runtime overhead
        # - Virtualization overhead
        # - Object storage access overhead
        
        # Apply additional overhead for cloud native
        cloud_overhead = 1.25  # 25% additional overhead
        adapted_value = int(scaled_value * cloud_overhead)
        
        # Apply standard constraints
        return super()._adapt_memory(source_value, adapted_value, **opts)
    
    def _adapt_cpu(self, source_value: int, scaled_value: int, **opts) -> int:
        """Override with cloud native specific CPU adaptation."""
        # Cloud native environments often have CPU overhead due to:
        # - Container runtime overhead
        # - Virtualization overhead
        # - Network virtualization overhead
        
        # Apply additional overhead for cloud native
        cloud_overhead = 1.1  # 10% additional overhead
        adapted_value = int(scaled_value * cloud_overhead)
        
        # Apply standard constraints
        return super()._adapt_cpu(source_value, adapted_value, **opts)
    
    def _adapt_disk(self, source_value: int, scaled_value: int, **opts) -> int:
        """Override with cloud native specific disk adaptation."""
        # Cloud native environments require additional disk space for:
        # - Container image layers
        # - Temporary storage for object storage operations
        # - Log storage
        # - Checkpoint storage
        
        # Apply additional overhead for cloud native
        cloud_overhead = 2.2  # 120% additional overhead for containerization
        adapted_value = int(scaled_value * cloud_overhead)
        
        # Apply standard constraints
        return super()._adapt_disk(source_value, adapted_value, **opts)
    
    def _adapt_runtime(self, source_value: int, scaled_value: int, **opts) -> int:
        """Override with cloud native specific runtime adaptation."""
        # Cloud native environments often have longer runtime due to:
        # - Container startup time
        # - Object storage transfer time
        # - Cold start overhead
        # - Network latency
        
        # Apply additional overhead for cloud native
        cloud_overhead = 1.35  # 35% additional overhead
        adapted_value = int(scaled_value * cloud_overhead)
        
        # Apply standard constraints
        return super()._adapt_runtime(source_value, adapted_value, **opts) 