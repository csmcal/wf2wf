#!/usr/bin/env python3
"""
Simple test to isolate path handling issues.
"""

import tempfile
from pathlib import Path

from wf2wf.core import Workflow, Task, ParameterSpec, EnvironmentSpecificValue, Edge
from wf2wf.exporters import CWLExporter

def create_simple_workflow() -> Workflow:
    """Create a simple test workflow."""
    task = Task(
        id="test_task",
        inputs=[ParameterSpec(id="input", type="File")],
        outputs=[ParameterSpec(id="output", type="File")],
        command=EnvironmentSpecificValue({
            "shared_filesystem": "echo 'test'",
            "distributed_computing": "echo 'test'",
            "cloud_native": "echo 'test'"
        }),
        label="Test Task"
    )
    
    edges = []
    workflow = Workflow(
        name="simple_test",
        tasks={"test_task": task},
        inputs=[ParameterSpec(id="input", type="File")],
        outputs=[ParameterSpec(id="output", type="File")],
        edges=edges
    )
    
    return workflow

def main():
    """Test simple export."""
    workflow = create_simple_workflow()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        output_path = temp_path / "test.cwl"
        
        print(f"Output path type: {type(output_path)}")
        print(f"Output path: {output_path}")
        print(f"Output path parent: {output_path.parent}")
        
        exporter = CWLExporter(verbose=True)
        exporter.export_workflow(workflow, output_path, single_file=True)

if __name__ == "__main__":
    main() 