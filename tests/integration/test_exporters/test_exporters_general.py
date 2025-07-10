"""
Comprehensive tests for all wf2wf exporters.

This module consolidates tests for:
- Basic exporter functionality and registry
- Individual exporter implementations (CWL, DAGMan, Snakemake, Nextflow, WDL, Galaxy, BCO)
- Advanced features and edge cases
- Export workflow integration
"""

import logging
import tempfile
import pytest
import yaml
import json
from pathlib import Path
from typing import Dict, Any

from wf2wf.core import (
    Workflow, Task, ParameterSpec, EnvironmentSpecificValue, Edge,
    ScatterSpec
)
from wf2wf.exporters import (
    CWLExporter, DAGManExporter, SnakemakeExporter, NextflowExporter,
    WDLExporter, GalaxyExporter, BCOExporter,
    export_workflow, get_exporter, list_formats
)
from wf2wf.exporters import cwl as cwl_exporter
from wf2wf.importers import cwl as cwl_importer

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class TestExporterRegistry:
    """Test exporter registry and basic functionality."""

    def test_list_formats(self):
        """Test that all expected formats are available."""
        formats = list_formats()
        expected_formats = ['cwl', 'dagman', 'snakemake', 'nextflow', 'wdl', 'galaxy', 'bco']
        
        for format_name in expected_formats:
            assert format_name in formats, f"Expected format {format_name} not found"

    def test_get_exporter(self):
        """Test getting exporters by format name."""
        # Test valid formats
        assert get_exporter('cwl') == CWLExporter
        assert get_exporter('dagman') == DAGManExporter
        assert get_exporter('snakemake') == SnakemakeExporter
        assert get_exporter('nextflow') == NextflowExporter
        assert get_exporter('wdl') == WDLExporter
        assert get_exporter('galaxy') == GalaxyExporter
        assert get_exporter('bco') == BCOExporter

    def test_get_exporter_invalid(self):
        """Test getting exporter with invalid format."""
        with pytest.raises(ValueError):
            get_exporter('invalid_format')

    def test_exporter_instantiation(self):
        """Test that all exporters can be instantiated."""
        exporters = [
            CWLExporter, DAGManExporter, SnakemakeExporter, NextflowExporter,
            WDLExporter, GalaxyExporter, BCOExporter
        ]
        
        for exporter_class in exporters:
            exporter = exporter_class(verbose=True)
            assert exporter is not None
            assert hasattr(exporter, 'export_workflow')


class TestWorkflowCreation:
    """Test workflow creation utilities."""

    def create_simple_workflow(self) -> Workflow:
        """Create a simple test workflow."""
        command = EnvironmentSpecificValue("echo 'test'")
        command.set_for_environment("echo 'test'", "distributed_computing")
        command.set_for_environment("echo 'test'", "cloud_native")
        
        task = Task(
            id="test_task",
            inputs=[ParameterSpec(id="input", type="File")],
            outputs=[ParameterSpec(id="output", type="File")],
            command=command,
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

    def create_complex_workflow(self) -> Workflow:
        """Create a complex test workflow with multiple tasks and environment-specific values."""
        
        # Create environment-specific values
        command_shared = EnvironmentSpecificValue("python process_data.py --input {input} --output {output}")
        command_shared.set_for_environment("python process_data.py --input {input} --output {output} --cluster", "distributed_computing")
        command_shared.set_for_environment("python process_data.py --input {input} --output {output} --cloud", "cloud_native")
        
        script_shared = EnvironmentSpecificValue("scripts/process_data.py")
        script_shared.set_for_environment("scripts/process_data.py", "distributed_computing")
        script_shared.set_for_environment("scripts/process_data.py", "cloud_native")
        
        container_shared = EnvironmentSpecificValue("python:3.9-slim")
        container_shared.set_for_environment("python:3.9-slim", "distributed_computing")
        container_shared.set_for_environment("python:3.9-slim", "cloud_native")
        
        cpu_shared = EnvironmentSpecificValue(2)
        cpu_shared.set_for_environment(4, "distributed_computing")
        cpu_shared.set_for_environment(8, "cloud_native")
        
        mem_shared = EnvironmentSpecificValue(4096)
        mem_shared.set_for_environment(8192, "distributed_computing")
        mem_shared.set_for_environment(16384, "cloud_native")
        
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

    def create_refactored_test_workflow(self) -> Workflow:
        """Create a test workflow for refactored exporter tests."""
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


class TestBasicExportFunctionality:
    """Test basic export functionality."""

    def test_simple_export(self):
        """Test simple export functionality."""
        workflow = TestWorkflowCreation().create_simple_workflow()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "test.cwl"
            
            exporter = CWLExporter(verbose=True)
            exporter.export_workflow(workflow, output_path, single_file=True)
            
            assert output_path.exists(), "Output file should be created"

    def test_export_workflow_function(self):
        """Test the export_workflow convenience function."""
        workflow = TestWorkflowCreation().create_simple_workflow()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "test.cwl"
            
            export_workflow(workflow, output_path, 'cwl', verbose=True)
            
            assert output_path.exists(), "Output file should be created"

    def test_all_exporters_basic(self):
        """Test all exporters with basic workflow."""
        workflow = TestWorkflowCreation().create_complex_workflow()
        
        # Define exporter tests
        exporter_tests = [
            ('cwl', 'workflow.cwl', {"format": "yaml", "single_file": True}),
            ('dagman', 'workflow.dag', {"inline_submit": True}),
            ('snakemake', 'Snakefile', {"create_all_rule": True}),
            ('nextflow', 'main.nf', {"use_dsl2": True, "add_channels": True}),
            ('wdl', 'workflow.wdl', {}),
            ('galaxy', 'workflow.ga', {}),
            ('bco', 'workflow.bco.json', {"validate": False}),
        ]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            for format_name, output_name, opts in exporter_tests:
                output_path = temp_path / output_name
                
                try:
                    export_workflow(workflow, output_path, format_name, verbose=True, **opts)
                    assert output_path.exists(), f"Output file for {format_name} should be created"
                except Exception as e:
                    pytest.fail(f"Export to {format_name} failed: {e}")


class TestIndividualExporters:
    """Test individual exporter implementations."""

    def test_cwl_exporter(self):
        """Test CWL exporter specifically."""
        workflow = TestWorkflowCreation().create_complex_workflow()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "workflow.cwl"
            
            exporter = CWLExporter(verbose=True)
            exporter.export_workflow(workflow, output_path, format="yaml", single_file=True)
            
            assert output_path.exists()
            
            # Check content
            content = output_path.read_text()
            assert "cwlVersion" in content
            assert "inputs:" in content
            assert "outputs:" in content
            assert "steps:" in content

    def test_dagman_exporter(self):
        """Test DAGMan exporter specifically."""
        workflow = TestWorkflowCreation().create_complex_workflow()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "workflow.dag"
            
            exporter = DAGManExporter(verbose=True)
            exporter.export_workflow(workflow, output_path, inline_submit=True)
            
            assert output_path.exists()
            
            # Check content
            content = output_path.read_text()
            assert "JOB" in content
            assert "PARENT" in content

    def test_snakemake_exporter(self):
        """Test Snakemake exporter specifically."""
        workflow = TestWorkflowCreation().create_complex_workflow()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "Snakefile"
            
            exporter = SnakemakeExporter(verbose=True)
            exporter.export_workflow(workflow, output_path, create_all_rule=True)
            
            assert output_path.exists()
            
            # Check content
            content = output_path.read_text()
            assert "rule" in content
            assert "input:" in content
            assert "output:" in content

    def test_nextflow_exporter(self):
        """Test Nextflow exporter specifically."""
        workflow = TestWorkflowCreation().create_complex_workflow()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "main.nf"
            
            exporter = NextflowExporter(verbose=True)
            exporter.export_workflow(workflow, output_path, use_dsl2=True, add_channels=True)
            
            assert output_path.exists()
            
            # Check content
            content = output_path.read_text()
            assert "process" in content
            assert "input:" in content
            assert "output:" in content

    def test_wdl_exporter(self):
        """Test WDL exporter specifically."""
        workflow = TestWorkflowCreation().create_complex_workflow()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "workflow.wdl"
            
            exporter = WDLExporter(verbose=True)
            exporter.export_workflow(workflow, output_path)
            
            assert output_path.exists()
            
            # Check content
            content = output_path.read_text()
            assert "version" in content
            assert "workflow" in content
            assert "task" in content

    def test_galaxy_exporter(self):
        """Test Galaxy exporter specifically."""
        workflow = TestWorkflowCreation().create_complex_workflow()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "workflow.ga"
            
            exporter = GalaxyExporter(verbose=True)
            exporter.export_workflow(workflow, output_path)
            
            assert output_path.exists()
            
            # Check content
            content = output_path.read_text()
            assert "a_galaxy_workflow" in content or "class" in content

    def test_bco_exporter(self):
        """Test BCO exporter specifically."""
        workflow = TestWorkflowCreation().create_complex_workflow()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "workflow.bco.json"
            
            exporter = BCOExporter(verbose=True)
            exporter.export_workflow(workflow, output_path, validate=False)
            
            assert output_path.exists()
            
            # Check content
            content = output_path.read_text()
            assert "bco_spec_version" in content or "provenance_domain" in content


class TestRefactoredExporters:
    """Test refactored exporter functionality."""

    def test_refactored_exporters(self):
        """Test all refactored exporters."""
        workflow = TestWorkflowCreation().create_refactored_test_workflow()
        
        # Test exporter registry
        formats = list_formats()
        assert len(formats) > 0, "Should have available formats"
        
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
                # Test get_exporter function
                retrieved_exporter = get_exporter(format_name)
                assert retrieved_exporter == exporter_class, f"get_exporter failed for {format_name}"
                
                # Test exporter instantiation
                exporter = exporter_class(verbose=True)
                assert exporter._get_target_format() == format_name, f"Target format mismatch for {format_name}"
                
                # Test export
                output_file = temp_path / f"test.{format_name}"
                export_workflow(workflow, output_file, format_name, verbose=True)
                assert output_file.exists(), f"Export to {format_name} should create file"


class TestAdvancedFeatures:
    """Test advanced exporter features."""

    def test_environment_specific_values(self):
        """Test that exporters handle environment-specific values correctly."""
        workflow = TestWorkflowCreation().create_complex_workflow()
        
        # Test with different environments
        environments = ["shared_filesystem", "distributed_computing", "cloud_native"]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            for env in environments:
                output_path = temp_path / f"workflow_{env}.cwl"
                
                exporter = CWLExporter(verbose=True)
                exporter.export_workflow(workflow, output_path, environment=env)
                
                assert output_path.exists(), f"Export for environment {env} should work"

    def test_error_handling(self):
        """Test exporter error handling."""
        # Test with invalid workflow
        with pytest.raises(Exception):
            export_workflow(None, Path("/tmp/test.cwl"), 'cwl')

    def test_output_path_handling(self):
        """Test various output path scenarios."""
        workflow = TestWorkflowCreation().create_simple_workflow()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Test with different path types
            paths = [
                temp_path / "test.cwl",
                str(temp_path / "test.cwl"),
                temp_path / "subdir" / "test.cwl"
            ]
            
            for output_path in paths:
                if isinstance(output_path, Path) and output_path.parent != temp_path:
                    output_path.parent.mkdir(exist_ok=True)
                
                export_workflow(workflow, output_path, 'cwl')
                assert Path(output_path).exists(), f"Export to {output_path} should work"


def test_exporter_integration():
    """Integration test for all exporters."""
    logger.info("Starting comprehensive exporter integration test...")
    
    # Create test workflow
    workflow_creator = TestWorkflowCreation()
    workflow = workflow_creator.create_complex_workflow()
    logger.info(f"Created test workflow with {len(workflow.tasks)} tasks")
    
    # Define exporter tests
    exporter_tests = [
        ('cwl', 'workflow.cwl', {"format": "yaml", "single_file": True}),
        ('dagman', 'workflow.dag', {"inline_submit": True}),
        ('snakemake', 'Snakefile', {"create_all_rule": True}),
        ('nextflow', 'main.nf', {"use_dsl2": True, "add_channels": True}),
        ('wdl', 'workflow.wdl', {}),
        ('galaxy', 'workflow.ga', {}),
        ('bco', 'workflow.bco.json', {"validate": False}),
    ]
    
    # Run tests
    results = {}
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        for format_name, output_name, opts in exporter_tests:
            output_path = temp_path / output_name
            
            try:
                logger.info(f"Testing {format_name} exporter...")
                export_workflow(workflow, output_path, format_name, verbose=True, **opts)
                
                if output_path.exists():
                    logger.info(f"✓ {format_name} - Output created: {output_path}")
                    results[format_name] = True
                else:
                    logger.error(f"✗ {format_name} - Output file not found: {output_path}")
                    results[format_name] = False
                    
            except Exception as e:
                logger.error(f"✗ {format_name} - Error: {e}")
                results[format_name] = False
    
    # Report results
    logger.info("\n" + "="*50)
    logger.info("EXPORTER INTEGRATION TEST RESULTS")
    logger.info("="*50)
    
    passed = sum(1 for success in results.values() if success)
    total = len(results)
    
    for format_name, success in results.items():
        status = "✓ PASS" if success else "✗ FAIL"
        logger.info(f"{format_name:20} {status}")
    
    logger.info("="*50)
    logger.info(f"Overall: {passed}/{total} exporters passed")
    
    assert passed == total, f"Expected all {total} exporters to pass, but only {passed} passed"
    logger.info("🎉 All exporters working correctly!")


if __name__ == "__main__":
    test_exporter_integration() 