"""
Tests for interactive prompt handling in exporters.

This module tests the interactive prompting functionality in exporters,
ensuring that user inputs are properly handled and values are set correctly.
"""

import pytest
from wf2wf.core import Workflow, Task
from wf2wf.interactive import get_prompter


class TestInteractivePrompts:
    """Test interactive prompt functionality in exporters."""
    
    def test_nextflow_prompts_with_gpu(self, interactive_responses):
        """Test Nextflow prompts including GPU configuration."""
        interactive_responses.set_responses([
            # Resource Configuration
            "4",      # CPU cores
            "8192",   # Memory (MB)
            "4096",   # Disk space (MB)
            "2",      # Threads
            "7200",   # Runtime (seconds)
            "2",      # GPU requirements choice (2 = basic)
            "2",      # GPU count
            # Environment Configuration
            "2",      # Environment type choice (2 = container)
            "biocontainers/fastqc:latest",  # Container image
            "",       # Working directory (use default)
            # Execution Configuration
            "1",      # Execution type choice (1 = command)
            "echo 'test'",  # Command
            # Error Handling Configuration
            "3",      # Retry count
            "60",     # Retry delay (seconds)
            "3600",   # Max runtime (seconds)
        ])
        
        workflow = Workflow(name="test_workflow_nextflow")
        task = Task(id="test_task")
        workflow.tasks["test_task"] = task
        
        # Use the unified interactive system
        prompter = get_prompter()
        prompter.prompt_for_missing_values(workflow, "export", "shared_filesystem")
        
        # Verify values were set correctly
        assert task.cpu.get_value_for("shared_filesystem") == 4
        assert task.mem_mb.get_value_for("shared_filesystem") == 8192
        assert task.disk_mb.get_value_for("shared_filesystem") == 4096
        assert task.threads.get_value_for("shared_filesystem") == 2
        assert task.time_s.get_value_for("shared_filesystem") == 7200
        assert task.gpu.get_value_for("shared_filesystem") == 2
        assert task.container.get_value_for("shared_filesystem") == "biocontainers/fastqc:latest"
        assert task.command.get_value_for("shared_filesystem") == "echo 'test'"
        assert task.retry_count.get_value_for("shared_filesystem") == 3
        assert task.retry_delay.get_value_for("shared_filesystem") == 60
        assert task.max_runtime.get_value_for("shared_filesystem") == 3600
    
    def test_snakemake_prompts_with_conda(self, interactive_responses):
        """Test Snakemake prompts with conda environment."""
        interactive_responses.set_responses([
            # Resource Configuration
            "8",      # CPU cores
            "16384",  # Memory (MB)
            "8192",   # Disk space (MB)
            "4",      # Threads
            "10800",  # Runtime (seconds)
            "1",      # GPU requirements choice (1 = none)
            # Environment Configuration
            "1",      # Environment type choice (1 = conda)
            "environment.yml",  # Conda environment file
            "/work",  # Working directory
            # Execution Configuration
            "2",      # Execution type choice (2 = script)
            "scripts/analyze.py",  # Script path
            # Error Handling Configuration
            "2",      # Retry count
            "120",    # Retry delay (seconds)
            "7200",   # Max runtime (seconds)
        ])
        
        workflow = Workflow(name="test_workflow_snakemake")
        task = Task(id="test_task")
        workflow.tasks["test_task"] = task
        
        # Use the unified interactive system
        prompter = get_prompter()
        prompter.prompt_for_missing_values(workflow, "export", "shared_filesystem")
        
        # Verify values were set correctly
        assert task.cpu.get_value_for("shared_filesystem") == 8
        assert task.mem_mb.get_value_for("shared_filesystem") == 16384
        assert task.disk_mb.get_value_for("shared_filesystem") == 8192
        assert task.threads.get_value_for("shared_filesystem") == 4
        assert task.time_s.get_value_for("shared_filesystem") == 10800
        assert task.gpu.get_value_for("shared_filesystem") == 0  # none choice
        assert task.conda.get_value_for("shared_filesystem") == "environment.yml"
        assert task.workdir.get_value_for("shared_filesystem") == "/work"
        assert task.script.get_value_for("shared_filesystem") == "scripts/analyze.py"
        assert task.retry_count.get_value_for("shared_filesystem") == 2
        assert task.retry_delay.get_value_for("shared_filesystem") == 120
        assert task.max_runtime.get_value_for("shared_filesystem") == 7200
    
    def test_advanced_gpu_configuration(self, interactive_responses):
        """Test advanced GPU configuration with memory specification."""
        interactive_responses.set_responses([
            # Resource Configuration
            "16",     # CPU cores
            "32768",  # Memory (MB)
            "16384",  # Disk space (MB)
            "8",      # Threads
            "14400",  # Runtime (seconds)
            "3",      # GPU requirements choice (3 = advanced)
            "4",      # GPU count
            "16384",  # GPU memory (MB)
            # Environment Configuration
            "2",      # Environment type choice (2 = container)
            "nvidia/cuda:11.8-devel-ubuntu20.04",  # Container image
            "",       # Working directory (use default)
            # Execution Configuration
            "1",      # Execution type choice (1 = command)
            "python train.py",  # Command
            # Error Handling Configuration
            "5",      # Retry count
            "300",    # Retry delay (seconds)
            "28800",  # Max runtime (seconds)
        ])
        
        workflow = Workflow(name="test_workflow_gpu")
        task = Task(id="test_task")
        workflow.tasks["test_task"] = task
        
        # Use the unified interactive system
        prompter = get_prompter()
        prompter.prompt_for_missing_values(workflow, "export", "shared_filesystem")
        
        # Verify values were set correctly
        assert task.cpu.get_value_for("shared_filesystem") == 16
        assert task.mem_mb.get_value_for("shared_filesystem") == 32768
        assert task.disk_mb.get_value_for("shared_filesystem") == 16384
        assert task.threads.get_value_for("shared_filesystem") == 8
        assert task.time_s.get_value_for("shared_filesystem") == 14400
        assert task.gpu.get_value_for("shared_filesystem") == 4
        assert task.gpu_mem_mb.get_value_for("shared_filesystem") == 16384
        assert task.container.get_value_for("shared_filesystem") == "nvidia/cuda:11.8-devel-ubuntu20.04"
        assert task.command.get_value_for("shared_filesystem") == "python train.py"
        assert task.retry_count.get_value_for("shared_filesystem") == 5
        assert task.retry_delay.get_value_for("shared_filesystem") == 300
        assert task.max_runtime.get_value_for("shared_filesystem") == 28800
    
    def test_import_context_prompts(self, interactive_responses):
        """Test interactive prompts in import context (no error handling)."""
        interactive_responses.set_responses([
            # Resource Configuration
            "2",      # CPU cores
            "4096",   # Memory (MB)
            "2048",   # Disk space (MB)
            "1",      # Threads
            "3600",   # Runtime (seconds)
            "1",      # GPU requirements choice (1 = none)
            # Environment Configuration
            "3",      # Environment type choice (3 = none)
            "",       # Working directory (use default)
            # Execution Configuration
            "1",      # Execution type choice (1 = command)
            "echo 'hello world'",  # Command
        ])
        
        workflow = Workflow(name="test_workflow_import")
        task = Task(id="test_task")
        workflow.tasks["test_task"] = task
        
        # Use the unified interactive system for import context
        prompter = get_prompter()
        prompter.prompt_for_missing_values(workflow, "import", "shared_filesystem")
        
        # Verify values were set correctly
        assert task.cpu.get_value_for("shared_filesystem") == 2
        assert task.mem_mb.get_value_for("shared_filesystem") == 4096
        assert task.disk_mb.get_value_for("shared_filesystem") == 2048
        assert task.threads.get_value_for("shared_filesystem") == 1
        assert task.time_s.get_value_for("shared_filesystem") == 3600
        assert task.gpu.get_value_for("shared_filesystem") == 0  # none choice
        assert task.command.get_value_for("shared_filesystem") == "echo 'hello world'"
        
        # Verify error handling fields are NOT set (import context)
        assert task.retry_count.get_value_for("shared_filesystem") is None
        assert task.retry_delay.get_value_for("shared_filesystem") is None
        assert task.max_runtime.get_value_for("shared_filesystem") is None
    
    def test_default_value_handling(self, interactive_responses):
        """Test that default values are used when user provides empty input."""
        interactive_responses.set_responses([
            "",       # CPU cores (use default: 1)
            "",       # Memory (MB) (use default: 4096)
            "",       # Disk space (MB) (use default: 4096)
            "",       # Threads (use default: 1)
            "",       # Runtime (seconds) (use default: 3600)
            "1",      # GPU requirements choice (1 = none)
            "1",      # Environment type choice (1 = conda)
            "",       # Working directory (use default)
            "1",      # Execution type choice (1 = command)
            "",       # Command (use default)
            # Error Handling Configuration
            "",       # Retry count (use default: 3)
            "",       # Retry delay (seconds) (use default: 60)
            "",       # Max runtime (seconds) (use default: 3600)
        ])
        
        workflow = Workflow(name="test_workflow_defaults")
        task = Task(id="test_task")
        workflow.tasks["test_task"] = task
        
        # Use the unified interactive system
        prompter = get_prompter()
        prompter.prompt_for_missing_values(workflow, "export", "shared_filesystem")
        
        # Verify default values were used
        assert task.cpu.get_value_for("shared_filesystem") == 1
        assert task.mem_mb.get_value_for("shared_filesystem") == 4096
        assert task.disk_mb.get_value_for("shared_filesystem") == 4096
        assert task.threads.get_value_for("shared_filesystem") == 1
        assert task.time_s.get_value_for("shared_filesystem") == 3600
        assert task.gpu.get_value_for("shared_filesystem") == 0  # none choice
        assert task.retry_count.get_value_for("shared_filesystem") == 3
        assert task.retry_delay.get_value_for("shared_filesystem") == 60
        assert task.max_runtime.get_value_for("shared_filesystem") == 3600 