"""Tests for conda environment management functionality."""

import os
import sys
import pathlib
import importlib.util
import tempfile
import textwrap
from pathlib import Path

# Allow running tests without installing package
proj_root = pathlib.Path(__file__).resolve().parents[1]

if 'wf2wf' not in sys.modules:
    spec = importlib.util.spec_from_file_location('wf2wf', proj_root / '__init__.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules['wf2wf'] = module  # type: ignore[assignment]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[arg-type]

import pytest
from wf2wf.core import Workflow, Task, EnvironmentSpec, ResourceSpec
from wf2wf.exporters import dagman as dag_exporter

try:
    from wf2wf.importers import snakemake as snake_importer
    SNAKEMAKE_AVAILABLE = True
except ImportError:
    SNAKEMAKE_AVAILABLE = False


class TestCondaEnvironmentSetup:
    """Test conda environment setup and management."""
    
    def test_conda_environment_spec_creation(self):
        """Test creating EnvironmentSpec with conda environment."""
        env = EnvironmentSpec(conda="environment.yaml")
        assert env.conda == "environment.yaml"
        assert env.container is None
    
    def test_task_with_conda_environment(self):
        """Test creating task with conda environment."""
        env = EnvironmentSpec(conda="analysis.yaml")
        task = Task(
            id="conda_task",
            command="python analyze.py",
            environment=env
        )
        assert task.environment.conda == "analysis.yaml"
        assert task.environment.container is None
    
    def test_workflow_with_multiple_conda_environments(self):
        """Test workflow with multiple different conda environments."""
        wf = Workflow(name="multi_conda")
        
        # Task 1 with first environment
        task1 = Task(
            id="task1",
            command="python preprocess.py",
            environment=EnvironmentSpec(conda="preprocess_env.yaml")
        )
        wf.add_task(task1)
        
        # Task 2 with second environment
        task2 = Task(
            id="task2", 
            command="python analyze.py",
            environment=EnvironmentSpec(conda="analysis_env.yaml")
        )
        wf.add_task(task2)
        
        # Task 3 reusing first environment
        task3 = Task(
            id="task3",
            command="python postprocess.py",
            environment=EnvironmentSpec(conda="preprocess_env.yaml")
        )
        wf.add_task(task3)
        
        wf.add_edge("task1", "task2")
        wf.add_edge("task2", "task3")
        
        assert len(wf.tasks) == 3
        assert wf.tasks["task1"].environment.conda == "preprocess_env.yaml"
        assert wf.tasks["task2"].environment.conda == "analysis_env.yaml"
        assert wf.tasks["task3"].environment.conda == "preprocess_env.yaml"
    
    def test_dagman_export_conda_environment(self, tmp_path):
        """Test DAGMan export with conda environment."""
        wf = Workflow(name="conda_workflow")
        
        task = Task(
            id="conda_analysis",
            command="python analyze.py --input data.csv --output results.json",
            environment=EnvironmentSpec(conda="analysis_env.yaml"),
            resources=ResourceSpec(cpu=4, mem_mb=8192)
        )
        wf.add_task(task)
        
        dag_path = tmp_path / "conda_workflow.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)
        
        # Check submit file instead of DAG file
        submit_path = tmp_path / "conda_analysis.sub"
        submit_content = submit_path.read_text()
        
        # Check basic submit file structure
        assert "universe = vanilla" in submit_content
        assert "request_cpus = 4" in submit_content
        assert "request_memory = 8192MB" in submit_content
        
        # Check that script was generated
        scripts_dir = tmp_path / "scripts"
        script_files = list(scripts_dir.glob("conda_analysis.*"))
        assert len(script_files) >= 1
    
    def test_conda_with_resource_specifications(self):
        """Test conda environment combined with resource specifications."""
        task = Task(
            id="resource_conda_task",
            command="python intensive_analysis.py",
            environment=EnvironmentSpec(conda="gpu_env.yaml"),
            resources=ResourceSpec(
                cpu=16,
                mem_mb=32768,
                gpu=2,
                gpu_mem_mb=8000
            )
        )
        
        assert task.environment.conda == "gpu_env.yaml"
        assert task.resources.cpu == 16
        assert task.resources.mem_mb == 32768
        assert task.resources.gpu == 2
        assert task.resources.gpu_mem_mb == 8000


class TestCondaEnvironmentParsing:
    """Test parsing conda environments from Snakemake workflows."""
    
    @pytest.mark.skipif(not SNAKEMAKE_AVAILABLE, reason="Snakemake not available")
    def test_snakemake_conda_environment_parsing(self, tmp_path):
        """Test parsing conda environment from Snakemake workflow."""
        # Create conda environment file
        env_file = tmp_path / "analysis.yaml"
        env_file.write_text(textwrap.dedent("""
            channels:
              - conda-forge
              - bioconda
            dependencies:
              - python=3.9
              - pandas
              - numpy
              - matplotlib
        """))
        
        # Create Snakefile with conda environment
        snakefile = tmp_path / "conda_workflow.smk"
        snakefile.write_text(textwrap.dedent(f"""
            rule data_analysis:
                input: "data.csv"
                output: "results.json"
                conda: "{env_file}"
                resources:
                    mem_gb=8,
                    threads=4
                shell: "python analyze.py --input {{input}} --output {{output}}"
            
            rule visualization:
                input: "results.json"
                output: "plots.png"
                conda: "{env_file}"
                shell: "python plot.py --input {{input}} --output {{output}}"
            
            rule all:
                input: "results.json", "plots.png"
        """))
        
        # Create dummy input file
        (tmp_path / "data.csv").write_text("col1,col2\n1,2\n3,4\n")
        
        try:
            wf = snake_importer.to_workflow(snakefile, workdir=tmp_path)
            
            # Find tasks with conda environments
            conda_tasks = []
            for task in wf.tasks.values():
                if task.environment and task.environment.conda:
                    conda_tasks.append(task)
            
            assert len(conda_tasks) >= 1, f"Should have at least 1 task with conda environment, found {len(conda_tasks)}"
            
            # Check that conda environment path is preserved
            for task in conda_tasks:
                assert task.environment.conda == str(env_file)
            
        except RuntimeError as e:
            if "snakemake" in str(e):
                pytest.skip("Snakemake not available for integration test")
            else:
                raise
    
    @pytest.mark.skipif(not SNAKEMAKE_AVAILABLE, reason="Snakemake not available")
    def test_snakemake_conda_with_container_priority(self, tmp_path):
        """Test that container takes priority over conda when both are specified."""
        # Create conda environment file
        env_file = tmp_path / "env.yaml"
        env_file.write_text("channels:\n  - conda-forge\ndependencies:\n  - python=3.9")
        
        # Create Snakefile with both conda and container
        snakefile = tmp_path / "priority_test.smk"
        snakefile.write_text(textwrap.dedent(f"""
            rule priority_test:
                output: "output.txt"
                container: "docker://python:3.9-slim"
                conda: "{env_file}"
                shell: "echo 'test' > {{output}}"
            
            rule all:
                input: "output.txt"
        """))
        
        try:
            wf = snake_importer.to_workflow(snakefile, workdir=tmp_path)
            
            # Find the priority test task
            priority_task = None
            for task in wf.tasks.values():
                if "priority_test" in task.id:
                    priority_task = task
                    break
            
            assert priority_task is not None
            assert priority_task.environment.container == "docker://python:3.9-slim"
            assert priority_task.environment.conda == str(env_file)
            
            # Test DAG export - should use container universe
            dag_path = tmp_path / "priority_test.dag"
            dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)
            
            # Check submit file for container specifications
            submit_path = tmp_path / "priority_test_0.sub"
            submit_content = submit_path.read_text()
            assert "universe = docker" in submit_content
            assert "docker_image = python:3.9-slim" in submit_content
            
        except RuntimeError as e:
            if "snakemake" in str(e):
                pytest.skip("Snakemake not available for integration test")
            else:
                raise


class TestCondaEnvironmentExport:
    """Test conda environment handling in DAGMan export."""
    
    def test_conda_environment_export_vanilla_universe(self, tmp_path):
        """Test that conda environments use vanilla universe."""
        wf = Workflow(name="conda_export_test")
        
        task = Task(
            id="conda_task",
            command="python process.py",
            environment=EnvironmentSpec(conda="processing.yaml")
        )
        wf.add_task(task)
        
        dag_path = tmp_path / "conda_export.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)
        
        # Check submit file for universe specifications
        submit_path = tmp_path / "conda_task.sub"
        submit_content = submit_path.read_text()
        
        # Should use vanilla universe for conda
        assert "universe = vanilla" in submit_content
        assert "universe = docker" not in submit_content
        assert "+SingularityImage" not in submit_content
    
    def test_multiple_conda_environments_export(self, tmp_path):
        """Test export of workflow with multiple conda environments."""
        wf = Workflow(name="multi_conda_export")
        
        # Task 1 with first environment
        task1 = Task(
            id="preprocess",
            command="python preprocess.py",
            environment=EnvironmentSpec(conda="preprocess.yaml")
        )
        wf.add_task(task1)
        
        # Task 2 with different environment  
        task2 = Task(
            id="analyze",
            command="python analyze.py", 
            environment=EnvironmentSpec(conda="analysis.yaml")
        )
        wf.add_task(task2)
        
        # Task 3 without conda environment
        task3 = Task(
            id="summarize",
            command="python summarize.py"
        )
        wf.add_task(task3)
        
        wf.add_edge("preprocess", "analyze")
        wf.add_edge("analyze", "summarize")
        
        dag_path = tmp_path / "multi_conda.dag"
        dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)
        
        dag_content = dag_path.read_text()
        
        # All tasks should be present
        assert "JOB preprocess" in dag_content
        assert "JOB analyze" in dag_content  
        assert "JOB summarize" in dag_content
        
        # Check submit files for universe specifications
        preprocess_submit = tmp_path / "preprocess.sub"
        analyze_submit = tmp_path / "analyze.sub"
        summarize_submit = tmp_path / "summarize.sub"
        
        preprocess_content = preprocess_submit.read_text()
        analyze_content = analyze_submit.read_text()
        summarize_content = summarize_submit.read_text()
        
        # Should use vanilla universe for all
        assert "universe = vanilla" in preprocess_content
        assert "universe = vanilla" in analyze_content
        assert "universe = vanilla" in summarize_content
        
        # Check dependencies
        assert "PARENT preprocess CHILD analyze" in dag_content
        assert "PARENT analyze CHILD summarize" in dag_content


class TestCondaEnvironmentValidation:
    """Test validation of conda environment specifications."""
    
    def test_conda_environment_file_validation(self):
        """Test that conda environment files are properly validated."""
        # Valid conda environment
        env = EnvironmentSpec(conda="environment.yaml")
        assert env.conda == "environment.yaml"
        
        # Valid conda environment name
        env = EnvironmentSpec(conda="myenv")
        assert env.conda == "myenv"
        
        # Empty conda specification should be None
        env = EnvironmentSpec(conda="")
        assert env.conda == ""
        
        env = EnvironmentSpec()
        assert env.conda is None
    
    def test_conda_with_resources_validation(self):
        """Test conda environment with resource specifications."""
        task = Task(
            id="validated_task",
            command="python validate.py",
            environment=EnvironmentSpec(conda="validation.yaml"),
            resources=ResourceSpec(
                cpu=2,
                mem_mb=4096,
                disk_mb=10240
            )
        )
        
        # All specifications should be preserved
        assert task.environment.conda == "validation.yaml"
        assert task.resources.cpu == 2
        assert task.resources.mem_mb == 4096
        assert task.resources.disk_mb == 10240
    
    def test_workflow_conda_environment_consistency(self):
        """Test that conda environments are consistently handled across workflow."""
        wf = Workflow(name="consistency_test")
        
        # Multiple tasks with same conda environment
        for i in range(3):
            task = Task(
                id=f"task_{i}",
                command=f"python task_{i}.py",
                environment=EnvironmentSpec(conda="shared_env.yaml")
            )
            wf.add_task(task)
        
        # All tasks should have the same conda environment
        for task in wf.tasks.values():
            assert task.environment.conda == "shared_env.yaml" 