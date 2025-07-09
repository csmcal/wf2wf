#!/usr/bin/env python3
"""
Test script to verify all exporters are working correctly with the updates.
"""

import logging
import tempfile
from pathlib import Path
from typing import Dict, Any

from wf2wf.core import (
    Workflow, Task, ParameterSpec, EnvironmentSpecificValue, Edge
)
from wf2wf.exporters import (
    CWLExporter, DAGManExporter, SnakemakeExporter, NextflowExporter,
    WDLExporter, GalaxyExporter, BCOExporter
)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def create_test_workflow() -> Workflow:
    """Create a test workflow with multiple tasks and environment-specific values."""
    
    # Create environment-specific values
    command_shared = EnvironmentSpecificValue({
        "shared_filesystem": "python process_data.py --input {input} --output {output}",
        "distributed_computing": "python process_data.py --input {input} --output {output} --cluster",
        "cloud_native": "python process_data.py --input {input} --output {output} --cloud"
    })
    
    script_shared = EnvironmentSpecificValue({
        "shared_filesystem": "scripts/process_data.py",
        "distributed_computing": "scripts/process_data.py",
        "cloud_native": "scripts/process_data.py"
    })
    
    container_shared = EnvironmentSpecificValue({
        "shared_filesystem": "python:3.9-slim",
        "distributed_computing": "python:3.9-slim",
        "cloud_native": "python:3.9-slim"
    })
    
    cpu_shared = EnvironmentSpecificValue({
        "shared_filesystem": 2,
        "distributed_computing": 4,
        "cloud_native": 8
    })
    
    mem_shared = EnvironmentSpecificValue({
        "shared_filesystem": 4096,
        "distributed_computing": 8192,
        "cloud_native": 16384
    })
    
    # Create tasks
    task1 = Task(
        id="prepare_data",
        inputs=[ParameterSpec(id="input_file", type="File")],
        outputs=[ParameterSpec(id="processed_data", type="File")],
        command=command_shared,
        script=script_shared,
        container=container_shared,
        cpu=cpu_shared,
        mem_mb=mem_shared,
        label="Prepare Data",
        doc="Prepare input data for processing"
    )
    
    task2 = Task(
        id="analyze_data",
        inputs=[ParameterSpec(id="processed_data", type="File")],
        outputs=[ParameterSpec(id="analysis_results", type="File")],
        command=command_shared,
        script=script_shared,
        container=container_shared,
        cpu=cpu_shared,
        mem_mb=mem_shared,
        label="Analyze Data",
        doc="Analyze the processed data"
    )
    
    task3 = Task(
        id="generate_report",
        inputs=[ParameterSpec(id="analysis_results", type="File")],
        outputs=[ParameterSpec(id="final_report", type="File")],
        command=command_shared,
        script=script_shared,
        container=container_shared,
        cpu=cpu_shared,
        mem_mb=mem_shared,
        label="Generate Report",
        doc="Generate final analysis report"
    )
    
    # Create edges as Edge objects
    edges = [
        Edge(parent="prepare_data", child="analyze_data"),
        Edge(parent="analyze_data", child="generate_report")
    ]
    # Create workflow
    workflow = Workflow(
        name="test_workflow",
        label="Test Workflow",
        doc="A test workflow for exporter validation",
        version="1.0.0",
        inputs=[ParameterSpec(id="input_file", type="File")],
        outputs=[ParameterSpec(id="final_report", type="File")],
        tasks={
            "prepare_data": task1,
            "analyze_data": task2,
            "generate_report": task3
        },
        edges=edges
    )
    
    return workflow


def test_exporter(exporter_class, workflow: Workflow, output_name: str, **opts: Any) -> bool:
    """Test a specific exporter."""
    try:
        logger.info(f"Testing {exporter_class.__name__}...")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / output_name
            
            # Create exporter and export workflow
            exporter = exporter_class(verbose=True)
            exporter.export_workflow(workflow, output_path, **opts)
            
            # Check if output file was created
            if output_path.exists():
                logger.info(f"✓ {exporter_class.__name__} - Output created: {output_path}")
                return True
            else:
                logger.error(f"✗ {exporter_class.__name__} - Output file not found: {output_path}")
                return False
                
    except Exception as e:
        logger.error(f"✗ {exporter_class.__name__} - Error: {e}")
        return False


def main():
    """Run tests for all exporters."""
    logger.info("Starting exporter tests...")
    
    # Create test workflow
    workflow = create_test_workflow()
    logger.info(f"Created test workflow with {len(workflow.tasks)} tasks")
    
    # Define exporter tests
    exporter_tests = [
        (CWLExporter, "workflow.cwl", {"format": "yaml", "single_file": True}),
        (DAGManExporter, "workflow.dag", {"inline_submit": True}),
        (SnakemakeExporter, "Snakefile", {"create_all_rule": True}),
        (NextflowExporter, "main.nf", {"use_dsl2": True, "add_channels": True}),
        (WDLExporter, "workflow.wdl", {}),
        (GalaxyExporter, "workflow.ga", {}),
        (BCOExporter, "workflow.bco.json", {"validate": False}),
    ]
    
    # Run tests
    results = {}
    for exporter_class, output_name, opts in exporter_tests:
        success = test_exporter(exporter_class, workflow, output_name, **opts)
        results[exporter_class.__name__] = success
    
    # Report results
    logger.info("\n" + "="*50)
    logger.info("EXPORTER TEST RESULTS")
    logger.info("="*50)
    
    passed = 0
    total = len(results)
    
    for exporter_name, success in results.items():
        status = "✓ PASS" if success else "✗ FAIL"
        logger.info(f"{exporter_name:20} {status}")
        if success:
            passed += 1
    
    logger.info("="*50)
    logger.info(f"Overall: {passed}/{total} exporters passed")
    
    if passed == total:
        logger.info("🎉 All exporters working correctly!")
        return 0
    else:
        logger.error("❌ Some exporters failed!")
        return 1


if __name__ == "__main__":
    exit(main()) 