#!/usr/bin/env python3
"""Test script for the updated DAGMan exporter."""

import tempfile
import shutil
from pathlib import Path
from wf2wf.core import Workflow, Task, Edge, EnvironmentSpecificValue
from wf2wf.exporters.dagman import DAGManExporter

def create_test_workflow():
    """Create a test workflow with environment-specific values."""
    workflow = Workflow(
        name="test_dagman_workflow"
    )
    
    # Create tasks with environment-specific values
    task1 = Task(
        id="prepare_data",
        command=EnvironmentSpecificValue("python prepare_data.py", ["shared_filesystem"]),
        script=EnvironmentSpecificValue("scripts/prepare_data.py", ["shared_filesystem"]),
        cpu=EnvironmentSpecificValue(2, ["shared_filesystem"]),
        mem_mb=EnvironmentSpecificValue(4096, ["shared_filesystem"]),
        disk_mb=EnvironmentSpecificValue(10240, ["shared_filesystem"]),
        retry_count=EnvironmentSpecificValue(1, ["shared_filesystem"]),
        priority=EnvironmentSpecificValue(1, ["shared_filesystem"]),
        container=EnvironmentSpecificValue(None, ["shared_filesystem"]),
        conda=EnvironmentSpecificValue("analysis_env", ["shared_filesystem"]),
        env_vars=EnvironmentSpecificValue({"DATA_DIR": "/data"}, ["shared_filesystem"]),
        extra={
            "requirements": EnvironmentSpecificValue("OpSys == \"LINUX\"", ["shared_filesystem"])
        }
    )
    
    task2 = Task(
        id="analyze_data",
        command=EnvironmentSpecificValue("Rscript analyze_data.R", ["shared_filesystem"]),
        script=EnvironmentSpecificValue("scripts/analyze_data.R", ["shared_filesystem"]),
        cpu=EnvironmentSpecificValue(4, ["shared_filesystem"]),
        mem_mb=EnvironmentSpecificValue(8192, ["shared_filesystem"]),
        disk_mb=EnvironmentSpecificValue(20480, ["shared_filesystem"]),
        retry_count=EnvironmentSpecificValue(2, ["shared_filesystem"]),
        priority=EnvironmentSpecificValue(2, ["shared_filesystem"]),
        container=EnvironmentSpecificValue(None, ["shared_filesystem"]),
        conda=EnvironmentSpecificValue("r_env", ["shared_filesystem"]),
        env_vars=EnvironmentSpecificValue({"R_LIBS": "/usr/local/lib/R/site-library"}, ["shared_filesystem"]),
        extra={
            "requirements": EnvironmentSpecificValue("OpSys == \"LINUX\"", ["shared_filesystem"])
        }
    )
    
    task3 = Task(
        id="generate_report",
        command=EnvironmentSpecificValue("python generate_report.py", ["shared_filesystem"]),
        script=EnvironmentSpecificValue("scripts/generate_report.py", ["shared_filesystem"]),
        cpu=EnvironmentSpecificValue(1, ["shared_filesystem"]),
        mem_mb=EnvironmentSpecificValue(2048, ["shared_filesystem"]),
        disk_mb=EnvironmentSpecificValue(5120, ["shared_filesystem"]),
        retry_count=EnvironmentSpecificValue(1, ["shared_filesystem"]),
        priority=EnvironmentSpecificValue(1, ["shared_filesystem"]),
        container=EnvironmentSpecificValue(None, ["shared_filesystem"]),
        conda=EnvironmentSpecificValue("report_env", ["shared_filesystem"]),
        env_vars=EnvironmentSpecificValue({"REPORT_DIR": "/reports"}, ["shared_filesystem"]),
        extra={
            "requirements": EnvironmentSpecificValue("OpSys == \"LINUX\"", ["shared_filesystem"])
        }
    )
    
    # Add tasks to workflow
    workflow.tasks["prepare_data"] = task1
    workflow.tasks["analyze_data"] = task2
    workflow.tasks["generate_report"] = task3
    
    # Add edges
    workflow.edges = [
        Edge(parent="prepare_data", child="analyze_data"),
        Edge(parent="analyze_data", child="generate_report")
    ]
    
    return workflow

def test_dagman_exporter():
    """Test the DAGMan exporter with shared infrastructure."""
    print("Testing DAGMan exporter with shared infrastructure...")
    
    # Create test workflow
    workflow = create_test_workflow()
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Test with different target environments
        for target_env in ["shared_filesystem", "distributed_computing", "cloud_native"]:
            print(f"\n--- Testing target environment: {target_env} ---")
            
            # Create exporter
            exporter = DAGManExporter(
                interactive=False,
                verbose=True,
                target_environment=target_env
            )
            
            # Export workflow
            dag_file = temp_path / f"test_workflow_{target_env}.dag"
            scripts_dir = temp_path / f"scripts_{target_env}"
            
            try:
                exporter.export_workflow(
                    workflow,
                    dag_file,
                    workdir=temp_path,
                    scripts_dir=scripts_dir,
                    default_memory="4GB",
                    default_disk="10GB",
                    default_cpus=2,
                    inline_submit=False
                )
                
                # Check that files were created
                assert dag_file.exists(), f"DAG file not created for {target_env}"
                assert scripts_dir.exists(), f"Scripts directory not created for {target_env}"
                
                # Check that script files were created
                script_files = list(scripts_dir.glob("*.sh"))
                assert len(script_files) == 3, f"Expected 3 script files, got {len(script_files)} for {target_env}"
                
                # Check DAG file content
                dag_content = dag_file.read_text()
                assert "prepare_data" in dag_content, f"prepare_data not found in DAG for {target_env}"
                assert "analyze_data" in dag_content, f"analyze_data not found in DAG for {target_env}"
                assert "generate_report" in dag_content, f"generate_report not found in DAG for {target_env}"
                assert "PARENT prepare_data CHILD analyze_data" in dag_content, f"Dependency not found in DAG for {target_env}"
                assert "PARENT analyze_data CHILD generate_report" in dag_content, f"Dependency not found in DAG for {target_env}"
                
                # Check submit files
                submit_files = list(temp_path.glob("*.sub"))
                assert len(submit_files) == 3, f"Expected 3 submit files, got {len(submit_files)} for {target_env}"
                
                # Check submit file content for environment-specific values
                for submit_file in submit_files:
                    submit_content = submit_file.read_text()
                    if target_env == "shared_filesystem":
                        assert "+CondaEnv = " in submit_content, f"Conda environment not found in submit file for {target_env}"
                
                print(f"✅ {target_env}: All files created successfully")
                print(f"   DAG file: {dag_file}")
                print(f"   Scripts: {len(script_files)} files")
                print(f"   Submit files: {len(submit_files)} files")
                
            except Exception as e:
                print(f"❌ {target_env}: Error during export: {e}")
                raise
    
    print("\n🎉 All DAGMan exporter tests passed!")

if __name__ == "__main__":
    test_dagman_exporter() 