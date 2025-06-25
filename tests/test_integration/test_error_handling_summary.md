# Error Handling Tests Summary

This document summarizes the comprehensive error-handling edge case tests implemented for wf2wf.

## Test Coverage

### 1. Circular Dependencies (`TestCircularDependencies`)
- **Simple circular dependency (A→B→A)**: Tests detection of basic circular dependencies in Snakemake workflows
- **Complex circular dependency (A→B→C→A)**: Tests detection of multi-step circular dependencies
- **Workflow IR cycle handling**: Tests that manually created cycles in the IR are handled gracefully during export

### 2. Empty Workflows (`TestEmptyWorkflows`)
- **Completely empty Snakefile**: Tests handling of files with no content
- **Comments-only Snakefile**: Tests handling of files with only comments and no rules
- **No target rules**: Tests handling of workflows with rules but no target rules to execute
- **Empty IR export**: Tests that empty Workflow IR objects export gracefully

### 3. Malformed Snakefiles (`TestMalformedSnakefiles`)
- **Python syntax errors**: Tests handling of Snakefiles with invalid Python syntax
- **Missing required directives**: Tests handling of rules missing required directives (e.g., output)

### 4. Missing Input Files (`TestMissingInputFiles`)
- **Strict mode failures**: Tests proper error handling when input files are missing
- **Forceall mode recovery**: Tests that `--forceall` allows processing despite missing inputs

### 5. Invalid Resource Specifications (`TestInvalidResourceSpecifications`)
- **Invalid resource syntax**: Tests handling of malformed resource specifications
- **Negative resource values**: Tests graceful handling of negative resource values

### 6. Snakemake Executable Handling (`TestSnakemakeExecutableHandling`)
- **Snakemake not found**: Tests proper error messages when Snakemake is not installed
- **Permission denied**: Tests handling of permission errors when executing Snakemake

### 7. Integration Error Handling (`TestIntegrationErrorHandling`)
- **Error propagation**: Tests that errors propagate correctly through the import→export pipeline
- **Partial workflow recovery**: Tests that partially valid workflows can still be processed

## Key Testing Patterns

### Mock Strategy
- Uses `unittest.mock.patch` to mock Snakemake CLI calls
- Simulates various error conditions without requiring actual Snakemake installation
- Provides controlled, reproducible test environment

### Error Detection
- Tests both import-time errors (Snakemake failures) and export-time errors
- Verifies proper exception types and error messages
- Ensures graceful degradation where appropriate

### Assertions
- **"Toothy" assertions**: Check both IR structure and DAGMan export artifacts
- **Error message validation**: Verify meaningful error messages are provided
- **Graceful failure**: Ensure failures don't crash the system unexpectedly

## Implementation Details

### Mocking Pattern
```python
def _mock_run_error(cmd, capture_output=False, text=False, check=False, **kwargs):
    m = MagicMock()
    if "--dag" in cmd:
        m.stdout = ""
        m.stderr = "Error message"
        m.returncode = 1
        raise CalledProcessError(1, cmd, output="", stderr=m.stderr)
    return m

with patch("wf2wf.importers.snakemake.subprocess.run", side_effect=_mock_run_error):
    with pytest.raises(RuntimeError) as exc_info:
        snake_importer.to_workflow(snakefile, workdir=tmp_path)
    assert "expected error text" in str(exc_info.value)
```

### Test Organization
- Each logical error category has its own test class
- Tests focus on core error handling behavior rather than detailed parsing
- Integration tests verify end-to-end error propagation

## Benefits

1. **Robustness**: Ensures wf2wf handles edge cases gracefully
2. **User Experience**: Provides meaningful error messages for common issues
3. **Maintainability**: Comprehensive test coverage makes refactoring safer
4. **Documentation**: Tests serve as examples of expected error handling behavior

## Future Extensions

The test framework can be easily extended to cover additional error scenarios:
- Network-related errors during container pulls
- File system permission issues
- Resource constraint violations
- Version compatibility issues

## Test Results

All 17 error handling tests pass successfully:
- ✅ 3 circular dependency tests
- ✅ 4 empty workflow tests  
- ✅ 2 malformed Snakefile tests
- ✅ 2 missing input file tests
- ✅ 2 invalid resource tests
- ✅ 2 executable handling tests
- ✅ 2 integration error tests

Total test suite: 47 passed, 1 skipped (requires Snakemake installation) 