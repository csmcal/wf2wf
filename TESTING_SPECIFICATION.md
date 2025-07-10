# wf2wf Testing Specification

## Overview

This document defines the comprehensive testing strategy for the wf2wf workflow conversion tool. The testing suite must ensure robust, reliable, and complete coverage of all conversion paths, edge cases, and error conditions.

## Test Organization Structure

```
tests/
├── conftest.py                    # Pytest configuration and shared fixtures
├── data/                          # Test data files
│   ├── workflows/                 # Sample workflows for testing
│   │   ├── simple/               # Basic workflows for unit tests
│   │   ├── complex/              # Complex workflows for integration tests
│   │   ├── edge_cases/           # Workflows with edge cases
│   │   └── invalid/              # Invalid workflows for error testing
│   ├── expected_outputs/         # Expected output files for comparison
│   └── fixtures/                 # Test fixtures and helper data
├── unit/                         # Unit tests (fast, isolated)
│   ├── test_core/               # Core functionality tests
│   ├── test_validate/           # Validation tests
│   ├── test_utils/              # Utility function tests
│   └── test_schemas/            # Schema validation tests
├── integration/                  # Integration tests (medium speed)
│   ├── test_importers/          # Importer functionality tests
│   ├── test_exporters/          # Exporter functionality tests
│   └── test_roundtrips/         # Roundtrip conversion tests
├── system/                       # System tests (slower, end-to-end)
│   ├── test_cli/                # Command-line interface tests
│   ├── test_performance/        # Performance and stress tests
│   └── test_error_handling/     # Error handling and recovery tests
├── regression/                   # Regression tests
│   ├── test_known_issues/       # Tests for previously fixed bugs
│   └── test_compatibility/      # Backward compatibility tests
└── output/                       # Test output directory (auto-cleaned)
```

## Test Categories and Requirements

### 1. Unit Tests (`unit/`)

**Purpose**: Test individual components in isolation
**Speed**: Fast (< 1 second per test)
**Coverage**: 90%+ code coverage

#### Core Tests (`test_core/`)
- **Workflow Class**: Construction, validation, serialization
- **Task Class**: All field types, environment-specific values
- **Edge Class**: DAG construction and validation
- **EnvironmentSpecificValue**: Value resolution, fallbacks, validation
- **ParameterSpec**: Type validation, default values
- **MetadataSpec**: Metadata preservation and serialization

#### Validation Tests (`test_validate/`)
- **Schema Validation**: JSON schema compliance
- **Enhanced Validation**: Semantic validation rules
- **Resource Validation**: CPU, memory, disk, GPU constraints
- **Environment Validation**: Environment name validation
- **File Path Validation**: Path format validation
- **Cross-field Validation**: Inter-field dependency validation

#### Utility Tests (`test_utils/`)
- **Resource Utils**: Resource parsing and conversion
- **Expression Utils**: Expression evaluation and validation
- **File Utils**: File path handling and validation
- **Logging Utils**: Logging configuration and output

### 2. Integration Tests (`integration/`)

**Purpose**: Test component interactions and conversion paths
**Speed**: Medium (1-10 seconds per test)
**Coverage**: All import/export combinations

#### Importer Tests (`test_importers/`)
- **Format-specific Importers**: CWL, Snakemake, Nextflow, DAGMan, WDL, Galaxy
- **Edge Case Handling**: Invalid inputs, missing fields, malformed files
- **Environment Detection**: Automatic environment inference
- **Resource Extraction**: CPU, memory, disk, GPU parsing
- **Dependency Resolution**: Task dependencies and ordering
- **Metadata Preservation**: Format-specific metadata handling

#### Exporter Tests (`test_exporters/`)
- **Format-specific Exporters**: All supported output formats
- **Resource Translation**: Resource specification conversion
- **Environment Adaptation**: Environment-specific value handling
- **File Generation**: Output file structure and content
- **Loss Tracking**: Information loss detection and reporting
- **Validation**: Output format validation

#### Roundtrip Tests (`test_roundtrips/`)
- **Format Pairs**: All import/export combinations
- **Fidelity Testing**: Information preservation across conversions
- **Loss Analysis**: Quantified information loss measurement
- **Regression Detection**: Changes in conversion behavior

### 3. System Tests (`system/`)

**Purpose**: Test complete workflows and real-world scenarios
**Speed**: Slow (10+ seconds per test)
**Coverage**: End-to-end functionality

#### CLI Tests (`test_cli/`)
- **Command Interface**: All CLI commands and options
- **Format Detection**: Automatic format recognition
- **Error Handling**: User-friendly error messages
- **Output Management**: File output and directory handling
- **Integration**: CLI with importers/exporters

#### Performance Tests (`test_performance/`)
- **Large Workflows**: 100+ task workflows
- **Memory Usage**: Memory consumption monitoring
- **Conversion Speed**: Performance benchmarking
- **Scalability**: Resource usage with workflow size
- **Stress Testing**: Concurrent conversions

#### Error Handling Tests (`test_error_handling/`)
- **Graceful Degradation**: Partial failure handling
- **Recovery Mechanisms**: Error recovery and retry
- **User Feedback**: Clear error messages and suggestions
- **Logging**: Comprehensive error logging

## Challenging Edge Cases for Import/Export/Roundtrip Testing

### 1. Environment-Specific Value Edge Cases

#### Complex Environment Mappings
```python
# Test workflows with:
- Multiple environments per value
- Environment-specific defaults
- Nested environment dependencies
- Environment inheritance chains
- Cross-environment value conflicts
```

#### Environment Resolution Edge Cases
```python
# Test scenarios:
- Missing environment values
- Invalid environment names
- Environment fallback chains
- Default value handling
- Environment-specific validation
```

### 2. Resource Specification Edge Cases

#### Resource Type Conversions
```python
# Test conversions between:
- CPU cores vs CPU time
- Memory (MB/GB/TB) vs memory time
- Disk space vs disk I/O
- GPU count vs GPU memory
- Network bandwidth vs latency
```

#### Resource Constraint Edge Cases
```python
# Test scenarios:
- Zero or negative resources
- Extremely large resource values
- Resource dependencies (e.g., GPU requires CPU)
- Resource conflicts (e.g., memory > disk)
- Resource inheritance and overrides
```

### 3. Workflow Structure Edge Cases

#### Complex DAG Patterns
```python
# Test workflows with:
- Self-referencing tasks
- Circular dependencies (should fail gracefully)
- Conditional execution paths
- Parallel execution branches
- Scatter/gather operations
- Checkpointing and recovery
```

#### Task Relationship Edge Cases
```python
# Test scenarios:
- Orphaned tasks (no dependencies)
- Isolated task clusters
- Cross-cluster dependencies
- Conditional dependencies
- Dynamic dependencies
```

### 4. Format-Specific Edge Cases

#### CWL Edge Cases
```python
# Test CWL-specific features:
- $graph workflows with multiple entrypoints
- Tool files with complex parameter types
- Expression evaluation and validation
- Resource hints and requirements
- Software requirements and containers
- Input/output schema validation
```

#### Snakemake Edge Cases
```python
# Test Snakemake-specific features:
- Wildcard patterns and expansion
- Checkpoint rules and dynamic DAGs
- Local rules and rule inheritance
- Resource specifications and limits
- Conda environment handling
- Container integration
```

#### Nextflow Edge Cases
```python
# Test Nextflow-specific features:
- Channel operations and transformations
- Process inheritance and composition
- Workflow composition and modules
- Resource allocation and scheduling
- Error handling and recovery
- Configuration profiles
```

#### DAGMan Edge Cases
```python
# Test DAGMan-specific features:
- Submit file generation and customization
- Resource allocation and limits
- Retry mechanisms and error handling
- Priority and scheduling
- File transfer and staging
- Environment variable handling
```

### 5. Data Type and Validation Edge Cases

#### Complex Data Types
```python
# Test handling of:
- Nested arrays and objects
- Union types and optional fields
- Custom data types and extensions
- Binary data and file references
- Metadata and provenance information
```

#### Validation Edge Cases
```python
# Test validation scenarios:
- Invalid data types
- Missing required fields
- Extra unknown fields
- Field value constraints
- Cross-field dependencies
- Format-specific constraints
```

### 6. Performance and Scalability Edge Cases

#### Large Workflow Handling
```python
# Test with workflows containing:
- 1000+ tasks
- Complex dependency graphs
- Large resource specifications
- Extensive metadata
- Multiple environment mappings
```

#### Memory and Resource Management
```python
# Test scenarios:
- Memory exhaustion handling
- Large file processing
- Concurrent conversions
- Resource cleanup
- Memory leaks detection
```

### 7. Error Recovery and Resilience Edge Cases

#### Partial Failure Scenarios
```python
# Test handling of:
- Corrupted input files
- Network failures during conversion
- Disk space exhaustion
- Permission errors
- Timeout conditions
```

#### Recovery Mechanisms
```python
# Test recovery from:
- Interrupted conversions
- Partial output generation
- Incomplete metadata
- Corrupted intermediate files
- State inconsistency
```

## Test Data Requirements

### 1. Sample Workflows

#### Simple Workflows
- Linear workflows (A → B → C)
- Parallel workflows (A → B, A → C)
- Diamond workflows (A → B → D, A → C → D)
- Basic resource specifications
- Standard environment mappings

#### Complex Workflows
- Multi-level DAGs with conditional paths
- Scatter/gather operations
- Checkpointing and recovery
- Complex resource dependencies
- Multiple environment configurations

#### Edge Case Workflows
- Invalid or malformed workflows
- Workflows with missing information
- Workflows with conflicting specifications
- Workflows with extreme resource values
- Workflows with unusual dependency patterns

### 2. Expected Outputs

#### Reference Outputs
- Canonical output files for each format
- Expected error messages and codes
- Performance benchmarks and baselines
- Loss analysis reports and metrics

#### Validation Data
- Schema validation test cases
- Format-specific validation rules
- Cross-format compatibility matrices
- Regression test data sets

## Test Execution Requirements

### 1. Test Isolation

- **Clean Environment**: Each test runs in isolation
- **Temporary Directories**: No permanent file creation
- **Resource Cleanup**: Automatic cleanup after tests
- **State Reset**: No test state leakage

### 2. Test Performance

- **Unit Tests**: < 1 second per test
- **Integration Tests**: < 10 seconds per test
- **System Tests**: < 60 seconds per test
- **Total Suite**: < 30 minutes for full run

### 3. Test Reliability

- **Deterministic**: Tests produce consistent results
- **Idempotent**: Tests can be run multiple times
- **Independent**: Tests don't depend on each other
- **Robust**: Tests handle timing and resource variations

### 4. Test Coverage

- **Code Coverage**: 90%+ line coverage
- **Branch Coverage**: 85%+ branch coverage
- **Function Coverage**: 95%+ function coverage
- **Format Coverage**: All supported formats tested

## Continuous Integration Requirements

### 1. Automated Testing

- **Pre-commit**: Fast tests on every commit
- **Pull Request**: Full test suite on PR
- **Nightly**: Extended tests and performance benchmarks
- **Release**: Complete validation before release

### 2. Test Reporting

- **Coverage Reports**: Detailed coverage analysis
- **Performance Reports**: Performance regression detection
- **Error Reports**: Comprehensive error analysis
- **Trend Analysis**: Long-term test result trends

### 3. Quality Gates

- **Test Pass Rate**: 100% test pass rate required
- **Coverage Threshold**: Minimum coverage requirements
- **Performance Threshold**: Performance regression limits
- **Error Threshold**: Maximum acceptable error rates

## Test Maintenance

### 1. Test Updates

- **Schema Changes**: Update tests when schemas change
- **Format Changes**: Update tests when formats evolve
- **Feature Additions**: Add tests for new features
- **Bug Fixes**: Add regression tests for fixed bugs

### 2. Test Documentation

- **Test Purpose**: Clear description of what each test validates
- **Test Data**: Documentation of test data sources and purpose
- **Test Maintenance**: Instructions for updating tests
- **Troubleshooting**: Common test issues and solutions

### 3. Test Review

- **Code Review**: All test changes require review
- **Coverage Review**: Regular coverage analysis
- **Performance Review**: Regular performance analysis
- **Quality Review**: Regular test quality assessment 