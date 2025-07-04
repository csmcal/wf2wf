"""
Tests for wf2wf.resource_utils module.

This module tests resource inference, normalization, validation, and profile management.
"""

import pytest
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
    ResourceSpec,  # Use ResourceSpec for resources
    ResourceProfile,  # Use ResourceProfile for profiles
)


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
        assert cluster.resources.cpu == 1
        assert cluster.resources.mem_mb == 2048  # 2GB
        assert cluster.resources.disk_mb == 4096  # 4GB

    def test_gpu_profile_values(self):
        """Test GPU profile has expected values."""
        gpu = DEFAULT_PROFILES["gpu"]
        assert gpu.name == "gpu"
        assert gpu.description == "GPU-enabled environment"
        assert gpu.environment == "hpc"
        assert gpu.priority == "high"
        assert gpu.resources.cpu == 4
        assert gpu.resources.mem_mb == 16384  # 16GB
        assert gpu.resources.disk_mb == 32768  # 32GB
        assert gpu.resources.gpu == 1
        assert gpu.resources.gpu_mem_mb == 8192  # 8GB GPU memory
        # No environment field on ResourceSpec


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
        resources = infer_resources_from_command("bwa mem -t 4 input.fq output.bam")
        assert resources.cpu == 4
        assert resources.mem_mb == 2048  # 2GB
        assert resources.disk_mb == 4096  # 4GB for sequence data
    
    def test_gatk_command(self):
        """Test GATK command inference."""
        resources = infer_resources_from_command("gatk HaplotypeCaller -I input.bam -O output.vcf")
        assert resources.cpu == 2
        assert resources.mem_mb == 8192  # 8GB
        assert resources.disk_mb == 4096  # 4GB for sequence data
    
    def test_gpu_command(self):
        """Test GPU command inference."""
        resources = infer_resources_from_command("python train_model.py --gpu --cuda")
        assert resources.gpu == 1
        assert resources.gpu_mem_mb == 4096  # 4GB GPU memory
        assert resources.cpu == 1
    
    def test_simple_command(self):
        """Test simple command inference."""
        resources = infer_resources_from_command("echo 'hello world'")
        assert resources.cpu == 1
    
    def test_empty_command(self):
        """Test empty command returns default resources."""
        resources = infer_resources_from_command("")
        assert resources.cpu == 1
        assert resources.mem_mb is None  # Not specified for empty command
        assert resources.threads == 1
    
    def test_script_inference(self):
        """Test resource inference from script content."""
        script = """
        #!/bin/bash
        samtools view -h input.bam | head -1000 > output.sam
        """
        resources = infer_resources_from_command("", script)
        assert resources.cpu == 1
        assert resources.mem_mb == 2048  # 2GB for samtools
        assert resources.disk_mb == 4096  # 4GB for sequence data


class TestResourceProfileApplication:
    """Test resource profile application."""
    
    def test_apply_cluster_profile(self):
        """Test applying cluster profile to empty resources."""
        resources = ResourceSpec()
        result = apply_resource_profile(resources, "cluster")

        assert result.cpu == 1
        assert result.mem_mb == 2048
        assert result.disk_mb == 4096
    
    def test_apply_profile_preserves_existing(self):
        """Test that existing resource values are preserved."""
        resources = ResourceSpec(cpu=4, mem_mb=8192)
        result = apply_resource_profile(resources, "cluster")
        
        assert result.cpu == 4  # Preserved
        assert result.mem_mb == 8192  # Preserved
        assert result.disk_mb == 4096  # Filled from profile
    
    def test_apply_gpu_profile(self):
        """Test applying GPU profile."""
        resources = ResourceSpec()  # All fields are None
        result = apply_resource_profile(resources, "gpu")

        # Should use profile values since input has None values
        assert result.cpu == 4  # From GPU profile
        assert result.mem_mb == 16384  # From GPU profile
        assert result.disk_mb == 32768  # From GPU profile
        assert result.gpu == 1  # From GPU profile
        assert result.gpu_mem_mb == 8192  # From GPU profile
    
    def test_invalid_profile(self):
        """Test that invalid profile names raise errors."""
        resources = ResourceSpec()
        with pytest.raises(ValueError):
            apply_resource_profile(resources, "nonexistent")


class TestResourceValidation:
    """Test resource validation."""
    
    def test_valid_resources(self):
        """Test that valid resources pass validation."""
        resources = ResourceSpec(
            cpu=4,
            mem_mb=8192,
            disk_mb=16384,
            time_s=14400
        )
        
        issues = validate_resources(resources, "cluster")
        assert len(issues) == 0
    
    def test_missing_cpu(self):
        """Test validation catches missing CPU."""
        resources = ResourceSpec(cpu=None)
        issues = validate_resources(resources, "cluster")
        assert "Missing CPU specification" in issues
    
    def test_missing_memory(self):
        """Test validation catches missing memory."""
        resources = ResourceSpec(mem_mb=None)
        issues = validate_resources(resources, "cluster")
        assert "Missing memory specification" in issues
    
    def test_excessive_cpu(self):
        """Test validation catches excessive CPU."""
        resources = ResourceSpec(cpu=100)
        issues = validate_resources(resources, "cluster")
        
        assert any("unusually high" in issue for issue in issues)
    
    def test_cluster_limits(self):
        """Test cluster-specific validation."""
        resources = ResourceSpec(cpu=64, mem_mb=1024 * 128)  # 128GB
        issues = validate_resources(resources, "cluster")
        
        assert any("may exceed cluster limits" in issue for issue in issues)
    
    def test_shared_environment_limits(self):
        """Test shared environment validation."""
        resources = ResourceSpec(cpu=16, mem_mb=1024 * 32)  # 32GB
        issues = validate_resources(resources, "shared")
        
        assert any("may impact shared system performance" in issue for issue in issues)


class TestProfileSuggestion:
    """Test resource profile suggestion."""
    
    def test_gpu_suggestion(self):
        """Test GPU profile suggestion."""
        resources = ResourceSpec(gpu=1)
        suggested = suggest_resource_profile(resources, "cluster")
        assert suggested == "gpu"
    
    def test_memory_intensive_suggestion(self):
        """Test memory-intensive profile suggestion."""
        resources = ResourceSpec(mem_mb=32768)  # 32GB
        suggested = suggest_resource_profile(resources, "cluster")
        assert suggested == "memory_intensive"
    
    def test_io_intensive_suggestion(self):
        """Test I/O-intensive profile suggestion."""
        resources = ResourceSpec(disk_mb=65536)  # 64GB
        suggested = suggest_resource_profile(resources, "cluster")
        assert suggested == "io_intensive"
    
    def test_environment_based_suggestion(self):
        """Test environment-based profile suggestion."""
        resources = ResourceSpec()
        
        # Test different environments
        assert suggest_resource_profile(resources, "hpc") == "hpc"
        assert suggest_resource_profile(resources, "cloud") == "cloud"
        assert suggest_resource_profile(resources, "cluster") == "cluster"
        assert suggest_resource_profile(resources, "shared") == "shared"


class TestProfileCreation:
    """Test profile creation from existing resources."""
    
    def test_create_profile_from_resources(self):
        """Test creating a profile from existing resources."""
        resources = ResourceSpec(
            cpu=8,
            mem_mb=16384,
            disk_mb=32768,
            time_s=28800,
            gpu=2,
            gpu_mem_mb=16384
        )

        profile = create_profile_from_existing(resources, "custom", "Custom profile")

        assert profile.name == "custom"
        assert profile.description == "Custom profile"
        assert profile.resources.cpu == 8
        assert profile.resources.mem_mb == 16384
        assert profile.resources.disk_mb == 32768
        assert profile.resources.time_s == 28800
        assert profile.resources.gpu == 2
        assert profile.resources.gpu_mem_mb == 16384


class TestIntegration:
    """Integration tests for resource utilities."""
    
    def test_full_workflow_processing(self):
        """Test complete resource processing workflow."""
        resources = ResourceSpec()
        
        # Apply cluster profile
        resources = apply_resource_profile(resources, "cluster")
        
        # Validate
        issues = validate_resources(resources, "cluster")
        assert len(issues) == 0
        
        # Suggest profile
        suggested = suggest_resource_profile(resources, "cluster")
        assert suggested == "cluster"
    
    def test_inference_and_profile_combination(self):
        """Test combining inference with profile application."""
        inferred = infer_resources_from_command("bwa mem -t 4 input.fq output.bam")

        # Apply profile to fill missing values
        result = apply_resource_profile(inferred, "cluster")

        # Should have inferred values plus profile defaults
        assert result.cpu == 4  # From inference
        assert result.mem_mb == 2048  # From inference
        assert result.disk_mb == 4096  # From inference
        # GPU should be None (not inferred, not in cluster profile)
        assert result.gpu is None
