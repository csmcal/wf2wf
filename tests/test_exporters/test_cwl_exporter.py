"""Tests for CWL exporter functionality."""

import pytest
import yaml
import json
from pathlib import Path

from wf2wf.exporters.cwl import from_workflow
from wf2wf.core import Workflow, Task, Edge, ResourceSpec, EnvironmentSpec


class TestCWLExporter:
    """Test CWL workflow export functionality."""
    
    def test_export_simple_workflow(self, persistent_test_output):
        """Test exporting a simple workflow to CWL."""
        # Create simple workflow
        workflow = Workflow(name="Simple Test", version="1.0")
        
        task = Task(
            id="test_task",
            command="echo 'Hello World'",
            resources=ResourceSpec(cpu=2, mem_mb=4096),
            environment=EnvironmentSpec(container="docker://ubuntu:20.04")
        )
        workflow.add_task(task)
        
        # Export to CWL
        output_file = persistent_test_output / "simple_workflow.cwl"
        from_workflow(workflow, output_file, verbose=True)
        
        # Verify main workflow file
        assert output_file.exists()
        
        with open(output_file, 'r') as f:
            content = f.read()
            assert '#!/usr/bin/env cwl-runner' in content
        
        # Parse and verify structure
        with open(output_file, 'r') as f:
            # Skip shebang line
            f.readline()
            cwl_doc = yaml.safe_load(f)
        
        assert cwl_doc['cwlVersion'] == 'v1.2'
        assert cwl_doc['class'] == 'Workflow'
        assert cwl_doc['label'] == 'Simple Test'
        
        # Check steps
        assert 'test_task' in cwl_doc['steps']
        step = cwl_doc['steps']['test_task']
        assert step['run'] == 'tools/test_task.cwl'
        
        # Verify tool file was created
        tool_file = persistent_test_output / "tools" / "test_task.cwl"
        assert tool_file.exists()
        
        with open(tool_file, 'r') as f:
            # Skip shebang
            f.readline()
            tool_doc = yaml.safe_load(f)
        
        assert tool_doc['class'] == 'CommandLineTool'
        assert tool_doc['baseCommand'] == ['echo']
        assert tool_doc['arguments'] == ["'Hello", "World'"]
        
        # Check resource requirements
        reqs = tool_doc['requirements']
        resource_req = next(r for r in reqs if r['class'] == 'ResourceRequirement')
        assert resource_req['coresMin'] == 2
        assert resource_req['ramMin'] == 4096
        
        # Check Docker requirement
        docker_req = next(r for r in reqs if r['class'] == 'DockerRequirement')
        assert docker_req['dockerPull'] == 'ubuntu:20.04'
    
    def test_export_multi_step_workflow(self, persistent_test_output):
        """Test exporting a workflow with multiple steps and dependencies."""
        workflow = Workflow(name="Multi Step Test", version="1.0")
        workflow.config = {
            'threshold': 0.05,
            'max_iterations': 1000,
            'output_dir': 'results'
        }
        
        # Create tasks
        task1 = Task(
            id="prepare_data",
            command="python prepare.py",
            resources=ResourceSpec(cpu=2, mem_mb=4096)
        )
        
        task2 = Task(
            id="analyze_data", 
            command="python analyze.py",
            resources=ResourceSpec(cpu=4, mem_mb=8192),
            environment=EnvironmentSpec(container="docker://python:3.9")
        )
        
        task3 = Task(
            id="generate_report",
            command="python report.py",
            resources=ResourceSpec(cpu=1, mem_mb=2048)
        )
        
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
        with open(output_file, 'r') as f:
            f.readline()  # Skip shebang
            cwl_doc = yaml.safe_load(f)
        
        # Check workflow structure
        assert len(cwl_doc['steps']) == 3
        assert 'prepare_data' in cwl_doc['steps']
        assert 'analyze_data' in cwl_doc['steps']
        assert 'generate_report' in cwl_doc['steps']
        
        # Check inputs from config
        inputs = cwl_doc['inputs']
        assert 'threshold' in inputs
        assert inputs['threshold']['type'] == 'float'
        assert inputs['threshold']['default'] == 0.05
        
        # Check step dependencies
        analyze_step = cwl_doc['steps']['analyze_data']
        assert analyze_step['in']['input_file'] == 'prepare_data/output_file'
        
        report_step = cwl_doc['steps']['generate_report']
        assert report_step['in']['input_file'] == 'analyze_data/output_file'
        
        # Check that all tool files were created
        tools_dir = persistent_test_output / "tools"
        assert (tools_dir / "prepare_data.cwl").exists()
        assert (tools_dir / "analyze_data.cwl").exists()
        assert (tools_dir / "generate_report.cwl").exists()
    
    def test_export_single_file_mode(self, persistent_test_output):
        """Test exporting workflow as single file with inline tools."""
        workflow = Workflow(name="Single File Test", version="1.0")
        
        task = Task(
            id="inline_task",
            command="echo 'inline test'",
            resources=ResourceSpec(cpu=1, mem_mb=2048)
        )
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
        with open(output_file, 'r') as f:
            f.readline()  # Skip shebang
            cwl_doc = yaml.safe_load(f)
        
        # Check that tool is inline
        step = cwl_doc['steps']['inline_task']
        assert isinstance(step['run'], dict)
        assert step['run']['class'] == 'CommandLineTool'
    
    def test_export_with_conda_environment(self, persistent_test_output):
        """Test exporting workflow with conda environment."""
        workflow = Workflow(name="Conda Test", version="1.0")
        
        task = Task(
            id="conda_task",
            command="python script.py",
            environment=EnvironmentSpec(conda={
                "dependencies": ["numpy=1.21.0", "pandas", "scipy=1.7.0"]
            })
        )
        workflow.add_task(task)
        
        # Export to CWL
        output_file = persistent_test_output / "conda_workflow.cwl"
        from_workflow(workflow, output_file, verbose=True)
        
        # Check tool file for software requirements
        tool_file = persistent_test_output / "tools" / "conda_task.cwl"
        with open(tool_file, 'r') as f:
            f.readline()  # Skip shebang
            tool_doc = yaml.safe_load(f)
        
        # Find SoftwareRequirement
        reqs = tool_doc['requirements']
        software_req = next(r for r in reqs if r['class'] == 'SoftwareRequirement')
        
        packages = software_req['packages']
        package_names = [p['package'] for p in packages]
        assert 'numpy' in package_names
        assert 'pandas' in package_names
        assert 'scipy' in package_names
        
        # Check version specifications
        numpy_pkg = next(p for p in packages if p['package'] == 'numpy')
        assert numpy_pkg['version'] == ['1.21.0']
    
    def test_export_json_format(self, persistent_test_output):
        """Test exporting workflow in JSON format."""
        workflow = Workflow(name="JSON Test", version="1.0")
        
        task = Task(id="json_task", command="echo 'json test'")
        workflow.add_task(task)
        
        # Export as JSON
        output_file = persistent_test_output / "json_workflow.cwl"
        from_workflow(workflow, output_file, format='json', verbose=True)
        
        # Verify JSON files were created
        json_workflow = persistent_test_output / "json_workflow.json"
        json_tool = persistent_test_output / "tools" / "json_task.json"
        
        assert json_workflow.exists()
        assert json_tool.exists()
        
        # Verify JSON structure
        with open(json_workflow, 'r') as f:
            cwl_doc = json.load(f)
        
        assert cwl_doc['cwlVersion'] == 'v1.2'
        assert cwl_doc['class'] == 'Workflow'
    
    def test_export_comprehensive_resources(self, persistent_test_output):
        """Test exporting workflow with comprehensive resource specifications."""
        workflow = Workflow(name="Resource Test", version="1.0")
        
        task = Task(
            id="resource_task",
            command="heavy_computation",
            resources=ResourceSpec(
                cpu=8,
                mem_mb=32768,
                disk_mb=10240,
                gpu=2
            )
        )
        workflow.add_task(task)
        
        # Export to CWL
        output_file = persistent_test_output / "resource_workflow.cwl"
        from_workflow(workflow, output_file, verbose=True)
        
        # Check resource requirements in tool file
        tool_file = persistent_test_output / "tools" / "resource_task.cwl"
        with open(tool_file, 'r') as f:
            f.readline()  # Skip shebang
            tool_doc = yaml.safe_load(f)
        
        reqs = tool_doc['requirements']
        resource_req = next(r for r in reqs if r['class'] == 'ResourceRequirement')
        
        assert resource_req['coresMin'] == 8
        assert resource_req['ramMin'] == 32768
        assert resource_req['tmpdirMin'] == 10240
        # Note: GPU not directly supported in CWL ResourceRequirement
    
    def test_export_complex_workflow_from_json(self, persistent_test_output):
        """Test exporting a complex workflow loaded from JSON."""
        # Create a complex workflow structure
        workflow_data = {
            "name": "Complex Analysis Pipeline",
            "version": "2.0",
            "config": {
                "input_data": "data/samples.txt",
                "quality_threshold": 0.8,
                "analysis_mode": "comprehensive"
            },
            "tasks": {
                "quality_control": {
                    "id": "quality_control",
                    "command": "qc_tool --input {input} --threshold {threshold}",
                    "resources": {"cpu": 4, "mem_mb": 8192, "disk_mb": 5120},
                    "environment": {"container": "docker://biotools/qc:latest"}
                },
                "alignment": {
                    "id": "alignment", 
                    "command": "align_reads --input {input} --reference {ref}",
                    "resources": {"cpu": 8, "mem_mb": 16384, "disk_mb": 20480},
                    "environment": {"container": "docker://biotools/aligner:v2.1"}
                },
                "variant_calling": {
                    "id": "variant_calling",
                    "command": "call_variants --aligned {input} --output {output}",
                    "resources": {"cpu": 6, "mem_mb": 12288, "disk_mb": 10240},
                    "environment": {"container": "docker://biotools/variants:latest"}
                }
            },
            "edges": [
                {"parent": "quality_control", "child": "alignment"},
                {"parent": "alignment", "child": "variant_calling"}
            ]
        }
        
        # Create workflow from data
        workflow = Workflow.from_dict(workflow_data)
        
        # Export to CWL
        output_file = persistent_test_output / "complex_pipeline.cwl"
        from_workflow(workflow, output_file, verbose=True)
        
        # Verify structure
        with open(output_file, 'r') as f:
            f.readline()  # Skip shebang
            cwl_doc = yaml.safe_load(f)
        
        assert len(cwl_doc['steps']) == 3
        assert cwl_doc['label'] == "Complex Analysis Pipeline"
        
        # Check config mapping to inputs
        inputs = cwl_doc['inputs']
        assert 'quality_threshold' in inputs
        assert inputs['quality_threshold']['default'] == 0.8
        
        # Verify all tool files exist
        tools_dir = persistent_test_output / "tools"
        assert (tools_dir / "quality_control.cwl").exists()
        assert (tools_dir / "alignment.cwl").exists()
        assert (tools_dir / "variant_calling.cwl").exists()
        
        # Check Docker containers in tool files
        qc_tool_file = tools_dir / "quality_control.cwl"
        with open(qc_tool_file, 'r') as f:
            f.readline()  # Skip shebang
            qc_tool = yaml.safe_load(f)
        
        reqs = qc_tool['requirements']
        docker_req = next(r for r in reqs if r['class'] == 'DockerRequirement')
        assert docker_req['dockerPull'] == 'biotools/qc:latest'
    
    def test_workflow_outputs_generation(self, persistent_test_output):
        """Test generation of workflow outputs."""
        workflow = Workflow(name="Output Test", version="1.0")
        
        # Create linear workflow
        task1 = Task(id="step1", command="process_step1")
        task2 = Task(id="step2", command="process_step2") 
        task3 = Task(id="final_step", command="generate_final_output")
        
        workflow.add_task(task1)
        workflow.add_task(task2)
        workflow.add_task(task3)
        
        workflow.add_edge("step1", "step2")
        workflow.add_edge("step2", "final_step")
        
        # Export to CWL
        output_file = persistent_test_output / "output_test_workflow.cwl"
        from_workflow(workflow, output_file, verbose=True)
        
        # Check outputs
        with open(output_file, 'r') as f:
            f.readline()  # Skip shebang
            cwl_doc = yaml.safe_load(f)
        
        outputs = cwl_doc['outputs']
        # Should have output from final step (no children)
        assert 'final_step_output' in outputs
        assert outputs['final_step_output']['outputSource'] == 'final_step/output_file'
    
    def test_error_handling(self, persistent_test_output):
        """Test error handling in CWL export."""
        # Test with empty workflow
        empty_workflow = Workflow(name="Empty", version="1.0")
        
        output_file = persistent_test_output / "empty_workflow.cwl"
        
        # Should handle empty workflow gracefully
        from_workflow(empty_workflow, output_file)
        
        assert output_file.exists()
        
        with open(output_file, 'r') as f:
            f.readline()  # Skip shebang
            cwl_doc = yaml.safe_load(f)
        
        assert cwl_doc['class'] == 'Workflow'
        assert cwl_doc['steps'] == {}
    
    def test_command_parsing(self, persistent_test_output):
        """Test parsing of different command formats."""
        workflow = Workflow(name="Command Test", version="1.0")
        
        # Test various command formats
        commands = [
            "simple_command",
            "command with args",
            "python script.py --input file.txt --output result.txt",
            "# Comment command",
            ""
        ]
        
        for i, cmd in enumerate(commands):
            task = Task(id=f"task_{i}", command=cmd)
            workflow.add_task(task)
        
        # Export to CWL
        output_file = persistent_test_output / "command_test_workflow.cwl"
        from_workflow(workflow, output_file, verbose=True)
        
        # Check tool files
        tools_dir = persistent_test_output / "tools"
        
        # Check first tool (simple command)
        with open(tools_dir / "task_0.cwl", 'r') as f:
            f.readline()  # Skip shebang
            tool = yaml.safe_load(f)
        assert tool['baseCommand'] == ['simple_command']
        
        # Check second tool (command with args)
        with open(tools_dir / "task_1.cwl", 'r') as f:
            f.readline()  # Skip shebang
            tool = yaml.safe_load(f)
        assert tool['baseCommand'] == ['command']
        assert tool['arguments'] == ['with', 'args']
        
        # Check comment command
        with open(tools_dir / "task_3.cwl", 'r') as f:
            f.readline()  # Skip shebang
            tool = yaml.safe_load(f)
        assert tool['baseCommand'] == ['echo', 'No command specified']  # Fallback for comments
        
        # Check empty command
        with open(tools_dir / "task_4.cwl", 'r') as f:
            f.readline()  # Skip shebang
            tool = yaml.safe_load(f)
        assert tool['baseCommand'] == ['echo', 'No command specified']  # Fallback for empty 