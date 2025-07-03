"""Tests for performance and edge case scenarios."""

import sys
import pathlib
import importlib.util
import pytest
import random

# Allow running tests without installing package
proj_root = pathlib.Path(__file__).resolve().parents[1]

if "wf2wf" not in sys.modules:
    spec = importlib.util.spec_from_file_location("wf2wf", proj_root / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["wf2wf"] = module  # type: ignore[assignment]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[arg-type]

from wf2wf.core import Workflow, Task, EnvironmentSpec, ResourceSpec
from wf2wf.exporters import dagman as dag_exporter

# Test if snakemake importer is available without importing it
import importlib.util
SNAKEMAKE_AVAILABLE = importlib.util.find_spec("wf2wf.importers.snakemake") is not None

class TestLargeWorkflowHandling:
    """Test handling of large workflows with many tasks."""

    def test_large_workflow_creation(self):
        """Test creating a workflow with many tasks."""
        wf = Workflow(name="large_workflow")

        # Create 100 tasks
        num_tasks = 100
        for i in range(num_tasks):
            task = Task(
                id=f"task_{i:03d}",
                command=f"echo 'Processing task {i}' > output_{i:03d}.txt",
                resources=ResourceSpec(
                    cpu=random.randint(1, 8), mem_mb=random.randint(1024, 16384)
                ),
            )
            wf.add_task(task)

        # Create a chain of dependencies
        for i in range(num_tasks - 1):
            wf.add_edge(f"task_{i:03d}", f"task_{i+1:03d}")

        assert len(wf.tasks) == num_tasks
        assert len(wf.edges) == num_tasks - 1

    def test_complex_dependency_network(self):
        """Test workflow with complex dependency patterns."""
        wf = Workflow(name="complex_dependencies")

        # Create a diamond dependency pattern
        # A -> B, C -> D
        # Where B and C both depend on A, and D depends on both B and C

        task_a = Task(id="A", command="echo 'Task A'")
        task_b = Task(id="B", command="echo 'Task B'")
        task_c = Task(id="C", command="echo 'Task C'")
        task_d = Task(id="D", command="echo 'Task D'")

        wf.add_task(task_a)
        wf.add_task(task_b)
        wf.add_task(task_c)
        wf.add_task(task_d)

        # Create diamond pattern
        wf.add_edge("A", "B")
        wf.add_edge("A", "C")
        wf.add_edge("B", "D")
        wf.add_edge("C", "D")

        # Add more complex patterns
        for i in range(1, 6):  # E1-E5
            task = Task(id=f"E{i}", command=f"echo 'Task E{i}'")
            wf.add_task(task)
            wf.add_edge("D", f"E{i}")  # D fans out to E1-E5

        # Final convergence task
        task_f = Task(id="F", command="echo 'Final task'")
        wf.add_task(task_f)
        for i in range(1, 6):
            wf.add_edge(f"E{i}", "F")  # E1-E5 converge to F

        # Verify structure
        assert len(wf.tasks) == 10  # A, B, C, D, E1-E5, F
        assert len(wf.edges) == 14  # 2 + 2 + 5 + 5 = 14

        # Verify specific dependencies exist
        parent_child_pairs = [(edge.parent, edge.child) for edge in wf.edges]
        assert ("A", "B") in parent_child_pairs
        assert ("A", "C") in parent_child_pairs
        assert ("B", "D") in parent_child_pairs
        assert ("C", "D") in parent_child_pairs
        assert ("D", "E1") in parent_child_pairs
        assert ("E5", "F") in parent_child_pairs

    def test_workflow_with_special_characters(self):
        """Test workflow with special characters in task IDs and commands."""
        wf = Workflow(name="special_chars_workflow")

        # Task with underscores and numbers
        task1 = Task(
            id="data_preprocessing_v2",
            command="python preprocess_data_v2.py --input='file with spaces.txt'",
        )
        wf.add_task(task1)

        # Task with hyphens
        task2 = Task(
            id="quality-control-check", command="bash quality-check.sh --threshold=0.95"
        )
        wf.add_task(task2)

        # Task with mixed case
        task3 = Task(id="FinalAnalysis", command="Rscript FinalAnalysis.R")
        wf.add_task(task3)

        wf.add_edge("data_preprocessing_v2", "quality-control-check")
        wf.add_edge("quality-control-check", "FinalAnalysis")

        assert len(wf.tasks) == 3
        assert len(wf.edges) == 2

        # Verify task IDs are preserved
        assert "data_preprocessing_v2" in wf.tasks
        assert "quality-control-check" in wf.tasks
        assert "FinalAnalysis" in wf.tasks

    def test_empty_task_handling(self):
        """Test handling of tasks with minimal specifications."""
        wf = Workflow(name="empty_task_test")

        # Task with only ID and command
        minimal_task = Task(id="minimal", command="echo 'minimal'")
        wf.add_task(minimal_task)

        # Task with empty command (should be allowed)
        empty_command_task = Task(id="empty_command", command="")
        wf.add_task(empty_command_task)

        # Task with script instead of command
        script_task = Task(id="script_task", script="analyze.py")
        wf.add_task(script_task)

        assert len(wf.tasks) == 3
        assert wf.tasks["minimal"].command == "echo 'minimal'"
        assert wf.tasks["empty_command"].command == ""
        assert wf.tasks["script_task"].script == "analyze.py"


class TestEdgeCaseHandling:
    """Test edge cases and error conditions."""

    def test_duplicate_task_id_prevention(self):
        """Test that duplicate task IDs are prevented."""
        wf = Workflow(name="duplicate_test")

        # Add first task
        task1 = Task(id="duplicate_id", command="echo 'first'")
        wf.add_task(task1)

        # Adding second task with same ID should raise an error
        task2 = Task(id="duplicate_id", command="echo 'second'")
        with pytest.raises(ValueError, match="Duplicate task id"):
            wf.add_task(task2)

    def test_self_dependency_prevention(self):
        """Test that self-dependencies are handled appropriately."""
        wf = Workflow(name="self_dep_test")

        task = Task(id="self_task", command="echo 'self'")
        wf.add_task(task)

        # Attempting to add self-dependency should be prevented
        # The behavior depends on implementation - it might raise an error
        # or silently ignore the self-dependency
        try:
            wf.add_edge("self_task", "self_task")
            # If no error, verify it wasn't actually added
            self_edges = [
                e
                for e in wf.edges
                if e.parent == "self_task" and e.child == "self_task"
            ]
            assert len(self_edges) == 0, "Self-dependency should not be allowed"
        except ValueError:
            # Expected behavior - self-dependencies should raise an error
            pass

    def test_nonexistent_task_dependencies(self):
        """Test handling of dependencies to nonexistent tasks."""
        wf = Workflow(name="nonexistent_dep_test")

        task = Task(id="existing_task", command="echo 'exists'")
        wf.add_task(task)

        # Attempting to add dependency to nonexistent task should fail
        with pytest.raises((KeyError, ValueError)):
            wf.add_edge("existing_task", "nonexistent_task")

        with pytest.raises((KeyError, ValueError)):
            wf.add_edge("nonexistent_parent", "existing_task")

    def test_workflow_json_roundtrip_with_complex_data(self):
        """Test JSON serialization/deserialization with complex data."""
        wf = Workflow(
            name="complex_json_test",
            config={
                "nested_config": {
                    "sub_option": "value",
                    "numeric_list": [1, 2, 3, 4, 5],
                },
                "unicode_string": "Test with émojis 🚀 and ñ characters",
            },
            meta={
                "tags": ["test", "json", "unicode"],
                "special_chars": "!@#$%^&*()",
                "nested_meta": {
                    "author": {"name": "Test User", "email": "test@example.com"}
                },
            },
        )

        # Add task with complex resources
        task = Task(
            id="complex_task",
            command="echo 'complex' > output.txt",
            resources=ResourceSpec(
                cpu=4,
                mem_mb=8192,
                extra={
                    "requirements": '(OpSysAndVer == "CentOS7")',
                    "+ProjectName": '"Test Project"',
                    "rank": "Memory",
                },
            ),
            environment=EnvironmentSpec(
                container="docker://python:3.9-slim", conda="environment.yaml"
            ),
        )
        wf.add_task(task)

        # Convert to JSON and back
        wf_json = wf.to_json()
        wf_restored = Workflow.from_json(wf_json)

        # Verify complex data is preserved
        assert wf_restored.name == "complex_json_test"
        assert wf_restored.config["nested_config"]["sub_option"] == "value"
        assert (
            wf_restored.config["unicode_string"]
            == "Test with émojis 🚀 and ñ characters"
        )
        assert wf_restored.meta["tags"] == ["test", "json", "unicode"]
        assert wf_restored.meta["nested_meta"]["author"]["name"] == "Test User"

        # Verify task data is preserved
        restored_task = wf_restored.tasks["complex_task"]
        assert restored_task.command == "echo 'complex' > output.txt"
        assert restored_task.resources.cpu == 4
        assert (
            restored_task.resources.extra["requirements"]
            == '(OpSysAndVer == "CentOS7")'
        )
        assert restored_task.environment.container == "docker://python:3.9-slim"
        assert restored_task.environment.conda == "environment.yaml"

    def test_workflow_with_unicode_content(self):
        """Test workflow with Unicode content in various fields."""
        wf = Workflow(name="unicode_test_🚀")

        # Task with Unicode in command
        unicode_task = Task(
            id="unicode_task",
            command="echo 'Processing data with special chars: café, naïve, résumé' > output_ñ.txt",
        )
        wf.add_task(unicode_task)

        # Task with Unicode in script path
        script_task = Task(id="script_with_unicode", script="scripts/análisis.py")
        wf.add_task(script_task)

        wf.add_edge("unicode_task", "script_with_unicode")

        assert len(wf.tasks) == 2
        assert wf.tasks["unicode_task"].command.startswith("echo 'Processing data")
        assert wf.tasks["script_with_unicode"].script == "scripts/análisis.py"


class TestDAGManExportPerformance:
    """Test DAGMan export performance with various scenarios."""

    def test_dagman_export_large_workflow(self, tmp_path):
        """Test DAGMan export performance with large workflow."""
        wf = Workflow(name="large_export_test")

        # Create 50 tasks (reasonable size for performance test)
        num_tasks = 50
        for i in range(num_tasks):
            task = Task(
                id=f"task_{i:03d}",
                command=f"python process_chunk_{i}.py",
                resources=ResourceSpec(
                    cpu=random.randint(1, 4), mem_mb=random.randint(2048, 8192)
                ),
            )
            wf.add_task(task)

        # Create some dependencies (not fully connected to avoid too much complexity)
        for i in range(0, num_tasks - 1, 5):  # Every 5th task depends on previous
            if i > 0:
                wf.add_edge(f"task_{i-5:03d}", f"task_{i:03d}")

        # Export to DAG
        dag_path = tmp_path / "large_export.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Verify export completed successfully
        assert dag_path.exists()
        dag_content = dag_path.read_text()

        # Verify all tasks are present
        for i in range(num_tasks):
            assert f"JOB task_{i:03d}" in dag_content

        # Verify scripts directory was created
        scripts_dir = tmp_path / "scripts"
        assert scripts_dir.exists()

        # Should have one script per task
        script_files = list(scripts_dir.glob("task_*.sh"))
        assert len(script_files) == num_tasks

    def test_dagman_export_with_special_characters(self, tmp_path):
        """Test DAGMan export with special characters in various fields."""
        wf = Workflow(name="special_chars_export")

        # Task with special characters in command
        special_task = Task(
            id="special_chars_task",
            command="echo 'File with spaces and (parentheses).txt' && echo \"Quotes and 'mixed' quotes\"",
            resources=ResourceSpec(
                cpu=2,
                mem_mb=4096,
                extra={
                    "requirements": '(Memory > 4000) && (OpSysAndVer == "CentOS7")',
                    "+ProjectName": '"Project with spaces and symbols!"',
                },
            ),
        )
        wf.add_task(special_task)

        # Export to DAG
        dag_path = tmp_path / "special_chars.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        assert dag_path.exists()
        dag_content = dag_path.read_text()

        # Verify special characters are properly handled
        assert "JOB special_chars_task" in dag_content

        # Check submit file for resource specifications
        submit_path = tmp_path / "special_chars_task.sub"
        submit_content = submit_path.read_text()

        assert "request_cpus = 2" in submit_content
        assert "request_memory = 4096MB" in submit_content

        # Verify custom attributes with special characters
        assert (
            'requirements = (Memory > 4000) && (OpSysAndVer == "CentOS7")'
            in submit_content
        )
        assert '+ProjectName = "Project with spaces and symbols!"' in submit_content

        # Verify script was created and contains the command
        scripts_dir = tmp_path / "scripts"
        script_files = list(scripts_dir.glob("special_chars_task.*"))
        assert len(script_files) == 1

        script_content = script_files[0].read_text()
        assert "echo 'File with spaces and (parentheses).txt'" in script_content
        assert "echo \"Quotes and 'mixed' quotes\"" in script_content
