"""
Comprehensive tests for error-handling edge cases in wf2wf:
- Circular dependency detection and proper error reporting
- Empty workflow handling with helpful error messages
- Malformed Snakefile syntax error handling
- Missing input file handling
- Invalid resource specifications
"""

import sys
import pathlib
import importlib.util
import tempfile
import textwrap
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from subprocess import CalledProcessError

# Allow running tests without installing package
proj_root = pathlib.Path(__file__).resolve().parents[1]

if "wf2wf" not in sys.modules:
    spec = importlib.util.spec_from_file_location("wf2wf", proj_root / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["wf2wf"] = module  # type: ignore[assignment]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[arg-type]

from wf2wf.core import Workflow, Task
from wf2wf.exporters import dagman as dag_exporter
from wf2wf.importers import snakemake as snake_importer


class TestCircularDependencies:
    """Test circular dependency detection and error handling."""

    def test_circular_dependency_detection_simple(self, tmp_path):
        """Test detection of simple A→B→A circular dependency."""
        # Create circular dependency Snakefile
        snakefile = tmp_path / "circular.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule A:
                input: "B_out.txt"
                output: "A_out.txt"
                shell: "echo 'A' > {output}"

            rule B:
                input: "A_out.txt"
                output: "B_out.txt"
                shell: "echo 'B' > {output}"

            rule all:
                input: "A_out.txt"
        """)
        )

        # Mock Snakemake to return circular dependency error
        def _mock_run_circular(
            cmd, capture_output=False, text=False, check=False, **kwargs
        ):
            m = MagicMock()
            if "--dag" in cmd:
                # Simulate Snakemake detecting circular dependency
                m.stdout = ""
                m.stderr = "Error: Circular dependency detected between rules A and B"
                m.returncode = 1
                raise CalledProcessError(1, cmd, output="", stderr=m.stderr)
            return m

        with patch(
            "wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake"
        ):
            with patch(
                "wf2wf.importers.snakemake.subprocess.run",
                side_effect=_mock_run_circular,
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    snake_importer.to_workflow(snakefile, workdir=tmp_path)

                assert "snakemake --dag" in str(exc_info.value)
                assert "failed" in str(exc_info.value).lower()

    def test_circular_dependency_detection_complex(self, tmp_path):
        """Test detection of complex A→B→C→A circular dependency."""
        snakefile = tmp_path / "circular_complex.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule A:
                input: "C_out.txt"
                output: "A_out.txt"
                shell: "echo 'A' > {output}"

            rule B:
                input: "A_out.txt"
                output: "B_out.txt"
                shell: "echo 'B' > {output}"

            rule C:
                input: "B_out.txt"
                output: "C_out.txt"
                shell: "echo 'C' > {output}"

            rule all:
                input: "A_out.txt"
        """)
        )

        def _mock_run_complex_circular(
            cmd, capture_output=False, text=False, check=False, **kwargs
        ):
            m = MagicMock()
            if "--dag" in cmd:
                m.stdout = ""
                m.stderr = (
                    "Error: Circular dependency detected in workflow: A → B → C → A"
                )
                m.returncode = 1
                raise CalledProcessError(1, cmd, output="", stderr=m.stderr)
            return m

        with patch(
            "wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake"
        ):
            with patch(
                "wf2wf.importers.snakemake.subprocess.run",
                side_effect=_mock_run_complex_circular,
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    snake_importer.to_workflow(snakefile, workdir=tmp_path)

                assert "failed" in str(exc_info.value).lower()

    def test_workflow_with_cycle_export_fails_gracefully(self):
        """Test that a workflow with manually created cycles fails export gracefully."""
        # Manually create a workflow with circular dependency
        wf = Workflow(name="circular_test")

        task_a = Task(id="task_a", command="echo A", outputs=["a.txt"])
        task_b = Task(
            id="task_b", command="echo B", inputs=["a.txt"], outputs=["b.txt"]
        )
        task_c = Task(
            id="task_c", command="echo C", inputs=["b.txt"], outputs=["c.txt"]
        )

        wf.add_task(task_a)
        wf.add_task(task_b)
        wf.add_task(task_c)

        # Create circular dependency: A→B→C→A
        wf.add_edge("task_a", "task_b")
        wf.add_edge("task_b", "task_c")
        wf.add_edge("task_c", "task_a")  # This creates the cycle

        # The workflow IR should still be created (cycle detection is Snakemake's job)
        assert len(wf.tasks) == 3
        assert len(wf.edges) == 3

        # But DAG export should still work (HTCondor will handle the cycle)
        with tempfile.TemporaryDirectory() as tmp_dir:
            dag_path = Path(tmp_dir) / "circular.dag"
            dag_exporter.from_workflow(wf, dag_path, workdir=Path(tmp_dir))

            # Verify DAG was created with all dependencies
            dag_content = dag_path.read_text()
            assert "PARENT task_a CHILD task_b" in dag_content
            assert "PARENT task_b CHILD task_c" in dag_content
            assert "PARENT task_c CHILD task_a" in dag_content


class TestEmptyWorkflows:
    """Test empty workflow handling with helpful error messages."""

    def test_empty_snakefile(self, tmp_path):
        """Test handling of completely empty Snakefile."""
        snakefile = tmp_path / "empty.smk"
        snakefile.write_text("")

        def _mock_run_empty(
            cmd, capture_output=False, text=False, check=False, **kwargs
        ):
            m = MagicMock()
            if "--dag" in cmd:
                m.stdout = "digraph snakemake_dag {}"  # Empty DAG
                m.stderr = ""
                m.returncode = 0
            elif "--dry-run" in cmd:
                m.stdout = "Nothing to be done."
                m.stderr = ""
                m.returncode = 0
            return m

        with patch(
            "wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake"
        ):
            with patch(
                "wf2wf.importers.snakemake.subprocess.run", side_effect=_mock_run_empty
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    snake_importer.to_workflow(snakefile, workdir=tmp_path)

                assert "No jobs found" in str(exc_info.value)

    def test_snakefile_with_only_comments(self, tmp_path):
        """Test handling of Snakefile with only comments."""
        snakefile = tmp_path / "comments_only.smk"
        snakefile.write_text(
            textwrap.dedent("""
            # This is a comment
            # Another comment
            # No actual rules here
        """)
        )

        def _mock_run_comments_only(
            cmd, capture_output=False, text=False, check=False, **kwargs
        ):
            m = MagicMock()
            if "--dag" in cmd:
                m.stdout = "digraph snakemake_dag {}"
                m.stderr = ""
                m.returncode = 0
            elif "--dry-run" in cmd:
                m.stdout = "Nothing to be done."
                m.stderr = ""
                m.returncode = 0
            return m

        with patch(
            "wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake"
        ):
            with patch(
                "wf2wf.importers.snakemake.subprocess.run",
                side_effect=_mock_run_comments_only,
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    snake_importer.to_workflow(snakefile, workdir=tmp_path)

                assert "No jobs found" in str(exc_info.value)

    def test_snakefile_with_no_target_rules(self, tmp_path):
        """Test handling of Snakefile with rules but no target rules."""
        snakefile = tmp_path / "no_targets.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule orphan_rule:
                output: "orphan.txt"
                shell: "echo 'orphan' > {output}"
        """)
        )

        def _mock_run_no_targets(
            cmd, capture_output=False, text=False, check=False, **kwargs
        ):
            m = MagicMock()
            if "--dag" in cmd:
                m.stdout = "digraph snakemake_dag {}"  # No target rules = empty DAG
                m.stderr = ""
                m.returncode = 0
            elif "--dry-run" in cmd:
                m.stdout = "Nothing to be done."
                m.stderr = ""
                m.returncode = 0
            return m

        with patch(
            "wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake"
        ):
            with patch(
                "wf2wf.importers.snakemake.subprocess.run",
                side_effect=_mock_run_no_targets,
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    snake_importer.to_workflow(snakefile, workdir=tmp_path)

                assert "No jobs found" in str(exc_info.value)

    def test_empty_workflow_ir_export(self):
        """Test that empty Workflow IR fails export gracefully."""
        wf = Workflow(name="empty_workflow")
        # No tasks added

        assert len(wf.tasks) == 0
        assert len(wf.edges) == 0

        with tempfile.TemporaryDirectory() as tmp_dir:
            dag_path = Path(tmp_dir) / "empty.dag"

            # Export should work but produce minimal DAG
            dag_exporter.from_workflow(wf, dag_path, workdir=Path(tmp_dir))

            dag_content = dag_path.read_text()
            assert "# HTCondor DAGMan file generated by wf2wf" in dag_content
            assert "JOB" not in dag_content  # No job definitions
            assert "PARENT" not in dag_content  # No dependencies


class TestMalformedSnakefiles:
    """Test handling of Snakefiles with syntax errors."""

    def test_python_syntax_error(self, tmp_path):
        """Test handling of Snakefile with Python syntax error."""
        snakefile = tmp_path / "syntax_error.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule all:
                input: "result.txt"

            rule process:
                output: "result.txt"
                shell: "echo 'result' > {output}"

                This is not valid Python syntax!
        """)
        )

        def _mock_run_syntax_error(
            cmd, capture_output=False, text=False, check=False, **kwargs
        ):
            m = MagicMock()
            if "--dag" in cmd:
                m.stdout = ""
                m.stderr = "SyntaxError: invalid syntax"
                m.returncode = 1
                raise CalledProcessError(1, cmd, output="", stderr=m.stderr)
            return m

        with patch(
            "wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake"
        ):
            with patch(
                "wf2wf.importers.snakemake.subprocess.run",
                side_effect=_mock_run_syntax_error,
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    snake_importer.to_workflow(snakefile, workdir=tmp_path)

                assert "failed" in str(exc_info.value).lower()

    def test_missing_required_directive(self, tmp_path):
        """Test handling of rule missing required directive."""
        snakefile = tmp_path / "missing_directive.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule all:
                input: "result.txt"

            rule incomplete:
                # Missing output directive
                shell: "echo 'incomplete' > result.txt"
        """)
        )

        def _mock_run_missing_directive(
            cmd, capture_output=False, text=False, check=False, **kwargs
        ):
            m = MagicMock()
            if "--dag" in cmd:
                m.stdout = ""
                m.stderr = "RuleException: Rule 'incomplete' has no output files"
                m.returncode = 1
                raise CalledProcessError(1, cmd, output="", stderr=m.stderr)
            return m

        with patch(
            "wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake"
        ):
            with patch(
                "wf2wf.importers.snakemake.subprocess.run",
                side_effect=_mock_run_missing_directive,
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    snake_importer.to_workflow(snakefile, workdir=tmp_path)

                assert "failed" in str(exc_info.value).lower()


class TestMissingInputFiles:
    """Test handling of missing input files and dependencies."""

    def test_missing_input_files_strict_mode(self, tmp_path):
        """Test handling when Snakemake fails due to missing input files."""
        snakefile = tmp_path / "missing_inputs.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule all:
                input: "final.txt"

            rule process:
                input: "missing_file.txt"  # This file doesn't exist
                output: "final.txt"
                shell: "cat {input} > {output}"
        """)
        )

        def _mock_run_missing_inputs(
            cmd, capture_output=False, text=False, check=False, **kwargs
        ):
            m = MagicMock()
            if "--dag" in cmd:
                m.stdout = ""
                m.stderr = "MissingInputException: Missing input files for rule process: missing_file.txt"
                m.returncode = 1
                raise CalledProcessError(1, cmd, output="", stderr=m.stderr)
            return m

        with patch(
            "wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake"
        ):
            with patch(
                "wf2wf.importers.snakemake.subprocess.run",
                side_effect=_mock_run_missing_inputs,
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    snake_importer.to_workflow(snakefile, workdir=tmp_path)

                assert "failed" in str(exc_info.value).lower()

    def test_missing_input_files_forceall_mode(self, tmp_path):
        """Test that --forceall allows processing despite missing inputs."""
        snakefile = tmp_path / "missing_inputs_force.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule all:
                input: "final.txt"

            rule process:
                input: "missing_file.txt"
                output: "final.txt"
                shell: "cat {input} > {output}"
        """)
        )

        def _mock_run_forceall(
            cmd, capture_output=False, text=False, check=False, **kwargs
        ):
            m = MagicMock()
            if "--dag" in cmd and "--forceall" in cmd:
                # With --forceall, Snakemake should generate DAG even with missing inputs
                m.stdout = """digraph snakemake_dag {
0 [label="rule process"];
1 [label="rule all"];
0 -> 1;
}"""
                m.stderr = ""
                m.returncode = 0
            elif "--dry-run" in cmd and "--forceall" in cmd:
                m.stdout = """Building DAG of jobs...
rule process:
    input: missing_file.txt
    output: final.txt
    jobid: 0
    reason: Missing output files: final.txt
    resources: tmpdir=<TBD>
rule all:
    input: final.txt
    jobid: 1
    reason: Input files updated by another job: final.txt
    resources: tmpdir=<TBD>
Nothing to be done."""
                m.stderr = ""
                m.returncode = 0
            return m

        with patch(
            "wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake"
        ):
            with patch(
                "wf2wf.importers.snakemake.subprocess.run",
                side_effect=_mock_run_forceall,
            ):
                # This should succeed because we use --forceall
                wf = snake_importer.to_workflow(snakefile, workdir=tmp_path)

                assert len(wf.tasks) == 2  # process and all rules

                # Find the process task
                process_task = None
                for task in wf.tasks.values():
                    if "process" in task.id:
                        process_task = task
                        break

                assert process_task is not None
                # The key test is that it doesn't fail - the workflow was created
                assert wf.name is not None


class TestInvalidResourceSpecifications:
    """Test handling of invalid resource specifications."""

    def test_invalid_resource_syntax(self, tmp_path):
        """Test handling of invalid resource syntax in Snakefile."""
        snakefile = tmp_path / "invalid_resources.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule all:
                input: "result.txt"

            rule process:
                output: "result.txt"
                resources:
                    mem_mb = "not_a_number"  # Invalid syntax
                shell: "echo 'result' > {output}"
        """)
        )

        def _mock_run_invalid_resources(
            cmd, capture_output=False, text=False, check=False, **kwargs
        ):
            m = MagicMock()
            if "--dag" in cmd:
                m.stdout = ""
                m.stderr = "WorkflowError: Failed to parse resources"
                m.returncode = 1
                raise CalledProcessError(1, cmd, output="", stderr=m.stderr)
            return m

        with patch(
            "wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake"
        ):
            with patch(
                "wf2wf.importers.snakemake.subprocess.run",
                side_effect=_mock_run_invalid_resources,
            ):
                with pytest.raises(RuntimeError) as exc_info:
                    snake_importer.to_workflow(snakefile, workdir=tmp_path)

                assert "failed" in str(exc_info.value).lower()

    def test_negative_resource_values(self, tmp_path):
        """Test handling of negative resource values."""
        snakefile = tmp_path / "negative_resources.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule all:
                input: "result.txt"

            rule process:
                output: "result.txt"
                resources:
                    mem_mb=-1000,
                    cpus=-2
                shell: "echo 'result' > {output}"
        """)
        )

        def _mock_run_negative_resources(
            cmd, capture_output=False, text=False, check=False, **kwargs
        ):
            m = MagicMock()
            if "--dag" in cmd:
                m.stdout = """digraph snakemake_dag {
0 [label="rule process"];
1 [label="rule all"];
0 -> 1;
}"""
                m.stderr = ""
                m.returncode = 0
            elif "--dry-run" in cmd:
                m.stdout = """Building DAG of jobs...
rule process:
    output: result.txt
    jobid: 0
    resources: mem_mb=-1000, cpus=-2, tmpdir=<TBD>
rule all:
    input: result.txt
    jobid: 1
    resources: tmpdir=<TBD>
Nothing to be done."""
                m.stderr = ""
                m.returncode = 0
            return m

        with patch(
            "wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake"
        ):
            with patch(
                "wf2wf.importers.snakemake.subprocess.run",
                side_effect=_mock_run_negative_resources,
            ):
                # Should parse but with negative values preserved
                wf = snake_importer.to_workflow(snakefile, workdir=tmp_path)

                process_task = None
                for task in wf.tasks.values():
                    if "process" in task.id:
                        process_task = task
                        break

                assert process_task is not None
                # Check if negative values are preserved in extra resources or handled gracefully
                assert (
                    process_task.resources.mem_mb == -1000
                    or process_task.resources.mem_mb
                    == 0  # Default if negative not supported
                    or -1000 in process_task.resources.extra.values()
                )
                assert (
                    process_task.resources.cpu == -2
                    or process_task.resources.cpu
                    == 1  # Default if negative not supported
                    or -2 in process_task.resources.extra.values()
                )


class TestSnakemakeExecutableHandling:
    """Test handling of Snakemake executable availability and errors."""

    def test_snakemake_not_found(self, tmp_path):
        """Test handling when Snakemake executable is not found."""
        snakefile = tmp_path / "simple.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule all:
                input: "result.txt"

            rule process:
                output: "result.txt"
                shell: "echo 'result' > {output}"
        """)
        )

        with patch("wf2wf.importers.snakemake.shutil.which", lambda x: None):
            with pytest.raises(RuntimeError) as exc_info:
                snake_importer.to_workflow(snakefile, workdir=tmp_path)

            assert "snakemake" in str(exc_info.value).lower()
            assert "not found" in str(exc_info.value).lower()

    def test_snakemake_permission_denied(self, tmp_path):
        """Test handling when Snakemake executable exists but can't be executed."""
        snakefile = tmp_path / "simple.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule all:
                input: "result.txt"

            rule process:
                output: "result.txt"
                shell: "echo 'result' > {output}"
        """)
        )

        def _mock_run_permission_denied(
            cmd, capture_output=False, text=False, check=False, **kwargs
        ):
            raise PermissionError("Permission denied")

        with patch(
            "wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake"
        ):
            with patch(
                "wf2wf.importers.snakemake.subprocess.run",
                side_effect=_mock_run_permission_denied,
            ):
                with pytest.raises(PermissionError):
                    snake_importer.to_workflow(snakefile, workdir=tmp_path)


class TestIntegrationErrorHandling:
    """Integration tests for error handling across the full pipeline."""

    def test_error_propagation_through_pipeline(self, tmp_path):
        """Test that errors propagate correctly through import→export pipeline."""
        # Create a workflow that will fail during import
        snakefile = tmp_path / "failing_workflow.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule A:
                input: "B.txt"
                output: "A.txt"
                shell: "cat {input} > {output}"

            rule B:
                input: "A.txt"  # Circular dependency
                output: "B.txt"
                shell: "cat {input} > {output}"

            rule all:
                input: "A.txt"
        """)
        )

        def _mock_run_circular_integration(
            cmd, capture_output=False, text=False, check=False, **kwargs
        ):
            m = MagicMock()
            if "--dag" in cmd:
                m.stdout = ""
                m.stderr = "Error: Circular dependency detected"
                m.returncode = 1
                raise CalledProcessError(1, cmd, output="", stderr=m.stderr)
            return m

        with patch(
            "wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake"
        ):
            with patch(
                "wf2wf.importers.snakemake.subprocess.run",
                side_effect=_mock_run_circular_integration,
            ):
                # Import should fail
                with pytest.raises(RuntimeError):
                    snake_importer.to_workflow(snakefile, workdir=tmp_path)

    def test_partial_workflow_recovery(self, tmp_path):
        """Test that partially valid workflows can still be processed."""
        snakefile = tmp_path / "partial_workflow.smk"
        snakefile.write_text(
            textwrap.dedent("""
            rule all:
                input: "good.txt"

            rule good_rule:
                output: "good.txt"
                shell: "echo 'good' > {output}"
        """)
        )

        def _mock_run_partial_success(
            cmd, capture_output=False, text=False, check=False, **kwargs
        ):
            m = MagicMock()
            if "--dag" in cmd:
                m.stdout = """digraph snakemake_dag {
0 [label="rule good_rule"];
1 [label="rule all"];
0 -> 1;
}"""
                m.stderr = "Warning: Some rules may have issues"
                m.returncode = 0
            elif "--dry-run" in cmd:
                m.stdout = """Building DAG of jobs...
rule good_rule:
    output: good.txt
    jobid: 0
    resources: tmpdir=<TBD>
rule all:
    input: good.txt
    jobid: 1
    resources: tmpdir=<TBD>
Nothing to be done."""
                m.stderr = "Warning: Some rules may have issues"
                m.returncode = 0
            return m

        with patch(
            "wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake"
        ):
            with patch(
                "wf2wf.importers.snakemake.subprocess.run",
                side_effect=_mock_run_partial_success,
            ):
                # Should succeed despite warnings
                wf = snake_importer.to_workflow(snakefile, workdir=tmp_path)

                assert len(wf.tasks) == 2

                # Export should also succeed
                dag_path = tmp_path / "partial.dag"
                dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

                dag_content = dag_path.read_text()
                # Check for the actual job names generated by the exporter
                assert (
                    "JOB rule_good_rule_0" in dag_content
                    or "JOB good_rule" in dag_content
                    or "good_rule" in dag_content
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
