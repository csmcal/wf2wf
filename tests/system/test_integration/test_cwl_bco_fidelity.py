"""
Comprehensive tests for CWL and BCO fidelity preservation.

This module tests the complete preservation of CWL v1.2.1 and BCO features
across all import/export operations, including round-trip conversions through
different workflow engines.
"""

import yaml
import pytest

from wf2wf.core import (
    Workflow,
    Task,
    ProvenanceSpec,
    DocumentationSpec,
    ParameterSpec,
    RequirementSpec,
)
from wf2wf.importers.cwl import to_workflow
from wf2wf.exporters.cwl import from_workflow
from wf2wf.exporters.dagman import from_workflow as dagman_from_workflow
from wf2wf.importers.dagman import to_workflow as dagman_to_workflow


class TestCWLFidelityPreservation:
    """Test comprehensive CWL feature preservation."""

    def test_advanced_metadata_preservation(self, persistent_test_output):
        """Test preservation of advanced CWL metadata."""
        # Create workflow with comprehensive metadata
        provenance = ProvenanceSpec(
            authors=[{"name": "Test Author", "orcid": "orcid:0000-0000-0000-0000"}],
            version="2.1.0",
            license="MIT",
            doi="10.1000/test.doi",
            keywords=["bioinformatics", "workflow", "analysis"],
        )

        documentation = DocumentationSpec(
            label="Advanced Analysis Pipeline",
            doc="Comprehensive bioinformatics analysis workflow with advanced features",
            intent=["http://edamontology.org/operation_0004"],
        )

        workflow = Workflow(
            name="advanced_metadata_test",
            version="2.1.0",
            label="Advanced Metadata Test",
            doc="Test workflow for metadata preservation",
            provenance=provenance,
            documentation=documentation,
            cwl_version="v1.2",
        )

        # Add task with advanced metadata
        task = Task(
            id="analysis_task",
            label="Primary Analysis",
            doc="Main analysis step with comprehensive metadata",
            provenance=provenance,
            documentation=documentation,
            intent=["http://edamontology.org/operation_0004"],
        )
        # Set command using new IR
        task.command.set_for_environment("analysis_tool --input {input} --output {output}", "shared_filesystem")
        workflow.add_task(task)

        # Export to CWL
        cwl_file = persistent_test_output / "advanced_metadata.cwl"
        from_workflow(workflow, cwl_file, preserve_metadata=True, verbose=True)

        # Re-import and verify preservation
        imported_workflow = to_workflow(cwl_file, preserve_metadata=True)

        # Verify workflow-level metadata
        assert imported_workflow.label == "Advanced Metadata Test"
        assert imported_workflow.doc == "Test workflow for metadata preservation"
        assert imported_workflow.cwl_version == "v1.2"
        assert imported_workflow.provenance is not None
        assert imported_workflow.provenance.version == "2.1.0"
        assert imported_workflow.provenance.license == "MIT"
        assert "bioinformatics" in imported_workflow.provenance.keywords

        # Verify task-level metadata
        imported_task = imported_workflow.tasks["analysis_task"]
        assert imported_task.label == "Primary Analysis"
        assert imported_task.doc == "Main analysis step with comprehensive metadata"
        assert imported_task.intent == ["http://edamontology.org/operation_0004"]

    def test_parameter_specifications_preservation(self, persistent_test_output):
        """Test preservation of CWL parameter specifications."""
        workflow = Workflow(name="param_spec_test", version="1.0")

        # Create task with comprehensive parameter specifications
        input_params = [
            ParameterSpec(
                id="input_file",
                type="File",
                label="Input Data File",
                doc="Primary input data file",
                format="http://edamontology.org/format_1930",  # FASTQ
                secondary_files=[".fai", ".amb"],
                streamable=True,
                load_contents=False,
            ),
            ParameterSpec(
                id="threshold",
                type="float",
                label="Analysis Threshold",
                doc="Quality threshold for analysis",
                default=0.05,
            ),
        ]

        output_params = [
            ParameterSpec(
                id="results",
                type="File",
                label="Analysis Results",
                doc="Primary analysis output",
                format="http://edamontology.org/format_3475",  # TSV
                output_binding={"glob": "results.tsv"},
            )
        ]

        task = Task(
            id="param_task",
            inputs=input_params,
            outputs=output_params,
        )
        # Set command using new IR
        task.command.set_for_environment("analysis_tool", "shared_filesystem")
        workflow.add_task(task)

        # Export to CWL
        cwl_file = persistent_test_output / "param_spec.cwl"
        from_workflow(workflow, cwl_file, preserve_metadata=True)

        # Re-import and verify parameter preservation
        imported_workflow = to_workflow(cwl_file, preserve_metadata=True)
        imported_task = imported_workflow.tasks["param_task"]

        # Verify input parameters
        input_file_param = next(p for p in imported_task.inputs if p.id == "input_file")
        assert input_file_param.type == "File"
        assert input_file_param.format == "http://edamontology.org/format_1930"
        assert ".fai" in input_file_param.secondary_files
        assert input_file_param.streamable is True

        threshold_param = next(p for p in imported_task.inputs if p.id == "threshold")
        assert threshold_param.type == "float"
        assert threshold_param.default == 0.05

        # Verify output parameters
        results_param = next(p for p in imported_task.outputs if p.id == "results")
        assert results_param.type == "File"
        assert results_param.format == "http://edamontology.org/format_3475"
        assert results_param.output_binding["glob"] == "results.tsv"

    def test_requirements_and_hints_preservation(self, tmp_path):
        """Test preservation of CWL requirements and hints."""
        workflow = Workflow(name="requirements_test", version="1.0")

        # Create comprehensive requirements and hints
        requirements = [
            RequirementSpec(
                "DockerRequirement", {"dockerPull": "biocontainers/fastqc:v0.11.9_cv8"}
            ),
            RequirementSpec(
                "ResourceRequirement",
                {"coresMin": 4, "ramMin": 8192, "tmpdirMin": 10240, "outdirMin": 5120},
            ),
            RequirementSpec(
                "EnvironmentVarRequirement",
                {
                    "envDef": [
                        {"envName": "TMPDIR", "envValue": "/tmp"},
                        {"envName": "THREADS", "envValue": "$(runtime.cores)"},
                    ]
                },
            ),
        ]

        hints = [
            RequirementSpec("NetworkAccess", {"networkAccess": True}),
            RequirementSpec("TimeLimit", {"timelimit": 3600}),
        ]

        task = Task(
            id="requirements_task",
        )
        task.requirements.set_for_environment(requirements, "shared_filesystem")
        task.hints.set_for_environment(hints, "shared_filesystem")
        # Set command using new IR
        task.command.set_for_environment("fastqc $(inputs.input_file.path)", "shared_filesystem")
        workflow.add_task(task)

        # Export to CWL
        cwl_file = tmp_path / "requirements.cwl"
        from_workflow(workflow, cwl_file, preserve_metadata=True, verbose=True)

        # Re-import and verify requirements preservation
        imported_workflow = to_workflow(cwl_file, preserve_metadata=True)
        imported_task = imported_workflow.tasks["requirements_task"]

        # Debug: Print what was imported
        print(f"Imported task ID: {imported_task.id}")
        imported_requirements = imported_task.requirements.get_value_for("shared_filesystem") or []
        imported_hints = imported_task.hints.get_value_for("shared_filesystem") or []
        print(f"Imported requirements count: {len(imported_requirements)}")
        print(f"Imported hints count: {len(imported_hints)}")
        for i, req in enumerate(imported_requirements):
            print(f"  Requirement {i}: {req.class_name} - {req.data}")
        for i, hint in enumerate(imported_hints):
            print(f"  Hint {i}: {hint.class_name} - {hint.data}")

        # Verify requirements
        docker_req = next(
            r for r in imported_requirements if r.class_name == "DockerRequirement"
        )
        assert docker_req.data["dockerPull"] == "biocontainers/fastqc:v0.11.9_cv8"

        resource_req = next(
            r for r in imported_requirements if r.class_name == "ResourceRequirement"
        )
        assert resource_req.data["coresMin"] == 4
        assert resource_req.data["ramMin"] == 8192
        assert resource_req.data["tmpdirMin"] == 10240
        assert resource_req.data["outdirMin"] == 5120

        env_req = next(
            r for r in imported_requirements if r.class_name == "EnvironmentVarRequirement"
        )
        env_def = env_req.data["envDef"]
        assert len(env_def) == 2
        assert env_def[0]["envName"] == "TMPDIR"
        assert env_def[0]["envValue"] == "/tmp"
        assert env_def[1]["envName"] == "THREADS"
        assert env_def[1]["envValue"] == "$(runtime.cores)"

        # Verify hints
        network_hint = next(
            h for h in imported_hints if h.class_name == "NetworkAccess"
        )
        assert network_hint.data["networkAccess"] is True

        time_hint = next(h for h in imported_hints if h.class_name == "TimeLimit")
        assert time_hint.data["timelimit"] == 3600


class TestRoundTripFidelity:
    """Test round-trip fidelity preservation across different workflow engines."""

    @pytest.mark.xfail(reason="IR lacks values for target environment (distributed_computing) and no default is set; adaptation/loss reporting for missing environment-specific values needs implementation")
    def test_cwl_to_dagman_to_cwl_roundtrip(self, persistent_test_output):
        """Test CWL -> IR -> DAGMan -> IR -> CWL round-trip preservation."""
        # Create comprehensive CWL workflow
        original_workflow = self._create_comprehensive_cwl_workflow()

        # Step 1: CWL -> IR (import)
        cwl_file1 = persistent_test_output / "original.cwl"
        from_workflow(original_workflow, cwl_file1, preserve_metadata=True)
        imported_workflow = to_workflow(cwl_file1, preserve_metadata=True)

        # Step 2: IR -> DAGMan (export)
        dag_file = persistent_test_output / "intermediate.dag"
        dagman_from_workflow(
            imported_workflow, dag_file, scripts_dir=persistent_test_output / "scripts"
        )

        # Step 3: DAGMan -> IR (import)
        # Note: DAGMan import will lose some CWL-specific features, but should preserve core workflow
        dagman_workflow = dagman_to_workflow(dag_file)

        # Step 4: IR -> CWL (export)
        cwl_file2 = persistent_test_output / "roundtrip.cwl"
        from_workflow(dagman_workflow, cwl_file2, preserve_metadata=True)
        final_workflow = to_workflow(cwl_file2, preserve_metadata=True)

        # Verify core workflow structure is preserved
        assert final_workflow.name == original_workflow.name
        assert len(final_workflow.tasks) == len(original_workflow.tasks)
        assert len(final_workflow.edges) == len(original_workflow.edges)

        # Verify task structure preservation
        for task_id in original_workflow.tasks:
            assert task_id in final_workflow.tasks
            original_task = original_workflow.tasks[task_id]
            final_task = final_workflow.tasks[task_id]

            # Core attributes should be preserved
            assert final_task.id == original_task.id
            assert final_task.command == original_task.command

            # Resource requirements should be preserved (converted through DAGMan)
            if original_task.cpu.get_value_with_default("shared_filesystem", 0) > 1:
                assert final_task.cpu.get_value_with_default("shared_filesystem", 0) >= 1
            if original_task.mem_mb.get_value_with_default("shared_filesystem", 0) > 0:
                assert final_task.mem_mb.get_value_with_default("shared_filesystem", 0) >= 0

    def _create_comprehensive_cwl_workflow(self) -> Workflow:
        """Create a workflow with comprehensive CWL features for testing."""
        provenance = ProvenanceSpec(
            authors=[{"name": "Test Author 2", "orcid": "orcid:0000-0000-0000-0002"}], version="1.5.0", license="GPL-3.0"
        )

        workflow = Workflow(
            name="comprehensive_test_workflow",
            version="1.5.0",
            provenance=provenance,
            cwl_version="v1.2",
        )

        # Task with comprehensive features
        task1 = Task(
            id="comprehensive_task",
            provenance=provenance,
        )
        # Set command using new IR
        task1.command.set_for_environment("analysis_tool --input {input} --output {output}", "shared_filesystem")
        # Set resources using new IR
        task1.cpu.set_for_environment(4, "shared_filesystem")
        task1.mem_mb.set_for_environment(8192, "shared_filesystem")
        task1.disk_mb.set_for_environment(10240, "shared_filesystem")
        # Set requirements and hints using new IR
        task1.requirements.set_for_environment([
            RequirementSpec("DockerRequirement", {"dockerPull": "biotools/analysis:latest"}),
            RequirementSpec("ResourceRequirement", {"coresMin": 4, "ramMin": 8192}),
        ], "shared_filesystem")
        task1.hints.set_for_environment([
            RequirementSpec("NetworkAccess", {"networkAccess": True})
        ], "shared_filesystem")
        task1.retry_count.set_for_environment(3, "shared_filesystem")
        task1.priority.set_for_environment(10, "shared_filesystem")

        task2 = Task(
            id="followup_task",
        )
        task2.when.set_for_environment("$(inputs.run_followup)", "shared_filesystem")
        # Set command using new IR
        task2.command.set_for_environment("process_results --input {input}", "shared_filesystem")
        # Set resources using new IR
        task2.cpu.set_for_environment(2, "shared_filesystem")
        task2.mem_mb.set_for_environment(4096, "shared_filesystem")

        workflow.add_task(task1)
        workflow.add_task(task2)
        workflow.add_edge("comprehensive_task", "followup_task")

        return workflow


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling for CWL/BCO features."""

    def test_empty_workflow_handling(self, persistent_test_output):
        """Test handling of empty workflows."""
        empty_workflow = Workflow(name="empty_test", version="1.0")

        cwl_file = persistent_test_output / "empty.cwl"
        from_workflow(empty_workflow, cwl_file)

        imported_workflow = to_workflow(cwl_file)
        assert imported_workflow.name == "empty_test"
        assert len(imported_workflow.tasks) == 0
        assert len(imported_workflow.edges) == 0

    def test_malformed_cwl_handling(self, persistent_test_output):
        """Test handling of malformed CWL files."""
        malformed_cwl = persistent_test_output / "malformed.cwl"
        with open(malformed_cwl, "w") as f:
            f.write("#!/usr/bin/env cwl-runner\n")
            f.write("invalid: yaml: content: [\n")

        with pytest.raises(Exception):
            to_workflow(malformed_cwl)

    def test_missing_required_fields(self, persistent_test_output):
        """Test handling of CWL files with missing required fields."""
        minimal_cwl = {
            "cwlVersion": "v1.2",
            "class": "Workflow",
            # Missing required fields like inputs, outputs, steps
        }

        cwl_file = persistent_test_output / "minimal.cwl"
        with open(cwl_file, "w") as f:
            f.write("#!/usr/bin/env cwl-runner\n\n")
            yaml.dump(minimal_cwl, f)

        # Should handle gracefully and create minimal workflow
        workflow = to_workflow(cwl_file)
        assert workflow.name is not None
        assert len(workflow.tasks) == 0

    def test_large_workflow_performance(self, persistent_test_output):
        """Test performance with large workflows."""
        # Create workflow with many tasks
        large_workflow = Workflow(name="large_test", version="1.0")

        for i in range(100):
            task = Task(
                id=f"task_{i:03d}",
            )
            # Set command using new IR
            task.command.set_for_environment(f"echo 'Task {i}'", "shared_filesystem")
            # Set resources using new IR
            task.cpu.set_for_environment(1, "shared_filesystem")
            task.mem_mb.set_for_environment(1024, "shared_filesystem")
            large_workflow.add_task(task)

            # Add some dependencies
            if i > 0:
                large_workflow.add_edge(f"task_{i-1:03d}", f"task_{i:03d}")

        # Test export performance
        cwl_file = persistent_test_output / "large.cwl"
        from_workflow(large_workflow, cwl_file)

        # Test import performance
        imported_workflow = to_workflow(cwl_file)

        assert len(imported_workflow.tasks) == 100
        assert len(imported_workflow.edges) == 99

    def test_unicode_and_special_characters(self, persistent_test_output):
        """Test handling of Unicode and special characters."""
        workflow = Workflow(name="unicode_test", version="1.0")

        task = Task(
            id="unicode_task",
            label="Unicode Test Task: αβγ",
            doc="Task with Unicode characters: αβγδε and emoji 🧬🔬",
        )
        # Set command using new IR
        task.command.set_for_environment("echo 'Testing: αβγ 中文 🧬'", "shared_filesystem")
        workflow.add_task(task)

        cwl_file = persistent_test_output / "unicode.cwl"
        from_workflow(workflow, cwl_file, preserve_metadata=True)

        imported_workflow = to_workflow(cwl_file, preserve_metadata=True)
        imported_task = imported_workflow.tasks["unicode_task"]

        assert "αβγ" in imported_task.label
        assert "🧬" in imported_task.doc
        assert "中文" in imported_task.command.get_value_for("shared_filesystem")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
