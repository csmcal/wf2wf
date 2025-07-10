"""
Tests for wf2wf.resource_utils module.

This module tests resource inference, normalization, validation, and profile management.
"""

import pytest
import tempfile
import json
from pathlib import Path
from wf2wf.resource_utils import (
    DEFAULT_PROFILES,
    normalize_memory,
    normalize_time,
    infer_resources_from_command,
    apply_resource_profile,
    validate_resources,
    suggest_resource_profile,
    load_custom_profile,
    save_custom_profile,
    get_available_profiles,
    create_profile_from_existing,
    ResourceProfile,
)
from wf2wf.core import Task, EnvironmentSpecificValue


class TestResourceProfiles:
    """Test resource profile functionality."""
    
    def test_default_profiles_exist(self):
        """Test that all expected default profiles exist."""
        expected_profiles = [
            "shared", "cluster", "cloud", "hpc", "gpu", 
            "memory_intensive", "io_intensive"
        ]
        
        available = get_available_profiles()
        for profile_name in expected_profiles:
            assert profile_name in available
            assert isinstance(available[profile_name], ResourceProfile)
    
    def test_cluster_profile_values(self):
        """Test cluster profile has expected values."""
        cluster = DEFAULT_PROFILES["cluster"]
        assert cluster.name == "cluster"
        assert cluster.description == "HTCondor/SGE cluster environment"
        assert cluster.environment == "cluster"
        assert cluster.priority == "normal"
        assert cluster.cpu == 1
        assert cluster.mem_mb == 2048  # 2GB
        assert cluster.disk_mb == 4096  # 4GB

    def test_gpu_profile_values(self):
        """Test GPU profile has expected values."""
        gpu = DEFAULT_PROFILES["gpu"]
        assert gpu.name == "gpu"
        assert gpu.description == "GPU-enabled environment"
        assert gpu.environment == "gpu"
        assert gpu.priority == "high"
        assert gpu.cpu == 4
        assert gpu.mem_mb == 16384  # 16GB
        assert gpu.disk_mb == 32768  # 32GB
        assert gpu.gpu == 1
        assert gpu.gpu_mem_mb == 8192  # 8GB GPU memory


class TestMemoryNormalization:
    """Test memory value normalization."""
    
    def test_plain_numbers(self):
        """Test plain number values."""
        assert normalize_memory(1024) == 1024
        assert normalize_memory(2048.5) == 2048
    
    def test_kb_units(self):
        """Test KB unit conversion."""
        assert normalize_memory("1024KB") == 1
        assert normalize_memory("2048 KB") == 2
        assert normalize_memory("1.5KB") == 0  # 1.5/1024 = 0.001 -> 0 when converted to int
    
    def test_mb_units(self):
        """Test MB unit conversion."""
        assert normalize_memory("1024MB") == 1024
        assert normalize_memory("2 MB") == 2
        assert normalize_memory("1.5MB") == 1
    
    def test_gb_units(self):
        """Test GB unit conversion."""
        assert normalize_memory("1GB") == 1024
        assert normalize_memory("2.5 GB") == 2560
        assert normalize_memory("0.5GB") == 512
    
    def test_tb_units(self):
        """Test TB unit conversion."""
        assert normalize_memory("1TB") == 1024 * 1024
        assert normalize_memory("0.5 TB") == 512 * 1024
    
    def test_short_units(self):
        """Test short unit notation."""
        assert normalize_memory("1G") == 1024
        assert normalize_memory("2M") == 2
        assert normalize_memory("1024K") == 1
    
    def test_invalid_values(self):
        """Test invalid memory values raise errors."""
        with pytest.raises(ValueError):
            normalize_memory("invalid")
        with pytest.raises(ValueError):
            normalize_memory("1PB")  # Unsupported unit


class TestTimeNormalization:
    """Test time value normalization."""
    
    def test_plain_numbers(self):
        """Test plain number values."""
        assert normalize_time(3600) == 3600
        assert normalize_time(1800.5) == 1800
    
    def test_seconds(self):
        """Test seconds unit conversion."""
        assert normalize_time("60s") == 60
        assert normalize_time("30 sec") == 30
        assert normalize_time("45 seconds") == 45
    
    def test_minutes(self):
        """Test minutes unit conversion."""
        assert normalize_time("60m") == 3600
        assert normalize_time("30 min") == 1800
        assert normalize_time("45 minutes") == 2700
    
    def test_hours(self):
        """Test hours unit conversion."""
        assert normalize_time("1h") == 3600
        assert normalize_time("2.5 hours") == 9000
        assert normalize_time("0.5h") == 1800
    
    def test_days(self):
        """Test days unit conversion."""
        assert normalize_time("1d") == 86400
        assert normalize_time("0.5 days") == 43200
    
    def test_invalid_values(self):
        """Test invalid time values raise errors."""
        with pytest.raises(ValueError):
            normalize_time("invalid")
        with pytest.raises(ValueError):
            normalize_time("1w")  # Unsupported unit


class TestResourceInference:
    """Test resource inference from commands."""
    
    def test_bwa_command(self):
        """Test BWA command inference."""
        resources = infer_resources_from_command(EnvironmentSpecificValue("bwa mem -t 4 input.fq output.bam", ["shared_filesystem"]))
        assert resources["cpu"] == 4
        assert resources["mem_mb"] == 4096  # 4GB for alignment tools
        assert resources["disk_mb"] == 8192  # 8GB for sequence data
    
    def test_gatk_command(self):
        """Test GATK command inference."""
        resources = infer_resources_from_command(EnvironmentSpecificValue("gatk HaplotypeCaller -I input.bam -O output.vcf", ["shared_filesystem"]))
        assert resources["cpu"] == 2
        assert resources["mem_mb"] == 8192  # 8GB
        assert resources["disk_mb"] == 4096  # 4GB for variant data
    
    def test_gpu_command(self):
        """Test GPU command inference."""
        resources = infer_resources_from_command(EnvironmentSpecificValue("python train_model.py --gpu --cuda", ["shared_filesystem"]))
        assert resources["gpu"] == 1
        assert resources["gpu_mem_mb"] == 4096  # 4GB GPU memory
        assert resources["cpu"] == 1
    
    def test_simple_command(self):
        """Test simple command inference."""
        resources = infer_resources_from_command(EnvironmentSpecificValue("echo 'hello world'", ["shared_filesystem"]))
        assert resources["cpu"] == 1
    
    def test_empty_command(self):
        """Test empty command returns default resources."""
        resources = infer_resources_from_command(EnvironmentSpecificValue("", ["shared_filesystem"]))
        assert resources["cpu"] == 1
        assert resources["threads"] == 1
    
    def test_script_inference(self):
        """Test resource inference from script content."""
        script = """
        #!/bin/bash
        samtools view -h input.bam | head -1000 > output.sam
        """
        resources = infer_resources_from_command(EnvironmentSpecificValue(script, ["shared_filesystem"]))
        assert resources["cpu"] == 1
        assert resources["mem_mb"] == 2048  # 2GB for samtools
        assert resources["disk_mb"] == 8192  # 8GB for sequence data


class TestResourceProfileApplication:
    """Test resource profile application."""
    
    def test_apply_cluster_profile(self):
        """Test applying cluster profile to task."""
        task = Task(id="test_task")
        cluster_profile = DEFAULT_PROFILES["cluster"]
        
        apply_resource_profile(task, cluster_profile)
        
        assert task.cpu.get_value_with_default("cluster") == 1
        assert task.mem_mb.get_value_with_default("cluster") == 2048
        assert task.disk_mb.get_value_with_default("cluster") == 4096
    
    def test_apply_profile_preserves_existing(self):
        """Test that applying profile preserves existing values."""
        task = Task(id="test_task")
        task.cpu.set_for_environment(8, "shared_filesystem")
        
        cluster_profile = DEFAULT_PROFILES["cluster"]
        apply_resource_profile(task, cluster_profile)
        
        # Should preserve existing value
        assert task.cpu.get_value_with_default("shared_filesystem") == 8
        # Should add cluster value
        assert task.cpu.get_value_with_default("cluster") == 1
    
    def test_apply_gpu_profile(self):
        """Test applying GPU profile to task."""
        task = Task(id="test_task")
        gpu_profile = DEFAULT_PROFILES["gpu"]
        
        apply_resource_profile(task, gpu_profile)
        
        assert task.cpu.get_value_with_default("gpu") == 4
        assert task.mem_mb.get_value_with_default("gpu") == 16384
        assert task.gpu.get_value_with_default("gpu") == 1
        assert task.gpu_mem_mb.get_value_with_default("gpu") == 8192
    
    def test_invalid_profile(self):
        """Test applying invalid profile raises error."""
        task = Task(id="test_task")
        with pytest.raises(AttributeError):
            apply_resource_profile(task, "invalid_profile")


class TestResourceValidation:
    """Test resource validation."""
    
    def test_valid_resources(self):
        """Test that valid resources pass validation."""
        task = Task(id="test_task")
        task.cpu.set_for_environment(2, "shared_filesystem")
        task.mem_mb.set_for_environment(4096, "shared_filesystem")
        task.disk_mb.set_for_environment(8192, "shared_filesystem")
        
        issues = validate_resources(task, "shared_filesystem")
        assert not issues
    
    def test_excessive_cpu(self):
        """Test validation catches excessive CPU."""
        task = Task(id="test_task")
        task.cpu.set_for_environment(100, "shared_filesystem")
        task.mem_mb.set_for_environment(4096, "shared_filesystem")
        
        issues = validate_resources(task, "shared_filesystem")
        assert any("excessive" in issue.lower() for issue in issues)
    
    def test_cluster_limits(self):
        """Test cluster environment limits."""
        task = Task(id="test_task")
        task.cpu.set_for_environment(64, "cluster")
        task.mem_mb.set_for_environment(131072, "cluster")  # 128GB
        
        issues = validate_resources(task, "cluster")
        assert any("cluster" in issue.lower() for issue in issues)
    
    def test_shared_environment_limits(self):
        """Test shared filesystem environment limits."""
        task = Task(id="test_task")
        task.cpu.set_for_environment(8, "shared_filesystem")
        task.mem_mb.set_for_environment(16384, "shared_filesystem")  # 16GB
        issues = validate_resources(task, "shared_filesystem")
        print("Shared env limit issues:", issues)
        # Accept either 'shared' or 'filesystem' in the error message
        assert any("shared" in issue.lower() or "filesystem" in issue.lower() for issue in issues)


class TestProfileSuggestion:
    """Test resource profile suggestion."""
    
    def test_gpu_suggestion(self):
        """Test GPU profile suggestion."""
        task = Task(id="test_task")
        task.gpu.set_for_environment(1, "shared_filesystem")
        
        suggested = suggest_resource_profile(task, "shared_filesystem")
        assert suggested == "gpu"
    
    def test_memory_intensive_suggestion(self):
        """Test memory intensive profile suggestion."""
        task = Task(id="test_task")
        task.mem_mb.set_for_environment(65536, "shared_filesystem")  # 64GB
        
        suggested = suggest_resource_profile(task, "shared_filesystem")
        assert suggested == "memory_intensive"
    
    def test_io_intensive_suggestion(self):
        """Test I/O intensive profile suggestion."""
        task = Task(id="test_task")
        task.disk_mb.set_for_environment(131072, "shared_filesystem")  # 128GB
        
        suggested = suggest_resource_profile(task, "shared_filesystem")
        assert suggested == "io_intensive"
    
    def test_environment_based_suggestion(self):
        """Test environment-based profile suggestion."""
        task = Task(id="test_task")
        task.cpu.set_for_environment(2, "cloud")
        
        suggested = suggest_resource_profile(task, "cloud")
        assert suggested == "cloud"
        
        suggested = suggest_resource_profile(task, "cluster")
        assert suggested == "cluster"


class TestProfileCreation:
    """Test profile creation from existing resources."""
    
    def test_create_profile_from_task(self):
        """Test creating profile from existing task."""
        task = Task(id="test_task")
        task.cpu.set_for_environment(4, "shared_filesystem")
        task.mem_mb.set_for_environment(8192, "shared_filesystem")
        task.disk_mb.set_for_environment(16384, "shared_filesystem")
        task.gpu.set_for_environment(1, "shared_filesystem")
        profile = create_profile_from_existing(task, "test_profile", "Test profile")
        print("Created profile:", profile)
        assert profile.name == "test_profile"
        assert profile.description == "Test profile"
        assert profile.cpu == 4
        assert profile.mem_mb == 8192
        assert profile.disk_mb == 16384
        assert profile.gpu == 1


class TestProfileSerialization:
    """Test profile loading and saving."""
    
    def test_save_and_load_profile(self):
        """Test saving and loading a custom profile."""
        profile = ResourceProfile(
            name="test_profile",
            description="Test profile",
            environment="shared_filesystem",
            priority="normal",
            cpu=4,
            mem_mb=8192,
            disk_mb=16384,
            gpu=1,
            gpu_mem_mb=4096
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            profile_path = Path(f.name)
        
        try:
            save_custom_profile(profile, profile_path)
            loaded_profile = load_custom_profile(profile_path)
            
            assert loaded_profile.name == profile.name
            assert loaded_profile.description == profile.description
            assert loaded_profile.cpu == profile.cpu
            assert loaded_profile.mem_mb == profile.mem_mb
            assert loaded_profile.gpu == profile.gpu
        finally:
            profile_path.unlink(missing_ok=True)


class TestIntegration:
    """Test integration scenarios."""
    
    def test_full_workflow_processing(self):
        """Test complete workflow resource processing."""
        # Create task with inferred resources
        resources = infer_resources_from_command(EnvironmentSpecificValue("bwa mem -t 4 input.fq output.bam", ["shared_filesystem"]))
        task = Task(id="bwa_task")
        task.cpu.set_for_environment(resources["cpu"], "shared_filesystem")
        task.mem_mb.set_for_environment(resources["mem_mb"], "shared_filesystem")
        task.disk_mb.set_for_environment(resources["disk_mb"], "shared_filesystem")
        # Validate resources
        issues = validate_resources(task, "shared_filesystem")
        assert not issues
        # Suggest profile
        suggested = suggest_resource_profile(task, "shared_filesystem")
        print("Suggested profile:", suggested)
        assert suggested in ["hpc", "cluster", "shared"]
    
    def test_inference_and_profile_combination(self):
        """Test combining inference with profile application."""
        # Infer resources from command
        resources = infer_resources_from_command(EnvironmentSpecificValue("gatk HaplotypeCaller -I input.bam -O output.vcf", ["shared_filesystem"]))
        
        # Create task
        task = Task(id="gatk_task")
        task.cpu.set_for_environment(resources["cpu"], "shared_filesystem")
        task.mem_mb.set_for_environment(resources["mem_mb"], "shared_filesystem")
        
        # Apply cluster profile to fill missing values
        cluster_profile = DEFAULT_PROFILES["cluster"]
        apply_resource_profile(task, cluster_profile)
        
        # Should have both inferred and profile values
        assert task.cpu.get_value_with_default("shared_filesystem") == 2  # inferred
        assert task.cpu.get_value_with_default("cluster") == 1  # profile
        assert task.mem_mb.get_value_with_default("shared_filesystem") == 8192  # inferred
        assert task.mem_mb.get_value_with_default("cluster") == 2048  # profile
