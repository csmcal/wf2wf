# wf2wf Tests

This directory contains comprehensive tests for the wf2wf workflow conversion tool.

## Test Structure

```
tests/
├── conftest.py              # Pytest configuration and shared fixtures
├── test_cli/                # Command-line interface tests
├── test_core/               # Core functionality tests
├── test_exporters/          # Exporter module tests
├── test_importers/          # Importer module tests
├── test_integration/        # Integration and end-to-end tests
├── test_output/             # Test output directory (auto-cleaned)
└── data/                    # Test data files
```

## Test Isolation and Cleanup

The test suite uses a comprehensive cleanup system to ensure tests don't pollute the base project directory:

### Automatic Cleanup Features

1. **Test Isolation**: All tests run in temporary directories via the `ensure_clean_test_env` fixture
2. **Session Cleanup**: Automatic cleanup before and after test sessions
3. **Base Directory Protection**: Prevents test files from being created in the project root
4. **Test Output Management**: Dedicated `test_output/` directory with automatic cleanup

### Test Fixtures

- `persistent_test_output`: Creates test-specific subdirectories in `tests/test_output/`
- `temp_output_dir`: Creates temporary directories that are automatically cleaned up
- `dagman_test_export`: Helper for DAGMan exports that uses proper test directories
- `clean_test_output_dir`: Manages the test output directory while preserving `.gitignore`

### Manual Cleanup

If needed, you can manually clean test artifacts:

```bash
python cleanup_test_files.py
```

This script:
- Cleans the `tests/test_output/` directory (preserving `.gitignore`)
- Removes any test files from the base project directory
- Removes generated directories (`scripts/`, `modules/`, `tools/`) if they contain test files

## Running Tests

### Run All Tests
```bash
python -m pytest
```

### Run Specific Test Categories
```bash
# Core functionality
python -m pytest tests/test_core/

# Exporters
python -m pytest tests/test_exporters/

# Importers  
python -m pytest tests/test_importers/

# CLI interface
python -m pytest tests/test_cli/

# Integration tests
python -m pytest tests/test_integration/
```

### Run Tests with Verbose Output
```bash
python -m pytest -v
```

### Run Tests with Coverage
```bash
python -m pytest --cov=wf2wf --cov-report=html
```

## Test Categories

### Core Tests (`test_core/`)
- Basic workflow operations
- Resource specifications
- Container and conda environment handling
- Retry and priority features
- GPU and resource parsing

### Importer Tests (`test_importers/`)
- Snakemake workflow parsing
- Nextflow workflow parsing
- CWL workflow parsing
- DAGMan workflow parsing
- Conda environment handling
- Wildcards and resource extraction

### Exporter Tests (`test_exporters/`)
- DAGMan export functionality
- Nextflow export functionality
- Snakemake export functionality
- CWL export functionality
- Resource and environment preservation

### CLI Tests (`test_cli/`)
- Command-line interface functionality
- Format detection
- Workflow serialization
- Integration with importers/exporters
- Cleanup verification

### Integration Tests (`test_integration/`)
- End-to-end workflow conversions
- Advanced feature combinations
- Performance and edge cases
- Error handling
- Cross-format conversions

## Test Data

The `tests/data/` directory contains sample workflows and test files used across multiple test modules.

## Writing New Tests

When writing new tests:

1. Use the provided fixtures for proper test isolation
2. Use `persistent_test_output` for tests that need to verify file outputs
3. Use `temp_output_dir` for tests that don't need persistent outputs
4. For DAGMan exports, use the `dagman_test_export` helper fixture
5. Ensure tests clean up after themselves (fixtures handle this automatically)

### Example Test Structure

```python
def test_my_feature(persistent_test_output):
    """Test description."""
    # Create test workflow
    wf = Workflow(name="test_workflow")
    # ... setup workflow
    
    # Export to test directory
    output_file = persistent_test_output / "output.ext"
    exporter.from_workflow(wf, output_file)
    
    # Verify results
    assert output_file.exists()
    # ... additional assertions
```

## Continuous Integration

The test suite is designed to run cleanly in CI environments with:
- Automatic cleanup to prevent test pollution
- Proper isolation between test runs
- Comprehensive coverage of all conversion paths
- Error handling verification 