"""
Specific adaptation strategies for different environment pairs.
"""

from .shared_to_distributed import SharedToDistributedAdapter
from .shared_to_cloud import SharedToCloudAdapter

__all__ = [
    "SharedToDistributedAdapter",
    "SharedToCloudAdapter"
] 