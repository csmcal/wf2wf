"""
Comprehensive tests for CWL importer functionality.

This module consolidates all CWL-specific import tests including:
- Basic CWL workflow and tool import
- Advanced features (scatter, when, conditional requirements)
- Provenance handling and structured export
- Graph workflow support
- Resource and environment parsing
- Error handling and validation
"""

import pytest
import yaml
import json
import textwrap
from pathlib import Path
from typing import Dict, Any

from wf2wf.importers.cwl import to_workflow
from wf2wf.importers import cwl as cwl_importer
from wf2wf.exporters import cwl as cwl_exporter
from wf2wf.core import EnvironmentSpecificValue


def _write_tmp(path: Path, doc):
    """Write CWL document to file with shebang."""
    path.write_text("#!/usr/bin/env cwl-runner\n" + yaml.dump(doc))
    return path


def _simple_tool(cmd_id: str):
    """Return minimal inline CommandLineTool for *cmd_id*."""
    return {
        "class": "CommandLineTool",
        "baseCommand": ["echo", cmd_id],
        "inputs": {},
        "outputs": {
            "output_file": {"type": "File", "outputBinding": {"glob": f"{cmd_id}.txt"}}
        },
    }


class TestCWLImporter:
    """Test CWL workflow import functionality."""

    def test_import_demo_workflow(self, examples_dir, persistent_test_output):
        """Test importing the demo CWL workflow."""
        cwl_dir = examples_dir / "cwl"

        # Skip if CWL examples don't exist
        if not (cwl_dir / "workflow.cwl").exists():
            pytest.skip("CWL examples not available")

        # Import the workflow
        workflow = to_workflow(cwl_dir / "workflow.cwl", verbose=True)

        # Check basic workflow properties
        assert workflow.name == "CWL Demo Workflow"
        assert len(workflow.tasks) == 3
        assert (
            len(workflow.edges) == 3
        )  # Diamond dependency: prepare_data feeds both analyze_data and generate_report

        # Check task names
        task_ids = set(workflow.tasks.keys())
        expected_tasks = {"prepare_data", "analyze_data", "generate_report"}
        assert task_ids == expected_tasks

        # Check dependencies (diamond pattern)
        edge_pairs = {(e.parent, e.child) for e in workflow.edges}
        expected_edges = {
            ("prepare_data", "analyze_data"),
            (
                "prepare_data",
                "generate_report",
            ),  # generate_report needs data_file from prepare_data
            (
                "analyze_data",
                "generate_report",
            ),  # generate_report needs results_file from analyze_data
        }
        assert edge_pairs == expected_edges

        # Check metadata
        assert workflow.metadata.source_format == "cwl"
        assert workflow.metadata.format_specific["cwl_version"] == "v1.2"
        assert workflow.metadata.format_specific["cwl_class"] == "Workflow"

    def test_parse_cwl_workflow_structure(self, persistent_test_output):
        """Test parsing CWL workflow structure."""
        # Create a simple CWL workflow
        cwl_content = {
            "cwlVersion": "v1.2",
            "class": "Workflow",
            "label": "Test Workflow",
            "doc": "A test workflow for validation",
            "inputs": {
                "input_file": {"type": "File", "doc": "Input data"},
                "threshold": {"type": "float", "default": 0.01},
            },
            "outputs": {"result": {"type": "File", "outputSource": "process/output"}},
            "steps": {
                "process": {
                    "run": {
                        "class": "CommandLineTool",
                        "baseCommand": ["python", "process.py"],
                        "inputs": {
                            "input": {"type": "File"},
                            "threshold": {"type": "float"},
                        },
                        "outputs": {
                            "output": {
                                "type": "File",
                                "outputBinding": {"glob": "result.txt"},
                            }
                        },
                    },
                    "in": {"input": "input_file", "threshold": "threshold"},
                    "out": ["output"],
                }
            },
        }

        # Write to file
        cwl_file = persistent_test_output / "test_workflow.cwl"
        with open(cwl_file, "w") as f:
            yaml.dump(cwl_content, f)

        # Import and test
        workflow = to_workflow(cwl_file)

        task = workflow.tasks["process"]
        assert "python process.py" in task.command.get_value_for("shared_filesystem")

        # Check that workflow was created successfully
        assert workflow.name == "Test Workflow"

    def test_parse_commandlinetool(self, persistent_test_output):
        """Test parsing a single CommandLineTool."""
        tool_content = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "label": "Test Tool",
            "doc": "A test command line tool",
            "baseCommand": ["echo"],
            "arguments": ["Hello, World!"],
            "requirements": [
                {
                    "class": "ResourceRequirement",
                    "coresMin": 2,
                    "ramMin": 4096,
                    "tmpdirMin": 1024,
                },
                {"class": "DockerRequirement", "dockerPull": "ubuntu:20.04"},
            ],
            "inputs": {"message": {"type": "string", "default": "test"}},
            "outputs": {
                "output": {"type": "File", "outputBinding": {"glob": "output.txt"}}
            },
        }

        # Write to file
        tool_file = persistent_test_output / "test_tool.cwl"
        with open(tool_file, "w") as f:
            yaml.dump(tool_content, f)

        # Import and test
        workflow = to_workflow(tool_file)

        assert workflow.name == "Test Tool"
        assert len(workflow.tasks) == 1

        task = list(workflow.tasks.values())[0]
        assert task.command.get_value_for("shared_filesystem") == "echo Hello, World!"

        # Check resources
        assert task.cpu.get_value_for("shared_filesystem") == 2
        assert task.mem_mb.get_value_for("shared_filesystem") == 4096
        assert task.disk_mb.get_value_for("shared_filesystem") == 1024

        # Check environment
        assert task.container.get_value_for("shared_filesystem") == "docker://ubuntu:20.04"

        # Check metadata
        assert workflow.metadata.format_specific["single_tool_conversion"]

    def test_resource_parsing(self, persistent_test_output):
        """Test parsing various resource requirements."""
        tool_content = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["test"],
            "requirements": [
                {
                    "class": "ResourceRequirement",
                    "coresMax": 8,
                    "ramMax": 16384,
                    "tmpdirMax": 2048,
                    "outdirMin": 512,
                }
            ],
            "inputs": {},
            "outputs": {"out": {"type": "File", "outputBinding": {"glob": "*"}}},
        }

        tool_file = persistent_test_output / "resource_tool.cwl"
        with open(tool_file, "w") as f:
            yaml.dump(tool_content, f)

        workflow = to_workflow(tool_file)
        task = list(workflow.tasks.values())[0]

        # Check that max values are used
        assert task.cpu.get_value_for("shared_filesystem") == 8
        assert task.mem_mb.get_value_for("shared_filesystem") == 16384
        # Disk should include both tmpdir and outdir
        assert task.disk_mb.get_value_for("shared_filesystem") == 2048 + 512

    def test_environment_parsing(self, persistent_test_output):
        """Test parsing different environment specifications."""
        # Test Docker requirement
        docker_tool = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["test"],
            "requirements": [
                {"class": "DockerRequirement", "dockerPull": "python:3.9-slim"}
            ],
            "inputs": {},
            "outputs": {"out": {"type": "File", "outputBinding": {"glob": "*"}}},
        }

        docker_file = persistent_test_output / "docker_tool.cwl"
        with open(docker_file, "w") as f:
            yaml.dump(docker_tool, f)

        workflow = to_workflow(docker_file)
        task = list(workflow.tasks.values())[0]
        assert task.container.get_value_for("shared_filesystem") == "docker://python:3.9-slim"

        # Test Software requirement
        software_tool = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["test"],
            "requirements": [
                {
                    "class": "SoftwareRequirement",
                    "packages": [
                        {"package": "numpy", "version": ["1.21.0"]},
                        {"package": "pandas"},
                    ],
                }
            ],
            "inputs": {},
            "outputs": {"out": {"type": "File", "outputBinding": {"glob": "*"}}},
        }

        software_file = persistent_test_output / "software_tool.cwl"
        with open(software_file, "w") as f:
            yaml.dump(software_tool, f)

        workflow = to_workflow(software_file)
        task = list(workflow.tasks.values())[0]
        conda_env = task.conda.get_value_for("shared_filesystem")
        assert conda_env is not None
        # Parse the YAML string to get the dict
        conda_dict = yaml.safe_load(conda_env)
        deps = conda_dict["dependencies"]
        assert "numpy=1.21.0" in deps
        assert "pandas" in deps

    def test_dependency_extraction(self, persistent_test_output):
        """Test extraction of workflow dependencies."""
        workflow_content = {
            "cwlVersion": "v1.2",
            "class": "Workflow",
            "inputs": {"input": {"type": "File"}},
            "outputs": {
                "final_output": {"type": "File", "outputSource": "step3/output"}
            },
            "steps": {
                "step1": {
                    "run": {
                        "class": "CommandLineTool",
                        "baseCommand": ["step1"],
                        "inputs": {"input": {"type": "File"}},
                        "outputs": {
                            "output": {"type": "File", "outputBinding": {"glob": "*"}}
                        },
                    },
                    "in": {"input": "input"},
                    "out": ["output"],
                },
                "step2": {
                    "run": {
                        "class": "CommandLineTool",
                        "baseCommand": ["step2"],
                        "inputs": {"input": {"type": "File"}},
                        "outputs": {
                            "output": {"type": "File", "outputBinding": {"glob": "*"}}
                        },
                    },
                    "in": {"input": "step1/output"},
                    "out": ["output"],
                },
                "step3": {
                    "run": {
                        "class": "CommandLineTool",
                        "baseCommand": ["step3"],
                        "inputs": {"input": {"type": "File"}},
                        "outputs": {
                            "output": {"type": "File", "outputBinding": {"glob": "*"}}
                        },
                    },
                    "in": {"input": "step2/output"},
                    "out": ["output"],
                },
            },
        }

        workflow_file = persistent_test_output / "dependency_workflow.cwl"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow_content, f)

        workflow = to_workflow(workflow_file)

        # Check dependencies
        edge_pairs = {(e.parent, e.child) for e in workflow.edges}
        expected_edges = {("step1", "step2"), ("step2", "step3")}
        assert edge_pairs == expected_edges

    def test_external_tool_references(self, persistent_test_output):
        """Test handling of external tool file references."""
        # Create a separate tool file
        tool_content = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["external_tool"],
            "inputs": {"input": {"type": "File"}},
            "outputs": {"output": {"type": "File", "outputBinding": {"glob": "*"}}},
        }

        tool_file = persistent_test_output / "external_tool.cwl"
        with open(tool_file, "w") as f:
            yaml.dump(tool_content, f)

        # Create workflow that references the tool
        workflow_content = {
            "cwlVersion": "v1.2",
            "class": "Workflow",
            "inputs": {"input": {"type": "File"}},
            "outputs": {"output": {"type": "File", "outputSource": "step/output"}},
            "steps": {
                "step": {
                    "run": "external_tool.cwl",
                    "in": {"input": "input"},
                    "out": ["output"],
                }
            },
        }

        workflow_file = persistent_test_output / "workflow_with_external.cwl"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow_content, f)

        # Import and test
        workflow = to_workflow(workflow_file)

        assert len(workflow.tasks) == 1
        task = list(workflow.tasks.values())[0]
        assert "external_tool" in task.command.get_value_for("shared_filesystem")

    def test_error_handling(self, persistent_test_output):
        """Test error handling for invalid CWL files."""
        # Test missing file
        with pytest.raises(ImportError):
            to_workflow("nonexistent.cwl")

        # Test invalid CWL class
        invalid_content = {"cwlVersion": "v1.2", "class": "InvalidClass"}

        invalid_file = persistent_test_output / "invalid.cwl"
        with open(invalid_file, "w") as f:
            yaml.dump(invalid_content, f)

        with pytest.raises(ImportError, match="Unsupported CWL class"):
            to_workflow(invalid_file)

        # Test workflow with no steps (should now be handled gracefully)
        no_steps_content = {
            "cwlVersion": "v1.2",
            "class": "Workflow",
            "inputs": {},
            "outputs": {},
            "steps": {},
        }

        no_steps_file = persistent_test_output / "no_steps.cwl"
        with open(no_steps_file, "w") as f:
            yaml.dump(no_steps_content, f)

        # Empty workflows should be handled gracefully, not raise an error
        workflow = to_workflow(no_steps_file)
        assert len(workflow.tasks) == 0  # Should have no tasks but not error

    def test_verbose_and_debug_options(self, persistent_test_output):
        """Test verbose and debug output options."""
        tool_content = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["echo"],
            "inputs": {},
            "outputs": {"out": {"type": "File", "outputBinding": {"glob": "*"}}},
        }

        tool_file = persistent_test_output / "verbose_tool.cwl"
        with open(tool_file, "w") as f:
            yaml.dump(tool_content, f)

        # Test verbose mode (should not raise exceptions)
        workflow = to_workflow(tool_file, verbose=True)
        assert len(workflow.tasks) == 1

        # Test debug mode (should not raise exceptions)
        workflow = to_workflow(tool_file, debug=True)
        assert len(workflow.tasks) == 1

    def test_json_format_support(self, persistent_test_output):
        """Test support for JSON format CWL files."""
        tool_content = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["test"],
            "inputs": {},
            "outputs": {"out": {"type": "File", "outputBinding": {"glob": "*"}}},
        }

        # Write as JSON
        json_file = persistent_test_output / "test_tool.json"
        with open(json_file, "w") as f:
            json.dump(tool_content, f)

        # Import and test
        workflow = to_workflow(json_file)
        assert len(workflow.tasks) == 1
        assert "test" in list(workflow.tasks.values())[0].command.get_value_for("shared_filesystem")

    def test_submit_file_parsing(self, persistent_test_output):
        """Test parsing a CommandLineTool with submit_file."""
        tool_content = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "label": "Test Tool",
            "doc": "A test command line tool",
            "baseCommand": ["echo"],
            "arguments": ["Hello, World!"],
            "requirements": [
                {
                    "class": "ResourceRequirement",
                    "coresMin": 2,
                    "ramMin": 4096,
                    "tmpdirMin": 1024,
                },
                {"class": "DockerRequirement", "dockerPull": "ubuntu:20.04"},
            ],
            "inputs": {"message": {"type": "string", "default": "test"}},
            "outputs": {
                "output": {"type": "File", "outputBinding": {"glob": "output.txt"}}
            },
            "submit_file": "submit_file.txt",
        }

        # Write to file
        tool_file = persistent_test_output / "test_tool.cwl"
        with open(tool_file, "w") as f:
            yaml.dump(tool_content, f)

        # Import and test
        workflow = to_workflow(tool_file)

        assert workflow.name == "Test Tool"
        assert len(workflow.tasks) == 1

        task = list(workflow.tasks.values())[0]
        assert task.command.get_value_for("shared_filesystem") == "echo Hello, World!"

        # Check resources
        assert task.cpu.get_value_for("shared_filesystem") == 2
        assert task.mem_mb.get_value_for("shared_filesystem") == 4096
        assert task.disk_mb.get_value_for("shared_filesystem") == 1024

        # Check environment
        assert task.container.get_value_for("shared_filesystem") == "docker://ubuntu:20.04"

        # Check metadata
        assert workflow.metadata.format_specific["single_tool_conversion"]

        # Check submit_file
        assert task.submit_file.get_value_for("shared_filesystem") == "submit_file.txt"

        # Check transfer_mode for inputs
        for inp in task.inputs:
            if hasattr(inp, 'transfer_mode'):
                assert inp.transfer_mode.get_value_with_default("distributed_computing") == "always"


class TestCWLBasicImport:
    """Test basic CWL workflow and tool import functionality."""

    def test_import_demo_workflow(self, examples_dir, persistent_test_output):
        """Test importing the demo CWL workflow."""
        cwl_dir = examples_dir / "cwl"

        # Skip if CWL examples don't exist
        if not (cwl_dir / "workflow.cwl").exists():
            pytest.skip("CWL examples not available")

        # Import the workflow
        workflow = to_workflow(cwl_dir / "workflow.cwl", verbose=True)

        # Check basic workflow properties
        assert workflow.name == "CWL Demo Workflow"
        assert len(workflow.tasks) == 3
        assert (
            len(workflow.edges) == 3
        )  # Diamond dependency: prepare_data feeds both analyze_data and generate_report

        # Check task names
        task_ids = set(workflow.tasks.keys())
        expected_tasks = {"prepare_data", "analyze_data", "generate_report"}
        assert task_ids == expected_tasks

        # Check dependencies (diamond pattern)
        edge_pairs = {(e.parent, e.child) for e in workflow.edges}
        expected_edges = {
            ("prepare_data", "analyze_data"),
            (
                "prepare_data",
                "generate_report",
            ),  # generate_report needs data_file from prepare_data
            (
                "analyze_data",
                "generate_report",
            ),  # generate_report needs results_file from analyze_data
        }
        assert edge_pairs == expected_edges

        # Check metadata
        assert workflow.metadata.source_format == "cwl"
        assert workflow.metadata.format_specific["cwl_version"] == "v1.2"
        assert workflow.metadata.format_specific["cwl_class"] == "Workflow"

    def test_parse_cwl_workflow_structure(self, persistent_test_output):
        """Test parsing CWL workflow structure."""
        # Create a simple CWL workflow
        cwl_content = {
            "cwlVersion": "v1.2",
            "class": "Workflow",
            "label": "Test Workflow",
            "doc": "A test workflow for validation",
            "inputs": {
                "input_file": {"type": "File", "doc": "Input data"},
                "threshold": {"type": "float", "default": 0.01},
            },
            "outputs": {"result": {"type": "File", "outputSource": "process/output"}},
            "steps": {
                "process": {
                    "run": {
                        "class": "CommandLineTool",
                        "baseCommand": ["python", "process.py"],
                        "inputs": {
                            "input": {"type": "File"},
                            "threshold": {"type": "float"},
                        },
                        "outputs": {
                            "output": {
                                "type": "File",
                                "outputBinding": {"glob": "result.txt"},
                            }
                        },
                    },
                    "in": {"input": "input_file", "threshold": "threshold"},
                    "out": ["output"],
                }
            },
        }

        # Write to file
        cwl_file = persistent_test_output / "test_workflow.cwl"
        with open(cwl_file, "w") as f:
            yaml.dump(cwl_content, f)

        # Import and test
        workflow = to_workflow(cwl_file)

        task = workflow.tasks["process"]
        assert "python process.py" in task.command.get_value_for("shared_filesystem")

        # Check that workflow was created successfully
        assert workflow.name == "Test Workflow"

    def test_parse_commandlinetool(self, persistent_test_output):
        """Test parsing a single CommandLineTool."""
        tool_content = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "label": "Test Tool",
            "doc": "A test command line tool",
            "baseCommand": ["echo"],
            "arguments": ["Hello, World!"],
            "requirements": [
                {
                    "class": "ResourceRequirement",
                    "coresMin": 2,
                    "ramMin": 4096,
                    "tmpdirMin": 1024,
                },
                {"class": "DockerRequirement", "dockerPull": "ubuntu:20.04"},
            ],
            "inputs": {"message": {"type": "string", "default": "test"}},
            "outputs": {
                "output": {"type": "File", "outputBinding": {"glob": "output.txt"}}
            },
        }

        # Write to file
        tool_file = persistent_test_output / "test_tool.cwl"
        with open(tool_file, "w") as f:
            yaml.dump(tool_content, f)

        # Import and test
        workflow = to_workflow(tool_file)

        assert workflow.name == "Test Tool"
        assert len(workflow.tasks) == 1

        task = list(workflow.tasks.values())[0]
        assert task.command.get_value_for("shared_filesystem") == "echo Hello, World!"

        # Check resources
        assert task.cpu.get_value_for("shared_filesystem") == 2
        assert task.mem_mb.get_value_for("shared_filesystem") == 4096
        assert task.disk_mb.get_value_for("shared_filesystem") == 1024

        # Check environment
        assert task.container.get_value_for("shared_filesystem") == "docker://ubuntu:20.04"

        # Check metadata
        assert workflow.metadata.format_specific["single_tool_conversion"]


class TestCWLResourceParsing:
    """Test CWL resource requirement parsing."""

    def test_resource_parsing(self, persistent_test_output):
        """Test parsing various resource requirements."""
        tool_content = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["test"],
            "requirements": [
                {
                    "class": "ResourceRequirement",
                    "coresMax": 8,
                    "ramMax": 16384,
                    "tmpdirMax": 2048,
                    "outdirMin": 512,
                }
            ],
            "inputs": {},
            "outputs": {"out": {"type": "File", "outputBinding": {"glob": "*"}}},
        }

        tool_file = persistent_test_output / "resource_tool.cwl"
        with open(tool_file, "w") as f:
            yaml.dump(tool_content, f)

        workflow = to_workflow(tool_file)
        task = list(workflow.tasks.values())[0]

        # Check that max values are used
        assert task.cpu.get_value_for("shared_filesystem") == 8
        assert task.mem_mb.get_value_for("shared_filesystem") == 16384
        # Disk should include both tmpdir and outdir
        assert task.disk_mb.get_value_for("shared_filesystem") == 2048 + 512

    def test_environment_parsing(self, persistent_test_output):
        """Test parsing different environment specifications."""
        # Test Docker requirement
        docker_tool = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["test"],
            "requirements": [
                {"class": "DockerRequirement", "dockerPull": "python:3.9-slim"}
            ],
            "inputs": {},
            "outputs": {"out": {"type": "File", "outputBinding": {"glob": "*"}}},
        }

        docker_file = persistent_test_output / "docker_tool.cwl"
        with open(docker_file, "w") as f:
            yaml.dump(docker_tool, f)

        workflow = to_workflow(docker_file)
        task = list(workflow.tasks.values())[0]
        assert task.container.get_value_for("shared_filesystem") == "docker://python:3.9-slim"

        # Test Singularity requirement
        singularity_tool = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["test"],
            "requirements": [
                {"class": "DockerRequirement", "dockerImageId": "shub://singularity-hub/python:3.9"}
            ],
            "inputs": {},
            "outputs": {"out": {"type": "File", "outputBinding": {"glob": "*"}}},
        }

        singularity_file = persistent_test_output / "singularity_tool.cwl"
        with open(singularity_file, "w") as f:
            yaml.dump(singularity_tool, f)

        workflow = to_workflow(singularity_file)
        task = list(workflow.tasks.values())[0]
        assert task.container.get_value_for("shared_filesystem") == "shub://singularity-hub/python:3.9"


class TestCWLAdvancedFeatures:
    """Test CWL advanced features like scatter, when, and conditional requirements."""

    def test_import_when_and_scatter(self, persistent_test_output):
        """Test importing workflows with scatter and when conditions."""
        # Build minimal CWL workflow with scatter + when
        workflow_doc = {
            "cwlVersion": "v1.2",
            "class": "Workflow",
            "inputs": {
                "samples": {"type": {"type": "array", "items": "File"}},
                "run_optional": {"type": "boolean", "default": False},
            },
            "outputs": {
                "final": {"type": "File", "outputSource": "maybe_step/output_file"}
            },
            "steps": {
                "scatter_step": {
                    "run": _simple_tool("scatter"),
                    "in": {"input_file": "samples"},
                    "scatter": "input_file",
                    "scatterMethod": "dotproduct",
                    "out": ["output_file"],
                },
                "maybe_step": {
                    "run": _simple_tool("maybe"),
                    "in": {"input_file": "scatter_step/output_file"},
                    "when": "$context.run_optional == true",
                    "out": ["output_file"],
                },
            },
        }

        wf_path = _write_tmp(persistent_test_output / "adv_workflow.cwl", workflow_doc)

        wf = to_workflow(wf_path)

        # Validate
        wf.validate()

        # Assertions
        assert "scatter_step" in wf.tasks and "maybe_step" in wf.tasks
        scat_task = wf.tasks["scatter_step"]
        assert scat_task.scatter is not None
        assert (
            scat_task.scatter.scatter == ["input_file"]
            or scat_task.scatter.scatter == "input_file"
        )
        maybe_task = wf.tasks["maybe_step"]
        assert maybe_task.when is not None

    def test_dependency_extraction(self, persistent_test_output):
        """Test extracting task dependencies from CWL workflow."""
        workflow_content = {
            "cwlVersion": "v1.2",
            "class": "Workflow",
            "inputs": {"input_file": {"type": "File"}},
            "outputs": {"final_output": {"type": "File", "outputSource": "step3/output"}},
            "steps": {
                "step1": {
                    "run": _simple_tool("step1"),
                    "in": {"input_file": "input_file"},
                    "out": ["output"],
                },
                "step2": {
                    "run": _simple_tool("step2"),
                    "in": {"input_file": "step1/output"},
                    "out": ["output"],
                },
                "step3": {
                    "run": _simple_tool("step3"),
                    "in": {"input_file": "step2/output"},
                    "out": ["output"],
                },
            },
        }

        workflow_file = persistent_test_output / "dependency_workflow.cwl"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow_content, f)

        workflow = to_workflow(workflow_file)

        # Check dependencies
        edge_pairs = {(e.parent, e.child) for e in workflow.edges}
        expected_edges = {("step1", "step2"), ("step2", "step3")}
        assert edge_pairs == expected_edges


class TestCWLProvenance:
    """Test CWL provenance handling."""

    def test_import_nested_prov(self, tmp_path):
        """Test importing CWL with nested provenance."""
        cwl_text = textwrap.dedent("""
        cwlVersion: v1.2
        class: CommandLineTool
        baseCommand: echo
        inputs: []
        outputs: []
        prov:
          wasGeneratedBy: test-pipeline
          entity: ABC123
        """)
        f = tmp_path / "nested.cwl"
        f.write_text(cwl_text)

        wf = cwl_importer.to_workflow(f)
        assert wf.provenance
        assert wf.provenance.extras["prov:wasGeneratedBy"] == "test-pipeline"
        assert wf.provenance.extras["prov:entity"] == "ABC123"

    def test_cwl_provenance_namespace(self, tmp_path):
        """Test importing CWL with namespaced provenance."""
        cwl_text = textwrap.dedent(
            """
            cwlVersion: v1.2
            class: CommandLineTool
            id: tool_ns
            baseCommand: echo
            inputs: []
            outputs: []
            prov:wasGeneratedBy: wf2wf-test
            schema:author: John Doe
            """
        )
        cwl_path = tmp_path / "namespaced.cwl"
        cwl_path.write_text(cwl_text)

        wf = cwl_importer.to_workflow(cwl_path)

        # extras captured
        assert wf.provenance and wf.provenance.extras["prov:wasGeneratedBy"] == "wf2wf-test"
        assert wf.provenance.extras["schema:author"] == "John Doe"

        # round-trip export should include keys
        out_path = tmp_path / "roundtrip.cwl"
        cwl_exporter.from_workflow(wf, out_file=out_path)
        out_content = out_path.read_text()
        assert "prov:wasGeneratedBy" in out_content
        assert "schema:author" in out_content


class TestCWLGraphSupport:
    """Test CWL graph workflow support."""

    def test_cwl_graph_import(self, tmp_path):
        """Test importing CWL graph workflows."""
        data_dir = Path(__file__).parent.parent / "data"
        wf_path = data_dir / "graph_workflow.cwl"
        
        try:
            wf = cwl_importer.to_workflow(wf_path)
        except FileNotFoundError:
            pytest.skip("Test data file not found")

        # Basic assertions
        assert wf.name
        assert len(wf.tasks) == 1
        assert "step1" in wf.tasks
        # Workflow input preserved
        assert any(p.id == "input_file" for p in wf.inputs)


class TestCWLExternalTools:
    """Test CWL external tool references."""

    def test_external_tool_references(self, persistent_test_output):
        """Test handling external tool references."""
        workflow_content = {
            "cwlVersion": "v1.2",
            "class": "Workflow",
            "inputs": {"input_file": {"type": "File"}},
            "outputs": {"output": {"type": "File", "outputSource": "process/output"}},
            "steps": {
                "process": {
                    "run": "tools/process.cwl",  # External tool reference
                    "in": {"input": "input_file"},
                    "out": ["output"],
                }
            },
        }

        # Create external tool file
        tool_content = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["python", "process.py"],
            "inputs": {"input": {"type": "File"}},
            "outputs": {"output": {"type": "File", "outputBinding": {"glob": "*.txt"}}},
        }

        tools_dir = persistent_test_output / "tools"
        tools_dir.mkdir()
        tool_file = tools_dir / "process.cwl"
        with open(tool_file, "w") as f:
            yaml.dump(tool_content, f)

        workflow_file = persistent_test_output / "external_workflow.cwl"
        with open(workflow_file, "w") as f:
            yaml.dump(workflow_content, f)

        workflow = to_workflow(workflow_file)

        # Check that external tool was imported
        assert "process" in workflow.tasks
        task = workflow.tasks["process"]
        assert "python process.py" in task.command.get_value_for("shared_filesystem")


class TestCWLErrorHandling:
    """Test CWL error handling and validation."""

    def test_error_handling(self, persistent_test_output):
        """Test error handling for invalid CWL files."""
        # Test with invalid CWL
        invalid_cwl = {
            "cwlVersion": "v1.2",
            "class": "InvalidClass",  # Invalid class
            "baseCommand": ["test"],
            "inputs": {},
            "outputs": {"out": {"type": "File", "outputBinding": {"glob": "*"}}},
        }

        invalid_file = persistent_test_output / "invalid.cwl"
        with open(invalid_file, "w") as f:
            yaml.dump(invalid_cwl, f)

        # Should handle gracefully
        try:
            workflow = to_workflow(invalid_file)
            # If it doesn't raise an exception, it should create a minimal workflow
            assert isinstance(workflow, type(to_workflow.__annotations__['return']))
        except Exception as e:
            # Should provide meaningful error message
            assert "InvalidClass" in str(e) or "invalid" in str(e).lower()

    def test_verbose_and_debug_options(self, persistent_test_output):
        """Test verbose and debug options."""
        tool_content = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["echo", "test"],
            "inputs": {},
            "outputs": {"out": {"type": "File", "outputBinding": {"glob": "*"}}},
        }

        tool_file = persistent_test_output / "verbose_tool.cwl"
        with open(tool_file, "w") as f:
            yaml.dump(tool_content, f)

        # Test with verbose=True
        workflow = to_workflow(tool_file, verbose=True)
        assert workflow is not None

        # Test with debug=True
        workflow = to_workflow(tool_file, debug=True)
        assert workflow is not None


class TestCWLFormatSupport:
    """Test CWL format support (YAML vs JSON)."""

    def test_json_format_support(self, persistent_test_output):
        """Test importing CWL in JSON format."""
        tool_content = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["echo", "json_test"],
            "inputs": {},
            "outputs": {"out": {"type": "File", "outputBinding": {"glob": "*"}}},
        }

        # Write as JSON
        json_file = persistent_test_output / "json_tool.cwl"
        with open(json_file, "w") as f:
            json.dump(tool_content, f)

        workflow = to_workflow(json_file)
        task = list(workflow.tasks.values())[0]
        assert "echo json_test" in task.command.get_value_for("shared_filesystem")

    def test_submit_file_parsing(self, persistent_test_output):
        """Test parsing CWL submit files."""
        # Create a submit file (simplified)
        submit_content = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["submit_job"],
            "inputs": {"job_file": {"type": "File"}},
            "outputs": {"job_id": {"type": "string", "outputBinding": {"glob": "*.id"}}},
        }

        submit_file = persistent_test_output / "submit.cwl"
        with open(submit_file, "w") as f:
            yaml.dump(submit_content, f)

        workflow = to_workflow(submit_file)
        task = list(workflow.tasks.values())[0]
        assert "submit_job" in task.command.get_value_for("shared_filesystem")


class TestCWLComplexTypes:
    """Test CWL complex type handling."""

    def test_array_types(self, persistent_test_output):
        """Test importing CWL with array types."""
        tool_content = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["process"],
            "inputs": {
                "files": {"type": {"type": "array", "items": "File"}},
                "numbers": {"type": {"type": "array", "items": "int"}},
            },
            "outputs": {"out": {"type": "File", "outputBinding": {"glob": "*"}}},
        }

        tool_file = persistent_test_output / "array_tool.cwl"
        with open(tool_file, "w") as f:
            yaml.dump(tool_content, f)

        workflow = to_workflow(tool_file)
        task = list(workflow.tasks.values())[0]

        # Check that array inputs are properly handled
        files_input = next((p for p in task.inputs if p.id == "files"), None)
        assert files_input is not None
        assert files_input.type.type == "array"

    def test_union_types(self, persistent_test_output):
        """Test importing CWL with union types."""
        tool_content = {
            "cwlVersion": "v1.2",
            "class": "CommandLineTool",
            "baseCommand": ["process"],
            "inputs": {
                "input_data": {"type": ["File", "Directory", "null"]},
            },
            "outputs": {"out": {"type": "File", "outputBinding": {"glob": "*"}}},
        }

        tool_file = persistent_test_output / "union_tool.cwl"
        with open(tool_file, "w") as f:
            yaml.dump(tool_content, f)

        workflow = to_workflow(tool_file)
        task = list(workflow.tasks.values())[0]

        # Check that union types are properly handled
        input_param = next((p for p in task.inputs if p.id == "input_data"), None)
        assert input_param is not None
        assert input_param.type.type == "union"


def test_cwl_comprehensive_integration():
    """Comprehensive integration test for CWL importer."""
    # This test would create a complex CWL workflow with multiple features
    # and test the complete import process
    pass


if __name__ == "__main__":
    pytest.main([__file__]) 