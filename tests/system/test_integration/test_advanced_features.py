"""
Tests for advanced wf2wf features including configuration management,
performance optimization, and edge case handling.

This module tests the advanced capabilities of the wf2wf system that go beyond
basic workflow conversion, including configuration precedence, large workflow
handling, and various edge cases.
"""

import sys
import pathlib
import importlib.util

# Allow running tests without installing package
proj_root = pathlib.Path(__file__).resolve().parents[1]

if "wf2wf" not in sys.modules:
    spec = importlib.util.spec_from_file_location("wf2wf", proj_root / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["wf2wf"] = module  # type: ignore[assignment]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[arg-type]

import pytest
from pathlib import Path

from wf2wf.core import Workflow, Task, EnvironmentSpecificValue
from wf2wf.exporters import dagman as dag_exporter


class TestConfigurationManagement:
    """Test configuration handling and precedence."""

    def test_workflow_config_storage(self):
        """Test Workflow config attribute for storing configuration."""
        config_data = {
            "default_memory": "8GB",
            "default_disk": "10GB",
            "default_cpus": 4,
            "custom_attributes": {
                "+WantGPULab": "true",
                "requirements": '(OpSysAndVer == "CentOS7")',
            },
        }
        
        # Create metadata spec with config data
        from wf2wf.core import MetadataSpec
        metadata = MetadataSpec(format_specific={"config": config_data})
        
        wf = Workflow(name="config_test", metadata=metadata)
        assert wf.metadata.format_specific["config"]["default_memory"] == "8GB"
        assert wf.metadata.format_specific["config"]["default_cpus"] == 4
        assert wf.metadata.format_specific["config"]["custom_attributes"]["+WantGPULab"] == "true"

    def test_workflow_config_serialization(self, tmp_path):
        """Test workflow config survives JSON serialization/deserialization."""
        config_data = {
            "default_memory": "8GB",
            "scripts_dir": "custom_scripts",
            "condor_attributes": {"+WantGPULab": "true"},
        }

        # Create metadata spec with config data
        from wf2wf.core import MetadataSpec
        metadata = MetadataSpec(format_specific={"config": config_data})
        
        wf = Workflow(name="config_test", metadata=metadata)

        # Save and reload
        json_path = tmp_path / "workflow.json"
        wf.save_json(json_path)

        loaded_wf = Workflow.load_json(json_path)
        assert loaded_wf.metadata.format_specific["config"]["default_memory"] == "8GB"
        assert loaded_wf.metadata.format_specific["config"]["scripts_dir"] == "custom_scripts"
        assert loaded_wf.metadata.format_specific["config"]["condor_attributes"]["+WantGPULab"] == "true"

    def test_resource_defaults_application(self):
        """Test applying resource defaults to tasks without explicit resources."""
        wf = Workflow(name="defaults_test")

        # Task without explicit resources
        default_task = Task(id="default_task")
        default_task.command.set_for_environment("echo 'default'", "shared_filesystem")
        wf.add_task(default_task)

        # Task with explicit resources
        explicit_task = Task(
            id="explicit_task",
        )
        explicit_task.command.set_for_environment("echo 'explicit'", "shared_filesystem")
        explicit_task.cpu.set_for_environment(8, "shared_filesystem")
        explicit_task.mem_mb.set_for_environment(16384, "shared_filesystem")
        wf.add_task(explicit_task)

        # Default resource values
        default_cpu = 4
        default_mem_mb = 8192
        default_disk_mb = 10240

        # Simulate applying defaults to tasks without explicit resources
        for task in wf.tasks.values():
            # Check if task has environment-specific values (not just defaults)
            if not task.cpu.has_environment_specific_value("shared_filesystem"):
                task.cpu.set_for_environment(default_cpu, "shared_filesystem")
            if not task.mem_mb.has_environment_specific_value("shared_filesystem"):
                task.mem_mb.set_for_environment(default_mem_mb, "shared_filesystem")
            if not task.disk_mb.has_environment_specific_value("shared_filesystem"):
                task.disk_mb.set_for_environment(default_disk_mb, "shared_filesystem")

        # Verify defaults were applied correctly
        assert wf.tasks["default_task"].cpu.get_value_with_default("shared_filesystem") == 4
        assert wf.tasks["default_task"].mem_mb.get_value_with_default("shared_filesystem") == 8192
        assert wf.tasks["default_task"].disk_mb.get_value_with_default("shared_filesystem") == 10240

        # Verify explicit resources were preserved
        assert wf.tasks["explicit_task"].cpu.get_value_with_default("shared_filesystem") == 8
        assert wf.tasks["explicit_task"].mem_mb.get_value_with_default("shared_filesystem") == 16384
        # Disk not set for explicit_task, so it should have the applied default
        assert wf.tasks["explicit_task"].disk_mb.get_value_with_default("shared_filesystem") == 10240

    def test_workflow_metadata_preservation(self):
        """Test that workflow metadata is preserved through operations."""
        meta_data = {
            "created_by": "wf2wf",
            "source_format": "snakemake",
            "conversion_time": "2024-01-01T12:00:00Z",
            "custom_settings": {"enable_gpu": True, "max_retries": 3},
        }

        # Create metadata spec with meta data
        from wf2wf.core import MetadataSpec
        metadata = MetadataSpec(format_specific={"meta": meta_data})
        
        wf = Workflow(name="meta_test", metadata=metadata)
        assert wf.metadata.format_specific["meta"]["created_by"] == "wf2wf"
        assert wf.metadata.format_specific["meta"]["source_format"] == "snakemake"
        assert wf.metadata.format_specific["meta"]["custom_settings"]["enable_gpu"] is True
        assert wf.metadata.format_specific["meta"]["custom_settings"]["max_retries"] == 3


class TestPerformanceAndScaling:
    """Test performance with large workflows and complex scenarios."""

    def test_large_workflow_creation(self):
        """Test creating a workflow with many tasks."""
        wf = Workflow(name="large_workflow")

        # Create 100 tasks with dependencies
        num_tasks = 100
        for i in range(num_tasks):
            task = Task(
                id=f"task_{i:03d}",
                command=f"echo 'Processing step {i}' > output_{i:03d}.txt",
            )
            task.cpu.set_for_environment(2, "shared_filesystem")
            task.mem_mb.set_for_environment(4096, "shared_filesystem")
            task.disk_mb.set_for_environment(1024, "shared_filesystem")
            wf.add_task(task)

            # Add dependency to previous task (creating a chain)
            if i > 0:
                wf.add_edge(f"task_{i-1:03d}", f"task_{i:03d}")

        # Verify structure
        assert len(wf.tasks) == num_tasks
        assert len(wf.edges) == num_tasks - 1

        # Verify first and last tasks
        assert "task_000" in wf.tasks
        assert "task_099" in wf.tasks
        assert wf.tasks["task_050"].cpu.get_value_with_default("shared_filesystem") == 2

    def test_complex_dependency_network(self):
        """Test workflow with complex dependency patterns."""
        wf = Workflow(name="complex_deps")

        # Create a diamond dependency pattern
        # A -> B, C
        # B, C -> D
        tasks = []
        for task_id in ["A", "B", "C", "D"]:
            task = Task(id=task_id, command=f"echo 'Task {task_id}' > {task_id}.txt")
            wf.add_task(task)
            tasks.append(task)

        # Add diamond dependencies
        wf.add_edge("A", "B")
        wf.add_edge("A", "C")
        wf.add_edge("B", "D")
        wf.add_edge("C", "D")

        # Create fan-out pattern
        # D -> E1, E2, E3, E4, E5
        for i in range(1, 6):
            task_id = f"E{i}"
            task = Task(id=task_id, command=f"echo 'Fan-out task {i}' > {task_id}.txt")
            wf.add_task(task)
            wf.add_edge("D", task_id)

        # Create fan-in pattern
        # E1, E2, E3, E4, E5 -> F
        final_task = Task(id="F", command="echo 'Final task' > F.txt")
        wf.add_task(final_task)

        for i in range(1, 6):
            wf.add_edge(f"E{i}", "F")

        # Verify structure
        assert len(wf.tasks) == 10  # A, B, C, D, E1-E5, F
        assert len(wf.edges) == 14  # 2 + 2 + 5 + 5 = 14

        # Verify specific dependencies exist
        edge_pairs = [(e.parent, e.child) for e in wf.edges]
        assert ("A", "B") in edge_pairs
        assert ("A", "C") in edge_pairs
        assert ("B", "D") in edge_pairs
        assert ("C", "D") in edge_pairs
        assert ("E1", "F") in edge_pairs

    def test_workflow_with_special_characters(self):
        """Test workflow handling tasks with special characters in names/paths."""
        wf = Workflow(name="special_chars")

        # Task with special characters in file paths
        special_task = Task(
            id="special_chars_task",
            command="echo 'test' > 'output with spaces.txt'",
            inputs=["input-file_v1.2.txt", "data (copy).csv"],
            outputs=["result [final].txt", "summary-2024_01_01.log"],
        )
        wf.add_task(special_task)

        # Verify the task was created correctly
        assert special_task.inputs[0] == "input-file_v1.2.txt"
        assert special_task.inputs[1] == "data (copy).csv"
        assert special_task.outputs[0] == "result [final].txt"
        assert special_task.outputs[1] == "summary-2024_01_01.log"

    def test_empty_task_handling(self):
        """Test handling of tasks with minimal specifications."""
        wf = Workflow(name="empty_tasks")

        # Task with minimal specification
        empty_task = Task(id="empty_task")
        empty_task.command.set_for_environment("echo 'empty'", "shared_filesystem")
        wf.add_task(empty_task)

        # Verify default resource values
        assert empty_task.cpu.get_value_with_default("shared_filesystem") == 1
        assert empty_task.mem_mb.get_value_with_default("shared_filesystem") == 4096
        assert empty_task.disk_mb.get_value_with_default("shared_filesystem") == 4096
        assert empty_task.gpu.get_value_with_default("shared_filesystem") == 0
        assert empty_task.extra == {}

        # Verify task can be exported (should use defaults)
        assert len(wf.tasks) == 1
        assert "empty_task" in wf.tasks


class TestEdgeCases:
    """Test various edge cases and error conditions."""

    def test_duplicate_task_id_prevention(self):
        """Test that duplicate task IDs are prevented."""
        wf = Workflow(name="duplicate_test")

        task1 = Task(id="duplicate_id")
        task1.command.set_for_environment("echo 'first'", "shared_filesystem")
        wf.add_task(task1)

        task2 = Task(id="duplicate_id")
        task2.command.set_for_environment("echo 'second'", "shared_filesystem")

        with pytest.raises(ValueError, match="Duplicate task id"):
            wf.add_task(task2)

    def test_self_dependency_prevention(self):
        """Test handling of self-referential dependencies."""
        wf = Workflow(name="self_dep_test")

        task = Task(id="self_task")
        task.command.set_for_environment("echo 'self'", "shared_filesystem")
        wf.add_task(task)

        # Self-dependencies should be silently ignored
        wf.add_edge("self_task", "self_task")

        # Verify the edge was NOT added
        self_edges = [e for e in wf.edges if e.parent == e.child]
        assert len(self_edges) == 0

    def test_nonexistent_task_dependencies(self):
        """Test handling of dependencies to nonexistent tasks."""
        wf = Workflow(name="missing_dep_test")

        task = Task(id="existing_task")
        task.command.set_for_environment("echo 'exists'", "shared_filesystem")
        wf.add_task(task)

        # Adding edges to nonexistent tasks should raise errors
        with pytest.raises(KeyError, match="not found in workflow"):
            wf.add_edge("existing_task", "nonexistent_task")

        with pytest.raises(KeyError, match="not found in workflow"):
            wf.add_edge("another_missing_task", "existing_task")

    def test_workflow_json_roundtrip_with_complex_data(self, tmp_path):
        """Test JSON serialization/deserialization with complex nested data."""
        wf = Workflow(name="complex_json_test")

        # Task with complex nested data structures
        complex_task = Task(
            id="complex_task",
        )
        complex_task.command.set_for_environment("python complex_script.py", "shared_filesystem")
        complex_task.cpu.set_for_environment(8, "shared_filesystem")
        complex_task.mem_mb.set_for_environment(16384, "shared_filesystem")
        complex_task.extra = {
            "custom_list": EnvironmentSpecificValue(["a", "b", "c"]),
            "custom_dict": EnvironmentSpecificValue({"key1": "value1", "key2": 42}),
        }
        
        # Create metadata spec with complex data
        from wf2wf.core import MetadataSpec
        metadata = MetadataSpec(
            format_specific={
                "description": "A task with complex nested data",
                "tags": ["analysis", "complex", "test"],
                "config": {"enable_logging": True, "log_level": "DEBUG"},
            }
        )
        complex_task.metadata = metadata
        
        wf.add_task(complex_task)

        # Save and reload
        json_path = tmp_path / "complex_workflow.json"
        wf.save_json(json_path)

        loaded_wf = Workflow.load_json(json_path)
        loaded_task = loaded_wf.tasks["complex_task"]

        # Verify complex data was preserved
        assert loaded_task.extra["custom_list"].get_value_with_default("shared_filesystem") == ["a", "b", "c"]
        assert loaded_task.extra["custom_dict"].get_value_with_default("shared_filesystem")["key2"] == 42

        assert loaded_task.metadata.format_specific["tags"] == ["analysis", "complex", "test"]
        assert loaded_task.metadata.format_specific["config"]["enable_logging"] is True

    def test_workflow_with_unicode_content(self):
        """Test workflow handling of Unicode characters."""
        wf = Workflow(name="unicode_test")

        unicode_task = Task(
            id="unicode_task",
        )
        unicode_task.command.set_for_environment("echo '测试 🧬 Análisis' > résultats.txt", "shared_filesystem")
        unicode_task.inputs = ["données_入力.csv"]
        unicode_task.outputs = ["結果_output.txt"]
        
        # Create metadata spec with Unicode data
        from wf2wf.core import MetadataSpec
        metadata = MetadataSpec(
            format_specific={
                "description": "Tâche avec caractères Unicode 中文 🔬",
                "author": "José María González",
            }
        )
        unicode_task.metadata = metadata
        
        wf.add_task(unicode_task)

        # Verify Unicode content is preserved
        assert "测试 🧬 Análisis" in unicode_task.command.get_value_for("shared_filesystem")
        assert unicode_task.inputs[0] == "données_入力.csv"
        assert unicode_task.outputs[0] == "結果_output.txt"
        assert "José María González" in unicode_task.metadata.format_specific["author"]


class TestDAGManExportAdvanced:
    """Test advanced DAGMan export features."""

    def test_dagman_export_large_workflow(self, tmp_path):
        """Test DAGMan export performance with large workflows."""
        wf = Workflow(name="large_export_test")

        # Create a moderately large workflow (50 tasks)
        num_tasks = 50
        for i in range(num_tasks):
            task = Task(
                id=f"task_{i:02d}",
            )
            task.command.set_for_environment(f"echo 'Task {i}' > output_{i:02d}.txt", "distributed_computing")
            task.cpu.set_for_environment(2 if i % 2 == 0 else 4, "distributed_computing")
            task.mem_mb.set_for_environment(4096 + (i * 100), "distributed_computing")  # Varying memory requirements
            task.disk_mb.set_for_environment(1024 + (i * 50), "distributed_computing")  # Varying disk requirements
            wf.add_task(task)

            # Create some dependencies (not fully linear)
            if i > 0 and i % 5 != 0:  # Skip every 5th task for parallel branches
                wf.add_edge(f"task_{i-1:02d}", f"task_{i:02d}")

        # Export to DAG
        dag_path = tmp_path / "large_workflow.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        # Verify DAG file was created and has reasonable content
        assert dag_path.exists()
        dag_content = dag_path.read_text()

        # Check that all tasks are represented
        for i in range(num_tasks):
            assert f"task_{i:02d}" in dag_content

        # Verify some resource specifications in submit files
        # Check a few sample submit files for resource specifications
        task_00_submit = tmp_path / "task_00.sub"
        task_01_submit = tmp_path / "task_01.sub"

        task_00_content = task_00_submit.read_text()
        task_01_content = task_01_submit.read_text()

        assert "request_cpus = 2" in task_00_content  # Even task (i=0)
        assert "request_cpus = 4" in task_01_content  # Odd task (i=1)
        assert "request_memory" in task_00_content
        assert "request_disk" in task_00_content

    def test_dagman_export_with_special_characters(self, tmp_path):
        """Test DAGMan export handles special characters properly."""
        wf = Workflow(name="special_chars_export")

        task = Task(
            id="special_task",
        )
        task.command.set_for_environment("echo 'test with spaces and (parentheses)' > 'output file.txt'", "shared_filesystem")
        task.inputs = ["input-file_v1.2.txt"]
        task.outputs = ["result [final].txt"]
        wf.add_task(task)

        dag_path = tmp_path / "special_chars.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

        assert dag_path.exists()
        dag_content = dag_path.read_text()

        # Verify the task is present in the DAG
        assert "special_task" in dag_content

        # Note: The exact handling of special characters in DAGMan output
        # depends on the exporter implementation
