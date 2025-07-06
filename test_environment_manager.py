#!/usr/bin/env python3
"""
Test script for the EnvironmentManager class.

This script tests the basic functionality of the EnvironmentManager class
to ensure it works correctly with the new environment-specific IR.
"""

import sys
import pathlib
import importlib.util
from pathlib import Path
from unittest.mock import patch

# Allow running tests without installing package
proj_root = pathlib.Path(__file__).resolve().parents[0]

if "wf2wf" not in sys.modules:
    spec = importlib.util.spec_from_file_location("wf2wf", proj_root / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["wf2wf"] = module  # type: ignore[assignment]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[arg-type]

from wf2wf.core import Workflow, Task, EnvironmentSpecificValue
from wf2wf.environ import EnvironmentManager


class TestEnvironmentManager:
    """Test cases for the EnvironmentManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.env_manager = EnvironmentManager(interactive=False, verbose=True)
        
        # Create a test workflow
        self.workflow = Workflow(name="test_workflow", version="1.0")
        
        # Add test tasks with correct EnvironmentSpecificValue structure
        task1 = Task(
            id="task1",
            command=EnvironmentSpecificValue("python script.py", ["shared_filesystem"]),
            container=EnvironmentSpecificValue("python:3.9", ["shared_filesystem"]),
            cpu=EnvironmentSpecificValue(2, ["shared_filesystem"]),
            mem_mb=EnvironmentSpecificValue(4096, ["shared_filesystem"])
        )
        
        task2 = Task(
            id="task2",
            command=EnvironmentSpecificValue("blast -query input.fasta", ["shared_filesystem"]),
            conda=EnvironmentSpecificValue("environment.yml", ["shared_filesystem"]),
            cpu=EnvironmentSpecificValue(4, ["shared_filesystem"]),
            mem_mb=EnvironmentSpecificValue(8192, ["shared_filesystem"])
        )
        
        task3 = Task(
            id="task3",
            command=EnvironmentSpecificValue("echo 'hello world'", ["shared_filesystem"])
            # No environment specification
        )
        
        self.workflow.add_task(task1)
        self.workflow.add_task(task2)
        self.workflow.add_task(task3)
    
    def test_detect_and_parse_environments(self):
        """Test environment detection and parsing."""
        source_path = Path("/tmp/test_workflow.smk")
        
        env_info = self.env_manager.detect_and_parse_environments(
            self.workflow, "snakemake", source_path
        )
        
        # Check detected containers
        assert "python:3.9" in env_info['containers']
        
        # Check detected conda environments
        assert "environment.yml" in env_info['conda_environments']
        
        # Check environment files
        assert "environment.yml" in env_info['environment_files']
        
        # Check missing environments
        assert "task3" in env_info['missing_environments']
        
        # Check metadata
        assert env_info['environment_metadata']['source_format'] == "snakemake"
        assert env_info['environment_metadata']['total_tasks'] == 3
        assert env_info['environment_metadata']['tasks_with_environments'] == 2
        assert env_info['environment_metadata']['tasks_without_environments'] == 1
    
    def test_analyze_task_environment(self):
        """Test individual task environment analysis."""
        task = self.workflow.tasks["task1"]
        source_path = Path("/tmp/test_workflow.smk")
        
        env_info = self.env_manager._analyze_task_environment(task, source_path)
        
        assert env_info['container'] == "python:3.9"
        assert env_info['conda'] is None
        assert env_info['environment_file'] is None
        assert env_info['metadata']['container_source'] == 'explicit'
        assert len(env_info['warnings']) == 0
    
    def test_analyze_task_environment_with_conda(self):
        """Test task environment analysis with conda specification."""
        task = self.workflow.tasks["task2"]
        source_path = Path("/tmp/test_workflow.smk")
        
        env_info = self.env_manager._analyze_task_environment(task, source_path)
        
        assert env_info['container'] is None
        assert env_info['conda'] == "environment.yml"
        assert env_info['environment_file'] == "environment.yml"
        assert env_info['metadata']['conda_source'] == 'explicit'
    
    def test_analyze_task_environment_without_env(self):
        """Test task environment analysis without environment specification."""
        task = self.workflow.tasks["task3"]
        source_path = Path("/tmp/test_workflow.smk")
        
        env_info = self.env_manager._analyze_task_environment(task, source_path)
        
        assert env_info['container'] is None
        assert env_info['conda'] is None
        assert env_info['environment_file'] is None
        assert len(env_info['warnings']) == 0
    
    def test_is_environment_file(self):
        """Test environment file detection."""
        # Test environment file extensions
        assert self.env_manager._is_environment_file("environment.yml") is True
        assert self.env_manager._is_environment_file("environment.yaml") is True
        assert self.env_manager._is_environment_file("requirements.txt") is True
        assert self.env_manager._is_environment_file("environment.lock") is True
        
        # Test container images (should not be files)
        assert self.env_manager._is_environment_file("python:3.9") is False
        assert self.env_manager._is_environment_file("docker://python:3.9") is False
        assert self.env_manager._is_environment_file("ubuntu:20.04") is False
        
        # Test relative paths
        assert self.env_manager._is_environment_file("./env/environment.yml") is True
        assert self.env_manager._is_environment_file("../environments/bio.yml") is True
        
        # Test empty or None
        assert self.env_manager._is_environment_file("") is False
        assert self.env_manager._is_environment_file(None) is False
    
    def test_infer_missing_environments(self):
        """Test inference of missing environment specifications."""
        # Clear environment specifications from task3
        task3 = self.workflow.tasks["task3"]
        task3.container = EnvironmentSpecificValue()
        task3.conda = EnvironmentSpecificValue()
        
        self.env_manager.infer_missing_environments(self.workflow, "snakemake")
        
        # Check that container was inferred for task3
        container = task3.container.get_value_for('shared_filesystem')
        assert container is not None
        assert "ubuntu" in container  # Should infer ubuntu for echo command
    
    def test_infer_container_from_command(self):
        """Test container inference from command."""
        # Test Python commands
        container = self.env_manager._infer_container_from_command("python script.py")
        assert "python" in container
        
        # Test R commands
        container = self.env_manager._infer_container_from_command("rscript analysis.R")
        assert "rocker" in container
        
        # Test bioinformatics commands
        container = self.env_manager._infer_container_from_command("blast -query input.fasta")
        assert "biocontainers" in container
        
        # Test machine learning commands
        container = self.env_manager._infer_container_from_command("python -c 'import tensorflow'")
        assert "tensorflow" in container
        
        # Test general Linux commands
        container = self.env_manager._infer_container_from_command("echo 'hello world'")
        assert "ubuntu" in container
        
        # Test None/empty commands
        assert self.env_manager._infer_container_from_command(None) is None
        assert self.env_manager._infer_container_from_command("") is None
    
    def test_infer_conda_environment_from_command(self):
        """Test conda environment inference from command."""
        # Test Python commands
        conda_env = self.env_manager._infer_conda_environment_from_command("python script.py")
        assert conda_env == "environment.yml"
        
        # Test R commands
        conda_env = self.env_manager._infer_conda_environment_from_command("rscript analysis.R")
        assert conda_env == "r_environment.yml"
        
        # Test bioinformatics commands
        conda_env = self.env_manager._infer_conda_environment_from_command("blast -query input.fasta")
        assert conda_env == "bioinformatics.yml"
        
        # Test machine learning commands
        conda_env = self.env_manager._infer_conda_environment_from_command("python -c 'import tensorflow'")
        assert conda_env == "ml_environment.yml"
        
        # Test None/empty commands
        assert self.env_manager._infer_conda_environment_from_command(None) is None
        assert self.env_manager._infer_conda_environment_from_command("") is None
    
    @patch('wf2wf.environ.build_or_reuse_env_image')
    def test_build_environment_images(self, mock_build):
        """Test environment image building."""
        # Mock successful build
        mock_build.return_value = {
            'success': True,
            'image_name': 'test_workflow-environment',
            'digest': 'sha256:abc123'
        }
        
        # Add conda environment to task
        task = self.workflow.tasks["task3"]
        task.conda.set_for_environment("environment.yml", "shared_filesystem")
        
        build_results = self.env_manager.build_environment_images(
            self.workflow,
            registry="myregistry.com",
            push=False,
            dry_run=True
        )
        
        # Check build results
        assert len(build_results['built_images']) == 1
        assert len(build_results['failed_builds']) == 0
        
        # Check that task was updated with built container
        container = task.container.get_value_for('shared_filesystem')
        assert container is not None
        assert "test_workflow-environment" in container
    
    def test_adapt_environments_for_target(self):
        """Test environment adaptation for target format."""
        # Add container to task
        task = self.workflow.tasks["task3"]
        task.container.set_for_environment("python:3.9", "shared_filesystem")
        
        # Adapt for different target formats
        self.env_manager.adapt_environments_for_target(self.workflow, "dagman")
        
        # Check that container was adapted (this would depend on the actual adaptation logic)
        container = task.container.get_value_for('shared_filesystem')
        assert container is not None
    
    def test_validate_environment_choice(self):
        """Test environment choice validation."""
        # Valid choices
        self.env_manager._validate_environment_choice("1")
        self.env_manager._validate_environment_choice("2")
        self.env_manager._validate_environment_choice("3")
        self.env_manager._validate_environment_choice("4")
        
        # Valid container specs
        self.env_manager._validate_environment_choice("python:3.9")
        self.env_manager._validate_environment_choice("docker://python:3.9")
        self.env_manager._validate_environment_choice("myregistry.com/myimage:latest")
        
        # Invalid choices
        with pytest.raises(ValueError):
            self.env_manager._validate_environment_choice("5")
        
        with pytest.raises(ValueError):
            self.env_manager._validate_environment_choice("invalid")
    
    def test_is_valid_container_spec(self):
        """Test container specification validation."""
        # Valid container specs
        assert self.env_manager._is_valid_container_spec("python:3.9") is True
        assert self.env_manager._is_valid_container_spec("ubuntu:20.04") is True
        assert self.env_manager._is_valid_container_spec("myregistry.com/myimage:latest") is True
        assert self.env_manager._is_valid_container_spec("docker://python:3.9") is True
        assert self.env_manager._is_valid_container_spec("myimage") is True
        
        # Invalid container specs
        assert self.env_manager._is_valid_container_spec("") is False
        assert self.env_manager._is_valid_container_spec(None) is False
        assert self.env_manager._is_valid_container_spec("invalid:spec:with:too:many:colons") is False
    
    @patch('wf2wf.environ.click')
    def test_prompt_user_with_click(self, mock_click):
        """Test user prompting with click library."""
        mock_click.prompt.return_value = "test_response"
        
        response = self.env_manager._prompt_user("Test message", "default")
        
        assert response == "test_response"
        mock_click.prompt.assert_called_once()
    
    @patch('builtins.input')
    def test_prompt_user_without_click(self, mock_input):
        """Test user prompting without click library."""
        mock_input.return_value = "test_response"
        
        # Mock click as None to simulate missing click
        with patch.dict('wf2wf.importers.environment_manager.__dict__', {'click': None}):
            response = self.env_manager._prompt_user("Test message", "default")
        
        assert response == "test_response"
        mock_input.assert_called_once()
    
    def test_prompt_user_validation(self):
        """Test user prompting with validation."""
        with patch('builtins.input') as mock_input:
            mock_input.return_value = "invalid"
            
            # Mock click as None to simulate missing click
            with patch.dict('wf2wf.importers.environment_manager.__dict__', {'click': None}):
                with pytest.raises(ValueError):
                    self.env_manager._prompt_user(
                        "Test message",
                        "default",
                        validation_func=lambda x: (_ for _ in ()).throw(ValueError("Invalid"))
                    )


class TestEnvironmentManagerIntegration:
    """Integration tests for EnvironmentManager with real workflows."""
    
    def test_full_workflow_environment_processing(self):
        """Test complete environment processing workflow."""
        # Create a realistic workflow
        workflow = Workflow(name="bioinformatics_pipeline", version="1.0")
        
        # Add tasks with various environment specifications
        task1 = Task(
            id="fastqc",
            command=EnvironmentSpecificValue("fastqc input.fastq", ["shared_filesystem"]),
            conda=EnvironmentSpecificValue("bioinformatics.yml", ["shared_filesystem"])
        )
        
        task2 = Task(
            id="alignment",
            command=EnvironmentSpecificValue("bwa mem ref.fa input.fastq", ["shared_filesystem"]),
            container=EnvironmentSpecificValue("biocontainers/bwa:latest", ["shared_filesystem"])
        )
        
        task3 = Task(
            id="analysis",
            command=EnvironmentSpecificValue("python analysis.py", ["shared_filesystem"])
            # No environment specification
        )
        
        workflow.add_task(task1)
        workflow.add_task(task2)
        workflow.add_task(task3)
        
        # Process with environment manager
        env_manager = EnvironmentManager(interactive=False, verbose=True)
        
        # Detect environments
        env_info = env_manager.detect_and_parse_environments(workflow, "snakemake")
        
        # Verify detection results
        assert len(env_info['containers']) == 1
        assert "biocontainers/bwa:latest" in env_info['containers']
        assert len(env_info['conda_environments']) == 1
        assert "bioinformatics.yml" in env_info['conda_environments']
        assert len(env_info['missing_environments']) == 1
        assert "analysis" in env_info['missing_environments']
        
        # Infer missing environments
        env_manager.infer_missing_environments(workflow, "snakemake")
        
        # Verify inference results
        analysis_task = workflow.tasks["analysis"]
        container = analysis_task.container.get_value_for('shared_filesystem')
        assert container is not None
        assert "python" in container  # Should infer Python container
    
    def test_environment_manager_with_advanced_features(self):
        """Test environment manager with advanced workflow features."""
        workflow = Workflow(name="ml_pipeline", version="1.0")
        
        # Create task with advanced features
        task = Task(
            id="training",
            command=EnvironmentSpecificValue("python train.py", ["shared_filesystem"]),
            container=EnvironmentSpecificValue("tensorflow/tensorflow:latest", ["shared_filesystem"]),
            checkpointing=EnvironmentSpecificValue(
                CheckpointSpec(
                    strategy="filesystem",
                    interval=300,
                    storage_location="/tmp/checkpoints",
                    enabled=True,
                    notes="Training checkpoints"
                ), ["shared_filesystem"]
            ),
            logging=EnvironmentSpecificValue(
                LoggingSpec(
                    log_level="INFO",
                    log_format="json",
                    log_destination="/tmp/logs",
                    aggregation="syslog",
                    notes="Training logs"
                ), ["shared_filesystem"]
            ),
            security=EnvironmentSpecificValue(
                SecuritySpec(
                    encryption="AES256",
                    access_policies="least-privilege",
                    secrets={},
                    authentication="oauth",
                    notes="Training security"
                ), ["shared_filesystem"]
            ),
            networking=EnvironmentSpecificValue(
                NetworkingSpec(
                    network_mode="bridge",
                    allowed_ports=[80, 443],
                    egress_rules=["0.0.0.0/0"],
                    ingress_rules=["10.0.0.0/8"],
                    notes="Training networking"
                ), ["shared_filesystem"]
            )
        )
        
        workflow.add_task(task)
        
        # Process with environment manager
        env_manager = EnvironmentManager(interactive=False, verbose=True)
        env_info = env_manager.detect_and_parse_environments(workflow, "snakemake")
        
        # Verify advanced features are detected
        task_env_info = env_manager._analyze_task_environment(task)
        assert task_env_info['metadata']['checkpointing'] is True
        assert task_env_info['metadata']['logging'] is True
        assert task_env_info['metadata']['security'] is True
        assert task_env_info['metadata']['networking'] is True


if __name__ == "__main__":
    pytest.main([__file__]) 