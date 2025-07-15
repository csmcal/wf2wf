"""
wf2wf.interactive – Unified interactive prompting system.

This module provides a centralized, testable, and consistent interactive
prompting system for both importers and exporters. It consolidates all
prompting logic and provides a clean interface for user interaction.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional, Callable, Union
from pathlib import Path

from wf2wf.core import Workflow, Task, EnvironmentSpecificValue

logger = logging.getLogger(__name__)


class InteractivePrompter:
    """Centralized interactive prompting system."""
    
    def __init__(self, interactive: bool = True, verbose: bool = False):
        self.interactive = interactive
        self.verbose = verbose
    
    def prompt_for_missing_values(
        self, 
        workflow: Workflow, 
        context: str, 
        target_environment: str = "shared_filesystem"
    ) -> None:
        """
        Prompt for missing values in a workflow.
        
        Args:
            workflow: Workflow to prompt for
            context: Context ('import' or 'export')
            target_environment: Target environment name
        """
        if not self.interactive or os.environ.get("WF2WF_NO_PROMPT") == "1":
            return
        
        if self.verbose:
            logger.info(f"Starting interactive prompting for {context} context")
        
        for task in workflow.tasks.values():
            self._prompt_task_resources(task, target_environment, context)
            self._prompt_task_environment(task, target_environment, context)
            self._prompt_task_execution(task, target_environment, context)
            
            if context == "export":
                self._prompt_task_error_handling(task, target_environment)
    
    def _prompt_task_resources(self, task: Task, environment: str, context: str) -> None:
        """Prompt for task resource requirements."""
        if self.verbose:
            print(f"\n=== Resource Configuration for {task.id} ===")
        
        # Core resource fields
        resource_prompts = [
            ("CPU cores", "cpu", int, 1),
            ("Memory (MB)", "mem_mb", int, 4096),
            ("Disk space (MB)", "disk_mb", int, 4096),
            ("Threads", "threads", int, 1),
            ("Runtime (seconds)", "time_s", int, 3600),
        ]
        
        # Process core resources
        for prompt_text, field_name, value_type, default in resource_prompts:
            if not self._has_env_value(getattr(task, field_name), environment):
                value = self._prompt_user(f"{prompt_text} (default: {default}): ", value_type, default)
                if value is not None:
                    getattr(task, field_name).set_for_environment(value, environment)
        
        # GPU requirements (optional)
        if not self._has_env_value(task.gpu, environment):
            gpu_choice = self._prompt_choice(
                "GPU requirements", 
                ["none", "basic", "advanced"], 
                "none"
            )
            if gpu_choice == "basic":
                gpu_count = self._prompt_user("GPU count (default: 1): ", int, 1)
                if gpu_count and gpu_count > 0:
                    task.gpu.set_for_environment(gpu_count, environment)
            elif gpu_choice == "advanced":
                gpu_count = self._prompt_user("GPU count (default: 1): ", int, 1)
                gpu_mem = self._prompt_user("GPU memory (MB) (default: 8192): ", int, 8192)
                if gpu_count and gpu_count > 0:
                    task.gpu.set_for_environment(gpu_count, environment)
                if gpu_mem and gpu_mem > 0:
                    task.gpu_mem_mb.set_for_environment(gpu_mem, environment)
            else:  # Explicitly set GPU to 0 for 'none'
                task.gpu.set_for_environment(0, environment)
    
    def _prompt_task_environment(self, task: Task, environment: str, context: str) -> None:
        """Prompt for task environment specifications."""
        if self.verbose:
            print(f"\n=== Environment Configuration for {task.id} ===")
        
        # Environment specification
        if not self._has_env_value(task.conda, environment) and not self._has_env_value(task.container, environment):
            env_choice = self._prompt_choice("Environment type", ["conda", "container", "none"], "conda")
            if env_choice == "conda":
                conda_env = self._prompt_user("Conda environment file (default: environment.yml): ", str, "environment.yml")
                if conda_env:
                    task.conda.set_for_environment(conda_env, environment)
            elif env_choice == "container":
                container = self._prompt_user("Container image (default: default-runtime:latest): ", str, "default-runtime:latest")
                if container:
                    task.container.set_for_environment(container, environment)
        
        # Working directory
        if not self._has_env_value(task.workdir, environment):
            workdir = self._prompt_user("Working directory (default: current): ", str, "")
            if workdir:
                task.workdir.set_for_environment(workdir, environment)
    
    def _prompt_task_execution(self, task: Task, environment: str, context: str) -> None:
        """Prompt for task execution specifications."""
        if self.verbose:
            print(f"\n=== Execution Configuration for {task.id} ===")
        
        # Command or script
        if not self._has_env_value(task.command, environment) and not self._has_env_value(task.script, environment):
            exec_choice = self._prompt_choice("Execution type", ["command", "script"], "command")
            if exec_choice == "command":
                command = self._prompt_user("Command: ", str, "")
                if command:
                    task.command.set_for_environment(command, environment)
            else:
                script = self._prompt_user("Script path: ", str, "")
                if script:
                    task.script.set_for_environment(script, environment)
    
    def _prompt_task_error_handling(self, task: Task, environment: str) -> None:
        """Prompt for task error handling (export context only)."""
        if self.verbose:
            print(f"\n=== Error Handling Configuration for {task.id} ===")
        
        error_prompts = [
            ("Retry count", "retry_count", int, 3),
            ("Retry delay (seconds)", "retry_delay", int, 60),
            ("Max runtime (seconds)", "max_runtime", int, 3600),
        ]
        
        for prompt_text, field_name, value_type, default in error_prompts:
            if not self._has_env_value(getattr(task, field_name), environment):
                value = self._prompt_user(f"{prompt_text} (default: {default}): ", value_type, default)
                if value is not None:
                    getattr(task, field_name).set_for_environment(value, environment)
    
    def _prompt_user(self, prompt: str, value_type: type, default: Any) -> Optional[Any]:
        """Prompt user for input with type conversion and default value."""
        if self.verbose:
            logger.debug(f"Prompting: {prompt} (type: {value_type}, default: {default})")
        
        try:
            user_input = input(prompt).strip()
            
            if not user_input:
                if self.verbose:
                    logger.debug(f"Using default: {default}")
                return default
            
            result = value_type(user_input)
            if self.verbose:
                logger.debug(f"User input converted: {result}")
            return result
            
        except (ValueError, KeyboardInterrupt) as e:
            if self.verbose:
                logger.debug(f"Input error: {e}, using default: {default}")
            print(f"Using default value: {default}")
            return default
    
    def _prompt_choice(self, prompt: str, choices: List[str], default: str) -> str:
        """Prompt user to choose from a list of options."""
        if self.verbose:
            logger.debug(f"Choice prompt: {prompt} (choices: {choices}, default: {default})")
        
        print(f"{prompt}:")
        for i, choice in enumerate(choices, 1):
            marker = " (default)" if choice == default else ""
            print(f"  {i}. {choice}{marker}")
        
        try:
            user_input = input("Enter choice: ").strip()
            
            if not user_input:
                if self.verbose:
                    logger.debug(f"Using default choice: {default}")
                return default
            
            choice_index = int(user_input) - 1
            if 0 <= choice_index < len(choices):
                result = choices[choice_index]
                if self.verbose:
                    logger.debug(f"Selected choice: {result}")
                return result
            else:
                if self.verbose:
                    logger.debug(f"Invalid choice index: {choice_index}, using default")
                print(f"Invalid choice. Using default: {default}")
                return default
                
        except (ValueError, KeyboardInterrupt) as e:
            if self.verbose:
                logger.debug(f"Choice error: {e}, using default: {default}")
            print(f"Using default choice: {default}")
            return default
    
    def _has_env_value(self, env_value: EnvironmentSpecificValue, environment: str) -> bool:
        """Check if EnvironmentSpecificValue has a value for the given environment."""
        if env_value is None:
            return False
        
        # Check for environment-specific value
        value = env_value.get_value_for(environment)
        if value is not None:
            return True
        
        # Check for universal value (empty environments list)
        value = env_value.get_value_for("")
        return value is not None

    def prompt_text(self, prompt: str, default: str = "") -> str:
        """Prompt user for text input."""
        return self._prompt_user(f"{prompt} (default: {default}): ", str, default)
    
    def prompt_int(self, prompt: str, default: int = 0, min_value: int = None, max_value: int = None) -> int:
        """Prompt user for integer input with optional min/max validation."""
        while True:
            result = self._prompt_user(f"{prompt} (default: {default}): ", int, default)
            if min_value is not None and result < min_value:
                print(f"Value must be at least {min_value}")
                continue
            if max_value is not None and result > max_value:
                print(f"Value must be at most {max_value}")
                continue
            return result

    def prompt_choice(self, prompt: str, choices: list, default: str) -> str:
        """Prompt user to choose from a list of options."""
        return self._prompt_choice(prompt, choices, default)


# Global prompter instance
_global_prompter = InteractivePrompter()


def get_prompter() -> InteractivePrompter:
    """Get the global prompter instance."""
    return _global_prompter


def set_prompter(prompter: InteractivePrompter) -> None:
    """Set the global prompter instance (mainly for testing)."""
    global _global_prompter
    _global_prompter = prompter


# Convenience functions for backward compatibility
def prompt_for_missing_values(
    workflow: Workflow, 
    context: str, 
    target_environment: str = "shared_filesystem"
) -> None:
    """Convenience function for prompting for missing values."""
    _global_prompter.prompt_for_missing_values(workflow, context, target_environment)


def prompt_for_missing_information(workflow: Workflow, source_format: str) -> None:
    """
    Prompt for missing information during import.
    
    Args:
        workflow: Workflow to prompt for
        source_format: Source format name
    """
    prompter = get_prompter()
    
    print(f"\n=== Import Configuration for {source_format.upper()} ===")
    
    # Prompt for workflow-level information
    if not workflow.name or workflow.name == "imported_workflow":
        workflow.name = prompter.prompt_text("Workflow name", default="my_workflow")
    
    if not workflow.version:
        workflow.version = prompter.prompt_text("Workflow version", default="1.0")
    
    if not workflow.label:
        workflow.label = prompter.prompt_text("Workflow label (optional)", default="")
        if not workflow.label:
            workflow.label = None
    
    # Prompt for task-level information
    for task in workflow.tasks.values():
        print(f"\n--- Task: {task.id} ---")
        
        # Prompt for missing resource specifications
        if task.cpu.get_value_for('shared_filesystem') is None:
            cpu = prompter.prompt_int("CPU cores", default=1, min_value=1, max_value=64)
            task.cpu.set_for_environment(cpu, 'shared_filesystem')
        
        if task.mem_mb.get_value_for('shared_filesystem') is None:
            mem = prompter.prompt_int("Memory (MB)", default=4096, min_value=512, max_value=131072)
            task.mem_mb.set_for_environment(mem, 'shared_filesystem')
        
        if task.disk_mb.get_value_for('shared_filesystem') is None:
            disk = prompter.prompt_int("Disk space (MB)", default=4096, min_value=512, max_value=1048576)
            task.disk_mb.set_for_environment(disk, 'shared_filesystem')
        
        # Prompt for GPU if not specified
        if task.gpu.get_value_for('shared_filesystem') is None:
            use_gpu = prompter.prompt_choice("Use GPU?", choices=["no", "yes"], default="no")
            if use_gpu == "yes":
                gpu_count = prompter.prompt_int("GPU count", default=1, min_value=1, max_value=8)
                task.gpu.set_for_environment(gpu_count, 'shared_filesystem')
                
                gpu_mem = prompter.prompt_int("GPU memory (MB)", default=8192, min_value=1024, max_value=32768)
                task.gpu_mem_mb.set_for_environment(gpu_mem, 'shared_filesystem')
        
        # Prompt for environment if not specified
        if (task.container.get_value_for('shared_filesystem') is None and 
            task.conda.get_value_for('shared_filesystem') is None):
            
            env_type = prompter.prompt_choice(
                "Environment type", 
                choices=["none", "conda", "container"], 
                default="none"
            )
            
            if env_type == "conda":
                conda_env = prompter.prompt_text("Conda environment file or name")
                task.conda.set_for_environment(conda_env, 'shared_filesystem')
            elif env_type == "container":
                container_img = prompter.prompt_text("Container image (e.g., biocontainers/fastqc:latest)")
                task.container.set_for_environment(container_img, 'shared_filesystem')
        
        # Prompt for execution parameters
        if task.retry_count.get_value_for('shared_filesystem') is None:
            retries = prompter.prompt_int("Retry count", default=0, min_value=0, max_value=10)
            task.retry_count.set_for_environment(retries, 'shared_filesystem')
        
        if task.time_s.get_value_for('shared_filesystem') is None:
            time_limit = prompter.prompt_int("Time limit (seconds)", default=3600, min_value=60, max_value=86400)
            task.time_s.set_for_environment(time_limit, 'shared_filesystem')


def prompt_for_execution_model_confirmation(
    source_format: str, 
    content_analysis: Any
) -> str:
    """
    Prompt for execution model confirmation during import.
    Args:
        source_format: Source format name
        content_analysis: Content analysis results
        
    Returns:
        Selected execution model string
    """
    prompter = get_prompter()

    # Handle case where content_analysis is None
    if content_analysis is None:
        print(f"\n=== Execution Model Detection for {source_format.upper()} ===")
        print("Warning: Could not analyze workflow content for execution model detection.")
        print("Using format-based default.")
        
        # Use format-based default
        format_defaults = {
            "snakemake": "shared_filesystem",
            "dagman": "distributed_computing", 
            "nextflow": "hybrid",
            "cwl": "shared_filesystem",
            "wdl": "shared_filesystem",
            "galaxy": "shared_filesystem"
        }
        default_model = format_defaults.get(source_format.lower(), "unknown")
        
        print(f"Default execution model for {source_format}: {default_model}")
        
        # Present options
        models = [
            ("Shared Filesystem (NFS, Lustre, local cluster)", "shared_filesystem"),
            ("Distributed Computing (HTCondor, Grid, cloud batch)", "distributed_computing"),
            ("Hybrid (Nextflow, mixed cloud/HPC)", "hybrid"),
            ("Cloud-native (S3/GCS/Azure, serverless)", "cloud_native"),
            ("Other / Not sure", "unknown"),
            ("Use format default", "auto")
        ]
        print("\nPlease select the expected execution model for this workflow:")
        for idx, (desc, _) in enumerate(models, 1):
            print(f"  {idx}) {desc}")

        while True:
            choice = input(f"Select option (1-{len(models)} or 'auto'): ").strip().lower()
            if choice == 'auto' or choice == str(len(models)):
                # Use format default
                model = default_model
                print(f"Using format default: {model}")
                return model
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(models) - 1:
                    model = models[idx][1]
                    print(f"Selected execution model: {model}")
                    return model
                else:
                    print(f"Please enter a number between 1 and {len(models)} or 'auto'.")
            except ValueError:
                print(f"Please enter a valid number or 'auto'.")

    print(f"\n=== Execution Model Detection for {source_format.upper()} ===")
    print(f"Detected model: {content_analysis.execution_model}")

    if content_analysis.indicators:
        print("\nDetection evidence:")
        for model_type, indicators in content_analysis.indicators.items():
            if indicators:
                print(f"  {model_type}:")
                for indicator in indicators[:3]:  # Show first 3
                    print(f"    - {indicator}")
                if len(indicators) > 3:
                    print(f"    ... and {len(indicators) - 3} more")

    if content_analysis.recommendations:
        print("\nRecommendations:")
        for rec in content_analysis.recommendations:
            print(f"  - {rec}")

    # Present options
    models = [
        ("Shared Filesystem (NFS, Lustre, local cluster)", "shared_filesystem"),
        ("Distributed Computing (HTCondor, Grid, cloud batch)", "distributed_computing"),
        ("Hybrid (Nextflow, mixed cloud/HPC)", "hybrid"),
        ("Cloud-native (S3/GCS/Azure, serverless)", "cloud_native"),
        ("Other / Not sure", "unknown"),
        ("Auto-detect; will default to auto when no other option is selected", "auto")
    ]
    print("\nPlease select the expected execution model for this workflow:")
    for idx, (desc, _) in enumerate(models, 1):
        print(f"  {idx}) {desc}")

    while True:
        choice = input(f"Select option (1-{len(models)} or 'auto'): ").strip().lower()
        if choice == 'auto' or choice == str(len(models)):
            # Use auto-detect
            model = content_analysis.execution_model
            print(f"Using automatic execution model detection: {model}")
            return model
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models) - 1:
                model = models[idx][1]
                print(f"Selected execution model: {model}")
                return model
            else:
                print(f"Please enter a number between 1 and {len(models)} or 'auto'.")
        except ValueError:
            print(f"Please enter a valid number or 'auto'.")


def prompt_for_workflow_optimization(workflow: Workflow, target_format: str) -> None:
    """
    Prompt for workflow optimization for target format.
    
    Args:
        workflow: Workflow to optimize
        target_format: Target format name
    """
    prompter = get_prompter()
    
    print(f"\n=== Workflow Optimization for {target_format.upper()} ===")
    
    # Analyze current workflow
    optimizations = []
    
    # Check for missing resource specifications
    for task in workflow.tasks.values():
        if task.cpu.get_value_for('shared_filesystem') is None:
            optimizations.append(f"Add CPU specification for task '{task.id}'")
        
        if task.mem_mb.get_value_for('shared_filesystem') is None:
            optimizations.append(f"Add memory specification for task '{task.id}'")
        
        if task.disk_mb.get_value_for('shared_filesystem') is None:
            optimizations.append(f"Add disk specification for task '{task.id}'")
    
    # Check for environment consistency
    containers = set()
    conda_envs = set()
    
    for task in workflow.tasks.values():
        container = task.container.get_value_for('shared_filesystem')
        if container:
            containers.add(container)
        
        conda = task.conda.get_value_for('shared_filesystem')
        if conda:
            conda_envs.add(conda)
    
    if len(containers) > 3:
        optimizations.append(f"Consolidate {len(containers)} different containers")
    
    if len(conda_envs) > 2:
        optimizations.append(f"Consolidate {len(conda_envs)} different conda environments")
    
    # Show optimization suggestions
    if optimizations:
        print("Suggested optimizations:")
        for opt in optimizations:
            print(f"  - {opt}")
        
        apply_opt = prompter.prompt_choice(
            "Apply optimizations?",
            choices=["yes", "no", "selective"],
            default="no"
        )
        
        if apply_opt == "yes":
            # Apply all optimizations
            _apply_workflow_optimizations(workflow, target_format)
        elif apply_opt == "selective":
            # Let user choose which optimizations to apply
            _apply_selective_optimizations(workflow, target_format, optimizations)
    else:
        print("No optimizations needed for this workflow.")


def _apply_workflow_optimizations(workflow: Workflow, target_format: str) -> None:
    """
    Apply workflow optimizations for target format.
    
    Args:
        workflow: Workflow to optimize
        target_format: Target format name
    """
    prompter = get_prompter()
    
    print("Applying optimizations...")
    
    # Apply default resource specifications
    for task in workflow.tasks.values():
        if task.cpu.get_value_for('shared_filesystem') is None:
            task.cpu.set_for_environment(1, 'shared_filesystem')
        
        if task.mem_mb.get_value_for('shared_filesystem') is None:
            task.mem_mb.set_for_environment(4096, 'shared_filesystem')
        
        if task.disk_mb.get_value_for('shared_filesystem') is None:
            task.disk_mb.set_for_environment(4096, 'shared_filesystem')
    
    # Consolidate environments if needed
    containers = set()
    conda_envs = set()
    
    for task in workflow.tasks.values():
        container = task.container.get_value_for('shared_filesystem')
        if container:
            containers.add(container)
        
        conda = task.conda.get_value_for('shared_filesystem')
        if conda:
            conda_envs.add(conda)
    
    if len(containers) > 3:
        # Suggest consolidation
        print(f"Found {len(containers)} different containers. Consider using a common base image.")
    
    if len(conda_envs) > 2:
        # Suggest consolidation
        print(f"Found {len(conda_envs)} different conda environments. Consider using a common environment.")
    
    print("Optimizations applied successfully.")


def _apply_selective_optimizations(
    workflow: Workflow, 
    target_format: str, 
    optimizations: list
) -> None:
    """
    Apply selective optimizations chosen by user.
    
    Args:
        workflow: Workflow to optimize
        target_format: Target format name
        optimizations: List of available optimizations
    """
    prompter = get_prompter()
    
    print("\nSelect optimizations to apply:")
    for i, opt in enumerate(optimizations, 1):
        print(f"  {i}. {opt}")
    
    selected = prompter.prompt_text(
        "Enter optimization numbers (comma-separated, or 'all'):",
        default="all"
    )
    
    if selected.lower() == "all":
        selected_indices = list(range(1, len(optimizations) + 1))
    else:
        try:
            selected_indices = [int(x.strip()) for x in selected.split(",")]
        except ValueError:
            print("Invalid selection. No optimizations applied.")
            return
    
    # Apply selected optimizations
    for idx in selected_indices:
        if 1 <= idx <= len(optimizations):
            opt = optimizations[idx - 1]
            print(f"Applying: {opt}")
            
            # Apply the specific optimization
            if "CPU specification" in opt:
                task_id = opt.split("'")[1]
                if task_id in workflow.tasks:
                    workflow.tasks[task_id].cpu.set_for_environment(1, 'shared_filesystem')
            
            elif "memory specification" in opt:
                task_id = opt.split("'")[1]
                if task_id in workflow.tasks:
                    workflow.tasks[task_id].mem_mb.set_for_environment(4096, 'shared_filesystem')
            
            elif "disk specification" in opt:
                task_id = opt.split("'")[1]
                if task_id in workflow.tasks:
                    workflow.tasks[task_id].disk_mb.set_for_environment(4096, 'shared_filesystem')
    
    print("Selected optimizations applied successfully.") 