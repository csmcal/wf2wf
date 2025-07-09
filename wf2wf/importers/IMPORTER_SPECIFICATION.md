# Importer Specification Template

**Based on lessons learned from Snakemake importer refactor**

This document defines the standard architecture and patterns that all importers should follow after the comprehensive refactor to eliminate duplication and leverage shared infrastructure.

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

All importers MUST inherit from `BaseImporter` and follow this structure:

```python
class FormatImporter(BaseImporter):
    """Format-specific importer using shared infrastructure."""
    
    def _parse_source(self, path: Path, **opts) -> Dict[str, Any]:
        """Parse format-specific content - REQUIRED IMPLEMENTATION."""
        # Format-specific parsing logic only
        # Return structured data for workflow creation
        pass
    
    def _create_basic_workflow(self, parsed_data: Dict[str, Any]) -> Workflow:
        """Create basic workflow from parsed data - OPTIONAL OVERRIDE."""
        # Default implementation in BaseImporter is usually sufficient
        # Override only if format-specific workflow creation is needed
        pass
    
    def _extract_tasks(self, parsed_data: Dict[str, Any]) -> List[Task]:
        """Extract tasks from parsed data - OPTIONAL OVERRIDE."""
        # Default implementation in BaseImporter is usually sufficient
        # Override only if format-specific task extraction is needed
        pass
    
    def _extract_edges(self, parsed_data: Dict[str, Any]) -> List[Edge]:
        """Extract edges from parsed data - OPTIONAL OVERRIDE."""
        # Default implementation in BaseImporter is usually sufficient
        # Override only if format-specific edge extraction is needed
        pass
    
    def _get_source_format(self) -> str:
        """Get the source format name - REQUIRED IMPLEMENTATION."""
        return "format_name"
```

### 1.2 Workflow Integration

The `import_workflow()` method in `BaseImporter` provides the unified workflow:

```python
def import_workflow(self, path: Path, **opts) -> Workflow:
    """
    Enhanced import method with shared infrastructure integration.
    
    This method provides:
    1. Source parsing via _parse_source()
    2. Basic workflow creation via _create_basic_workflow()
    3. Loss side-car integration
    4. Intelligent inference using shared infrastructure
    5. Interactive prompting when enabled
    6. Environment management
    7. Validation and return
    """
```

**DO NOT OVERRIDE** this method unless absolutely necessary. The shared workflow handles:
- Loss side-car detection and application
- Intelligent inference of missing information
- Interactive prompting for missing data
- Environment adaptation
- Validation and error handling

---

## Required Methods

### 2.1 _parse_source() - REQUIRED

This is the ONLY method that MUST be implemented by each importer:

```python
def _parse_source(self, path: Path, **opts) -> Dict[str, Any]:
    """
    Parse format-specific content and return structured data.
    
    This method should:
    1. Parse the source file(s) using format-specific logic
    2. Extract all relevant information (tasks, edges, resources, etc.)
    3. Return a structured dictionary that can be used by shared infrastructure
    
    Returns:
        Dict containing all parsed information with standard keys:
        - tasks: List[Dict] - Task definitions
        - edges: List[Dict] - Edge definitions  
        - metadata: Dict - Format-specific metadata
        - resources: Dict - Resource specifications
        - environments: Dict - Environment specifications
        - etc.
    """
```

### 2.2 _get_source_format() - REQUIRED

```python
def _get_source_format(self) -> str:
    """Return the source format name for shared infrastructure."""
    return "format_name"  # e.g., "snakemake", "cwl", "dagman"
```

---

## Shared Infrastructure Usage

### 3.1 What to Use from Shared Infrastructure

**ALWAYS USE** these shared components:

1. **Loss Integration**: `detect_and_apply_loss_sidecar()` from `loss_integration.py`
2. **Inference Engine**: `infer_environment_specific_values()` from `inference.py`
3. **Interactive Prompting**: `prompt_for_missing_information()` from `interactive.py`
4. **Execution Model Detection**: `infer_execution_model()` from `inference.py`
5. **Resource Processing**: `process_workflow_resources()` from `resource_processor.py`
6. **Environment Management**: `EnvironmentManager` from `environ.py`

### 3.2 What NOT to Duplicate

**NEVER IMPLEMENT** these in individual importers:

1. ❌ Resource inference logic
2. ❌ Environment inference logic  
3. ❌ Error handling inference logic
4. ❌ Execution model detection logic
5. ❌ Interactive prompting logic
6. ❌ Loss side-car handling logic
7. ❌ Environment management logic
8. ❌ Validation logic (beyond format-specific validation)

### 3.3 Format-Specific Enhancements

Only implement format-specific logic that isn't covered by shared infrastructure:

```python
def _enhance_format_specific_features(self, workflow: Workflow, parsed_data: Dict[str, Any]):
    """Add format-specific enhancements not covered by shared infrastructure."""
    
    # Examples of format-specific logic:
    # - Snakemake: Wildcard processing, threads handling
    # - CWL: Expression evaluation, secondary files
    # - Nextflow: Channel analysis, module support
    # - DAGMan: Inline submit parsing, HTCondor attributes
```

---

## Code Organization

### 4.1 File Structure

```
wf2wf/importers/
├── base.py                    # Base importer class (shared)
├── inference.py               # Intelligent inference engine (shared)
├── interactive.py             # Interactive prompting system (shared)
├── loss_integration.py        # Loss side-car integration (shared)
├── resource_processor.py      # Resource processing (shared)
├── utils.py                   # Shared utilities (shared)
├── format_importer.py         # Format-specific importer
└── IMPORTER_SPECIFICATION.md  # This specification
```

### 4.2 Code Size Guidelines

After refactoring, importers should be:

- **Small**: 200-500 lines (down from 1000+ lines)
- **Focused**: Only format-specific parsing logic
- **Maintainable**: Clear separation of concerns
- **Testable**: Easy to unit test individual components

### 4.3 Import Statements

```python
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from wf2wf.core import Workflow, Task, Edge, EnvironmentSpecificValue
from wf2wf.importers.base import BaseImporter
from wf2wf.importers.loss_integration import detect_and_apply_loss_sidecar
from wf2wf.importers.inference import infer_environment_specific_values, infer_execution_model
from wf2wf.importers.interactive import prompt_for_missing_information
from wf2wf.importers.utils import parse_file_format, extract_resource_specifications

logger = logging.getLogger(__name__)
```

---

## Testing Requirements

### 5.1 Test Structure

```python
# tests/test_importers/test_format_importer.py

class TestFormatImporter:
    """Test format-specific importer functionality."""
    
    def test_parse_source(self):
        """Test _parse_source method."""
        pass
    
    def test_create_basic_workflow(self):
        """Test workflow creation from parsed data."""
        pass
    
    def test_extract_tasks(self):
        """Test task extraction."""
        pass
    
    def test_extract_edges(self):
        """Test edge extraction."""
        pass
    
    def test_loss_sidecar_integration(self):
        """Test loss side-car integration."""
        pass
    
    def test_inference_integration(self):
        """Test intelligent inference integration."""
        pass
    
    def test_interactive_mode(self):
        """Test interactive prompting."""
        pass
```

### 5.2 Integration Tests

```python
# tests/test_integration/test_format_roundtrip.py

def test_format_import_and_roundtrip():
    """Test complete import and round-trip conversion."""
    pass

def test_format_to_dagman():
    """Test format to DAGMan conversion."""
    pass
```

---

## Migration Checklist

### 6.1 Pre-Migration Analysis

- [ ] Identify duplicated logic in current importer
- [ ] Map format-specific vs. shared functionality
- [ ] Identify format-specific enhancements needed
- [ ] Plan test coverage for refactored components

### 6.2 Migration Steps

1. **Create new importer class**:
   - [ ] Inherit from `BaseImporter`
   - [ ] Implement `_parse_source()` method
   - [ ] Implement `_get_source_format()` method
   - [ ] Add format-specific enhancements if needed

2. **Remove duplicated logic**:
   - [ ] Remove resource inference methods
   - [ ] Remove environment inference methods
   - [ ] Remove error handling inference methods
   - [ ] Remove execution model detection methods
   - [ ] Remove interactive prompting methods
   - [ ] Remove loss side-car handling methods

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
- [ ] No duplicated logic with other importers
- [ ] All shared infrastructure features working
- [ ] Interactive mode functional
- [ ] Loss side-car integration working
- [ ] Documentation updated

---

## Example Implementation

### 7.1 Minimal Importer Example

```python
"""
wf2wf.importers.example – Example Format ➜ Workflow IR

Minimal example showing the refactored importer pattern.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from wf2wf.core import Workflow, Task, Edge
from wf2wf.importers.base import BaseImporter

logger = logging.getLogger(__name__)


class ExampleImporter(BaseImporter):
    """Example importer using shared infrastructure."""
    
    def _parse_source(self, path: Path, **opts) -> Dict[str, Any]:
        """Parse example format file and extract information."""
        if self.verbose:
            logger.info(f"Parsing example file: {path}")
        
        # Format-specific parsing logic here
        content = path.read_text()
        
        # Extract tasks, edges, resources, etc.
        tasks = self._parse_tasks(content)
        edges = self._parse_edges(content)
        resources = self._parse_resources(content)
        
        return {
            "tasks": tasks,
            "edges": edges,
            "resources": resources,
            "metadata": {
                "source_format": "example",
                "source_file": str(path),
                "parsing_notes": []
            }
        }
    
    def _get_source_format(self) -> str:
        """Get the source format name."""
        return "example"
    
    def _parse_tasks(self, content: str) -> List[Dict[str, Any]]:
        """Parse tasks from content - format-specific logic."""
        # Format-specific task parsing
        pass
    
    def _parse_edges(self, content: str) -> List[Dict[str, Any]]:
        """Parse edges from content - format-specific logic."""
        # Format-specific edge parsing
        pass
    
    def _parse_resources(self, content: str) -> Dict[str, Any]:
        """Parse resources from content - format-specific logic."""
        # Format-specific resource parsing
        pass


def to_workflow(path: Union[str, Path], **opts) -> Workflow:
    """Convert example file to Workflow IR using shared infrastructure."""
    importer = ExampleImporter(
        interactive=opts.get("interactive", False),
        verbose=opts.get("verbose", False)
    )
    return importer.import_workflow(path, **opts)
```

### 7.2 Enhanced Importer Example

```python
class EnhancedExampleImporter(BaseImporter):
    """Enhanced example importer with format-specific features."""
    
    def _parse_source(self, path: Path, **opts) -> Dict[str, Any]:
        """Parse enhanced example format with advanced features."""
        # Basic parsing
        parsed_data = super()._parse_source(path, **opts)
        
        # Add format-specific enhancements
        parsed_data["format_specific"] = {
            "advanced_features": self._parse_advanced_features(path),
            "custom_metadata": self._parse_custom_metadata(path)
        }
        
        return parsed_data
    
    def _enhance_format_specific_features(self, workflow: Workflow, parsed_data: Dict[str, Any]):
        """Add format-specific enhancements not covered by shared infrastructure."""
        if self.verbose:
            logger.info("Adding format-specific enhancements...")
        
        # Format-specific logic here
        for task in workflow.tasks.values():
            # Add format-specific task enhancements
            self._add_format_specific_task_features(task, parsed_data)
    
    def _add_format_specific_task_features(self, task: Task, parsed_data: Dict[str, Any]):
        """Add format-specific features to a task."""
        # Format-specific task enhancements
        pass
```

---

## Benefits of This Architecture

### 8.1 Code Reduction

- **70-80% reduction** in importer code size
- **Eliminated duplication** across all importers
- **Easier maintenance** - bugs fixed once in shared code
- **Faster development** - new importers can be added quickly

### 8.2 Enhanced Functionality

- **Consistent loss side-car handling** across all formats
- **Intelligent inference** fills in obvious missing information
- **Interactive mode** helps users complete incomplete workflows
- **Environment adaptation** for different execution environments
- **Better error handling** with consistent error messages

### 8.3 Improved User Experience

- **Interactive prompting** for missing information
- **Automatic inference** reduces manual configuration
- **Consistent behavior** across all importers
- **Better error messages** with actionable suggestions
- **Loss transparency** - users see what information was lost

### 8.4 Future-Proofing

- **Extensible architecture** - easy to add new importers
- **Plugin system** - third-party importers can use shared infrastructure
- **Standardized interfaces** - consistent API across all importers
- **Environment awareness** - ready for multi-environment IR

---

## Conclusion

This specification provides a clear template for refactoring all importers to use the shared infrastructure. By following this pattern, we can achieve:

1. **Significant code reduction** through elimination of duplication
2. **Enhanced functionality** through shared intelligent inference
3. **Improved user experience** through interactive prompting
4. **Better maintainability** through standardized architecture
5. **Future-proofing** through extensible design

The Snakemake refactor demonstrated that this approach works well and provides substantial benefits. All other importers should follow the same pattern to achieve similar improvements. 

## Compliance Checklist

All importers MUST:
- [ ] Inherit from BaseImporter
- [ ] NOT override import_workflow()
- [ ] Implement _parse_source() and _get_source_format()
- [ ] Use shared infrastructure for loss, inference, prompting, environment, and resource management
- [ ] Place all format-specific logic in enhancement methods (e.g., _enhance_format_specific_features)
- [ ] Pass all required and integration tests
- [ ] Maintain code size within recommended range (200-800 lines)
- [ ] Document any format-specific enhancements

## Prohibition of import_workflow() Override

**Importers MUST NOT override import_workflow().**
All workflow orchestration, loss handling, inference, prompting, and validation must be handled by the shared BaseImporter workflow. Only format-specific parsing and enhancement methods should be implemented in the importer.

## Code Size Guidelines

- Recommended: 200-800 lines per importer (not enforced, but for maintainability)
- Focus on format-specific parsing and enhancement only

## Required Shared Infrastructure Usage

Importers MUST use:
- Loss integration: detect_and_apply_loss_sidecar
- Inference: infer_environment_specific_values, infer_execution_model
- Interactive prompting: prompt_for_missing_information
- Resource processing: process_workflow_resources
- Environment management: EnvironmentManager

## Required Testing Requirements

- All importers must have unit tests for parsing, workflow creation, and enhancement methods
- All importers must pass integration and roundtrip tests
- All shared infrastructure features must be tested in at least one importer

## Compliance Validation Tool

A compliance validation tool will be provided to check:
- Inheritance and method overrides
- Shared infrastructure usage
- Code size
- Test coverage
- Compliance with this specification

## Reference Implementations

- **DAGMan Importer:** 95/100 (Reference, fully compliant)
- **CWL Importer:** 85/100 (Reference, minor improvements possible)
- **Snakemake Importer:** 90/100 (Reference, now fully compliant after refactor) 