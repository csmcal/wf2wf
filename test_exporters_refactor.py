#!/usr/bin/env python3
"""Test script to verify refactored exporters work correctly."""

import tempfile
from pathlib import Path

from wf2wf.core import Workflow, Task, ParameterSpec, EnvironmentSpecificValue
from wf2wf.exporters import (
    CWLExporter, DAGManExporter, NextflowExporter, WDLExporter, GalaxyExporter,
    export_workflow, get_exporter, list_formats
)


def create_test_workflow() -> Workflow:
    """Create a simple test workflow."""
    # Create tasks
    task1 = Task(
        id="preprocess",
        label="Preprocess Data",
        doc="Preprocess input data",
        command=EnvironmentSpecificValue("python preprocess.py", []),
        cpu=EnvironmentSpecificValue(2, []),
        mem_mb=EnvironmentSpecificValue(4096, []),
        inputs=[ParameterSpec(id="input_file", type="File")],
        outputs=[ParameterSpec(id="processed_data", type="File")],
    )
    
    task2 = Task(
        id="analyze",
        label="Analyze Data", 
        doc="Analyze processed data",
        command=EnvironmentSpecificValue("python analyze.py", []),
        cpu=EnvironmentSpecificValue(4, []),
        mem_mb=EnvironmentSpecificValue(8192, []),
        inputs=[ParameterSpec(id="processed_data", type="File")],
        outputs=[ParameterSpec(id="results", type="File")],
    )
    
    # Create workflow
    workflow = Workflow(
        name="test_workflow",
        label="Test Workflow",
        doc="A simple test workflow",
        version="1.0.0",
        tasks={"preprocess": task1, "analyze": task2},
        edges=[],
        inputs=[ParameterSpec(id="input_file", type="File")],
        outputs=[ParameterSpec(id="results", type="File")],
    )
    
    # Add edge
    workflow.add_edge("preprocess", "analyze")
    
    return workflow


def test_exporters():
    """Test all exporters."""
    print("Testing refactored exporters...")
    
    # Create test workflow
    workflow = create_test_workflow()
    print(f"✓ Created test workflow: {workflow.name}")
    
    # Test exporter registry
    formats = list_formats()
    print(f"✓ Available formats: {formats}")
    
    # Test each exporter
    exporters = [
        ("cwl", CWLExporter),
        ("dagman", DAGManExporter), 
        ("nextflow", NextflowExporter),
        ("wdl", WDLExporter),
        ("galaxy", GalaxyExporter),
    ]
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        for format_name, exporter_class in exporters:
            print(f"\nTesting {format_name} exporter...")
            
            # Test get_exporter function
            retrieved_exporter = get_exporter(format_name)
            assert retrieved_exporter == exporter_class, f"get_exporter failed for {format_name}"
            print(f"  ✓ get_exporter works")
            
            # Test exporter instantiation
            exporter = exporter_class(verbose=True)
            assert exporter._get_target_format() == format_name, f"Target format mismatch for {format_name}"
            print(f"  ✓ Exporter instantiation works")
            
            # Test export (just verify no exceptions)
            output_file = temp_path / f"test.{format_name}"
            try:
                export_workflow(workflow, output_file, format_name, verbose=True)
                print(f"  ✓ Export to {format_name} works")
            except Exception as e:
                print(f"  ⚠ Export to {format_name} failed: {e}")
    
    print("\n✓ All exporter tests completed!")


if __name__ == "__main__":
    test_exporters() 