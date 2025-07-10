# Test Suite Reorganization TODO

## Current State Assessment

### Files to Move from Root Directory
- [ ] `test_enhanced_validation.py` → `tests/unit/test_validate/test_enhanced_validation.py`
- [ ] `test_schema_validation.py` → `tests/unit/test_validate/test_schema_validation.py`
- [ ] `test_dagman_exporter.py` → `tests/integration/test_exporters/test_dagman_exporter.py`
- [ ] `test_simple_export.py` → `tests/integration/test_exporters/test_simple_export.py`
- [ ] `test_all_exporters.py` → `tests/integration/test_exporters/test_all_exporters.py`
- [ ] `test_wdl_exporter.py` → `tests/integration/test_exporters/test_wdl_exporter.py`
- [ ] `test_galaxy_exporter.py` → `tests/integration/test_exporters/test_galaxy_exporter.py`
- [ ] `test_environment_manager.py` → `tests/unit/test_core/test_environment_manager.py`
- [ ] `test_exporters_refactor.py` → `tests/integration/test_exporters/test_exporters_refactor.py`
- [ ] `test_metadata_spec.py` → `tests/unit/test_core/test_metadata_spec.py`
- [ ] `test_json_encoder.py` → `tests/unit/test_utils/test_json_encoder.py`
- [ ] `test_robustness.py` → `tests/system/test_performance/test_robustness.py`
- [ ] `test_universal_environment_ir.py` → `tests/unit/test_core/test_universal_environment_ir.py`
- [ ] `test_multi_environment_importers_exporters.py` → `tests/integration/test_roundtrips/test_multi_environment_roundtrips.py`

### Files to Delete (Debug/Scratch)
- [ ] `debug_mapping.py` (debug file)
- [ ] `debug_memory.py` (debug file)
- [ ] `pytestdebug.log` (debug log)
- [ ] `design_scratch.md` (design notes)

### Files to Keep in Root
- [ ] `run_tests.py` (test runner script)
- [ ] `pytest.ini` (pytest configuration)

## New Directory Structure Creation

### 1. Create New Test Directories
- [ ] Create `tests/unit/` directory
- [ ] Create `tests/unit/test_core/` directory
- [ ] Create `tests/unit/test_validate/` directory
- [ ] Create `tests/unit/test_utils/` directory
- [ ] Create `tests/unit/test_schemas/` directory
- [ ] Create `tests/integration/` directory
- [ ] Create `tests/integration/test_roundtrips/` directory
- [ ] Create `tests/system/` directory
- [ ] Create `tests/system/test_performance/` directory
- [ ] Create `tests/regression/` directory
- [ ] Create `tests/regression/test_known_issues/` directory
- [ ] Create `tests/regression/test_compatibility/` directory

### 2. Reorganize Existing Test Directories
- [ ] Move `tests/test_core/` → `tests/unit/test_core/`
- [ ] Move `tests/test_validate/` → `tests/unit/test_validate/`
- [ ] Move `tests/test_exporters/` → `tests/integration/test_exporters/`
- [ ] Move `tests/test_importers/` → `tests/integration/test_importers/`
- [ ] Move `tests/test_cli/` → `tests/system/test_cli/`
- [ ] Move `tests/test_integration/` → `tests/system/test_integration/`
- [ ] Move `tests/test_environ/` → `tests/unit/test_core/` (merge with core tests)
- [ ] Move `tests/test_loss/` → `tests/unit/test_core/` (merge with core tests)

### 3. Reorganize Test Data
- [ ] Create `tests/data/workflows/` directory
- [ ] Create `tests/data/workflows/simple/` directory
- [ ] Create `tests/data/workflows/complex/` directory
- [ ] Create `tests/data/workflows/edge_cases/` directory
- [ ] Create `tests/data/workflows/invalid/` directory
- [ ] Create `tests/data/expected_outputs/` directory
- [ ] Create `tests/data/fixtures/` directory
- [ ] Move existing test data files to appropriate subdirectories

## Test File Reorganization

### 1. Unit Tests (`tests/unit/`)

#### Core Tests (`test_core/`)
- [ ] Move and merge core functionality tests
- [ ] Consolidate environment-specific tests
- [ ] Consolidate resource and GPU tests
- [ ] Consolidate loss tracking tests
- [ ] Consolidate expression and type tests
- [ ] Add missing unit tests for core classes

#### Validation Tests (`test_validate/`)
- [ ] Move enhanced validation tests
- [ ] Move schema validation tests
- [ ] Add comprehensive validation test suite
- [ ] Add resource validation tests
- [ ] Add environment validation tests
- [ ] Add file path validation tests

#### Utility Tests (`test_utils/`)
- [ ] Move resource utility tests
- [ ] Move JSON encoder tests
- [ ] Add expression utility tests
- [ ] Add file utility tests
- [ ] Add logging utility tests

#### Schema Tests (`test_schemas/`)
- [ ] Add JSON schema validation tests
- [ ] Add schema evolution tests
- [ ] Add backward compatibility tests
- [ ] Add schema documentation tests

### 2. Integration Tests (`tests/integration/`)

#### Importer Tests (`test_importers/`)
- [ ] Reorganize existing importer tests
- [ ] Add missing edge case tests
- [ ] Add environment detection tests
- [ ] Add resource extraction tests
- [ ] Add dependency resolution tests
- [ ] Add metadata preservation tests

#### Exporter Tests (`test_exporters/`)
- [ ] Reorganize existing exporter tests
- [ ] Add missing edge case tests
- [ ] Add resource translation tests
- [ ] Add environment adaptation tests
- [ ] Add file generation tests
- [ ] Add loss tracking tests

#### Roundtrip Tests (`test_roundtrips/`)
- [ ] Create comprehensive roundtrip test suite
- [ ] Add all format pair combinations
- [ ] Add fidelity testing
- [ ] Add loss analysis tests
- [ ] Add regression detection tests
- [ ] Add multi-environment roundtrip tests

### 3. System Tests (`tests/system/`)

#### CLI Tests (`test_cli/`)
- [ ] Reorganize existing CLI tests
- [ ] Add command interface tests
- [ ] Add format detection tests
- [ ] Add error handling tests
- [ ] Add output management tests
- [ ] Add integration tests

#### Performance Tests (`test_performance/`)
- [ ] Move robustness tests
- [ ] Add large workflow tests
- [ ] Add memory usage tests
- [ ] Add conversion speed tests
- [ ] Add scalability tests
- [ ] Add stress tests

#### Error Handling Tests (`test_error_handling/`)
- [ ] Move error handling tests
- [ ] Add graceful degradation tests
- [ ] Add recovery mechanism tests
- [ ] Add user feedback tests
- [ ] Add logging tests

### 4. Regression Tests (`tests/regression/`)

#### Known Issues Tests (`test_known_issues/`)
- [ ] Create tests for previously fixed bugs
- [ ] Add regression prevention tests
- [ ] Add bug reproduction tests
- [ ] Add fix verification tests

#### Compatibility Tests (`test_compatibility/`)
- [ ] Add backward compatibility tests
- [ ] Add format evolution tests
- [ ] Add schema compatibility tests
- [ ] Add version migration tests

## Test Data Organization

### 1. Sample Workflows
- [ ] Create simple workflow examples
- [ ] Create complex workflow examples
- [ ] Create edge case workflow examples
- [ ] Create invalid workflow examples
- [ ] Document workflow purposes and test scenarios

### 2. Expected Outputs
- [ ] Generate reference output files
- [ ] Create expected error messages
- [ ] Create performance benchmarks
- [ ] Create loss analysis baselines

### 3. Test Fixtures
- [ ] Create reusable test fixtures
- [ ] Create mock data generators
- [ ] Create test environment setup
- [ ] Create cleanup utilities

## Test Infrastructure Updates

### 1. Pytest Configuration
- [ ] Update `pytest.ini` for new directory structure
- [ ] Add test markers for different test types
- [ ] Configure test discovery patterns
- [ ] Add performance test configuration

### 2. Test Fixtures
- [ ] Update `conftest.py` for new structure
- [ ] Add fixtures for new test categories
- [ ] Add performance test fixtures
- [ ] Add regression test fixtures

### 3. Test Utilities
- [ ] Create test data generators
- [ ] Create workflow builders
- [ ] Create comparison utilities
- [ ] Create performance measurement tools

## Documentation Updates

### 1. Test Documentation
- [ ] Update `tests/README.md`
- [ ] Add test organization documentation
- [ ] Add test writing guidelines
- [ ] Add test maintenance procedures

### 2. Test Examples
- [ ] Create example test files
- [ ] Create test templates
- [ ] Create best practices guide
- [ ] Create troubleshooting guide

### 3. Test Coverage Documentation
- [ ] Document test coverage requirements
- [ ] Document test performance requirements
- [ ] Document test reliability requirements
- [ ] Document test maintenance procedures

## Continuous Integration Updates

### 1. CI Configuration
- [ ] Update CI test execution
- [ ] Add test categorization
- [ ] Add performance test execution
- [ ] Add regression test execution

### 2. Test Reporting
- [ ] Configure coverage reporting
- [ ] Configure performance reporting
- [ ] Configure error reporting
- [ ] Configure trend analysis

### 3. Quality Gates
- [ ] Set test pass rate requirements
- [ ] Set coverage thresholds
- [ ] Set performance thresholds
- [ ] Set error rate limits

## Implementation Priority

### Phase 1: Foundation (Week 1)
- [ ] Create new directory structure
- [ ] Move files from root directory
- [ ] Update pytest configuration
- [ ] Basic test reorganization

### Phase 2: Consolidation (Week 2)
- [ ] Merge related test files
- [ ] Remove duplicate tests
- [ ] Standardize test patterns
- [ ] Update test fixtures

### Phase 3: Enhancement (Week 3)
- [ ] Add missing edge case tests
- [ ] Add comprehensive roundtrip tests
- [ ] Add performance tests
- [ ] Add regression tests

### Phase 4: Documentation (Week 4)
- [ ] Update documentation
- [ ] Create test examples
- [ ] Create maintenance procedures
- [ ] Update CI configuration

## Success Criteria

### 1. Test Organization
- [ ] All tests properly categorized
- [ ] No test files in root directory
- [ ] Clear test directory structure
- [ ] Consistent test naming

### 2. Test Coverage
- [ ] 90%+ code coverage
- [ ] All edge cases covered
- [ ] All format combinations tested
- [ ] All error conditions tested

### 3. Test Performance
- [ ] Unit tests < 1 second each
- [ ] Integration tests < 10 seconds each
- [ ] System tests < 60 seconds each
- [ ] Full suite < 30 minutes

### 4. Test Reliability
- [ ] 100% test pass rate
- [ ] Deterministic test results
- [ ] No test dependencies
- [ ] Proper test isolation

### 5. Test Maintainability
- [ ] Clear test documentation
- [ ] Consistent test patterns
- [ ] Reusable test utilities
- [ ] Automated test maintenance 