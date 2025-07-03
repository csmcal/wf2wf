"""Tests for CWL importer functionality."""

import pytest
import yaml
import json

from wf2wf.importers.cwl import to_workflow


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
        assert workflow.meta["source_format"] == "cwl"
        assert workflow.meta["cwl_version"] == "v1.2"
        assert workflow.meta["cwl_class"] == "Workflow"

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

        assert workflow.name == "Test Workflow"
        assert len(workflow.tasks) == 1
        assert "process" in workflow.tasks

        task = workflow.tasks["process"]
        assert "python process.py" in task.command

        # Check config from inputs
        assert "threshold" in workflow.config
        assert workflow.config["threshold"] == 0.01

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
        assert task.command == "echo Hello, World!"

        # Check resources
        assert task.resources.cpu == 2
        assert task.resources.mem_mb == 4096
        assert task.resources.disk_mb == 1024

        # Check environment
        assert task.environment is not None
        assert task.environment.container == "docker://ubuntu:20.04"

        # Check metadata
        assert workflow.meta["single_tool_conversion"]

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
        assert task.resources.cpu == 8
        assert task.resources.mem_mb == 16384
        # Disk should include both tmpdir and outdir
        assert task.resources.disk_mb == 2048 + 512

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
        assert task.environment.container == "docker://python:3.9-slim"

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
        assert task.environment.conda is not None
        deps = task.environment.conda["dependencies"]
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
        assert "external_tool" in task.command

    def test_error_handling(self, persistent_test_output):
        """Test error handling for invalid CWL files."""
        # Test missing file
        with pytest.raises(FileNotFoundError):
            to_workflow("nonexistent.cwl")

        # Test invalid CWL class
        invalid_content = {"cwlVersion": "v1.2", "class": "InvalidClass"}

        invalid_file = persistent_test_output / "invalid.cwl"
        with open(invalid_file, "w") as f:
            yaml.dump(invalid_content, f)

        with pytest.raises(RuntimeError, match="Unsupported CWL class"):
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
        assert "test" in list(workflow.tasks.values())[0].command
