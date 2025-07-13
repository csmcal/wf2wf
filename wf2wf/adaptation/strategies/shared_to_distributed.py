"""
Specialized adapter for shared filesystem to distributed computing conversions.
"""

from typing import Any, Optional
from ..base import EnvironmentAdapter
from ..resources import ResourceAdapter


class SharedToDistributedAdapter(ResourceAdapter):
    """
    Specialized adapter for converting from shared filesystem to distributed computing.
    
    This adapter handles the specific challenges of converting workflows designed
    for HPC clusters with shared filesystems to distributed computing environments
    like HTCondor or cloud batch systems.
    """
    
    def __init__(self, source_env: str, target_env: str):
        super().__init__(source_env, target_env)
        
        # Validate that this adapter is used for the correct environment pair
        if source_env != "shared_filesystem" or target_env != "distributed_computing":
            raise ValueError(
                f"This adapter is specifically for shared_filesystem → distributed_computing, "
                f"got {source_env} → {target_env}"
            )
    
    def _adapt_task_environment(self, task, **opts):
        """Override to handle distributed computing specific adaptations."""
        super()._adapt_task_environment(task, **opts)
        
        # Add distributed computing specific adaptations
        self._adapt_file_transfer_requirements(task, **opts)
        self._adapt_staging_requirements(task, **opts)
    
    def _adapt_file_transfer_requirements(self, task, **opts):
        """Adapt file transfer requirements for distributed computing."""
        # In distributed computing, files often need to be staged
        # This could involve setting up file transfer specifications
        # For now, we'll just log that this adaptation is needed
        self.log_adaptation(
            "file_transfer_mode",
            "direct",
            "staging",
            "Distributed computing requires file staging"
        )
    
    def _adapt_staging_requirements(self, task, **opts):
        """Adapt staging requirements for distributed computing."""
        # Distributed computing often requires input/output file staging
        # This could involve setting up staging directories and transfer protocols
        # For now, we'll just log that this adaptation is needed
        self.log_adaptation(
            "staging_required",
            False,
            True,
            "Distributed computing requires file staging"
        )
    
    def _adapt_memory(self, source_value: int, scaled_value: int, **opts) -> int:
        """Override with distributed computing specific memory adaptation."""
        # Distributed computing often has higher memory overhead due to:
        # - Process isolation
        # - Network communication overhead
        # - Staging buffer requirements
        
        # Apply additional overhead for distributed computing
        distributed_overhead = 1.15  # 15% additional overhead
        adapted_value = int(scaled_value * distributed_overhead)
        
        # Apply standard constraints
        return super()._adapt_memory(source_value, adapted_value, **opts)
    
    def _adapt_disk(self, source_value: int, scaled_value: int, **opts) -> int:
        """Override with distributed computing specific disk adaptation."""
        # Distributed computing requires additional disk space for:
        # - Staging input files
        # - Temporary output files
        # - Log files
        # - Checkpoint files
        
        # Apply additional overhead for distributed computing
        distributed_overhead = 1.8  # 80% additional overhead for staging
        adapted_value = int(scaled_value * distributed_overhead)
        
        # Apply standard constraints
        return super()._adapt_disk(source_value, adapted_value, **opts)
    
    def _adapt_runtime(self, source_value: int, scaled_value: int, **opts) -> int:
        """Override with distributed computing specific runtime adaptation."""
        # Distributed computing often has longer runtime due to:
        # - Job scheduling overhead
        # - File transfer time
        # - Resource allocation delays
        
        # Apply additional overhead for distributed computing
        distributed_overhead = 1.25  # 25% additional overhead
        adapted_value = int(scaled_value * distributed_overhead)
        
        # Apply standard constraints
        return super()._adapt_runtime(source_value, adapted_value, **opts) 