#!/usr/bin/env python3
"""Test script for the updated WDL exporter."""

import tempfile
from pathlib import Path

from wf2wf.core import Workflow, Task, ParameterSpec, EnvironmentSpecificValue, Edge

def test_wdl_exporter():
    """Test WDL exporter with a comprehensive workflow."""
    
    # Create a workflow with multiple tasks and dependencies
    workflow = Workflow(
        name="test_workflow",
        label="Test WDL Workflow",
        doc="A comprehensive test workflow for WDL export",
        version="1.0.0"
    )
    
    # Add workflow inputs
    input1 = ParameterSpec(id="input_file", type="File", label="Input File")
    input2 = ParameterSpec(id="sample_count", type="int", label="Sample Count", default=10)
    workflow.inputs.extend([input1, input2])
    
    # Create first task
    task1 = Task(id="preprocess_data", label="Preprocess Data", doc="Preprocess input data")
    task1.command.set_for_environment("python preprocess.py $input_file", "shared_filesystem")
    task1.command.set_for_environment("python preprocess.py $input_file", "cloud_native")
    task1.cpu.set_for_environment(2, "shared_filesystem")
    task1.cpu.set_for_environment(4, "cloud_native")
    task1.mem_mb.set_for_environment(1024, "shared_filesystem")
    task1.mem_mb.set_for_environment(2048, "cloud_native")
    task1.container.set_for_environment("python:3.9", "shared_filesystem")
    task1.container.set_for_environment("python:3.9", "cloud_native")
    task1.inputs.append(ParameterSpec(id="input_file", type="File"))
    task1.outputs.append(ParameterSpec(id="processed_data", type="File"))
    workflow.tasks[task1.id] = task1
    
    # Create second task
    task2 = Task(id="analyze_data", label="Analyze Data", doc="Analyze processed data")
    task2.command.set_for_environment("python analyze.py $processed_data $sample_count", "shared_filesystem")
    task2.command.set_for_environment("python analyze.py $processed_data $sample_count", "cloud_native")
    task2.cpu.set_for_environment(4, "shared_filesystem")
    task2.cpu.set_for_environment(8, "cloud_native")
    task2.mem_mb.set_for_environment(2048, "shared_filesystem")
    task2.mem_mb.set_for_environment(4096, "cloud_native")
    task2.container.set_for_environment("python:3.9", "shared_filesystem")
    task2.container.set_for_environment("python:3.9", "cloud_native")
    task2.inputs.extend([
        ParameterSpec(id="processed_data", type="File"),
        ParameterSpec(id="sample_count", type="int")
    ])
    task2.outputs.append(ParameterSpec(id="analysis_results", type="File"))
    workflow.tasks[task2.id] = task2
    
    # Create third task with conditional execution
    task3 = Task(id="generate_report", label="Generate Report", doc="Generate final report")
    task3.command.set_for_environment("python report.py $analysis_results", "shared_filesystem")
    task3.command.set_for_environment("python report.py $analysis_results", "cloud_native")
    task3.cpu.set_for_environment(1, "shared_filesystem")
    task3.cpu.set_for_environment(2, "cloud_native")
    task3.mem_mb.set_for_environment(512, "shared_filesystem")
    task3.mem_mb.set_for_environment(1024, "cloud_native")
    task3.when.set_for_environment("sample_count > 5", "shared_filesystem")
    task3.when.set_for_environment("sample_count > 5", "cloud_native")
    task3.inputs.append(ParameterSpec(id="analysis_results", type="File"))
    task3.outputs.append(ParameterSpec(id="final_report", type="File"))
    workflow.tasks[task3.id] = task3
    
    # Add dependencies
    workflow.add_edge("preprocess_data", "analyze_data")
    workflow.add_edge("analyze_data", "generate_report")
    
    # Add workflow outputs
    workflow.outputs.append(ParameterSpec(id="final_report", type="File"))
    
    # Test the exporter
    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / "test_workflow.wdl"
        
        from wf2wf.exporters.wdl import WDLExporter
        exporter = WDLExporter(verbose=True)
        exporter.export_workflow(workflow, output_path)
        
        print(f"✓ WDL workflow exported to {output_path}")
        
        # Check that the file was created
        assert output_path.exists(), "Output file was not created"
        
        # Check that task files were created
        tasks_dir = output_path.parent / "tasks"
        assert tasks_dir.exists(), "Tasks directory was not created"
        
        task_files = list(tasks_dir.glob("*.wdl"))
        assert len(task_files) == 3, f"Expected 3 task files, found {len(task_files)}"
        
        print("✓ All task files created successfully")
        
        # Read and display the main workflow
        with open(output_path) as f:
            main_content = f.read()
        
        print(f"✓ Main workflow length: {len(main_content)} characters")
        print("✓ Main workflow contains version:", "version 1.0" in main_content)
        print("✓ Main workflow contains workflow definition:", "workflow test_workflow" in main_content)
        print("✓ Main workflow contains imports:", "import \"tasks/*.wdl\"" in main_content)
        print("✓ Main workflow contains conditional execution:", "if (" in main_content)
        
        # Read and display a task file
        task_file = tasks_dir / "preprocess_data.wdl"
        with open(task_file) as f:
            task_content = f.read()
        
        print(f"✓ Task file length: {len(task_content)} characters")
        print("✓ Task file contains task definition:", "task preprocess_data" in task_content)
        print("✓ Task file contains command:", "command {" in task_content)
        print("✓ Task file contains runtime:", "runtime {" in task_content)
        print("✓ Task file contains meta:", "meta {" in task_content)

if __name__ == "__main__":
    test_wdl_exporter()
    print("✓ WDL exporter test completed successfully!") 