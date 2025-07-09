# Validation API

The `wf2wf.validate` module provides comprehensive validation for workflow objects, including JSON Schema validation, enhanced semantic checks, and utility functions for validation analysis.

## Basic Validation

### `validate_workflow(obj)`

Validates a workflow object or dictionary against the v0.1 JSON schema.

```python
from wf2wf.validate import validate_workflow
from wf2wf.core import Workflow, Task, EnvironmentSpecificValue

# Create a workflow
workflow = Workflow(name="test_workflow")
task = Task(
    id="test_task",
    command=EnvironmentSpecificValue("echo hello", ["shared_filesystem"])
)
workflow.add_task(task)

# Validate
try:
    validate_workflow(workflow)
    print("Workflow is valid!")
except jsonschema.ValidationError as e:
    print(f"Validation failed: {e}")
```

### `validate_workflow_with_enhanced_checks(obj)`

Provides comprehensive validation including both JSON Schema and enhanced semantic checks.

```python
from wf2wf.validate import validate_workflow_with_enhanced_checks

try:
    validate_workflow_with_enhanced_checks(workflow)
    print("Workflow passed all validation checks!")
except (jsonschema.ValidationError, ValueError) as e:
    print(f"Validation failed: {e}")
```

## Enhanced Validation Functions

### `validate_workflow_enhanced(obj)`

Performs enhanced validation and returns a list of issues found.

```python
from wf2wf.validate import validate_workflow_enhanced

issues = validate_workflow_enhanced(workflow)
if issues:
    print("Validation issues found:")
    for issue in issues:
        print(f"  - {issue}")
else:
    print("No validation issues found")
```

### `get_validation_summary(obj)`

Provides a comprehensive validation summary including statistics and warnings.

```python
from wf2wf.validate import get_validation_summary

summary = get_validation_summary(workflow)
print(f"Valid: {summary['valid']}")
print(f"Issues: {len(summary['issues'])}")
print(f"Warnings: {len(summary['warnings'])}")
print(f"Statistics: {summary['stats']}")
```

## Field-Specific Validation

### `validate_environment_name(environment)`

Validates that an environment name is from the predefined list.

```python
from wf2wf.validate import validate_environment_name

valid_environments = ["shared_filesystem", "distributed_computing", "cloud_native"]
for env in valid_environments:
    if validate_environment_name(env):
        print(f"{env} is a valid environment")
```

### `validate_resource_value(resource_name, value)`

Validates a resource value against defined rules.

```python
from wf2wf.validate import validate_resource_value

# Validate CPU cores
if validate_resource_value("cpu", 4):
    print("CPU value is valid")

# Validate memory (in MB)
if validate_resource_value("mem_mb", 8192):
    print("Memory value is valid")

# Invalid value
if not validate_resource_value("cpu", 0):  # CPU must be >= 1
    print("Invalid CPU value")
```

### `validate_file_path(path, path_type)`

Validates file paths against defined patterns.

```python
from wf2wf.validate import validate_file_path

# Validate Unix path
if validate_file_path("/data/input.txt", "unix_path"):
    print("Valid Unix path")

# Validate Docker image
if validate_file_path("ubuntu:20.04", "docker_image"):
    print("Valid Docker image")

# Validate conda environment
if validate_file_path("my_env", "conda_env"):
    print("Valid conda environment name")
```

### `validate_environment_specific_value(env_value)`

Validates an EnvironmentSpecificValue object and returns any issues.

```python
from wf2wf.validate import validate_environment_specific_value

env_value = {
    "values": [
        {
            "value": "python script.py",
            "environments": ["shared_filesystem"]
        }
    ],
    "default_value": None
}

issues = validate_environment_specific_value(env_value)
if not issues:
    print("EnvironmentSpecificValue is valid")
```

## Validation Constants

### `VALID_ENVIRONMENTS`

Set of predefined execution environments.

```python
from wf2wf.validate import VALID_ENVIRONMENTS

print("Valid environments:", VALID_ENVIRONMENTS)
# Output: {'shared_filesystem', 'distributed_computing', 'cloud_native', 'hybrid', 'local'}
```

### `RESOURCE_VALIDATION_RULES`

Dictionary defining validation rules for resource fields.

```python
from wf2wf.validate import RESOURCE_VALIDATION_RULES

print("CPU rules:", RESOURCE_VALIDATION_RULES["cpu"])
# Output: {'min': 1, 'max': 1024, 'type': <class 'int'>}
```

### `FILE_PATH_PATTERNS`

Dictionary of regex patterns for different file path types.

```python
from wf2wf.validate import FILE_PATH_PATTERNS

print("Available path types:", list(FILE_PATH_PATTERNS.keys()))
# Output: ['unix_path', 'windows_path', 'url', 'docker_image', 'conda_env']
```

## Validation Examples

### Complete Workflow Validation

```python
from wf2wf.core import Workflow, Task, Edge, EnvironmentSpecificValue
from wf2wf.validate import get_validation_summary

# Create a workflow
workflow = Workflow(name="data_analysis")

# Add tasks
prepare_task = Task(
    id="prepare_data",
    command=EnvironmentSpecificValue("python prepare.py", ["shared_filesystem"]),
    cpu=EnvironmentSpecificValue(2, ["shared_filesystem"]),
    mem_mb=EnvironmentSpecificValue(4096, ["shared_filesystem"])
)
workflow.add_task(prepare_task)

analyze_task = Task(
    id="analyze_data",
    command=EnvironmentSpecificValue("python analyze.py", ["shared_filesystem"]),
    cpu=EnvironmentSpecificValue(4, ["shared_filesystem"]),
    mem_mb=EnvironmentSpecificValue(8192, ["shared_filesystem"])
)
workflow.add_task(analyze_task)

# Add edge
workflow.add_edge(Edge(parent="prepare_data", child="analyze_data"))

# Get comprehensive validation summary
summary = get_validation_summary(workflow)

print(f"Workflow validation: {'PASSED' if summary['valid'] else 'FAILED'}")
print(f"Tasks: {summary['stats']['task_count']}")
print(f"Edges: {summary['stats']['edge_count']}")
print(f"Environments used: {summary['stats']['environments_used']}")

if summary['warnings']:
    print("\nWarnings:")
    for warning in summary['warnings']:
        print(f"  - {warning}")

if summary['issues']:
    print("\nIssues:")
    for issue in summary['issues']:
        print(f"  - {issue}")
```

### Resource Validation

```python
from wf2wf.validate import validate_resource_value, RESOURCE_VALIDATION_RULES

# Test various resource values
test_resources = [
    ("cpu", 4),
    ("cpu", 0),  # Invalid: must be >= 1
    ("mem_mb", 8192),
    ("mem_mb", 0),  # Invalid: must be >= 1
    ("gpu", 2),
    ("gpu", -1),  # Invalid: must be >= 0
    ("time_s", 3600),
    ("time_s", 0),  # Invalid: must be >= 1
]

for resource_name, value in test_resources:
    is_valid = validate_resource_value(resource_name, value)
    rules = RESOURCE_VALIDATION_RULES.get(resource_name, {})
    print(f"{resource_name}={value}: {'VALID' if is_valid else 'INVALID'}")
    if not is_valid:
        print(f"  Rules: {rules}")
```

### Environment-Specific Value Validation

```python
from wf2wf.validate import validate_environment_specific_value, VALID_ENVIRONMENTS

# Test various environment-specific values
test_values = [
    {
        "values": [
            {"value": "python script.py", "environments": ["shared_filesystem"]}
        ],
        "default_value": None
    },
    {
        "values": [
            {"value": "python script.py", "environments": ["invalid_env"]}  # Invalid environment
        ],
        "default_value": None
    },
    {
        "values": [
            {"value": "python script.py", "environments": ["shared_filesystem", "distributed_computing"]}
        ],
        "default_value": "python fallback.py"
    }
]

for i, env_value in enumerate(test_values):
    issues = validate_environment_specific_value(env_value)
    print(f"Test {i+1}: {'VALID' if not issues else 'INVALID'}")
    if issues:
        for issue in issues:
            print(f"  - {issue}")
```

## Error Handling

The validation functions provide different levels of error reporting:

1. **JSON Schema validation** raises `jsonschema.ValidationError`
2. **Enhanced validation** returns lists of issues or raises `ValueError`
3. **Utility functions** return boolean values or issue lists

```python
from wf2wf.validate import (
    validate_workflow,
    validate_workflow_with_enhanced_checks,
    validate_workflow_enhanced
)

try:
    # Basic validation
    validate_workflow(workflow)
except jsonschema.ValidationError as e:
    print(f"Schema validation failed: {e}")

try:
    # Comprehensive validation
    validate_workflow_with_enhanced_checks(workflow)
except (jsonschema.ValidationError, ValueError) as e:
    print(f"Comprehensive validation failed: {e}")

# Get detailed issues without exceptions
issues = validate_workflow_enhanced(workflow)
if issues:
    print("Validation issues:")
    for issue in issues:
        print(f"  - {issue}")
```

## Best Practices

1. **Use enhanced validation** for comprehensive checks during development
2. **Use basic validation** for performance-critical production code
3. **Check validation summary** for detailed analysis and statistics
4. **Validate individual fields** when building workflows programmatically
5. **Handle validation errors gracefully** in user-facing applications

```python
def create_and_validate_workflow(name, tasks_data):
    """Create a workflow and validate it with comprehensive checks."""
    workflow = Workflow(name=name)
    
    # Add tasks with validation
    for task_data in tasks_data:
        # Validate individual fields before creating task
        if not validate_environment_name(task_data.get("environment", "shared_filesystem")):
            raise ValueError(f"Invalid environment: {task_data['environment']}")
        
        if not validate_resource_value("cpu", task_data.get("cpu", 1)):
            raise ValueError(f"Invalid CPU value: {task_data['cpu']}")
        
        # Create task
        task = Task(
            id=task_data["id"],
            command=EnvironmentSpecificValue(task_data["command"], [task_data["environment"]]),
            cpu=EnvironmentSpecificValue(task_data["cpu"], [task_data["environment"]])
        )
        workflow.add_task(task)
    
    # Comprehensive validation
    summary = get_validation_summary(workflow)
    if not summary["valid"]:
        raise ValueError(f"Workflow validation failed:\n" + "\n".join(summary["issues"]))
    
    return workflow
``` 