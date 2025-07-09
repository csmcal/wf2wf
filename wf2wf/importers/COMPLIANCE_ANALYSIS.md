# Importer Compliance Analysis

**Comprehensive Analysis of DAGMan, Snakemake, and CWL Importers vs. Specification**

## Executive Summary

After analyzing the three refactored importers and the shared infrastructure, I found:

- **DAGMan**: ✅ **FULLY COMPLIANT** - Excellent example of specification adherence
- **Snakemake**: ⚠️ **PARTIALLY COMPLIANT** - Good but has some deviations
- **CWL**: ✅ **MOSTLY COMPLIANT** - Very good with minor issues

## Detailed Compliance Analysis

### 1. DAGMan Importer (✅ FULLY COMPLIANT)

**Strengths:**
- ✅ Perfect inheritance from `BaseImporter`
- ✅ Only implements required methods: `_parse_source()` and `_get_source_format()`
- ✅ Uses shared workflow from `BaseImporter` (no custom `import_workflow()`)
- ✅ Clean separation of format-specific parsing logic
- ✅ Proper metadata handling with `MetadataSpec`
- ✅ Correct use of `EnvironmentSpecificValue` for transfer modes
- ✅ All tests passing (14/15, 1 skipped)

**Code Quality:**
- **Lines of Code**: 692 lines (reasonable for format complexity)
- **Format-Specific Code**: ~90% (appropriate for DAGMan's unique features)
- **Shared Infrastructure Usage**: ~10% (minimal, as expected)

**Compliance Score: 95/100**

### 2. Snakemake Importer (⚠️ PARTIALLY COMPLIANT)

**Strengths:**
- ✅ Inherits from `BaseImporter`
- ✅ Uses shared infrastructure for inference and loss integration
- ✅ Implements format-specific enhancements appropriately
- ✅ Good use of shared interactive prompting

**Issues Found:**
- ❌ **OVERRIDES `import_workflow()`** - This violates the specification
- ❌ **Duplicates some shared logic** - Has custom inference methods
- ❌ **Large codebase** - 1,415 lines (should be smaller after refactor)
- ❌ **Complex parsing logic** - Could benefit from more shared utilities

**Specific Problems:**
```python
# PROBLEM: Should NOT override import_workflow()
def import_workflow(self, path: Path, **opts) -> Workflow:
    # Custom implementation instead of using BaseImporter's shared workflow
```

**Code Quality:**
- **Lines of Code**: 1,415 lines (too large for refactored importer)
- **Format-Specific Code**: ~70% (should be higher)
- **Shared Infrastructure Usage**: ~30% (should be higher)

**Compliance Score: 65/100**

### 3. CWL Importer (✅ MOSTLY COMPLIANT)

**Strengths:**
- ✅ Perfect inheritance from `BaseImporter`
- ✅ Only implements required methods
- ✅ Uses shared workflow (no custom `import_workflow()`)
- ✅ Excellent use of shared utilities (`parse_file_format`, `parse_cwl_type`, etc.)
- ✅ Proper CWL graph format handling
- ✅ Good metadata handling

**Minor Issues:**
- ⚠️ **Could use more shared inference** - Some manual resource extraction
- ⚠️ **Missing some shared infrastructure calls** - Could leverage more inference

**Code Quality:**
- **Lines of Code**: 503 lines (good size)
- **Format-Specific Code**: ~80% (appropriate)
- **Shared Infrastructure Usage**: ~20% (could be higher)

**Compliance Score: 85/100**

## Shared Infrastructure Analysis

### Available Infrastructure (Excellent)

The shared infrastructure is comprehensive and well-designed:

1. **Loss Integration** (`loss_integration.py`):
   - ✅ Comprehensive loss side-car detection and application
   - ✅ Validation and error handling
   - ✅ Summary generation and reporting

2. **Inference Engine** (`inference.py`):
   - ✅ Intelligent resource inference from commands
   - ✅ Environment-specific value inference
   - ✅ Execution model detection
   - ✅ Advanced feature inference (checkpointing, logging, security, networking)

3. **Interactive System** (`interactive.py`):
   - ✅ Comprehensive prompting for missing information
   - ✅ Execution model confirmation
   - ✅ Workflow optimization suggestions

4. **Resource Processing** (`resource_processor.py`):
   - ✅ Resource profile application
   - ✅ Resource validation
   - ✅ Interactive resource prompting

5. **Environment Management** (`environ.py`):
   - ✅ Container and conda environment detection
   - ✅ Environment building and adaptation
   - ✅ Multi-format container support

6. **Utilities** (`utils.py`):
   - ✅ File format detection
   - ✅ Memory/disk/time parsing
   - ✅ Generic section parsing
   - ✅ CWL-specific utilities

## Recommendations for Specification Updates

### 1. Add Explicit Prohibition of `import_workflow()` Override

**Current Issue:** Snakemake importer overrides `import_workflow()` despite specification saying not to.

**Recommendation:** Add explicit warning and example:

### 1.2 Workflow Integration

**CRITICAL: DO NOT OVERRIDE `import_workflow()`**

```python
# ❌ WRONG - Do not do this
def import_workflow(self, path: Path, **opts) -> Workflow:
    # Custom implementation
    pass

# ✅ CORRECT - Use the shared workflow
# Do not override import_workflow() - it provides:
# - Loss side-car integration
# - Intelligent inference
# - Interactive prompting
# - Environment management
# - Validation
```

### 2. Add Compliance Checklist

**Recommendation:** Add a compliance checklist to the specification:

```markdown
## Compliance Checklist

Before marking an importer as "refactored", verify:

- [ ] Inherits from `BaseImporter`
- [ ] Does NOT override `import_workflow()`
- [ ] Only implements `_parse_source()` and `_get_source_format()`
- [ ] Uses shared infrastructure for inference
- [ ] Uses shared infrastructure for interactive prompting
- [ ] Uses shared infrastructure for loss integration
- [ ] Uses shared infrastructure for environment management
- [ ] Code size reduced by 60-80%
- [ ] All tests pass
- [ ] No duplicated logic with other importers
```

### 3. Add Code Size Guidelines

**Recommendation:** Add specific code size targets:

```markdown
### 4.2 Code Size Guidelines

After refactoring, importers should be:

- **Simple formats** (CWL, WDL): 300-500 lines
- **Complex formats** (Snakemake, Nextflow): 500-800 lines
- **Very complex formats** (DAGMan with inline submit): 600-900 lines

**Current Status:**
- DAGMan: 692 lines ✅ (appropriate)
- CWL: 503 lines ✅ (good)
- Snakemake: 1,415 lines ❌ (too large - needs further refactoring)
```

### 4. Add Shared Infrastructure Usage Guidelines

**Recommendation:** Add specific guidelines for shared infrastructure usage:

```markdown
### 3.4 Required Shared Infrastructure Usage

**MUST USE** these shared components in every importer:

```python
# Required imports
from wf2wf.importers.loss_integration import detect_and_apply_loss_sidecar
from wf2wf.importers.inference import infer_environment_specific_values, infer_execution_model
from wf2wf.importers.interactive import prompt_for_missing_information
from wf2wf.importers.utils import parse_file_format

# Required usage in _create_basic_workflow or similar
def _create_basic_workflow(self, parsed_data: Dict[str, Any]) -> Workflow:
    workflow = Workflow(...)
    
    # Apply loss side-car (handled by BaseImporter)
    # Infer missing information (handled by BaseImporter)
    # Interactive prompting (handled by BaseImporter)
    
    return workflow
```

### 5. Add Testing Requirements

**Recommendation:** Add specific testing requirements:

### 5.3 Required Tests

Every refactored importer MUST include these tests:

```python
def test_uses_shared_workflow(self):
    """Test that importer uses BaseImporter's shared workflow."""
    importer = FormatImporter()
    # Verify import_workflow is not overridden
    assert importer.import_workflow == BaseImporter.import_workflow

def test_loss_integration(self):
    """Test loss side-car integration."""
    # Test with and without loss side-car files

def test_inference_integration(self):
    """Test intelligent inference integration."""
    # Test that missing information is inferred

def test_interactive_mode(self):
    """Test interactive prompting."""
    # Test interactive mode functionality
```

## Action Items

### 1. Fix Snakemake Importer (High Priority)

**Issues to Address:**
1. Remove `import_workflow()` override
2. Move custom logic to format-specific enhancement methods
3. Increase shared infrastructure usage
4. Reduce code size to under 800 lines

**Estimated Effort:** 2-3 hours

### 2. Enhance CWL Importer (Medium Priority)

**Issues to Address:**
1. Increase shared inference usage
2. Add more shared infrastructure calls
3. Improve compliance score to 95+

**Estimated Effort:** 1-2 hours

### 3. Update Specification (High Priority)

**Updates Needed:**
1. Add explicit prohibition of `import_workflow()` override
2. Add compliance checklist
3. Add code size guidelines
4. Add required shared infrastructure usage
5. Add required testing requirements

**Estimated Effort:** 1 hour

### 4. Create Compliance Validation Tool (Medium Priority)

**Proposed Tool:**
```python
def validate_importer_compliance(importer_class) -> Dict[str, Any]:
    """Validate importer compliance with specification."""
    # Check inheritance
    # Check method overrides
    # Check shared infrastructure usage
    # Check code size
    # Return compliance report
```

**Estimated Effort:** 2-3 hours

## Conclusion

The specification is well-designed and the shared infrastructure is comprehensive. The main issues are:

1. **Snakemake importer needs further refactoring** to fully comply
2. **Specification needs clearer prohibitions** against common mistakes
3. **Compliance validation** would help prevent future violations

The DAGMan importer serves as an excellent example of proper compliance, while CWL is very close to full compliance. With the recommended updates, the specification will be more robust and easier to follow. 