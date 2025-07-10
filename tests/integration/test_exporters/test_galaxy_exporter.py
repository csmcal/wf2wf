#!/usr/bin/env python3
"""Simple test script for Galaxy exporter."""

import tempfile
from pathlib import Path

from wf2wf.core import Workflow, Task, ParameterSpec, EnvironmentSpecificValue
from wf2wf.exporters.galaxy import GalaxyExporter

def test_galaxy_exporter():
    """Test Galaxy exporter with a simple workflow."""
    
    # Create a simple workflow
    workflow = Workflow(
        name="test_workflow",
        label="Test Workflow",
        doc="A simple test workflow",
        version="1.0.0"
    )
    
    # Add an input parameter
    input_param = ParameterSpec(
        id="input_file",
        type="File",
        label="Input File",
        doc="Input file for processing"
    )
    workflow.inputs.append(input_param)
    
    # Create a task
    task = Task(
        id="process_data",
        label="Process Data",
        doc="Process the input data"
    )
    
    # Set environment-specific values
    task.command.set_for_environment("python process.py $input_file", "shared_filesystem")
    task.command.set_for_environment("python process.py $input_file", "cloud_native")
    
    task.script.set_for_environment("process.py", "shared_filesystem")
    task.script.set_for_environment("process.py", "cloud_native")
    
    task.cpu.set_for_environment(2, "shared_filesystem")
    task.cpu.set_for_environment(4, "cloud_native")
    
    task.mem_mb.set_for_environment(1024, "shared_filesystem")
    task.mem_mb.set_for_environment(2048, "cloud_native")
    
    task.container.set_for_environment("python:3.9", "shared_filesystem")
    task.container.set_for_environment("python:3.9", "cloud_native")
    
    # Add task inputs and outputs
    task.inputs.append(ParameterSpec(id="input_file", type="File"))
    task.outputs.append(ParameterSpec(id="output_file", type="File"))
    
    workflow.tasks[task.id] = task
    
    # Test the exporter
    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / "test_workflow.json"
        
        exporter = GalaxyExporter(verbose=True)
        exporter.export_workflow(workflow, output_path)
        
        print(f"✓ Galaxy workflow exported to {output_path}")
        
        # Check that the file was created
        assert output_path.exists(), "Output file was not created"
        
        # Check that tool configs were created
        tool_config_dir = output_path.parent / "tool_configs"
        assert tool_config_dir.exists(), "Tool config directory was not created"
        
        tool_config_file = tool_config_dir / "process_data.xml"
        assert tool_config_file.exists(), "Tool config file was not created"
        
        print("✓ All files created successfully")
        
        # Read and display the workflow
        import json
        with open(output_path) as f:
            galaxy_workflow = json.load(f)
        
        print(f"✓ Workflow name: {galaxy_workflow.get('name')}")
        print(f"✓ Steps: {len(galaxy_workflow.get('steps', {}))}")
        
        # Read and display tool config
        with open(tool_config_file) as f:
            tool_config = f.read()
        
        print(f"✓ Tool config length: {len(tool_config)} characters")
        print("✓ Tool config contains command:", "command" in tool_config)
        print("✓ Tool config contains requirements:", "requirements" in tool_config)

if __name__ == "__main__":
    test_galaxy_exporter()
    print("✓ Galaxy exporter test completed successfully!") 