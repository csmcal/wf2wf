# Importer Assessment and Refactoring To-Do List

## Overview
This document tracks the assessment and refactoring of all importers in the wf2wf project to use the new shared infrastructure, intelligent inference, and comprehensive loss side-car integration.

## Assessment Criteria for Each Importer

### 1. Code Duplication Analysis
- [ ] How much code could be moved to shared infrastructure
- [ ] Current inheritance from BaseImporter
- [ ] Use of shared workflow pattern
- [ ] Duplication of common parsing patterns

### 2. Loss Side-Car Integration
- [ ] Current support for loss side-car
- [ ] Calls to `detect_and_apply_loss_sidecar()`
- [ ] Loss tracking during export
- [ ] Integration with loss reporting

### 3. Intelligent Inference
- [ ] What missing information could be auto-filled
- [ ] Use of `infer_environment_specific_values()`
- [ ] Use of `infer_execution_model()`
- [ ] Use of inference engine
- [ ] Environment-specific value inference
- [ ] Resource requirement inference

### 4. Interactive Mode
- [ ] What user prompting could be added
- [ ] Use of `prompt_for_missing_information()`
- [ ] Interactive environment adaptation
- [ ] User confirmation for lossy conversions
- [ ] Current interactive prompting support
- [ ] User prompting for missing information
- [ ] Environment adaptation prompting
- [ ] Execution model confirmation

### 5. Environment Management
- [ ] Integration with EnvironmentManager
- [ ] Multi-environment support
- [ ] Environment detection and parsing
- [ ] Container/conda environment handling
- [ ] Environment adaptation for target formats
- [ ] Container and conda environment handling
- [ ] Environment building and management

### 6. Error Handling and Validation
- [ ] Consistent error handling patterns
- [ ] Schema validation integration
- [ ] Graceful degradation
- [ ] User-friendly error messages

### 6. Execution Model Detection
- [ ] Automatic execution model detection
- [ ] Content-based analysis
- [ ] Transition analysis between models
- [ ] Interactive confirmation

---

## Importer Assessment Status

### ✅ **Snakemake Importer** (1,273 lines) - **COMPLETED**
- **Status**: Already refactored to use BaseImporter infrastructure
- **Assessment**: ✅ **EXCELLENT** - Most mature implementation
- **Next Steps**: Add loss side-car integration, enhance interactive mode

### 🔄 **CWL Importer** (1,254 lines) - **IN PROGRESS**
- **Status**: Recently refactored, basic loss side-car support
- **Assessment**: ✅ **GOOD** - Advanced CWL features, needs enhancement
- **Next Steps**: Complete loss side-car integration, enhance inference

### ⏳ **DAGMan Importer** (663 lines) - **PENDING**
- **Status**: Traditional DAGMan parsing, inline submit support
- **Assessment**: ⚠️ **NEEDS REFACTOR** - Not using BaseImporter
- **Next Steps**: Refactor to use BaseImporter, add loss side-car support

### ⏳ **Nextflow Importer** (716 lines) - **PENDING**
- **Status**: Nextflow DSL2 parsing
- **Assessment**: ⚠️ **NEEDS REFACTOR** - Not using BaseImporter
- **Next Steps**: Refactor to use BaseImporter, add channel analysis

### ⏳ **WDL Importer** (822 lines) - **PENDING**
- **Status**: WDL workflow parsing
- **Assessment**: ⚠️ **NEEDS REFACTOR** - Not using BaseImporter
- **Next Steps**: Refactor to use BaseImporter, add scatter/gather support

### ⏳ **Galaxy Importer** (451 lines) - **PENDING**
- **Status**: Galaxy workflow format
- **Assessment**: ⚠️ **NEEDS REFACTOR** - Not using BaseImporter
- **Next Steps**: Refactor to use BaseImporter, add tool integration

## Implementation Phases

### Phase 1: Complete Snakemake Enhancement (Current)
- [ ] Add loss side-car integration to Snakemake importer
- [ ] Enhance interactive mode for Snakemake
- [ ] Add execution model detection for Snakemake
- [ ] Test and validate Snakemake enhancements

### Phase 2: Refactor DAGMan Importer (Next Priority)
- [ ] Refactor DAGMan importer to inherit from BaseImporter
- [ ] Add loss side-car integration
- [ ] Add intelligent inference for missing information
- [ ] Add interactive mode support
- [ ] Test and validate DAGMan refactor

### Phase 3: Refactor Nextflow Importer
- [ ] Refactor Nextflow importer to inherit from BaseImporter
- [ ] Add channel analysis and dynamic workflow support
- [ ] Add loss side-car integration
- [ ] Add intelligent inference
- [ ] Test and validate Nextflow refactor

### Phase 4: Refactor WDL Importer
- [ ] Refactor WDL importer to inherit from BaseImporter
- [ ] Add scatter/gather operation support
- [ ] Add loss side-car integration
- [ ] Add intelligent inference
- [ ] Test and validate WDL refactor

### Phase 5: Refactor Galaxy Importer
- [ ] Refactor Galaxy importer to inherit from BaseImporter
- [ ] Add tool integration and dependency management
- [ ] Add loss side-car integration
- [ ] Add intelligent inference
- [ ] Test and validate Galaxy refactor

### Phase 6: Integration and Testing
- [ ] Comprehensive integration testing
- [ ] Performance benchmarking
- [ ] Documentation updates
- [ ] CLI integration updates
- [ ] Migration guide creation

## Success Metrics

### Code Metrics
- [ ] 70% reduction in total importer code
- [ ] 90% reduction in code duplication
- [ ] 100% consistency in error handling
- [ ] 100% consistency in loss side-car handling

### Functionality Metrics
- [ ] All existing tests pass for each importer
- [ ] New tests pass for shared functionality
- [ ] Interactive mode works for all importers
- [ ] Loss side-car integration works for all formats

### User Experience Metrics
- [ ] Reduced manual configuration through intelligent inference
- [ ] Better error messages with actionable suggestions
- [ ] Consistent behavior across all importers
- [ ] Improved workflow completion through interactive mode

## Notes and Observations

### Current Strengths
- Snakemake importer is already well-refactored
- CWL importer has good foundation with some loss side-car support
- BaseImporter infrastructure is solid and comprehensive
- Shared modules (inference, interactive, loss_integration, utils) are well-designed

### Current Weaknesses
- Most importers not using BaseImporter infrastructure
- Inconsistent loss side-car handling across importers
- No intelligent inference in most importers
- No interactive mode in most importers

### Priority Order
1. **Snakemake** - Complete enhancement (already refactored)
2. **DAGMan** - Simple refactor, good test case
3. **Nextflow** - Medium complexity, important format
4. **WDL** - Complex features, important for bioinformatics
5. **Galaxy** - Tool-based workflows, different paradigm

## Last Updated
- **Date**: 2025-01-27
- **Status**: Phase 1 in progress (Snakemake enhancement)
- **Next Action**: Complete Snakemake loss side-car integration 