"""
wf2wf.workflow_analysis – Workflow Format Analysis and Classification

This module provides utilities for analyzing workflow formats and determining
their execution models (shared filesystem vs distributed computing).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FormatAnalysis:
    """Analysis results for a workflow format."""
    
    format_name: str
    execution_model: str  # shared_filesystem, distributed_computing, hybrid, unknown


@dataclass
class ContentAnalysis:
    """Analysis results for workflow content."""
    
    execution_model: str  # shared_filesystem, distributed_computing, hybrid, unknown
    confidence: float  # 0.0 to 1.0 confidence in the detection
    indicators: Dict[str, List[str]]  # Evidence for the classification
    recommendations: List[str]  # Recommendations for target environment


# Workflow format execution models
FORMAT_EXECUTION_MODELS = {
    "snakemake": "shared_filesystem",
    "dagman": "distributed_computing", 
    "nextflow": "hybrid",
    "cwl": "shared_filesystem",
    "wdl": "shared_filesystem",
    "galaxy": "shared_filesystem",
}


def detect_execution_model_from_content(file_path: Path, format_name: str) -> ContentAnalysis:
    """
    Detect execution model by analyzing workflow content.
    
    This function examines the actual content of a workflow file to determine
    if it's designed for shared filesystem or distributed computing execution.
    
    Parameters
    ----------
    file_path : Path
        Path to the workflow file
    format_name : str
        Known format of the workflow (from extension or CLI flag)
        
    Returns
    -------
    ContentAnalysis
        Analysis of the workflow's execution model characteristics
    """
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        content_lower = content.lower()
        
        indicators = {
            "shared_filesystem": [],
            "distributed_computing": [],
            "hybrid": [],
            "cloud_native": []
        }
        
        # Shared filesystem indicators
        shared_indicators = [
            # File path patterns that suggest shared storage
            ('/shared/', 'Uses shared directory paths'),
            ('/nfs/', 'Uses NFS-mounted directories'),
            ('/lustre/', 'Uses Lustre filesystem'),
            ('/gpfs/', 'Uses GPFS filesystem'),
            ('/data/', 'Uses data directory structure'),
            ('/project/', 'Uses project directory structure'),
            ('/group/', 'Uses group directory structure'),
            ('gs://', 'Uses Google Cloud Storage'),
            ('s3://', 'Uses AWS S3 storage'),
            ('azure://', 'Uses Azure storage'),
            
            # Minimal resource specifications (rely on system defaults)
            ('threads:', 'Uses minimal thread specifications'),
            ('mem_mb:', 'Uses minimal memory specifications'),
            ('resources:', 'Uses basic resource specifications'),
            
            # System-wide environment assumptions
            ('conda:', 'Uses conda environments'),
            ('container:', 'Uses container specifications'),
            ('env:', 'Uses environment variables'),
            
            # Simple file operations
            ('cp ', 'Uses simple file copy operations'),
            ('mv ', 'Uses simple file move operations'),
            ('ln ', 'Uses symbolic links'),
            
            # Basic error handling
            ('retry', 'Uses basic retry mechanisms'),
            ('error', 'Uses basic error handling'),
        ]
        
        # Distributed computing indicators
        distributed_indicators = [
            # Explicit resource specifications
            ('request_cpus', 'Explicit CPU requirements'),
            ('request_memory', 'Explicit memory requirements'),
            ('request_disk', 'Explicit disk requirements'),
            ('request_gpus', 'Explicit GPU requirements'),
            ('gpus_minimum_memory', 'GPU memory specifications'),
            ('gpus_minimum_capability', 'GPU capability requirements'),
            
            # File transfer specifications
            ('transfer_input_files', 'Explicit input file transfers'),
            ('transfer_output_files', 'Explicit output file transfers'),
            ('should_transfer_files', 'File transfer configuration'),
            ('when_to_transfer_output', 'Output transfer timing'),
            
            # Job submission and management
            ('universe =', 'Job universe specification'),
            ('executable =', 'Executable specification'),
            ('queue', 'Job queuing'),
            ('priority', 'Job priority management'),
            ('retry', 'Advanced retry policies'),
            
            # Environment isolation
            ('docker_image', 'Docker container specification'),
            ('singularity_image', 'Singularity container specification'),
            ('apptainer_image', 'Apptainer container specification'),
            
            # HPC-specific features
            ('requirements =', 'Job placement requirements'),
            ('rank =', 'Job ranking preferences'),
            ('+ClassAd', 'Custom ClassAd attributes'),
            ('+WantGPULab', 'GPU lab requirements'),
            ('+ProjectName', 'Project identification'),
        ]
        
        # Hybrid indicators (features of both)
        hybrid_indicators = [
            # Nextflow-specific patterns
            ('publishDir', 'Uses Nextflow publishDir for output staging'),
            ('stash', 'Uses Nextflow stash for file management'),
            ('stageInMode', 'Uses Nextflow stage-in modes'),
            ('stageOutMode', 'Uses Nextflow stage-out modes'),
            
            # Advanced resource management
            ('accelerator', 'Uses accelerator specifications'),
            ('resource_labels', 'Uses resource labeling'),
        ]
        
        # Cloud-native indicators
        cloud_native_indicators = [
            # Cloud storage patterns
            ('gs://', 'Uses Google Cloud Storage'),
            ('s3://', 'Uses AWS S3 storage'),
            ('azure://', 'Uses Azure storage'),
            ('https://', 'Uses HTTP/HTTPS URLs'),
            ('http://', 'Uses HTTP URLs'),
            
            # Serverless patterns
            ('lambda', 'Uses AWS Lambda functions'),
            ('cloud_function', 'Uses Google Cloud Functions'),
            ('azure_function', 'Uses Azure Functions'),
            ('serverless', 'Uses serverless computing'),
            
            # Cloud-specific resource patterns
            ('instance_type', 'Uses cloud instance types'),
            ('machine_type', 'Uses cloud machine types'),
            ('region', 'Uses cloud regions'),
            ('zone', 'Uses cloud zones'),
            ('project', 'Uses cloud projects'),
            
            # Cloud workflow patterns
            ('step_functions', 'Uses AWS Step Functions'),
            ('dataflow', 'Uses Google Dataflow'),
            ('batch', 'Uses cloud batch services'),
        ]
        
        # Check for shared filesystem indicators
        for pattern, description in shared_indicators:
            if pattern in content_lower:
                indicators["shared_filesystem"].append(description)
        
        # Check for distributed computing indicators
        for pattern, description in distributed_indicators:
            if pattern in content_lower:
                indicators["distributed_computing"].append(description)
        
        # Check for hybrid indicators
        for pattern, description in hybrid_indicators:
            if pattern in content_lower:
                indicators["hybrid"].append(description)
        
        # Check for cloud-native indicators
        for pattern, description in cloud_native_indicators:
            if pattern in content_lower:
                indicators["cloud_native"].append(description)
        
        # Determine execution model based on indicators
        shared_count = len(indicators["shared_filesystem"])
        distributed_count = len(indicators["distributed_computing"])
        hybrid_count = len(indicators["hybrid"])
        cloud_native_count = len(indicators["cloud_native"])
        
        # Calculate confidence based on indicator strength
        total_indicators = shared_count + distributed_count + hybrid_count + cloud_native_count
        
        if total_indicators == 0:
            # No clear indicators found, use format-based default
            default_model = FORMAT_EXECUTION_MODELS.get(format_name, "unknown")
            return ContentAnalysis(
                execution_model=default_model,
                confidence=0.3,  # Low confidence when using defaults
                indicators=indicators,
                recommendations=[
                    f"No clear execution model indicators found. Using format default: {default_model}",
                    "Consider adding explicit resource specifications for better detection"
                ]
            )
        
        # Determine primary model with format-specific weighting
        # For format-specific models, give extra weight to format indicators
        format_default = FORMAT_EXECUTION_MODELS.get(format_name, "unknown")
        
        # Adjust counts based on format-specific indicators
        if format_name == "nextflow" and hybrid_count > 0:
            # Nextflow with hybrid indicators should strongly favor hybrid
            hybrid_count += 3  # Give extra weight
        elif format_name == "dagman" and distributed_count > 0:
            # DAGMan with distributed indicators should strongly favor distributed
            distributed_count += 3
        elif format_name == "snakemake" and shared_count > 0:
            # Snakemake with shared indicators should strongly favor shared
            shared_count += 2
        
        # Determine primary model
        if cloud_native_count > shared_count and cloud_native_count > distributed_count and cloud_native_count > hybrid_count:
            execution_model = "cloud_native"
            confidence = min(0.9, 0.5 + (cloud_native_count / total_indicators) * 0.4)
        elif distributed_count > shared_count and distributed_count > hybrid_count and distributed_count > cloud_native_count:
            execution_model = "distributed_computing"
            confidence = min(0.9, 0.5 + (distributed_count / total_indicators) * 0.4)
        elif shared_count > distributed_count and shared_count > hybrid_count and shared_count > cloud_native_count:
            execution_model = "shared_filesystem"
            confidence = min(0.9, 0.5 + (shared_count / total_indicators) * 0.4)
        elif hybrid_count > 0:
            execution_model = "hybrid"
            confidence = min(0.8, 0.4 + (hybrid_count / total_indicators) * 0.4)
        else:
            # Tie or unclear, use format-based default
            execution_model = format_default
            confidence = 0.4
        
        # Generate recommendations
        recommendations = []
        if execution_model == "shared_filesystem":
            recommendations.extend([
                "Workflow appears designed for shared filesystem execution",
                "Consider adding explicit resource specifications for distributed environments",
                "Review file transfer requirements for distributed computing"
            ])
        elif execution_model == "distributed_computing":
            recommendations.extend([
                "Workflow appears designed for distributed computing",
                "Resource specifications are well-defined",
                "File transfer mechanisms are explicitly configured"
            ])
        elif execution_model == "hybrid":
            recommendations.extend([
                "Workflow shows characteristics of both shared and distributed execution",
                "May require careful configuration for target environment",
                "Review both resource and file transfer specifications"
            ])
        elif execution_model == "cloud_native":
            recommendations.extend([
                "Workflow appears designed for cloud-native execution",
                "Uses cloud storage and/or serverless computing",
                "Consider cloud-specific optimizations and cost management"
            ])
        
        return ContentAnalysis(
            execution_model=execution_model,
            confidence=confidence,
            indicators=indicators,
            recommendations=recommendations
        )
        
    except (UnicodeDecodeError, IOError, OSError) as e:
        # File is binary or unreadable
        default_model = FORMAT_EXECUTION_MODELS.get(format_name, "unknown")
        return ContentAnalysis(
            execution_model=default_model,
            confidence=0.1,  # Very low confidence for unreadable files
            indicators={},
            recommendations=[
                f"Could not read file content: {e}",
                f"Using format-based default: {default_model}"
            ]
        )


def analyze_workflow_format(format_name: str) -> FormatAnalysis:
    """
    Analyze a workflow format and return its execution model.
    
    Parameters
    ----------
    format_name : str
        Name of the workflow format (snakemake, dagman, nextflow, etc.)
        
    Returns
    -------
    FormatAnalysis
        Analysis of the workflow format
    """
    execution_model = FORMAT_EXECUTION_MODELS.get(format_name, "unknown")
    
    return FormatAnalysis(
        format_name=format_name,
        execution_model=execution_model
    )


def get_file_transfer_recommendations(source_format: str, target_format: str) -> Dict[str, Any]:
    """
    Get file transfer recommendations for converting between formats.
    
    Parameters
    ----------
    source_format : str
        Source workflow format
    target_format : str
        Target workflow format
        
    Returns
    -------
    Dict[str, Any]
        Transfer recommendations and warnings
    """
    source_analysis = analyze_workflow_format(source_format)
    target_analysis = analyze_workflow_format(target_format)
    
    recommendations = {
        "source_model": source_analysis.execution_model,
        "target_model": target_analysis.execution_model,
        "transfer_changes_needed": False,
        "recommendations": [],
        "warnings": [],
    }
    
    # Check if transfer behavior needs to change
    if (source_analysis.execution_model == "shared_filesystem" and 
        target_analysis.execution_model == "distributed_computing"):
        recommendations["transfer_changes_needed"] = True
        recommendations["recommendations"].append(
            "Source assumes shared filesystem, target requires explicit file transfers"
        )
        recommendations["warnings"].append(
            "Files must be explicitly transferred in distributed computing environment"
        )
    
    return recommendations


def enhance_file_transfer_detection(file_paths: List[str], source_format: str, target_format: str) -> Dict[str, str]:
    """
    Enhanced file transfer mode detection based on format characteristics.
    
    Parameters
    ----------
    file_paths : List[str]
        List of file paths to analyze
    source_format : str
        Source workflow format
    target_format : str
        Target workflow format
        
    Returns
    -------
    Dict[str, str]
        Mapping of file paths to transfer modes
    """
    transfer_modes = {}
    recommendations = get_file_transfer_recommendations(source_format, target_format)
    
    for file_path in file_paths:
        path_lower = file_path.lower()
        
        # Enhanced pattern matching based on format characteristics
        if any(pattern in path_lower for pattern in [
            '/nfs/', '/mnt/', '/shared/', '/data/', '/storage/',
            '/lustre/', '/gpfs/', '/beegfs/', '/ceph/',
            'gs://', 's3://', 'azure://', 'http://', 'https://', 'ftp://',
            '/scratch/', '/work/', '/project/', '/group/',
        ]):
            transfer_modes[file_path] = "shared"
        elif any(pattern in path_lower for pattern in [
            '/tmp/', '/var/tmp/', '.tmp', 'temp_', 'tmp_',
            '/dev/', '/proc/', '/sys/',
            '.log', '.err', '.out',
        ]):
            transfer_modes[file_path] = "never"
        elif any(ext in path_lower for ext in [
            '.genome', '.fa', '.fasta', '.fna', '.faa',
            '.gtf', '.gff', '.gff3', '.bed', '.sam', '.bam',
            '.idx', '.index', '.dict',
        ]):
            # Reference data - check if we're moving to distributed computing
            if recommendations["transfer_changes_needed"]:
                transfer_modes[file_path] = "shared"
            else:
                transfer_modes[file_path] = "auto"
        else:
            # Regular files - check format requirements
            if recommendations["transfer_changes_needed"]:
                transfer_modes[file_path] = "auto"
            else:
                transfer_modes[file_path] = "auto"
    
    return transfer_modes 


def create_execution_model_spec(
    format_name: str,
    content_analysis: Optional[ContentAnalysis] = None,
    user_specified_model: Optional[str] = None
) -> "ExecutionModelSpec":
    """
    Create a detailed ExecutionModelSpec based on format and content analysis.
    
    Parameters
    ----------
    format_name : str
        The workflow format name
    content_analysis : Optional[ContentAnalysis]
        Results from content-based analysis
    user_specified_model : Optional[str]
        User-specified execution model
        
    Returns
    -------
    ExecutionModelSpec
        Detailed execution model specification
    """
    from wf2wf.core import ExecutionModelSpec
    
    # Determine the base model
    if user_specified_model:
        model = user_specified_model
        detection_method = "user_specified"
        detection_confidence = 1.0
    elif content_analysis:
        model = content_analysis.execution_model
        detection_method = "content"
        detection_confidence = content_analysis.confidence
    else:
        model = FORMAT_EXECUTION_MODELS.get(format_name, "unknown")
        detection_method = "extension"
        detection_confidence = 0.8
    
    # Set format-specific characteristics
    spec = ExecutionModelSpec(
        model=model,
        source_format=format_name,
        detection_method=detection_method
    )
    
    # Set execution environment characteristics based on model
    if model == "shared_filesystem":
        spec.filesystem_type = "shared"
        spec.resource_management = "implicit"
        spec.environment_isolation = "none"
        spec.file_transfer_mode = "none"
        spec.requires_file_transfer = False
        spec.requires_resource_specification = False
        spec.requires_environment_isolation = False
        spec.requires_error_handling = False
        
    elif model == "distributed_computing":
        spec.filesystem_type = "distributed"
        spec.resource_management = "explicit"
        spec.environment_isolation = "container"
        spec.file_transfer_mode = "manual"
        spec.requires_file_transfer = True
        spec.requires_resource_specification = True
        spec.requires_environment_isolation = True
        spec.requires_error_handling = True
        
    elif model == "hybrid":
        spec.filesystem_type = "hybrid"
        spec.resource_management = "dynamic"
        spec.environment_isolation = "container"
        spec.file_transfer_mode = "automatic"
        spec.requires_file_transfer = True
        spec.requires_resource_specification = True
        spec.requires_environment_isolation = True
        spec.requires_error_handling = True
        
    elif model == "cloud_native":
        spec.filesystem_type = "cloud_storage"
        spec.resource_management = "cloud_managed"
        spec.environment_isolation = "cloud_runtime"
        spec.file_transfer_mode = "cloud_storage"
        spec.requires_file_transfer = True
        spec.requires_resource_specification = True
        spec.requires_environment_isolation = True
        spec.requires_error_handling = True
    
    # Add detection indicators if available
    if content_analysis and content_analysis.indicators:
        for model_type, indicators in content_analysis.indicators.items():
            if indicators:
                spec.detection_indicators.extend(indicators)
    
    return spec


def analyze_execution_model_transition(
    source_spec: "ExecutionModelSpec",
    target_format: str
) -> Dict[str, Any]:
    """
    Analyze what changes are needed when transitioning between execution models.
    
    Parameters
    ----------
    source_spec : ExecutionModelSpec
        Source execution model specification
    target_format : str
        Target workflow format
        
    Returns
    -------
    Dict[str, Any]
        Analysis of required changes and potential issues
    """
    target_model = FORMAT_EXECUTION_MODELS.get(target_format, "unknown")
    
    analysis = {
        "source_model": source_spec.model,
        "target_model": target_model,
        "transition_type": f"{source_spec.model}_to_{target_model}",
        "required_changes": [],
        "potential_issues": [],
        "recommendations": []
    }
    
    # Analyze filesystem type changes
    if source_spec.filesystem_type != "distributed" and target_model == "distributed_computing":
        analysis["required_changes"].append("file_transfer_specification")
        analysis["required_changes"].append("resource_specification")
        analysis["potential_issues"].append("File paths may need transfer configuration")
        analysis["recommendations"].append("Review all file inputs/outputs for transfer requirements")
    
    # Analyze resource management changes
    if source_spec.resource_management == "implicit" and target_model == "distributed_computing":
        analysis["required_changes"].append("explicit_resource_specification")
        analysis["potential_issues"].append("Tasks may fail due to insufficient resources")
        analysis["recommendations"].append("Add explicit CPU, memory, and disk requirements")
    
    # Analyze environment isolation changes
    if source_spec.environment_isolation == "none" and target_model == "distributed_computing":
        analysis["required_changes"].append("environment_isolation")
        analysis["potential_issues"].append("Software dependencies may not be available")
        analysis["recommendations"].append("Specify container images or conda environments")
    
    # Analyze error handling changes
    if source_spec.requires_error_handling == False and target_model == "distributed_computing":
        analysis["required_changes"].append("error_handling_specification")
        analysis["potential_issues"].append("Failed jobs may not be retried")
        analysis["recommendations"].append("Add retry policies and failure handling")
    
    return analysis 