"""
Consolidated tests for CWL exporter functionality.

This module consolidates all CWL export tests including:
- Basic CWL export functionality
- Multi-step workflows and dependencies
- Single file and multi-file export modes
- Advanced features (scatter, when, conditional requirements)
- Graph options and structured export
- Provenance handling
- Complex type serialization
- Loss reporting
- SIF hints and environment specifications
- Resource and environment parsing
- Error handling and validation
"""

import yaml
import json
import pytest
import tempfile
from pathlib import Path
from typing import Dict, Any

from wf2wf.core import (
    Workflow, Task, ParameterSpec, EnvironmentSpecificValue, Edge,
    ScatterSpec
)
from wf2wf.exporters import cwl as cwl_exporter
from wf2wf.exporters.cwl import from_workflow
from wf2wf.importers import cwl as cwl_importer


def _read_yaml_skip_shebang(p: Path):
    """Read YAML file, skipping shebang if present."""
    with p.open() as f:
        first = f.readline()
        if first.startswith("#!"):
            return yaml.safe_load(f.read())
        f.seek(0)
        return yaml.safe_load(f.read())


def _extract_workflow_from_graph(cwl_doc):
    """Extract workflow document from $graph structure, or return the doc if already a workflow."""
    if "$graph" in cwl_doc:
        for item in cwl_doc["$graph"]:
            if item.get("class") == "Workflow":
                return item
        raise ValueError("No workflow found in $graph")
    elif cwl_doc.get("class") == "Workflow":
        return cwl_doc
    else:
        raise ValueError("No workflow found in document")

def _roundtrip_cwl(wf: Workflow, tmp_path: Path):
    """Roundtrip test helper that handles $graph structure."""
    out_path = tmp_path / "wf.cwl"
    cwl_exporter.from_workflow(wf, out_file=out_path, single_file=True)
    
    # Parse the output, handling $graph structure
    with open(out_path, "r") as f:
        f.readline()  # Skip shebang
        cwl_doc = yaml.safe_load(f)
    
    # Extract workflow from $graph if present
    workflow_doc = _extract_workflow_from_graph(cwl_doc)
    return workflow_doc


class TestCWLBasicExport:
    """Test basic CWL export functionality."""

    def test_export_simple_workflow(self, persistent_test_output):
        """Test exporting a simple workflow to CWL."""
        # Create simple workflow
        workflow = Workflow(name="Simple Test", version="1.0")

        task = Task(
            id="test_task",
        )
        task.command.set_for_environment("echo 'Hello World'", "shared_filesystem")
        task.cpu.set_for_environment(2, "shared_filesystem")
        task.mem_mb.set_for_environment(4096, "shared_filesystem")
        task.container.set_for_environment("docker://ubuntu:20.04", "shared_filesystem")
        workflow.add_task(task)

        # Export to CWL
        output_file = persistent_test_output / "simple_workflow.cwl"
        from_workflow(workflow, output_file, verbose=True)

        # Verify main workflow file
        assert output_file.exists()

        with open(output_file, "r") as f:
            content = f.read()
            assert "#!/usr/bin/env cwl-runner" in content

        # Parse and verify structure
        with open(output_file, "r") as f:
            # Skip shebang line
            f.readline()
            cwl_doc = yaml.safe_load(f)

        workflow_doc = _extract_workflow_from_graph(cwl_doc)
        assert workflow_doc["cwlVersion"] == "v1.2"
        assert workflow_doc["class"] == "Workflow"
        assert workflow_doc["label"] == "Simple Test"

        # Check steps
        assert "test_task" in workflow_doc["steps"]
        step = workflow_doc["steps"]["test_task"]
        assert step["run"] == "tools/test_task.cwl"

        # Verify tool file was created
        tool_file = persistent_test_output / "tools" / "test_task.cwl"
        assert tool_file.exists()

        with open(tool_file, "r") as f:
            # Skip shebang
            f.readline()
            tool_doc = yaml.safe_load(f)

        assert tool_doc["class"] == "CommandLineTool"
        assert tool_doc["baseCommand"] == ["echo"]
        assert tool_doc["arguments"] == ["Hello World"]

        # Check resource requirements
        reqs = tool_doc["requirements"]
        resource_req = next(r for r in reqs if r["class"] == "ResourceRequirement")
        assert resource_req["coresMin"] == 2
        assert resource_req["ramMin"] == 4096

        # Check Docker requirement
        docker_req = next(r for r in reqs if r["class"] == "DockerRequirement")
        assert docker_req["dockerPull"] == "ubuntu:20.04"

    def test_simple_cwl_export(self, tmp_path):
        """Test basic CWL export with simple workflow."""
        workflow = Workflow(name="simple_test")
        task = Task(
            id="test_task",
            inputs=[ParameterSpec(id="input", type="File")],
            outputs=[ParameterSpec(id="output", type="File")],
            label="Test Task"
        )
        task.command.set_for_environment("echo 'test'", "shared_filesystem")
        workflow.add_task(task)

        output_path = tmp_path / "workflow.cwl"
        cwl_exporter.from_workflow(workflow, output_path, format="yaml", single_file=True)

        assert output_path.exists()
        content = output_path.read_text()
        assert "cwlVersion" in content
        assert "inputs:" in content
        assert "outputs:" in content
        assert "steps:" in content

    def test_cwl_with_environment_specific_values(self, tmp_path):
        """Test CWL export with environment-specific values."""
        workflow = Workflow(name="env_test")
        task = Task(
            id="env_task",
        )
        # Set command for each environment separately
        task.command.set_for_environment("python script.py", "shared_filesystem")
        task.command.set_for_environment("python script.py --cluster", "distributed_computing")
        task.command.set_for_environment("python script.py --cloud", "cloud_native")
        
        # Set CPU for each environment separately
        task.cpu.set_for_environment(2, "shared_filesystem")
        task.cpu.set_for_environment(4, "distributed_computing")
        task.cpu.set_for_environment(8, "cloud_native")
        
        # Set memory for each environment separately
        task.mem_mb.set_for_environment(4096, "shared_filesystem")
        task.mem_mb.set_for_environment(8192, "distributed_computing")
        task.mem_mb.set_for_environment(16384, "cloud_native")
        
        workflow.add_task(task)

        output_path = tmp_path / "env_workflow.cwl"
        cwl_exporter.from_workflow(workflow, output_path, environment="shared_filesystem")

        assert output_path.exists()
        
        # Check the tool file for the command content
        tool_file = tmp_path / "tools" / "env_task.cwl"
        assert tool_file.exists()
        content = tool_file.read_text()
        # Check for the parsed command structure
        assert "baseCommand:" in content
        assert "arguments:" in content
        assert "python" in content
        assert "script.py" in content


class TestCWLMultiStepWorkflows:
    """Test CWL export with multi-step workflows and dependencies."""

    def test_export_multi_step_workflow(self, persistent_test_output):
        """Test exporting a workflow with multiple steps and dependencies."""
        workflow = Workflow(name="Multi Step Test", version="1.0")
        workflow.config = {
            "threshold": 0.05,
            "max_iterations": 1000,
            "output_dir": "results",
        }

        # Create tasks
        task1 = Task(
            id="prepare_data",
        )
        task1.command.set_for_environment("python prepare.py", "shared_filesystem")
        task1.cpu.set_for_environment(2, "shared_filesystem")
        task1.mem_mb.set_for_environment(4096, "shared_filesystem")

        task2 = Task(
            id="analyze_data",
        )
        task2.command.set_for_environment("python analyze.py", "shared_filesystem")
        task2.cpu.set_for_environment(4, "shared_filesystem")
        task2.mem_mb.set_for_environment(8192, "shared_filesystem")
        task2.container.set_for_environment("docker://python:3.9", "shared_filesystem")

        task3 = Task(
            id="generate_report",
        )
        task3.command.set_for_environment("python report.py", "shared_filesystem")
        task3.cpu.set_for_environment(1, "shared_filesystem")
        task3.mem_mb.set_for_environment(2048, "shared_filesystem")

        workflow.add_task(task1)
        workflow.add_task(task2)
        workflow.add_task(task3)

        # Add dependencies
        workflow.add_edge("prepare_data", "analyze_data")
        workflow.add_edge("analyze_data", "generate_report")

        # Export to CWL
        output_file = persistent_test_output / "multi_step_workflow.cwl"
        from_workflow(workflow, output_file, verbose=True)

        # Verify main workflow
        with open(output_file, "r") as f:
            f.readline()  # Skip shebang
            cwl_doc = yaml.safe_load(f)

        workflow_doc = _extract_workflow_from_graph(cwl_doc)

        # Check workflow structure
        assert len(workflow_doc["steps"]) == 3
        assert "prepare_data" in workflow_doc["steps"]
        assert "analyze_data" in workflow_doc["steps"]
        assert "generate_report" in workflow_doc["steps"]

        # Check inputs from config
        inputs = workflow_doc["inputs"]
        assert "threshold" in inputs
        assert inputs["threshold"]["type"] == "float"
        assert inputs["threshold"]["default"] == 0.05

        # Check step dependencies
        analyze_step = workflow_doc["steps"]["analyze_data"]
        assert analyze_step["in"]["input_file"] == "prepare_data/output_file"

        report_step = workflow_doc["steps"]["generate_report"]
        assert report_step["in"]["input_file"] == "analyze_data/output_file"

        # Check that all tool files were created
        tools_dir = persistent_test_output / "tools"
        assert (tools_dir / "prepare_data.cwl").exists()
        assert (tools_dir / "analyze_data.cwl").exists()
        assert (tools_dir / "generate_report.cwl").exists()

    def test_cwl_workflow_with_dependencies(self, tmp_path):
        """Test CWL export with task dependencies."""
        wf = Workflow(name="dependency_test")
        
        # Create tasks
        task1 = Task(id="prepare")
        task1.command.set_for_environment("echo prepare", "shared_filesystem")
        task2 = Task(id="process")
        task2.command.set_for_environment("echo process", "shared_filesystem")
        task3 = Task(id="finalize")
        task3.command.set_for_environment("echo finalize", "shared_filesystem")
        
        wf.add_task(task1)
        wf.add_task(task2)
        wf.add_task(task3)
        
        # Add dependencies
        wf.add_edge("prepare", "process")
        wf.add_edge("process", "finalize")

        out_file = tmp_path / "dependencies.cwl"
        cwl_exporter.from_workflow(wf, out_file, single_file=True)

        assert out_file.exists()
        doc = yaml.safe_load(out_file.read_text().split("\n", 2)[-1])
        
        workflow_doc = _extract_workflow_from_graph(doc)
        
        # Check steps exist
        steps = workflow_doc.get("steps", {})
        assert "prepare" in steps
        assert "process" in steps
        assert "finalize" in steps

    def test_cwl_workflow_inputs_outputs(self, tmp_path):
        """Test CWL workflow inputs and outputs."""
        wf = Workflow(name="io_test")
        
        # Add inputs
        wf.inputs = [
            ParameterSpec(id="input_file", type="File"),
            ParameterSpec(id="parameter", type="string")
        ]
        
        # Add outputs
        wf.outputs = [
            ParameterSpec(id="output_file", type="File"),
            ParameterSpec(id="log_file", type="File")
        ]
        
        # Add a task
        task = Task(id="process")
        task.command.set_for_environment("echo process", "shared_filesystem")
        wf.add_task(task)

        out_file = tmp_path / "io.cwl"
        cwl_exporter.from_workflow(wf, out_file, single_file=True)

        assert out_file.exists()
        doc = yaml.safe_load(out_file.read_text().split("\n", 2)[-1])
        
        workflow_doc = _extract_workflow_from_graph(doc)
        
        # Check inputs and outputs
        assert "inputs" in workflow_doc
        assert "outputs" in workflow_doc
        assert "input_file" in workflow_doc["inputs"]
        assert "output_file" in workflow_doc["outputs"]


class TestCWLExportModes:
    """Test different CWL export modes."""

    def test_export_single_file_mode(self, persistent_test_output):
        """Test exporting workflow as single file with inline tools."""
        workflow = Workflow(name="Single File Test", version="1.0")

        task = Task(
            id="inline_task",
        )
        task.command.set_for_environment("echo 'inline test'", "shared_filesystem")
        task.cpu.set_for_environment(1, "shared_filesystem")
        task.mem_mb.set_for_environment(2048, "shared_filesystem")
        workflow.add_task(task)

        # Export as single file
        output_file = persistent_test_output / "single_file_workflow.cwl"
        from_workflow(workflow, output_file, single_file=True, verbose=True)

        # Verify file exists
        assert output_file.exists()

        # Verify no tools directory was created
        tools_dir = persistent_test_output / "tools"
        assert not tools_dir.exists()

        # Parse and verify inline structure
        with open(output_file, "r") as f:
            f.readline()  # Skip shebang
            cwl_doc = yaml.safe_load(f)

        workflow_doc = _extract_workflow_from_graph(cwl_doc)

        # Check that tool is inline
        step = workflow_doc["steps"]["inline_task"]
        assert isinstance(step["run"], dict)
        assert step["run"]["class"] == "CommandLineTool"

    def test_cwl_multi_file_export(self, tmp_path):
        """Test CWL export with multiple files."""
        wf = Workflow(name="multifile_test")
        task = Task(id="test")
        task.command.set_for_environment("echo test", "shared_filesystem")
        wf.add_task(task)

        out_file = tmp_path / "multifile.cwl"
        cwl_exporter.from_workflow(wf, out_file, single_file=False)

        assert out_file.exists()
        # Should create additional files in tools directory
        tools_dir = out_file.parent / "tools"
        assert tools_dir.exists()


class TestCWLAdvancedFeatures:
    """Test CWL advanced features like scatter, when, and conditional requirements."""

    def test_export_when_and_scatter(self, tmp_path):
        """Test export with scatter and when conditions."""
        # Build IR with scatter + when
        wf = Workflow(name="adv_export")

        scatter_task = Task(
            id="scatter_step",
        )
        scatter_task.scatter.set_for_environment(
            ScatterSpec(scatter=["input_file"], scatter_method="nested_crossproduct"),
            "shared_filesystem"
        )
        scatter_task.command.set_for_environment("echo scatter", "shared_filesystem")
        scatter_task.cpu.set_for_environment(1, "shared_filesystem")

        when_task = Task(
            id="maybe_step",
        )
        when_task.when.set_for_environment("$context.run_optional == true", "shared_filesystem")
        when_task.command.set_for_environment("echo maybe", "shared_filesystem")
        when_task.cpu.set_for_environment(1, "shared_filesystem")

        wf.add_task(scatter_task)
        wf.add_task(when_task)
        wf.add_edge("scatter_step", "maybe_step")

        out_file = tmp_path / "adv_export.cwl"
        from_workflow(wf, out_file, verbose=True)

        cwl_doc = _read_yaml_skip_shebang(out_file)

        # Confirm requirements present
        req_classes = {r["class"] for r in cwl_doc["requirements"]}
        assert "ConditionalWhenRequirement" in req_classes
        assert "ScatterFeatureRequirement" in req_classes

        step_scatter = cwl_doc["steps"]["scatter_step"]
        # Accept both scalar and list for scatter
        scatter_val = step_scatter["scatter"]
        assert scatter_val == ["input_file"] or scatter_val == "input_file", f"Scatter should be list or scalar, got {scatter_val}"
        assert step_scatter["scatterMethod"] == "nested_crossproduct"

        step_when = cwl_doc["steps"]["maybe_step"]
        assert step_when["when"] == "$context.run_optional == true"

    def test_valuefrom_and_scatter(self, tmp_path):
        """Test valueFrom expressions with scatter."""
        wf = Workflow(name="valuefrom_scatter")
        task = Task(id="step1")
        ps_in = ParameterSpec(id="x", type="int", value_from="$(inputs.y * 2)")
        ps_y = ParameterSpec(id="y", type="int")
        task.inputs = [ps_in, ps_y]
        ps_out = ParameterSpec(id="out", type="int")
        task.outputs = [ps_out]
        task.scatter = ScatterSpec(scatter=["y"], scatter_method="dotproduct")
        wf.tasks = {task.id: task}
        wf.edges = []

        out_doc = _roundtrip_cwl(wf, tmp_path)

        step_def = out_doc["steps"]["step1"]
        assert step_def["scatter"] == "y", "Scatter should be scalar in shorthand form"
        assert "valueFrom" in step_def["in"]["x"], "valueFrom not emitted"


class TestCWLGraphOptions:
    """Test CWL graph options and structured export."""

    def test_cwl_graph_options(self, tmp_path):
        """Test CWL graph export options."""
        data_dir = Path(__file__).parent.parent / "data"
        src = data_dir / "graph_workflow.cwl"
        if not src.exists():
            pytest.skip("Test data file not found")
        wf = cwl_importer.to_workflow(src)
        out_path = tmp_path / "graph_opts.cwl"
        cwl_exporter.from_workflow(
            wf,
            out_file=out_path,
            graph=True,
            root_id="my_root",
            structure_prov=True,
        )
        doc = yaml.safe_load(out_path.read_text().split("\n", 2)[-1])
        workflow_doc = _extract_workflow_from_graph(doc)
        assert workflow_doc["$graph"][0]["id"] == "my_root"
        # provenance block optional

    def test_structured_provenance_export(self, tmp_path):
        """Test structured provenance export."""
        # Build workflow with namespaced extras
        wf = Workflow(name="prov_test")
        wf.metadata = {
            "prov:wasGeneratedBy": "wf2wf-unit", 
            "schema:author": "Alice"
        }
        out_path = tmp_path / "prov.cwl"

        cwl_exporter.from_workflow(
            wf, out_file=out_path, single_file=True, structure_prov=True
        )

        doc = yaml.safe_load(out_path.read_text().split("\n", 2)[-1])
        workflow_doc = _extract_workflow_from_graph(doc)
        # Expect nested blocks
        assert "prov" in workflow_doc and isinstance(workflow_doc["prov"], dict)
        assert workflow_doc["prov"]["wasGeneratedBy"] == "wf2wf-unit"
        assert "schema" in workflow_doc and workflow_doc["schema"]["author"] == "Alice"


class TestCWLComplexTypes:
    """Test CWL complex type serialization."""

    def test_complex_type_serialisation(self, tmp_path):
        """Test complex type serialization with records and arrays."""
        # Record type with name - simplified for current IR
        wf = Workflow(name="complex_types")
        wf.inputs.append(
            ParameterSpec(id="reads", type="array")
        )

        out_doc = _roundtrip_cwl(wf, tmp_path)

        workflow_doc = _extract_workflow_from_graph(out_doc)
        assert "$schemas" in workflow_doc, "$schemas block missing"
        # Reference by name inside inputs
        in_types = next(iter(workflow_doc["inputs"].values()))["type"]
        # CWL arrays of unspecified type default to string items
        assert in_types == {"type": "array", "items": "string"} or in_types == [
            "null",
            {"type": "array", "items": "string"},
        ]

    def test_secondary_files_on_workflow_output(self, tmp_path):
        """Test secondary files specification on workflow outputs."""
        wf = Workflow(name="sec_files")
        out_param = ParameterSpec(
            id="report", type="File", secondary_files=[".idx", ".stat"]
        )
        wf.outputs.append(out_param)

        out_doc = _roundtrip_cwl(wf, tmp_path)
        workflow_doc = _extract_workflow_from_graph(out_doc)
        report_def = workflow_doc["outputs"]["report"]
        assert report_def["secondaryFiles"] == [
            ".idx",
            ".stat",
        ], "secondaryFiles not preserved"


class TestCWLLossReporting:
    """Test CWL loss reporting functionality."""

    def test_loss_report_generation(self, tmp_path):
        """Test that loss reports are generated for unsupported features."""
        task = Task(id="gpu_task")
        task.gpu.set_for_environment(1, "shared_filesystem")
        task.gpu_mem_mb.set_for_environment(1024, "shared_filesystem")
        task.command.set_for_environment("echo test", "shared_filesystem")  # Need a command
        wf = Workflow(name="lossy", tasks={task.id: task})

        out_file = tmp_path / "wf.cwl"
        cwl_exporter.from_workflow(wf, out_file=out_file, single_file=True, verbose=False)

        loss_path = out_file.with_suffix(".loss.json")
        assert loss_path.exists(), "Loss report not generated"
        doc = json.loads(loss_path.read_text())
        entries = doc["entries"]
        # Check for actual loss reason text from the loss report
        assert any("GPU fields" in e["reason"] for e in entries)

    def test_loss_report_with_unsupported_features(self, tmp_path):
        """Test loss reporting with various unsupported features."""
        wf = Workflow(name="lossy_features")
        
        # Task with unsupported features
        task = Task(
            id="unsupported_task",
            extra={
                "custom_attr": "unsupported_value",
                "condor_requirements": "(OpSysAndVer == 'CentOS7')"
            }
        )
        task.command.set_for_environment("echo test", "shared_filesystem")
        task.gpu.set_for_environment(2, "shared_filesystem")
        task.gpu_mem_mb.set_for_environment(8192, "shared_filesystem")
        task.disk_mb.set_for_environment(1024000, "shared_filesystem")  # Large disk requirement
        wf.add_task(task)

        out_file = tmp_path / "lossy_features.cwl"
        cwl_exporter.from_workflow(wf, out_file, single_file=True, verbose=False)

        loss_path = out_file.with_suffix(".loss.json")
        assert loss_path.exists()
        
        doc = json.loads(loss_path.read_text())
        entries = doc["entries"]
        
        # Check for various loss reasons
        loss_reasons = [e["reason"] for e in entries]
        assert any("GPU" in reason for reason in loss_reasons)
        assert any("disk" in reason.lower() for reason in loss_reasons)


class TestCWLSIFHints:
    """Test CWL SIF hints and environment specifications."""

    def test_cwl_sif_hint(self, tmp_path):
        """Test CWL export with SIF hints."""
        wf = Workflow(name="wf")
        t = Task(
            id="t1",
        )
        t.command.set_for_environment("echo hi", "shared_filesystem")
        t.container.set_for_environment("docker://busybox", "shared_filesystem")
        t.env_vars.set_for_environment({"WF2WF_SIF": "/cvmfs/imgs/abc.sif"}, "shared_filesystem")
        wf.add_task(t)
        out = tmp_path / "wf.cwl"
        from_workflow(wf, out, tools_dir="tools", format="yaml", verbose=False)
        txt = out.read_text()
        assert "wf2wf_sif" in txt

    def test_cwl_container_specifications(self, tmp_path):
        """Test CWL export with various container specifications."""
        wf = Workflow(name="container_test")
        
        # Task with Docker container
        docker_task = Task(
            id="docker_task",
        )
        docker_task.command.set_for_environment("python script.py", "shared_filesystem")
        docker_task.container.set_for_environment("docker://python:3.9-slim", "shared_filesystem")
        wf.add_task(docker_task)
        
        # Task with Singularity container
        singularity_task = Task(
            id="singularity_task",
        )
        singularity_task.command.set_for_environment("python script.py", "shared_filesystem")

        out_file = tmp_path / "containers.cwl"
        cwl_exporter.from_workflow(wf, out_file, single_file=True)

        assert out_file.exists()
        content = out_file.read_text()
        assert "dockerPull" in content or "dockerImageId" in content


class TestCWLRequirements:
    """Test CWL requirements and resource specifications."""

    def test_cwl_resource_requirements(self, tmp_path):
        """Test CWL export with resource requirements."""
        wf = Workflow(name="resource_test")
        
        task = Task(
            id="resource_task",
        )
        task.command.set_for_environment("python intensive_script.py", "shared_filesystem")
        task.cpu.set_for_environment(8, "shared_filesystem")
        task.mem_mb.set_for_environment(16384, "shared_filesystem")
        task.time_s.set_for_environment(7200, "shared_filesystem")  # 2 hours
        wf.add_task(task)

        out_file = tmp_path / "resources.cwl"
        cwl_exporter.from_workflow(wf, out_file, single_file=True)

        assert out_file.exists()
        doc = yaml.safe_load(out_file.read_text().split("\n", 2)[-1])
        
        # In single-file mode, tools are inlined in the $graph
        # Find the CommandLineTool in the graph
        tool_doc = None
        for item in doc["$graph"]:
            if item.get("class") == "CommandLineTool":
                tool_doc = item
                break
        
        assert tool_doc is not None, "No CommandLineTool found in graph"
        
        # Check for ResourceRequirement in the tool
        requirements = tool_doc.get("requirements", [])
        resource_req = next((r for r in requirements if r["class"] == "ResourceRequirement"), None)
        assert resource_req is not None, "ResourceRequirement not found in tool"
        assert resource_req["coresMin"] == 8
        assert resource_req["ramMin"] == 16384

    def test_cwl_docker_requirements(self, tmp_path):
        """Test CWL export with Docker requirements."""
        wf = Workflow(name="docker_test")
        
        task = Task(
            id="docker_task",
        )
        task.command.set_for_environment("python script.py", "shared_filesystem")
        task.container.set_for_environment("docker://python:3.9-slim", "shared_filesystem")
        wf.add_task(task)

        out_file = tmp_path / "docker.cwl"
        cwl_exporter.from_workflow(wf, out_file, single_file=True)

        assert out_file.exists()
        doc = yaml.safe_load(out_file.read_text().split("\n", 2)[-1])
        
        # In single-file mode, tools are inlined in the $graph
        # Find the CommandLineTool in the graph
        tool_doc = None
        for item in doc["$graph"]:
            if item.get("class") == "CommandLineTool":
                tool_doc = item
                break
        
        assert tool_doc is not None, "No CommandLineTool found in graph"
        
        # Check for DockerRequirement in the tool
        requirements = tool_doc.get("requirements", [])
        docker_req = next((r for r in requirements if r["class"] == "DockerRequirement"), None)
        assert docker_req is not None, "DockerRequirement not found in tool"
        assert docker_req["dockerPull"] == "python:3.9-slim"

    def test_export_comprehensive_resources(self, persistent_test_output):
        """Test exporting workflow with comprehensive resource specifications."""
        workflow = Workflow(name="Comprehensive Resources", version="1.0")

        task = Task(
            id="resource_task",
        )
        task.command.set_for_environment("python intensive_analysis.py", "shared_filesystem")
        task.cpu.set_for_environment(16, "shared_filesystem")
        task.mem_mb.set_for_environment(32768, "shared_filesystem")
        task.disk_mb.set_for_environment(102400, "shared_filesystem")
        task.time_s.set_for_environment(14400, "shared_filesystem")  # 4 hours
        task.container.set_for_environment("docker://python:3.9-slim", "shared_filesystem")
        workflow.add_task(task)

        # Export to CWL
        output_file = persistent_test_output / "comprehensive_resources.cwl"
        from_workflow(workflow, output_file, verbose=True)

        # Check tool file for comprehensive requirements
        tool_file = persistent_test_output / "tools" / "resource_task.cwl"
        with open(tool_file, "r") as f:
            f.readline()  # Skip shebang
            tool_doc = yaml.safe_load(f)

        # tool_doc is already the CommandLineTool dict
        # Check resource requirements
        reqs = tool_doc["requirements"]
        resource_req = next(r for r in reqs if r["class"] == "ResourceRequirement")
        assert resource_req["coresMin"] == 16
        assert resource_req["ramMin"] == 32768
        assert resource_req["tmpdirMin"] == 102400

        # Check Docker requirement
        docker_req = next(r for r in reqs if r["class"] == "DockerRequirement")
        assert docker_req["dockerPull"] == "python:3.9-slim"


class TestCWLFormatOptions:
    """Test CWL format options and export variations."""

    def test_cwl_yaml_format(self, tmp_path):
        """Test CWL export in YAML format."""
        wf = Workflow(name="yaml_test")
        task = Task(id="test")
        task.command.set_for_environment("echo test", "shared_filesystem")
        wf.add_task(task)

        out_file = tmp_path / "yaml.cwl"
        cwl_exporter.from_workflow(wf, out_file, format="yaml", single_file=True)

        assert out_file.exists()
        content = out_file.read_text()
        # Should be valid YAML
        yaml.safe_load(content)

    def test_cwl_json_format(self, tmp_path):
        """Test CWL export in JSON format."""
        wf = Workflow(name="json_test")
        task = Task(id="test")
        task.command.set_for_environment("echo test", "shared_filesystem")
        wf.add_task(task)

        out_file = tmp_path / "json.cwl"
        cwl_exporter.from_workflow(wf, out_file, format="json", single_file=True)

        assert out_file.exists()
        content = out_file.read_text()
        # Should be valid JSON
        json.loads(content)

    def test_export_json_format(self, persistent_test_output):
        """Test exporting workflow in JSON format."""
        workflow = Workflow(name="JSON Test", version="1.0")

        task = Task(
            id="json_task",
        )
        task.command.set_for_environment("echo 'json test'", "shared_filesystem")
        task.cpu.set_for_environment(1, "shared_filesystem")
        task.mem_mb.set_for_environment(1024, "shared_filesystem")
        workflow.add_task(task)

        # Export as JSON
        output_file = persistent_test_output / "json_workflow.cwl"
        from_workflow(workflow, output_file, format="json", verbose=True)

        # Verify file exists and is valid JSON
        assert output_file.exists()
        with open(output_file, "r") as f:
            content = f.read()
            json.loads(content)  # Should parse as valid JSON


class TestCWLEnvironmentHandling:
    """Test CWL environment and conda handling."""

    def test_export_with_conda_environment(self, persistent_test_output):
        """Test exporting workflow with conda environment."""
        workflow = Workflow(name="Conda Test", version="1.0")

        task = Task(
            id="conda_task",
        )
        task.command.set_for_environment("python script.py", "shared_filesystem")
        task.conda.set_for_environment({"dependencies": ["numpy=1.21.0", "pandas", "scipy=1.7.0"]}, "shared_filesystem")
        workflow.add_task(task)

        # Export to CWL
        output_file = persistent_test_output / "conda_workflow.cwl"
        from_workflow(workflow, output_file, verbose=True)

        # Check tool file for software requirements
        tool_file = persistent_test_output / "tools" / "conda_task.cwl"
        with open(tool_file, "r") as f:
            f.readline()  # Skip shebang
            tool_doc = yaml.safe_load(f)

        # tool_doc is already the CommandLineTool dict
        # Check for software requirements
        reqs = tool_doc["requirements"]
        software_req = next((r for r in reqs if r["class"] == "SoftwareRequirement"), None)
        assert software_req is not None
        assert "numpy" in [pkg["package"] for pkg in software_req["packages"]]

    def test_command_parsing(self, persistent_test_output):
        """Test command parsing and argument handling."""
        workflow = Workflow(name="Command Test", version="1.0")

        # Test various command formats
        task = Task(
            id="command_task",
        )
        task.command.set_for_environment("python script.py --input file.txt --output result.txt", "shared_filesystem")
        workflow.add_task(task)

        # Export to CWL
        output_file = persistent_test_output / "command_workflow.cwl"
        from_workflow(workflow, output_file, verbose=True)

        # Check tool file for proper command parsing
        tool_file = persistent_test_output / "tools" / "command_task.cwl"
        with open(tool_file, "r") as f:
            f.readline()  # Skip shebang
            tool_doc = yaml.safe_load(f)

        # tool_doc is already the CommandLineTool dict
        # Check baseCommand and arguments
        assert tool_doc["baseCommand"] == ["python", "script.py"]
        assert "--input" in tool_doc["arguments"]
        assert "--output" in tool_doc["arguments"]


class TestCWLWorkflowOutputs:
    """Test CWL workflow output generation."""

    def test_workflow_outputs_generation(self, persistent_test_output):
        """Test that workflow outputs are properly generated."""
        workflow = Workflow(name="Output Test", version="1.0")

        # Create task with output
        task = Task(
            id="output_task",
        )
        task.command.set_for_environment("python generate_output.py", "shared_filesystem")
        task.outputs = [ParameterSpec(id="output_file", type="File")]
        workflow.add_task(task)

        # Add workflow output
        workflow.outputs = [ParameterSpec(id="final_output", type="File", value_from="output_task/output_file")]

        # Export to CWL
        output_file = persistent_test_output / "output_workflow.cwl"
        from_workflow(workflow, output_file, verbose=True)

        # Check workflow outputs
        with open(output_file, "r") as f:
            f.readline()  # Skip shebang
            cwl_doc = yaml.safe_load(f)

        workflow_doc = _extract_workflow_from_graph(cwl_doc)
        assert "outputs" in workflow_doc
        assert "final_output" in workflow_doc["outputs"]
        output_def = workflow_doc["outputs"]["final_output"]
        assert output_def["type"] == "File"
        assert output_def["outputSource"] == "output_task/output_file"


def test_cwl_comprehensive_integration():
    """Comprehensive integration test for CWL exporter."""
    # Create a complex workflow with multiple features
    wf = Workflow(name="comprehensive_test")
    
    # Add inputs and outputs
    wf.inputs = [
        ParameterSpec(id="input_file", type="File"),
        ParameterSpec(id="config", type="string")
    ]
    wf.outputs = [
        ParameterSpec(id="result", type="File"),
        ParameterSpec(id="report", type="File", secondary_files=[".idx"])
    ]
    
    # Create tasks with various features
    task1 = Task(
        id="prepare",
    )
    task1.scatter.set_for_environment(
        ScatterSpec(scatter=["input_file"], scatter_method="dotproduct"),
        "shared_filesystem"
    )
    task1.command.set_for_environment("python prepare.py", "shared_filesystem")
    task1.cpu.set_for_environment(2, "shared_filesystem")
    task1.mem_mb.set_for_environment(4096, "shared_filesystem")
    
    task2 = Task(
        id="process",
    )
    task2.when.set_for_environment("$context.run_processing == true", "shared_filesystem")
    task2.command.set_for_environment("python process.py", "shared_filesystem")
    task2.cpu.set_for_environment(4, "shared_filesystem")
    task2.mem_mb.set_for_environment(8192, "shared_filesystem")
    
    task3 = Task(
        id="finalize",
    )
    task3.command.set_for_environment("python finalize.py", "shared_filesystem")
    task3.container.set_for_environment("docker://python:3.9-slim", "shared_filesystem")
    
    wf.add_task(task1)
    wf.add_task(task2)
    wf.add_task(task3)
    
    # Add dependencies
    wf.add_edge("prepare", "process")
    wf.add_edge("process", "finalize")
    
    # Test export
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        out_file = temp_path / "comprehensive.cwl"
        
        cwl_exporter.from_workflow(
            wf, 
            out_file, 
            single_file=True, 
            format="yaml",
            verbose=True
        )
        
        assert out_file.exists()
        
        # Check loss report
        loss_file = out_file.with_suffix(".loss.json")
        if loss_file.exists():
            loss_data = json.loads(loss_file.read_text())
            assert "entries" in loss_data


if __name__ == "__main__":
    pytest.main([__file__]) 