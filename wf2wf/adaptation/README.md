# Workflow IR Environment Adaptation

## The Problem

When converting workflows between different execution environments, we face a problem translating resource requirements and :

### Scenario
1. **Source Workflow**: Snakemake workflow designed for shared filesystem (HPC cluster)
2. **Target Workflow**: DAGMan workflow for distributed computing (HTCondor cluster)
3. **Issue**: The source IR contains resource specifications for `shared_filesystem`, but the target exporter expects specifications for `distributed_computing`

### Example
```python
# Source IR (Snakemake → shared_filesystem)
task.mem_mb = EnvironmentSpecificValue([
    {"environments": ["shared_filesystem"], "value": 10240}
])

# Target Exporter (DAGMan → distributed_computing)
resources = task.mem_mb.get_value_for("distributed_computing")  # Returns None!
# Falls back to default: 4096MB instead of 10240MB
```

### Why This Happens
- **Different Execution Models**: Each workflow format is designed for specific execution environments
- **Environment-Specific Values**: Resource requirements vary by environment (overhead, scaling, etc.)

## The Solution: IR Adaptation

Our adaptation system addresses this by:

### 1. Environment Awareness
Understanding the characteristics of different execution environments:
- **Shared Filesystem**: Direct file access, minimal overhead
- **Distributed Computing**: Network overhead, staging requirements
- **Cloud Native**: Virtualization overhead, auto-scaling capabilities

### 2. Intelligent Translation
Converting resource specifications between environments:
```python
# Before Adaptation
task.mem_mb = EnvironmentSpecificValue([
    {"environments": ["shared_filesystem"], "value": 10240}
])

# After Adaptation
task.mem_mb = EnvironmentSpecificValue([
    {"environments": ["shared_filesystem"], "value": 10240},
    {"environments": ["distributed_computing"], "value": 11264}  # 10% overhead
])
```

### 3. Preserved Intent
Maintaining the original resource requirements while accounting for environment differences:
- **Memory**: Apply environment-specific scaling factors
- **CPU**: Account for virtualization overhead
- **Disk**: Include staging and temporary storage needs
- **GPU**: Handle GPU availability differences

## Key Concepts

### Environment Characteristics
Each execution environment has specific characteristics that affect resource requirements:

| Environment | Resource Overhead | Memory Scaling | Disk Scaling | Features |
|-------------|------------------|----------------|--------------|----------|
| Shared Filesystem | 1.0x | 1.0x | 1.0x | Direct access, modules |
| Distributed Computing | 1.2x | 1.1x | 1.5x | Staging, containers |
| Cloud Native | 1.3x | 1.2x | 2.0x | Auto-scaling, virtualization |

### Adaptation Strategies

#### 1. Direct Mapping
When the same resource type exists in both environments:
```python
# CPU requirements often translate directly
source_cpu = 8
target_cpu = 8  # No change needed
```

#### 2. Scaled Mapping
Apply environment-specific scaling factors:
```python
# Memory with overhead
source_memory = 10240  # MB
target_memory = source_memory * memory_scaling_factor
# Result: 10240 * 1.1 = 11264 MB for distributed computing
```

#### 3. Feature Adaptation
Handle environment-specific features:
```python
# GPU availability
if source_env.supports_gpu and not target_env.supports_gpu:
    # Fall back to CPU-only execution
    adapt_gpu_to_cpu(task)
```

#### 4. Resource Inference
Infer missing resources from available ones:
```python
# Estimate memory from CPU if not specified
if not task.mem_mb and task.cpu:
    estimated_memory = task.cpu.get_value() * 2048  # 2GB per CPU
    task.mem_mb = EnvironmentSpecificValue([...])
```

## Usage

### Basic Usage
```python
from wf2wf.adaptation import AdaptationRegistry

# Get adapter for environment pair
adapter = AdaptationRegistry().get_adapter("shared_filesystem", "distributed_computing")

# Adapt workflow
adapted_workflow = adapter.adapt_workflow(workflow)
```

### CLI Integration
```bash
# Automatic adaptation (default)
wf2wf convert snakefile.smk dagman --adapt-environments

# Manual adaptation
wf2wf convert snakefile.smk dagman --adapt-environments --adaptation-strategy conservative
```

### Custom Adaptation Rules
```python
# Register custom adapter
class CustomAdapter(EnvironmentAdapter):
    def adapt_memory(self, source_mem, source_env, target_env):
        return source_mem * 1.5  # 50% overhead

AdaptationRegistry().register_adapter("shared_filesystem", "custom_env", CustomAdapter)
```

## Benefits

### 1. Preserved Resource Intent
- Maintains original resource requirements
- Accounts for environment differences
- Prevents information loss during conversion

### 2. Improved User Experience
- Automatic adaptation reduces manual configuration
- Transparent adaptation decisions
- Configurable adaptation strategies

### 3. Better Resource Utilization
- Accurate resource specifications
- Reduced job failures due to insufficient resources
- Optimized cluster utilization

### 4. Extensibility
- Support for new execution environments
- Custom adaptation strategies
- Machine learning integration potential

## Related Work

This approach builds on established concepts in:

- **Resource Management**: HPC resource allocation and scheduling
- **Workflow Portability**: Cross-platform workflow execution
- **Performance Modeling**: Resource requirement prediction
- **Adaptive Computing**: Dynamic resource allocation

## Future Directions

1. **Machine Learning**: Predict optimal resource requirements from historical data
2. **Dynamic Adaptation**: Real-time adaptation based on cluster conditions
3. **User Feedback**: Learn from user corrections to adaptation decisions
4. **Multi-Environment**: Support workflows that span multiple environments
5. **Performance Optimization**: Minimize adaptation overhead for large workflows 