# Importer Comparison Template

**Before/After Analysis Based on Snakemake Refactor**

This document provides a template for comparing the state of each importer before and after refactoring to use shared infrastructure.

## Comparison Metrics

### Code Metrics
- **Lines of Code**: Total lines before vs. after
- **Duplicated Methods**: Number of methods that duplicate shared functionality
- **Shared Infrastructure Usage**: Percentage of functionality using shared components
- **Format-Specific Code**: Percentage of code that is truly format-specific

### Functionality Metrics
- **Features Preserved**: All existing functionality maintained
- **New Features Added**: Enhanced functionality through shared infrastructure
- **Test Coverage**: Test coverage maintained or improved
- **Performance**: Performance equivalent or better

---

## Snakemake Importer (REFERENCE IMPLEMENTATION)

### Before Refactor
- **Lines of Code**: ~1,269 lines
- **Duplicated Methods**: 4 major methods
  - `_detect_snakemake_execution_model()` (lines 106-130)
  - `_infer_snakemake_resources()` (lines 131-154)
  - `_infer_snakemake_environments()` (lines 155-171)
  - `_infer_snakemake_error_handling()` (lines 172-181)
- **Shared Infrastructure Usage**: ~20%
- **Format-Specific Code**: ~80%

### After Refactor
- **Lines of Code**: ~1,414 lines (includes enhanced features)
- **Duplicated Methods**: 0 (all removed)
- **Shared Infrastructure Usage**: ~70%
- **Format-Specific Code**: ~30%

### Key Changes
✅ **Removed Duplication**:
- Eliminated 4 duplicated inference methods
- Replaced with shared infrastructure calls
- Removed duplicated resource pattern analysis

✅ **Enhanced Functionality**:
- Added loss side-car integration
- Added intelligent inference
- Added interactive prompting
- Added environment adaptation

✅ **Improved Architecture**:
- Proper inheritance from BaseImporter
- Clear separation of concerns
- Better maintainability

---

## Template for Other Importers

### [FORMAT] Importer

#### Before Refactor
- **Lines of Code**: [X] lines
- **Duplicated Methods**: [List of duplicated methods]
- **Shared Infrastructure Usage**: [X]%
- **Format-Specific Code**: [X]%

#### After Refactor (Target)
- **Lines of Code**: [X] lines (target: 200-500)
- **Duplicated Methods**: 0 (all removed)
- **Shared Infrastructure Usage**: ~70%
- **Format-Specific Code**: ~30%

#### Migration Plan
1. **Phase 1**: Identify duplicated logic
   - [ ] Resource inference methods
   - [ ] Environment inference methods
   - [ ] Error handling inference methods
   - [ ] Execution model detection methods
   - [ ] Interactive prompting methods
   - [ ] Loss side-car handling methods

2. **Phase 2**: Implement new architecture
   - [ ] Inherit from BaseImporter
   - [ ] Implement _parse_source() method
   - [ ] Implement _get_source_format() method
   - [ ] Remove duplicated methods
   - [ ] Add format-specific enhancements

3. **Phase 3**: Integration and testing
   - [ ] All existing tests pass
   - [ ] New tests for shared infrastructure
   - [ ] Performance validation
   - [ ] Documentation updates

---

## Detailed Comparison Template

### [FORMAT] Importer - Detailed Analysis

#### Current State (Before Refactor)

**File**: `wf2wf/importers/[format].py`

**Code Statistics**:
- Total lines: [X]
- Methods: [X]
- Classes: [X]
- Functions: [X]

**Duplicated Methods Identified**:
```python
# List of methods that duplicate shared functionality
def _infer_[format]_resources(self, workflow: Workflow) -> None:
    # This duplicates infer_environment_specific_values() from inference.py
    pass

def _detect_[format]_execution_model(self, workflow: Workflow) -> str:
    # This duplicates infer_execution_model() from inference.py
    pass

def _infer_[format]_environments(self, workflow: Workflow) -> None:
    # This duplicates _infer_environment_isolation() from inference.py
    pass

def _infer_[format]_error_handling(self, workflow: Workflow) -> None:
    # This duplicates _infer_error_handling() from inference.py
    pass
```

**Format-Specific Logic**:
```python
# List of truly format-specific methods that should remain
def _parse_[format]_specific_content(self, content: str) -> Dict[str, Any]:
    # Format-specific parsing logic
    pass

def _extract_[format]_specific_features(self, data: Dict[str, Any]) -> List[Any]:
    # Format-specific feature extraction
    pass
```

#### Target State (After Refactor)

**File**: `wf2wf/importers/[format].py`

**Code Statistics**:
- Total lines: [X] (target: 200-500)
- Methods: [X] (reduced by ~60-80%)
- Classes: 1 (FormatImporter)
- Functions: [X] (format-specific utilities only)

**New Architecture**:
```python
class [Format]Importer(BaseImporter):
    """[Format] importer using shared infrastructure."""
    
    def _parse_source(self, path: Path, **opts) -> Dict[str, Any]:
        """Parse [format] file and extract all information."""
        # Format-specific parsing logic only
        pass
    
    def _get_source_format(self) -> str:
        """Get the source format name."""
        return "[format]"
    
    def _enhance_[format]_specific_features(self, workflow: Workflow, parsed_data: Dict[str, Any]):
        """Add [format]-specific enhancements not covered by shared infrastructure."""
        # Only format-specific logic that isn't covered by shared infrastructure
        pass
```

**Shared Infrastructure Integration**:
```python
# Uses shared infrastructure for all common functionality
from wf2wf.importers.loss_integration import detect_and_apply_loss_sidecar
from wf2wf.importers.inference import infer_environment_specific_values, infer_execution_model
from wf2wf.importers.interactive import prompt_for_missing_information
```

---

## Migration Checklist Template

### [FORMAT] Importer Migration Checklist

#### Pre-Migration Analysis
- [ ] **Code Analysis**: Identify all duplicated methods and logic
- [ ] **Feature Mapping**: Map format-specific vs. shared functionality
- [ ] **Test Coverage**: Ensure comprehensive test coverage exists
- [ ] **Performance Baseline**: Establish performance baseline

#### Migration Implementation
- [ ] **Create New Class**: Implement FormatImporter inheriting from BaseImporter
- [ ] **Implement Required Methods**: _parse_source() and _get_source_format()
- [ ] **Remove Duplicated Methods**: Delete all duplicated inference methods
- [ ] **Add Format-Specific Enhancements**: Implement format-specific logic only
- [ ] **Update Imports**: Import shared infrastructure modules
- [ ] **Update Dependencies**: Remove format-specific utility functions

#### Testing and Validation
- [ ] **Unit Tests**: All existing unit tests pass
- [ ] **Integration Tests**: All integration tests pass
- [ ] **New Tests**: Tests for shared infrastructure integration
- [ ] **Performance Tests**: Performance is equivalent or better
- [ ] **Functionality Tests**: All features preserved and enhanced

#### Documentation and Cleanup
- [ ] **Update Documentation**: Update importer documentation
- [ ] **Remove Dead Code**: Remove unused methods and functions
- [ ] **Update Examples**: Update examples to use new architecture
- [ ] **Code Review**: Complete code review of refactored importer

#### Post-Migration Validation
- [ ] **Code Metrics**: Verify code size reduction (60-80%)
- [ ] **Duplication Check**: Verify no duplicated logic remains
- [ ] **Shared Infrastructure**: Verify all shared features working
- [ ] **User Experience**: Verify improved user experience
- [ ] **Maintainability**: Verify improved maintainability

---

## Success Metrics Template

### [FORMAT] Importer Success Metrics

#### Code Quality Metrics
- [ ] **Code Reduction**: [X]% reduction in total lines
- [ ] **Duplication Elimination**: 100% of duplicated methods removed
- [ ] **Shared Infrastructure Usage**: [X]% of functionality uses shared components
- [ ] **Format-Specific Focus**: [X]% of code is truly format-specific

#### Functionality Metrics
- [ ] **Feature Preservation**: 100% of existing features preserved
- [ ] **New Features**: [X] new features added through shared infrastructure
- [ ] **Test Coverage**: [X]% test coverage maintained or improved
- [ ] **Performance**: Performance equivalent or better

#### User Experience Metrics
- [ ] **Interactive Mode**: Interactive prompting works correctly
- [ ] **Loss Transparency**: Loss side-car integration works
- [ ] **Error Handling**: Improved error messages and handling
- [ ] **Consistency**: Behavior consistent with other importers

#### Maintainability Metrics
- [ ] **Code Maintainability**: Improved maintainability score
- [ ] **Bug Reduction**: Reduced potential for bugs through shared code
- [ ] **Development Speed**: Faster development of new features
- [ ] **Documentation Quality**: Improved documentation quality

---

## Implementation Timeline Template

### [FORMAT] Importer Implementation Timeline

#### Week 1: Analysis and Planning
- [ ] Complete code analysis and duplication identification
- [ ] Create detailed migration plan
- [ ] Set up testing infrastructure
- [ ] Establish performance baselines

#### Week 2: Core Implementation
- [ ] Implement new FormatImporter class
- [ ] Implement _parse_source() method
- [ ] Remove duplicated methods
- [ ] Add format-specific enhancements

#### Week 3: Integration and Testing
- [ ] Integrate with shared infrastructure
- [ ] Update all tests
- [ ] Performance testing and optimization
- [ ] Bug fixes and refinements

#### Week 4: Documentation and Cleanup
- [ ] Update documentation
- [ ] Code cleanup and review
- [ ] Final testing and validation
- [ ] Deployment and monitoring

---

## Conclusion

This comparison template provides a systematic approach to refactoring all importers based on the successful Snakemake refactor. By following this template, we can ensure:

1. **Consistent Architecture**: All importers follow the same pattern
2. **Eliminated Duplication**: No duplicated logic across importers
3. **Enhanced Functionality**: All importers benefit from shared features
4. **Improved Maintainability**: Easier to maintain and extend
5. **Better User Experience**: Consistent behavior across all formats

The Snakemake refactor serves as the reference implementation, demonstrating that this approach works well and provides substantial benefits. All other importers should follow the same pattern to achieve similar improvements. 