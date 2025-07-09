# Exporter Specification Template

**Based on analysis of current exporter architecture and shared infrastructure**

This document defines the standard architecture and patterns that all exporters should follow to leverage shared infrastructure and eliminate duplication.

## Table of Contents

1. [Core Architecture](#core-architecture)
2. [Required Methods](#required-methods)
3. [Shared Infrastructure Usage](#shared-infrastructure-usage)
4. [Code Organization](#code-organization)
5. [Testing Requirements](#testing-requirements)
6. [Migration Checklist](#migration-checklist)
7. [Example Implementation](#example-implementation)

---

## Core Architecture

### 1.1 Inheritance Pattern

All exporters MUST inherit from `BaseExporter` and follow this structure:

```python
class FormatExporter(BaseExporter):
    """Format-specific exporter using shared infrastructure."""
    
    def _get_target_format(self) -> str:
        """Get the target format name - REQUIRED IMPLEMENTATION."""
        return "format_name"
    
    def _generate_output(self, workflow: Workflow, output_path: Path, **opts: Any) -> None:
        """Generate format-specific output - REQUIRED IMPLEMENTATION."""
        # Format-specific output generation logic only
        # All shared workflow orchestration handled by BaseExporter
        pass
```

### 1.2 Workflow Integration

The `export_workflow()` method in `BaseExporter` provides the unified workflow:

```python
def export_workflow(self, workflow: Workflow, output_path: Union[str, Path], **opts: Any) -> None:
    """
    Enhanced export method with shared infrastructure integration.
    
    This method provides:
    1. Loss tracking preparation and reset
    2. Intelligent inference of missing values using shared infrastructure
    3. Interactive prompting when enabled
    4. Format-specific loss detection and recording
    5. Output directory creation
    6. Format-specific output generation via _generate_output()
    7. Loss side-car writing with checksum computation
    8. Completion reporting with detailed information
    """
```

**DO NOT OVERRIDE** this method unless absolutely necessary. The shared workflow handles:
- Loss tracking and side-car generation with checksums
- Intelligent inference of missing information
- Interactive prompting for missing data
- Environment-specific value handling
- Validation and error handling

---

## Required Methods

### 2.1 _get_target_format() - REQUIRED

```python
def _get_target_format(self) -> str:
    """Return the target format name for shared infrastructure."""
    return "format_name"  # e.g., "cwl", "dagman", "snakemake"
```

### 2.2 _generate_output() - REQUIRED

```python
def _generate_output(self, workflow: Workflow, output_path: Path, **opts: Any) -> None:
    """
    Generate format-specific output from workflow.
    
    This method should:
    1. Generate format-specific files (workflow, tools, scripts, etc.)
    2. Handle format-specific options and configurations
    3. Write output files to the specified path
    4. Use shared infrastructure for environment-specific values
    
    Parameters:
        workflow: The workflow to export
        output_path: Path for the main output file
        **opts: Format-specific options
    """
```

---

## Shared Infrastructure Usage

### 3.1 What to Use from Shared Infrastructure

**ALWAYS USE** these shared components:

1. **Loss Integration**: `detect_and_record_losses()` from `loss_integration.py`
2. **Inference Engine**: `infer_missing_values()` from `inference.py`
3. **Interactive Prompting**: `prompt_for_missing_values()` from `interactive.py`
4. **Environment-Specific Values**: `_get_environment_specific_value()` from `BaseExporter`
5. **Resource Handling**: `_get_task_resources()` from `BaseExporter`
6. **Environment Handling**: `_get_task_environment()` from `BaseExporter`
7. **Error Handling**: `_get_task_error_handling()` from `BaseExporter`
8. **File Transfer**: `_get_task_file_transfer()` from `BaseExporter`
9. **Advanced Features**: `_get_task_advanced_features()` from `BaseExporter`
10. **Workflow Metadata**: `_get_workflow_metadata()` from `BaseExporter`
11. **Task Metadata**: `_get_task_metadata()` from `BaseExporter`
12. **File Writing**: `_write_file()`, `_write_json()`, `_write_yaml()` from `BaseExporter`
13. **Name Sanitization**: `_sanitize_name()` from `BaseExporter`
14. **Loss Recording**: `_record_loss_if_present()` from `BaseExporter`

### 3.2 Comprehensive BaseExporter Helper Methods

The `BaseExporter` provides extensive helper methods that should be used:

#### Environment-Specific Value Methods:
- `_get_environment_specific_value()` - Get value for specific environment with fallback
- `_get_environment_specific_value_for_target()` - Get value for target environment with fallback
- `_record_loss_if_present()` - Record loss if field has value for environment
- `_record_loss_if_present_for_target()` - Record loss if field has value for target environment

#### Task Attribute Methods:
- `_get_task_resources()` / `_get_task_resources_for_target()` - Extract resource specifications
- `_get_task_environment()` / `_get_task_environment_for_target()` - Extract environment specifications
- `_get_task_error_handling()` / `_get_task_error_handling_for_target()` - Extract error handling
- `_get_task_file_transfer()` / `_get_task_file_transfer_for_target()` - Extract file transfer specs
- `_get_task_advanced_features()` / `_get_task_advanced_features_for_target()` - Extract advanced features

#### Workflow Attribute Methods:
- `_get_workflow_requirements()` / `_get_workflow_requirements_for_target()` - Extract requirements
- `_get_workflow_hints()` / `_get_workflow_hints_for_target()` - Extract hints
- `_get_execution_model()` / `_get_execution_model_for_target()` - Extract execution model

#### Utility Methods:
- `_write_file()` - Write text content with error handling
- `_write_json()` - Write JSON data with error handling
- `_write_yaml()` - Write YAML data with error handling
- `_sanitize_name()` - Sanitize names for target format
- `_get_task_metadata()` - Extract task metadata for preservation
- `_get_workflow_metadata()` - Extract workflow metadata for preservation

### 3.3 Core EnvironmentSpecificValue Methods

Exporters should also use these core methods from `EnvironmentSpecificValue`:

#### Value Retrieval Methods:
- `get_value_for(environment: str)` - Get value for specific environment (no fallback)
- `get_value_with_default(environment: str)` - Get value with fallback to default value
- `get_default_value()` - Get the default value

#### Environment Checking Methods:
- `has_environment_specific_value(environment: str)` - Check if environment-specific value exists
- `has_default_value()` - Check if default value exists
- `is_applicable_to(environment: str)` - Check if any value applies to environment
- `all_environments()` - Get all environments that have values set

#### Value Modification Methods:
- `set_for_environment(value, environment)` - Set value for specific environment
- `set_default_value(value)` - Set the default value
- `add_environment(environment)` - Add environment to most recent value
- `remove_environment(environment)` - Remove environment from all values

### 3.4 Shared Utility Methods

Exporters should use these utility methods from shared infrastructure:

#### From `inference.py` and `interactive.py`:
- `_has_env_value(env_value, environment)` - Check if EnvironmentSpecificValue has value for environment

#### From `loss_integration.py`:
- `_get_env_value(env_value, environment)` - Get value with fallback logic

### 3.5 Best Practices for Environment-Specific Value Usage

**PREFER** these patterns:

```python
# ✅ GOOD: Use get_value_with_default for robust value retrieval
conda_env = task.conda.get_value_with_default(self.target_environment)

# ✅ GOOD: Use BaseExporter helper methods
resources = self._get_task_resources_for_target(task)
environment = self._get_task_environment_for_target(task)

# ✅ GOOD: Use _has_env_value for checking existence
if _has_env_value(task.cpu, self.target_environment):
    # Handle CPU specification
    pass

# ✅ GOOD: Use _record_loss_if_present_for_target for loss tracking
self._record_loss_if_present_for_target(task, "gpu", "GPU not supported in target format")
```

**AVOID** these patterns:

```python
# ❌ BAD: Direct access without fallback
conda_env = task.conda.get_value_for(self.target_environment)  # May return None

# ❌ BAD: Manual environment-specific value handling
if task.conda and hasattr(task.conda, 'get_value_for'):
    conda_env = task.conda.get_value_for(self.target_environment)

# ❌ BAD: Manual loss recording
if task.gpu and task.gpu.get_value_for(self.target_environment):
    loss_record(f"/tasks/{task.id}/gpu", "gpu", task.gpu.get_value_for(self.target_environment), "GPU not supported")
```

### 3.6 What NOT to Duplicate

**NEVER IMPLEMENT** these in individual exporters:

1. ❌ Loss tracking and side-car generation
2. ❌ Missing value inference logic
3. ❌ Interactive prompting logic
4. ❌ Environment-specific value handling
5. ❌ Resource extraction logic
6. ❌ Environment extraction logic
7. ❌ Error handling extraction logic
8. ❌ File transfer extraction logic
9. ❌ Advanced feature extraction logic
10. ❌ Output directory creation
11. ❌ Validation logic (beyond format-specific validation)
12. ❌ File writing utilities
13. ❌ Name sanitization logic
14. ❌ Metadata extraction logic

### 3.7 Format-Specific Enhancements

Only implement format-specific logic that isn't covered by shared infrastructure:

```python
def _enhance_format_specific_features(self, workflow: Workflow, output_path: Path, **opts: Any):
    """Add format-specific enhancements not covered by shared infrastructure."""
    
    # Examples of format-specific logic:
    # - CWL: Tool file generation, $graph support, BCO integration
    # - DAGMan: Submit file generation, script wrapper creation
    # - Snakemake: Rule generation, config file creation
    # - Nextflow: Module generation, channel analysis
    # - WDL: Task generation, workflow structure
    # - Galaxy: Tool XML generation, workflow XML structure
```

---

## Code Organization

### 4.1 File Structure

```
wf2wf/exporters/
├── base.py                    # Base exporter class and shared methods (shared)
├── inference.py               # Intelligent inference engine (shared)
├── interactive.py             # Interactive prompting system (shared)
├── loss_integration.py        # Loss detection and recording (shared)
├── format_exporter.py         # Format-specific exporter
└── EXPORTER_SPECIFICATION.md  # This specification
```

### 4.2 Code Size Guidelines

After refactoring, exporters should be:

- **Small**: 200-600 lines (depending on format complexity)
- **Focused**: Only format-specific output generation logic
- **Maintainable**: Clear separation of concerns
- **Testable**: Easy to unit test individual components

### 4.3 Import Statements

```python
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from wf2wf.core import Workflow, Task, ParameterSpec
from wf2wf.exporters.base import BaseExporter

logger = logging.getLogger(__name__)
```

---

## Testing Requirements

### 5.1 Test Structure

```python
# tests/test_exporters/test_format_exporter.py

class TestFormatExporter:
    """Test format-specific exporter functionality."""
    
    def test_get_target_format(self):
        """Test _get_target_format method."""
        pass
    
    def test_generate_output(self):
        """Test output generation from workflow."""
        pass
    
    def test_loss_integration(self):
        """Test loss detection and recording."""
        pass
    
    def test_inference_integration(self):
        """Test intelligent inference integration."""
        pass
    
    def test_interactive_mode(self):
        """Test interactive prompting."""
        pass
    
    def test_environment_specific_values(self):
        """Test environment-specific value handling."""
        pass
    
    def test_shared_helper_methods(self):
        """Test usage of shared helper methods."""
        pass
```

### 5.2 Integration Tests

```python
# tests/test_integration/test_format_roundtrip.py

def test_format_export_and_roundtrip():
    """Test complete export and round-trip conversion."""
    pass

def test_format_from_ir():
    """Test format export from IR."""
    pass
```

---

## Migration Checklist

### 6.1 Pre-Migration Analysis

- [ ] Identify duplicated logic in current exporter
- [ ] Map format-specific vs. shared functionality
- [ ] Identify format-specific enhancements needed
- [ ] Plan test coverage for refactored components

### 6.2 Migration Steps

1. **Create new exporter class**:
   - [ ] Inherit from `BaseExporter`
   - [ ] Implement `_get_target_format()` method
   - [ ] Implement `_generate_output()` method
   - [ ] Add format-specific enhancements if needed

2. **Remove duplicated logic**:
   - [ ] Remove loss tracking methods
   - [ ] Remove missing value inference methods
   - [ ] Remove interactive prompting methods
   - [ ] Remove environment-specific value handling methods
   - [ ] Remove resource extraction methods
   - [ ] Remove environment extraction methods
   - [ ] Remove error handling extraction methods
   - [ ] Remove file transfer extraction methods
   - [ ] Remove advanced feature extraction methods
   - [ ] Remove file writing utilities
   - [ ] Remove name sanitization logic
   - [ ] Remove metadata extraction logic

3. **Update imports and dependencies**:
   - [ ] Import shared infrastructure modules
   - [ ] Remove format-specific utility functions
   - [ ] Update method calls to use shared infrastructure

4. **Test and validate**:
   - [ ] All existing tests pass
   - [ ] New tests for shared infrastructure integration
   - [ ] Performance is equivalent or better
   - [ ] Functionality is preserved

### 6.3 Post-Migration Validation

- [ ] Code size reduced by 60-80%
- [ ] No duplicated logic with other exporters
- [ ] All shared infrastructure features working
- [ ] Interactive mode functional
- [ ] Loss side-car integration working
- [ ] Documentation updated

---

## Example Implementation

### 7.1 Minimal Exporter Example

```python
"""
wf2wf.exporters.example – Workflow IR ➜ Example Format

Minimal example showing the refactored exporter pattern.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Union

from wf2wf.core import Workflow, Task
from wf2wf.exporters.base import BaseExporter

logger = logging.getLogger(__name__)


class ExampleExporter(BaseExporter):
    """Example exporter using shared infrastructure."""
    
    def _get_target_format(self) -> str:
        """Get the target format name."""
        return "example"
    
    def _generate_output(self, workflow: Workflow, output_path: Path, **opts: Any) -> None:
        """Generate example format output."""
        if self.verbose:
            logger.info(f"Generating example format output: {output_path}")
        
        # Use shared infrastructure for environment-specific values
        for task in workflow.tasks.values():
            resources = self._get_task_resources_for_target(task)
            environment = self._get_task_environment_for_target(task)
            error_handling = self._get_task_error_handling_for_target(task)
            
            # Format-specific output generation logic here
            content = self._generate_task_content(task, resources, environment, error_handling)
        
        # Write output using shared file writing utilities
        self._write_file(content, output_path)
        
        if self.verbose:
            logger.info(f"✓ Example format workflow exported to {output_path}")
    
    def _generate_task_content(self, task: Task, resources: Dict[str, Any], 
                              environment: Dict[str, Any], error_handling: Dict[str, Any]) -> str:
        """Generate format-specific content - format-specific logic."""
        # Format-specific content generation
        pass


def from_workflow(wf: Workflow, out_file: Union[str, Path], **opts: Any) -> None:
    """Export workflow to example format using shared infrastructure."""
    exporter = ExampleExporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False)
    )
    exporter.export_workflow(wf, out_file, **opts)
```

### 7.2 Enhanced Exporter Example

```python
class EnhancedExampleExporter(BaseExporter):
    """Enhanced example exporter with format-specific features."""
    
    def _generate_output(self, workflow: Workflow, output_path: Path, **opts: Any) -> None:
        """Generate enhanced example format with advanced features."""
        # Basic output generation
        super()._generate_output(workflow, output_path, **opts)
        
        # Add format-specific enhancements
        self._generate_additional_files(workflow, output_path, **opts)
        self._enhance_format_specific_features(workflow, output_path, **opts)
    
    def _enhance_format_specific_features(self, workflow: Workflow, output_path: Path, **opts: Any):
        """Add format-specific enhancements not covered by shared infrastructure."""
        if self.verbose:
            logger.info("Adding format-specific enhancements...")
        
        # Format-specific logic here
        for task in workflow.tasks.values():
            # Add format-specific task enhancements
            self._add_format_specific_task_features(task, output_path, **opts)
    
    def _add_format_specific_task_features(self, task: Task, output_path: Path, **opts: Any):
        """Add format-specific features to a task."""
        # Format-specific task enhancements
        pass
```

---

## Benefits of This Architecture

### 8.1 Code Reduction

- **70-80% reduction** in exporter code size
- **Eliminated duplication** across all exporters
- **Easier maintenance** - bugs fixed once in shared code
- **Faster development** - new exporters can be added quickly

### 8.2 Enhanced Functionality

- **Consistent loss tracking** across all formats
- **Intelligent inference** fills in obvious missing information
- **Interactive mode** helps users complete incomplete workflows
- **Environment adaptation** for different execution environments
- **Better error handling** with consistent error messages

### 8.3 Improved User Experience

- **Interactive prompting** for missing information
- **Automatic inference** reduces manual configuration
- **Consistent behavior** across all exporters
- **Better error messages** with actionable suggestions
- **Loss transparency** - users see what information was lost

### 8.4 Future-Proofing

- **Extensible architecture** - easy to add new exporters
- **Plugin system** - third-party exporters can use shared infrastructure
- **Standardized interfaces** - consistent API across all exporters
- **Environment awareness** - ready for multi-environment IR

---

## Current State Analysis

### 8.5 Exporter Line Counts and Compliance Status

| Exporter | Lines | Status | Compliance | Notes |
|----------|-------|--------|------------|-------|
| **cwl.py** | 668 | ✅ **REFACTORED** | 95/100 | **REFERENCE** - Complex format, excellent shared infrastructure usage |
| **dagman.py** | 459 | ✅ **REFACTORED** | 90/100 | **EXCELLENT** - Good structure, excellent shared infrastructure usage |
| **snakemake.py** | 330 | ✅ **REFACTORED** | 90/100 | **EXCELLENT** - Clean structure, excellent shared infrastructure usage |
| **nextflow.py** | 469 | ✅ **REFACTORED** | 90/100 | **EXCELLENT** - Good structure, excellent shared infrastructure usage |
| **wdl.py** | 394 | ✅ **REFACTORED** | 85/100 | **EXCELLENT** - Good structure, good shared infrastructure usage |
| **galaxy.py** | 405 | ✅ **REFACTORED** | 85/100 | **EXCELLENT** - Good structure, good shared infrastructure usage |
| **bco.py** | 409 | ⚠️ **SPECIAL** | 70/100 | **SPECIAL CASE** - Standalone format, limited shared infrastructure usage |

### 8.6 Shared Infrastructure Files

| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| **base.py** | 319 | Base exporter class and comprehensive helper methods | ✅ **COMPLETE** |
| **inference.py** | 344 | Intelligent inference engine with format-specific rules | ✅ **COMPLETE** |
| **interactive.py** | 307 | Interactive prompting system with user-friendly interface | ✅ **COMPLETE** |
| **loss_integration.py** | 463 | Loss detection and recording with comprehensive coverage | ✅ **COMPLETE** |

---

## Conclusion

This specification provides a clear template for ensuring all exporters use the shared infrastructure effectively. The current state shows that most exporters are already well-refactored and compliant, with excellent use of shared infrastructure.

The architecture provides:

1. **Significant code reduction** through elimination of duplication
2. **Enhanced functionality** through shared intelligent inference
3. **Improved user experience** through interactive prompting
4. **Better maintainability** through standardized architecture
5. **Future-proofing** through extensible design

Most exporters are already following this pattern successfully, demonstrating that this approach works well and provides substantial benefits.

## Compliance Checklist

All exporters MUST:
- [ ] Inherit from BaseExporter
- [ ] NOT override export_workflow()
- [ ] Implement _get_target_format() and _generate_output()
- [ ] Use shared infrastructure for loss, inference, prompting, and environment handling
- [ ] Use comprehensive BaseExporter helper methods
- [ ] Place all format-specific logic in enhancement methods
- [ ] Pass all required and integration tests
- [ ] Maintain code size within recommended range (200-600 lines)
- [ ] Document any format-specific enhancements

## Prohibition of export_workflow() Override

**Exporters MUST NOT override export_workflow().**
All workflow orchestration, loss handling, inference, prompting, and validation must be handled by the shared BaseExporter workflow. Only format-specific output generation should be implemented in the exporter.

## Code Size Guidelines

- Recommended: 200-600 lines per exporter (depending on format complexity)
- Focus on format-specific output generation only

## Required Shared Infrastructure Usage

Exporters MUST use:
- Loss integration: detect_and_record_losses
- Inference: infer_missing_values
- Interactive prompting: prompt_for_missing_values
- Environment-specific values: _get_environment_specific_value
- Resource handling: _get_task_resources
- Environment handling: _get_task_environment
- Error handling: _get_task_error_handling
- File transfer: _get_task_file_transfer
- Advanced features: _get_task_advanced_features
- File writing: _write_file, _write_json, _write_yaml
- Name sanitization: _sanitize_name
- Metadata extraction: _get_task_metadata, _get_workflow_metadata
- Loss recording: _record_loss_if_present

## Required Testing Requirements

- All exporters must have unit tests for output generation
- All exporters must pass integration and roundtrip tests
- All shared infrastructure features must be tested
- All helper method usage must be tested

## Reference Implementations

- **CWL Exporter:** 95/100 (Reference, fully compliant, complex format)
- **DAGMan Exporter:** 90/100 (Reference, fully compliant)
- **Snakemake Exporter:** 90/100 (Reference, fully compliant)
- **Nextflow Exporter:** 90/100 (Reference, fully compliant)
- **WDL Exporter:** 85/100 (Reference, fully compliant)
- **Galaxy Exporter:** 85/100 (Reference, fully compliant)
- **BCO Exporter:** 70/100 (Special case, standalone format) 