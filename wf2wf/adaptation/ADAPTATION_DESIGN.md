# IR Adaptation System Design

## Overview

The IR adaptation system is responsible for enriching workflow IR objects when converting between different execution environments. This addresses a common problem where source workflows have execution-model-specific and environment-specific values that need to be adapted for target environments.

## Core Problem

When converting workflows between execution models (e.g., Snakemake → DAGMan), the source IR contains values relevant to the source execution environment (e.g., a shared filesystem), but the target exporter expects values for the target environment (e.g., a distributed computing handler). Without adaptation or some form of mapping logic, the exporter will lose or misspecify important resource specifications.

## Design Goals

1. **Preserve Intent**: Maintain the original resource requirements and specifications
2. **Environment Awareness**: Understand differences between execution environments
3. **Intelligent Fallbacks**: Use sensible defaults when direct mapping isn't possible
4. **Transparency**: Log adaptation decisions for user awareness
5. **Extensibility**: Support new execution environments and adaptation strategies

## Architecture

### Core Components

#### 1. `EnvironmentAdapter` (Base Class)
```python
class EnvironmentAdapter:
    """Base class for environment-specific adaptations."""
    
    def __init__(self, source_env: str, target_env: str):
        self.source_env = source_env
        self.target_env = target_env
        self.adaptation_log = []
    
    def adapt_workflow(self, workflow: Workflow) -> Workflow:
        """Adapt a workflow for the target environment."""
        
    def adapt_task(self, task: Task) -> Task:
        """Adapt a task for the target environment."""
        
    def log_adaptation(self, field: str, old_value: Any, new_value: Any, reason: str):
        """Log an adaptation decision."""
```

#### 2. `ResourceAdapter` (Specialized)
```python
class ResourceAdapter(EnvironmentAdapter):
    """Handles resource requirement adaptations."""
    
    def adapt_memory(self, source_mem: int, source_env: str, target_env: str) -> int:
        """Adapt memory requirements between environments."""
        
    def adapt_cpu(self, source_cpu: int, source_env: str, target_env: str) -> int:
        """Adapt CPU requirements between environments."""
        
    def adapt_disk(self, source_disk: int, source_env: str, target_env: str) -> int:
        """Adapt disk requirements between environments."""
```

#### 3. `EnvironmentMapper` (Configuration)
```python
class EnvironmentMapper:
    """Maps between execution environments and their characteristics."""
    
    ENVIRONMENT_CHARACTERISTICS = {
        "shared_filesystem": {
            "resource_overhead": 1.0,
            "memory_scaling": 1.0,
            "cpu_scaling": 1.0,
            "disk_scaling": 1.0,
            "supports_gpu": True,
            "supports_containers": True,
        },
        "distributed_computing": {
            "resource_overhead": 1.2,  # 20% overhead for distributed
            "memory_scaling": 1.1,     # Slight memory overhead
            "cpu_scaling": 1.0,
            "disk_scaling": 1.5,       # More disk for staging
            "supports_gpu": True,
            "supports_containers": True,
        },
        "cloud_native": {
            "resource_overhead": 1.3,
            "memory_scaling": 1.2,
            "cpu_scaling": 1.1,
            "disk_scaling": 2.0,       # Significant disk overhead
            "supports_gpu": True,
            "supports_containers": True,
        }
    }
```

#### 4. `AdaptationRegistry` (Factory)
```python
class AdaptationRegistry:
    """Registry for environment adaptation strategies."""
    
    def __init__(self):
        self.adapters = {}
        self._register_default_adapters()
    
    def get_adapter(self, source_env: str, target_env: str) -> EnvironmentAdapter:
        """Get the appropriate adapter for the environment pair."""
        
    def register_adapter(self, source_env: str, target_env: str, adapter_class: Type[EnvironmentAdapter]):
        """Register a custom adapter for an environment pair."""
```

### File Structure

```
wf2wf/adaptation/
├── __init__.py                 # Main adaptation interface
├── base.py                     # Base adapter classes
├── resources.py                # Resource-specific adaptations
├── environments.py             # Environment mapping and characteristics
├── registry.py                 # Adapter registry and factory
├── strategies/                 # Specific adaptation strategies
│   ├── __init__.py
│   ├── shared_to_distributed.py
│   ├── shared_to_cloud.py
│   └── distributed_to_cloud.py
├── utils.py                    # Adaptation utilities
└── logging.py                  # Adaptation logging and reporting
```

## Adaptation Strategies

### 1. Direct Mapping
When the same resource type exists in both environments, use direct value transfer.

### 2. Scaled Mapping
Apply environment-specific scaling factors to account for overhead:
- **Memory**: Apply memory scaling factor
- **CPU**: Apply CPU scaling factor  
- **Disk**: Apply disk scaling factor (higher for distributed/cloud)

### 3. Intelligent Fallbacks
When direct mapping isn't possible:
- **Missing GPU**: Fall back to CPU-only execution
- **Missing containers**: Use system dependencies
- **Missing modules**: Use conda environments or manual installation

### 4. Resource Inference
Infer missing resources from available ones:
- **Memory from CPU**: Estimate memory based on CPU count
- **Disk from data**: Estimate disk from input/output file sizes
- **Runtime from complexity**: Estimate runtime from resource usage

## Integration Points

### 1. CLI Integration
```python
# In cli.py
def convert_workflow(source_format, target_format, **opts):
    # ... existing conversion logic ...
    
    # Add adaptation step
    if opts.get("adapt_environments", True):
        adapter = AdaptationRegistry().get_adapter(source_env, target_env)
        workflow = adapter.adapt_workflow(workflow)
```

### 2. Exporter Integration
```python
# In exporters/base.py
def export_workflow(self, workflow: Workflow, output_path: Path, **opts):
    # Pre-export adaptation
    if opts.get("adapt_environments", True):
        adapter = AdaptationRegistry().get_adapter(
            workflow.execution_model.get_value_for(""), 
            self.target_environment
        )
        workflow = adapter.adapt_workflow(workflow)
    
    # ... existing export logic ...
```

### 3. Loss Reporting Integration
```python
# Adaptation decisions become part of the loss report
def log_adaptation(self, field: str, old_value: Any, new_value: Any, reason: str):
    loss_record(
        f"/adaptation/{field}",
        field,
        old_value,
        f"Adapted to {new_value}: {reason}",
        "system"
    )
```

## Configuration

### Environment Characteristics
```yaml
# config/environments.yaml
environments:
  shared_filesystem:
    resource_overhead: 1.0
    memory_scaling: 1.0
    cpu_scaling: 1.0
    disk_scaling: 1.0
    features:
      - gpu
      - containers
      - modules
      
  distributed_computing:
    resource_overhead: 1.2
    memory_scaling: 1.1
    cpu_scaling: 1.0
    disk_scaling: 1.5
    features:
      - gpu
      - containers
      - staging
      
  cloud_native:
    resource_overhead: 1.3
    memory_scaling: 1.2
    cpu_scaling: 1.1
    disk_scaling: 2.0
    features:
      - gpu
      - containers
      - auto_scaling
```

### Adaptation Rules
```yaml
# config/adaptation_rules.yaml
rules:
  memory:
    shared_filesystem_to_distributed_computing:
      scaling_factor: 1.1
      min_value: 512
      max_value: 32768
      
  disk:
    shared_filesystem_to_distributed_computing:
      scaling_factor: 1.5
      min_value: 1024
      max_value: 1048576
```

## Testing Strategy

### 1. Unit Tests
- Test individual adaptation strategies
- Test environment mapping logic
- Test resource scaling calculations

### 2. Integration Tests
- Test end-to-end adaptation workflows
- Test CLI integration
- Test exporter integration

### 3. Validation Tests
- Verify adapted values are reasonable
- Verify no information loss occurs
- Verify adaptation logs are complete

## Migration Plan

### Phase 1: Foundation
1. Create base adapter classes
2. Implement environment mapping
3. Add basic resource adaptation

### Phase 2: Integration
1. Integrate with CLI
2. Integrate with exporters
3. Add adaptation logging

### Phase 3: Advanced Features
1. Add intelligent fallbacks
2. Add resource inference
3. Add custom adaptation rules

### Phase 4: Optimization
1. Performance optimization
2. Configuration management
3. Advanced logging and reporting

## Future Enhancements

1. **Machine Learning**: Use ML to predict optimal resource requirements
2. **Historical Data**: Learn from previous successful adaptations
3. **User Feedback**: Allow users to provide adaptation preferences
4. **Dynamic Adaptation**: Real-time adaptation based on cluster conditions
5. **Multi-Environment**: Support workflows that span multiple environments 