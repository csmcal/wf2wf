"""Pytest configuration and shared fixtures for wf2wf tests."""

import pytest
import tempfile
import shutil
import os
from pathlib import Path


@pytest.fixture(scope="session")
def project_root():
    """Return the path to the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def examples_dir(project_root):
    """Return the path to the examples directory."""
    return project_root / "examples"


@pytest.fixture(scope="session")
def test_output_dir(project_root):
    """Return the path to the test output directory, creating it if needed."""
    output_dir = project_root / "tests" / "test_output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


@pytest.fixture
def test_data_dir():
    """Return the path to the test data directory."""
    return Path(__file__).parent / "data"


@pytest.fixture
def sample_workflow_json(test_data_dir):
    """Return the path to the sample workflow JSON file."""
    return test_data_dir / "test_workflow.json"


@pytest.fixture
def dagman_examples(examples_dir):
    """Return the path to the DAGMan examples directory."""
    return examples_dir / "dagman"


@pytest.fixture
def snakemake_examples(examples_dir):
    """Return the path to the Snakemake examples directory."""
    return examples_dir / "snake"


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def persistent_test_output(test_output_dir, request):
    """Create a subdirectory in test_output for a specific test."""
    # Create test-specific subdirectory based on test name
    test_name = request.node.name
    test_dir = test_output_dir / test_name
    test_dir.mkdir(exist_ok=True)
    
    # Clean the directory before the test
    if test_dir.exists():
        for item in test_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
    
    return test_dir


@pytest.fixture(autouse=True)
def ensure_clean_test_env(monkeypatch, tmp_path, project_root):
    """Ensure tests run in a clean environment with temporary working directory."""
    # Store original working directory
    original_cwd = Path.cwd()
    
    # Change to temporary directory for tests to avoid polluting the source tree
    monkeypatch.chdir(tmp_path)
    
    # Set environment variables to ensure test isolation
    monkeypatch.setenv("WF2WF_TEST_MODE", "1")
    
    # Store project root in environment for tests that need it
    monkeypatch.setenv("WF2WF_PROJECT_ROOT", str(project_root))
    
    # Ensure the wf2wf package is importable when subprocesses change directory
    # Prepend the project root to PYTHONPATH so `python -m wf2wf` works even
    # when the current working directory is not the repository root (as is the
    # case for the wet-run tests which execute in a temporary directory).
    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    new_pythonpath = (
        f"{project_root}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(project_root)
    )
    monkeypatch.setenv("PYTHONPATH", new_pythonpath)
    
    yield
    
    # Additional cleanup after test
    _cleanup_base_directory(project_root)


@pytest.fixture(autouse=True, scope="session")
def session_cleanup(project_root):
    """Clean up test files at the beginning and end of the test session."""
    
    def cleanup():
        """Remove any test files from the base directory."""
        _cleanup_base_directory(project_root)
        _cleanup_generated_directories(project_root)
    
    # Cleanup before tests
    cleanup()
    
    # Yield control to tests
    yield
    
    # Cleanup after all tests
    cleanup()


def _cleanup_base_directory(project_root: Path):
    """Clean up any test files that might be generated in the base directory."""
    cleanup_patterns = [
        "demo_*.nf",
        "demo_*.json", 
        "test_*.nf",
        "test_*.json",
        "test_*.dag",
        "test_*.sub",
        "test_*.smk",
        "test_*.cwl",
        "test_*.yaml",
        "test_*.yml",
        "*_test.*",
        "*_demo.*",
        "*.tmp"
    ]
    
    for pattern in cleanup_patterns:
        for file_path in project_root.glob(pattern):
            try:
                if file_path.is_file():
                    file_path.unlink()
            except (OSError, PermissionError):
                pass  # Ignore cleanup errors


def _cleanup_generated_directories(project_root: Path):
    """Clean up directories that might be generated during tests."""
    cleanup_dirs = [
        "scripts",
        "modules", 
        "tools",
        "logs"
    ]
    
    for dir_name in cleanup_dirs:
        dir_path = project_root / dir_name
        if dir_path.exists() and dir_path.is_dir():
            try:
                # Check if it's a test-generated directory (has test files)
                has_test_files = any(
                    f.name.startswith(('test_', 'demo_')) or f.suffix in ['.tmp']
                    for f in dir_path.rglob('*') if f.is_file()
                )
                
                # Only remove if it contains test files or is empty
                if has_test_files or not any(dir_path.iterdir()):
                    shutil.rmtree(dir_path)
            except (OSError, PermissionError):
                pass  # Ignore cleanup errors


@pytest.fixture(scope="session")
def clean_test_output_dir(test_output_dir):
    """Clean the test output directory but preserve .gitignore."""
    def cleanup_test_output():
        """Remove all files from test_output except .gitignore."""
        if test_output_dir.exists():
            for item in test_output_dir.iterdir():
                if item.name == ".gitignore":
                    continue  # Preserve .gitignore
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                except (OSError, PermissionError):
                    pass  # Ignore cleanup errors
    
    # Clean at start
    cleanup_test_output()
    
    yield test_output_dir
    
    # Clean at end (optional - could keep for debugging)
    # cleanup_test_output() 


@pytest.fixture(autouse=True, scope="session")
def manage_test_output_dir(test_output_dir):
    """Ensure tests/test_output is empty before session and clean it up afterwards (except .gitignore).
    This prevents stale artefacts from interfering with test results and keeps the repo tidy.
    Set WF2WF_KEEP_TEST_OUTPUT=1 to preserve files for debugging.
    """
    def _clean():
        for item in test_output_dir.iterdir():
            if item.name == ".gitignore":
                continue
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except (OSError, PermissionError):
                pass  # Ignore cleanup errors

    # Clean before any tests run
    if os.getenv("WF2WF_KEEP_TEST_OUTPUT") is None:
        _clean()

    yield test_output_dir

    # Clean after session unless user asked to keep
    if os.getenv("WF2WF_KEEP_TEST_OUTPUT") is None:
        _clean()


@pytest.fixture
def dagman_test_export(persistent_test_output):
    """Helper fixture for DAGMan exports that automatically uses test directories."""
    def _export(workflow, dag_filename="test.dag", **kwargs):
        """Export workflow to DAGMan using test directories."""
        from wf2wf.exporters import dagman as dag_exporter
        
        dag_path = persistent_test_output / dag_filename
        scripts_dir = persistent_test_output / "scripts"
        
        # Set default parameters for test isolation
        export_kwargs = {
            'workdir': persistent_test_output,
            'scripts_dir': scripts_dir,
            **kwargs  # Allow override of any parameters
        }
        
        dag_exporter.from_workflow(workflow, dag_path, **export_kwargs)
        return dag_path, scripts_dir
    
    return _export 


@pytest.fixture(autouse=True, scope="session")
def _docker_container_guard(request):
    """Detect containers started during the test session and warn or clean them.

    If the host has Docker and the environment variable WF2WF_CLEAN_CONTAINERS=1
    is set, containers that remain *running* after the tests will be stopped
    and removed automatically.  Otherwise we just print an informative
    warning so developers can clean up manually.
    """
    import shutil, subprocess, json, os

    if shutil.which("docker") is None:
        yield
        return

    def _list_running_ids() -> set[str]:
        try:
            out = subprocess.check_output([
                "docker", "ps", "--format", "{{json .}}"
            ], text=True)
            return {json.loads(line)["ID"] for line in out.splitlines() if line}
        except Exception:
            return set()

    before = _list_running_ids()
    yield  # run entire session
    after = _list_running_ids()

    new_ids = after - before
    if not new_ids:
        return

    msg = (
        f"\n⚠ wf2wf test-suite may have left {len(new_ids)} running Docker "
        "containers:\n  " + "\n  ".join(new_ids)
    )

    auto_clean = os.environ.get("WF2WF_CLEAN_CONTAINERS") == "1"
    if auto_clean:
        for cid in new_ids:
            subprocess.call(["docker", "rm", "-f", cid])
        print(msg + "\n→ Stopped & removed automatically (WF2WF_CLEAN_CONTAINERS=1).", flush=True)
    else:
        print(msg + "\nRun 'docker rm -f <id>' to clean them or rerun tests with WF2WF_CLEAN_CONTAINERS=1.", flush=True) 