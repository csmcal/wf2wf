"""
Pytest configuration and shared fixtures for wf2wf tests.

This module provides common fixtures and configuration for all tests,
including test data, mock objects, and utility functions.
"""

import os
import pytest
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any
from unittest.mock import patch, MagicMock
from wf2wf.core import Workflow, Task, EnvironmentSpecificValue
from wf2wf.interactive import get_prompter, set_test_responses, clear_test_responses


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
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def sample_workflow():
    """Create a sample workflow for testing."""
    workflow = Workflow(name="test_workflow")
    
    # Add sample tasks
    task1 = Task(id="task1")
    task1.cpu.set_for_environment(2, "shared_filesystem")
    task1.mem_mb.set_for_environment(4096, "shared_filesystem")
    task1.command.set_for_environment("echo 'hello'", "shared_filesystem")
    
    task2 = Task(id="task2")
    task2.cpu.set_for_environment(4, "shared_filesystem")
    task2.mem_mb.set_for_environment(8192, "shared_filesystem")
    task2.command.set_for_environment("echo 'world'", "shared_filesystem")
    
    workflow.tasks["task1"] = task1
    workflow.tasks["task2"] = task2
    
    # Add dependency
    workflow.add_edge("task1", "task2")
    
    return workflow

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

@pytest.fixture
def mock_environment_manager():
    """Create a mock environment manager."""
    mock = MagicMock()
    mock.detect_and_parse_environments.return_value = {
        'environment_metadata': {},
        'environment_warnings': []
    }
    mock.infer_missing_environments.return_value = None
    mock.prompt_for_missing_environments.return_value = None
    mock.build_environment_images.return_value = {
        'built_images': [],
        'failed_builds': []
    }
    return mock


@pytest.fixture
def interactive_responses(monkeypatch):
    """
    Fixture to provide specific test responses for interactive prompts.
    
    This monkeypatches the actual input() and click.prompt() functions
    to return predefined responses, allowing us to test the full interactive flow.
    
    Usage:
        def test_something(interactive_responses):
            interactive_responses.set_responses([
                "4",  # CPU cores
                "8192",  # Memory
                "y"  # Add GPU requirements
            ])
    """
    responses = []
    response_index = [0]  # Use list to make it mutable in nested functions
    
    def mock_input(prompt=""):
        """Mock input() function that returns predefined responses."""
        if response_index[0] < len(responses):
            response = responses[response_index[0]]
            response_index[0] += 1
            return response
        return ""  # Default empty response
    
    def mock_click_prompt(message, default=None, show_default=True, **kwargs):
        """Mock click.prompt() function that returns predefined responses."""
        if response_index[0] < len(responses):
            response = responses[response_index[0]]
            response_index[0] += 1
            return response
        return default or ""
    
    def set_responses(new_responses):
        """Set the responses that will be returned by input() and click.prompt()."""
        nonlocal responses
        responses = new_responses
        response_index[0] = 0  # Reset index
    
    def get_responses():
        """Get the current responses."""
        return responses.copy()
    
    # Monkey patch the input function
    monkeypatch.setattr("builtins.input", mock_input)
    
    # Monkey patch click.prompt if click is available
    try:
        import click
        monkeypatch.setattr("click.prompt", mock_click_prompt)
    except ImportError:
        pass  # Click not available, will use input() fallback
    
    # Create a simple object with the methods
    class InteractiveResponses:
        def set_responses(self, new_responses):
            set_responses(new_responses)
        
        def get_responses(self):
            return get_responses()
        
        @property
        def responses(self):
            return responses
    
    return InteractiveResponses()

@pytest.fixture
def default_interactive_responses(monkeypatch):
    """
    Fixture that provides sensible default responses for most interactive prompts.
    Use this when you want to test the happy path without specific edge cases.
    """
    responses = [
        "1",      # CPU cores
        "4096",   # Memory (MB)
        "4096",   # Disk space (MB)
        "1",      # Threads
        "2",      # Retry count
        "60",     # Retry delay
        "default-runtime:latest",  # Container image
        "environment.yml",  # Conda environment file
        "conda",  # Environment type
        "python=3.9",  # Conda environment specification
        "biocontainers/default:latest",  # Container specification
        "echo 'test'",  # Command
        "test.sh",  # Script
        "1",  # Choice
        "n",  # Would you like to add GPU requirements?
        "n",  # Would you like to add memory requirements?
        "n",  # Would you like to add publish directory?
        "n",  # Would you like to add input specifications?
        "n",  # Would you like to add output specifications?
        "default",  # Generic value
        "1",  # Generic choice
    ]
    
    response_index = [0]
    
    def mock_input(prompt=""):
        if response_index[0] < len(responses):
            response = responses[response_index[0]]
            response_index[0] += 1
            return response
        return ""
    
    def mock_click_prompt(message, default=None, show_default=True, **kwargs):
        if response_index[0] < len(responses):
            response = responses[response_index[0]]
            response_index[0] += 1
            return response
        return default or ""
    
    # Monkey patch the input function
    monkeypatch.setattr("builtins.input", mock_input)
    
    # Monkey patch click.prompt if click is available
    try:
        import click
        monkeypatch.setattr("click.prompt", mock_click_prompt)
    except ImportError:
        pass
    
    return responses

@pytest.fixture(autouse=True)
def ensure_clean_test_env(monkeypatch, tmp_path, project_root):
    """Ensure tests run in a clean environment with temporary working directory."""
    # Store original working directory
    Path.cwd()

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
        "*.tmp",
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
    cleanup_dirs = ["scripts", "modules", "tools", "logs"]

    for dir_name in cleanup_dirs:
        dir_path = project_root / dir_name
        if dir_path.exists() and dir_path.is_dir():
            try:
                # Check if it's a test-generated directory (has test files)
                has_test_files = any(
                    f.name.startswith(("test_", "demo_")) or f.suffix in [".tmp"]
                    for f in dir_path.rglob("*")
                    if f.is_file()
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
            "workdir": persistent_test_output,
            "scripts_dir": scripts_dir,
            **kwargs,  # Allow override of any parameters
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
    import shutil
    import subprocess
    import json
    import os

    if shutil.which("docker") is None:
        return  # Skip fixture entirely if Docker is not installed

    def _is_docker_daemon_running() -> bool:
        """Check if Docker daemon is actually running."""
        try:
            subprocess.run(
                ["docker", "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3
            )
            return True
        except Exception:
            return False

    if not _is_docker_daemon_running():
        return  # Skip fixture entirely if Docker daemon is not running

    def _list_running_ids() -> set[str]:
        try:
            out = subprocess.check_output(
                ["docker", "ps", "--format", "{{json .}}"], text=True
            )
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
        print(
            msg + "\n→ Stopped & removed automatically (WF2WF_CLEAN_CONTAINERS=1).",
            flush=True,
        )
    else:
        print(
            msg
            + "\nRun 'docker rm -f <id>' to clean them or rerun tests with WF2WF_CLEAN_CONTAINERS=1.",
            flush=True,
        )
