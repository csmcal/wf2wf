"""
Adapter registry and factory for environment adaptations.
"""

from typing import Dict, Type, Optional
from .base import EnvironmentAdapter
from .resources import ResourceAdapter
from .environments import environment_mapper
from .strategies import SharedToDistributedAdapter, SharedToCloudAdapter


class AdaptationRegistry:
    """
    Registry for environment adaptation strategies.
    
    This class manages different adaptation strategies and provides
    a factory interface for creating appropriate adapters.
    """
    
    def __init__(self):
        self.adapters: Dict[str, Type[EnvironmentAdapter]] = {}
        self._register_default_adapters()
    
    def register_adapter(self, source_env: str, target_env: str, adapter_class: Type[EnvironmentAdapter]):
        """
        Register a custom adapter for an environment pair.
        
        Args:
            source_env: Source environment name
            target_env: Target environment name
            adapter_class: Adapter class to register
        """
        key = self._make_key(source_env, target_env)
        self.adapters[key] = adapter_class
    
    def get_adapter(self, source_env: str, target_env: str) -> EnvironmentAdapter:
        """
        Get the appropriate adapter for the environment pair.
        
        Args:
            source_env: Source environment name
            target_env: Target environment name
            
        Returns:
            Environment adapter instance
            
        Raises:
            ValueError: If no adapter is available for the environment pair
        """
        # Validate environments
        if not environment_mapper.validate_environment(source_env):
            raise ValueError(f"Unsupported source environment: {source_env}")
        if not environment_mapper.validate_environment(target_env):
            raise ValueError(f"Unsupported target environment: {target_env}")
        
        # Check for exact match
        key = self._make_key(source_env, target_env)
        if key in self.adapters:
            adapter_class = self.adapters[key]
            return adapter_class(source_env, target_env)
        
        # Check for generic adapter
        generic_key = self._make_key("*", "*")
        if generic_key in self.adapters:
            adapter_class = self.adapters[generic_key]
            return adapter_class(source_env, target_env)
        
        # Fall back to default resource adapter
        return ResourceAdapter(source_env, target_env)
    
    def list_available_adapters(self) -> Dict[str, str]:
        """
        List all available adapters.
        
        Returns:
            Dictionary mapping environment pairs to adapter descriptions
        """
        result = {}
        for key, adapter_class in self.adapters.items():
            source_env, target_env = self._parse_key(key)
            result[f"{source_env} → {target_env}"] = adapter_class.__name__
        return result
    
    def has_adapter(self, source_env: str, target_env: str) -> bool:
        """
        Check if an adapter is available for the environment pair.
        
        Args:
            source_env: Source environment name
            target_env: Target environment name
            
        Returns:
            True if adapter is available
        """
        key = self._make_key(source_env, target_env)
        return key in self.adapters
    
    def _register_default_adapters(self):
        """Register default adaptation strategies."""
        # Register the default resource adapter for all pairs
        self.register_adapter("*", "*", ResourceAdapter)
        
        # Register specific adapters for common conversions
        # Special adapter for shared_filesystem to distributed_computing
        self.register_adapter("shared_filesystem", "distributed_computing", SharedToDistributedAdapter)
        
        # Special adapter for shared_filesystem to cloud_native  
        self.register_adapter("shared_filesystem", "cloud_native", SharedToCloudAdapter)
    
    def _make_key(self, source_env: str, target_env: str) -> str:
        """Create a key for the adapter registry."""
        return f"{source_env}:{target_env}"
    
    def _parse_key(self, key: str) -> tuple:
        """Parse a registry key into source and target environments."""
        return tuple(key.split(":", 1))


# Global instance for easy access
adaptation_registry = AdaptationRegistry() 