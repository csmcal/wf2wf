#!/usr/bin/env python3
"""
Test multi-environment functionality in importers and exporters.
"""

import tempfile
import os
from pathlib import Path
from wf2wf.importers.snakemake import to_workflow
from wf2wf.exporters.dagman import from_workflow
from wf2wf.exporters.cwl import from_workflow as cwl_from_workflow
from wf2wf.core import EnvironmentAdapter


def create_test_snakefile():
    """Create a test Snakefile with multi-environment features."""
    snakefile_content = """
# Test Snakefile with multi-environment features
rule analyze_data:
    input: "data/input.txt"
    output: "results/analysis.txt"
    resources:
        mem_mb: 8192
        cpus: 4
        gpu: 1
        time_min: 60
    conda: "envs/analysis.yaml"
    retries: 3
    shell: "python analyze.py {input} {output}"

rule preprocess:
    input: "raw/data.txt"
    output: "data/input.txt"
    resources:
        mem_mb: 4096
        cpus: 2
    container: "docker://python:3.9"
    shell: "python preprocess.py {input} {output}"
"""
    return snakefile_content


def test_multi_environment_import():
    """Test that Snakemake importer creates multi-environment specifications."""
    print("Testing multi-environment import...")
    
    # Create temporary Snakefile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.smk', delete=False) as f:
        f.write(create_test_snakefile())
        snakefile_path = f.name
    
    try:
        # Import workflow
        workflow = to_workflow(snakefile_path, parse_only=True, verbose=True)
        
        # Check that multi-environment fields are populated
        for task_id, task in workflow.tasks.items():
            print(f"\nTask: {task_id}")
            
            # Check multi-environment resources
            if hasattr(task, 'multi_env_resources') and task.multi_env_resources:
                print(f"  Multi-environment resources: ✓")
                
                # Check shared environment (should have minimal resources)
                shared_cpu = task.cpu.get_value_for("shared") if hasattr(task, "cpu") else None
                shared_mem = task.mem_mb.get_value_for("shared") if hasattr(task, "mem_mb") else None
                print(f"    Shared environment - CPU: {shared_cpu}, Memory: {shared_mem}")
                
                # Check distributed environment (should have full resources)
                distributed_cpu = task.cpu.get_value_for("distributed") if hasattr(task, "cpu") else None
                distributed_mem = task.mem_mb.get_value_for("distributed") if hasattr(task, "mem_mb") else None
                print(f"    Distributed environment - CPU: {distributed_cpu}, Memory: {distributed_mem}")
                
                # Check cloud environment (should have full resources)
                cloud_cpu = task.cpu.get_value_for("cloud") if hasattr(task, "cpu") else None
                cloud_mem = task.mem_mb.get_value_for("cloud") if hasattr(task, "mem_mb") else None
                print(f"    Cloud environment - CPU: {cloud_cpu}, Memory: {cloud_mem}")
            else:
                print(f"  Multi-environment resources: ✗")
            
            # Check multi-environment file transfer
            if hasattr(task, 'multi_env_file_transfer') and task.multi_env_file_transfer:
                print(f"  Multi-environment file transfer: ✓")
            else:
                print(f"  Multi-environment file transfer: ✗")
            
            # Check multi-environment error handling
            if hasattr(task, 'multi_env_error_handling') and task.multi_env_error_handling:
                print(f"  Multi-environment error handling: ✓")
                
                # Check retry counts for different environments
                shared_error = task.multi_env_error_handling.get_for_environment("shared")
                distributed_error = task.multi_env_error_handling.get_for_environment("distributed")
                print(f"    Shared retry count: {shared_error.retry_count}")
                print(f"    Distributed retry count: {distributed_error.retry_count}")
            else:
                print(f"  Multi-environment error handling: ✗")
        
        return workflow
        
    finally:
        # Clean up
        os.unlink(snakefile_path)


def test_multi_environment_adaptation():
    """Test environment adaptation functionality."""
    print("\nTesting multi-environment adaptation...")
    
    workflow = test_multi_environment_import()
    
    # Create environment adapter
    adapter = EnvironmentAdapter(workflow)
    
    # Test adaptation for different environments
    environments = ["shared", "distributed", "cloud"]
    
    for env in environments:
        print(f"\nAdapting for {env} environment:")
        adapted_workflow = adapter.adapt_for_environment(env)
        
        for task_id, task in adapted_workflow.tasks.items():
            print(f"  {task_id}:")
            cpu = task.cpu.get_value_for(env) if hasattr(task, "cpu") else None
            mem = task.mem_mb.get_value_for(env) if hasattr(task, "mem_mb") else None
            retry = task.retry_count.get_value_for(env) if hasattr(task, "retry_count") else None
            print(f"    CPU: {cpu}")
            print(f"    Memory: {mem}")
            print(f"    Retry: {retry}")


def test_multi_environment_export():
    """Test that exporters use multi-environment specifications."""
    print("\nTesting multi-environment export...")
    
    workflow = test_multi_environment_import()
    
    # Test DAGMan export
    print("\nTesting DAGMan export...")
    with tempfile.TemporaryDirectory() as temp_dir:
        dag_path = Path(temp_dir) / "workflow.dag"
        from_workflow(workflow, dag_path, verbose=True)
        
        # Check that DAG file was created
        if dag_path.exists():
            print(f"  DAG file created: ✓")
            print(f"  DAG file size: {dag_path.stat().st_size} bytes")
        else:
            print(f"  DAG file created: ✗")
    
    # Test CWL export
    print("\nTesting CWL export...")
    with tempfile.TemporaryDirectory() as temp_dir:
        cwl_path = Path(temp_dir) / "workflow.cwl"
        cwl_from_workflow(workflow, cwl_path, verbose=True)
        
        # Check that CWL file was created
        if cwl_path.exists():
            print(f"  CWL file created: ✓")
            print(f"  CWL file size: {cwl_path.stat().st_size} bytes")
        else:
            print(f"  CWL file created: ✗")


def test_environment_comparison():
    """Test comparison of workflows adapted for different environments."""
    print("\nTesting environment comparison...")
    
    workflow = test_multi_environment_import()
    adapter = EnvironmentAdapter(workflow)
    
    # Adapt for different environments
    shared_workflow = adapter.adapt_for_environment("shared")
    distributed_workflow = adapter.adapt_for_environment("distributed")
    cloud_workflow = adapter.adapt_for_environment("cloud")
    
    # Compare resource specifications
    for task_id in workflow.tasks.keys():
        print(f"\nTask: {task_id}")
        
        shared_task = shared_workflow.tasks[task_id]
        distributed_task = distributed_workflow.tasks[task_id]
        cloud_task = cloud_workflow.tasks[task_id]
        
        print(f"  Shared environment:")
        shared_cpu = shared_task.cpu.get_value_for("shared") if hasattr(shared_task, "cpu") else None
        shared_mem = shared_task.mem_mb.get_value_for("shared") if hasattr(shared_task, "mem_mb") else None
        shared_retry = shared_task.retry_count.get_value_for("shared") if hasattr(shared_task, "retry_count") else None
        print(f"    CPU: {shared_cpu}")
        print(f"    Memory: {shared_mem}")
        print(f"    Retry: {shared_retry}")
        
        print(f"  Distributed environment:")
        distributed_cpu = distributed_task.cpu.get_value_for("distributed") if hasattr(distributed_task, "cpu") else None
        distributed_mem = distributed_task.mem_mb.get_value_for("distributed") if hasattr(distributed_task, "mem_mb") else None
        distributed_retry = distributed_task.retry_count.get_value_for("distributed") if hasattr(distributed_task, "retry_count") else None
        print(f"    CPU: {distributed_cpu}")
        print(f"    Memory: {distributed_mem}")
        print(f"    Retry: {distributed_retry}")
        
        print(f"  Cloud environment:")
        cloud_cpu = cloud_task.cpu.get_value_for("cloud") if hasattr(cloud_task, "cpu") else None
        cloud_mem = cloud_task.mem_mb.get_value_for("cloud") if hasattr(cloud_task, "mem_mb") else None
        cloud_retry = cloud_task.retry_count.get_value_for("cloud") if hasattr(cloud_task, "retry_count") else None
        print(f"    CPU: {cloud_cpu}")
        print(f"    Memory: {cloud_mem}")
        print(f"    Retry: {cloud_retry}")


if __name__ == "__main__":
    print("Multi-Environment IR Importers/Exporters Test")
    print("=" * 50)
    
    try:
        test_multi_environment_import()
        test_multi_environment_adaptation()
        test_multi_environment_export()
        test_environment_comparison()
        
        print("\n" + "=" * 50)
        print("All tests completed successfully! ✓")
        
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc() 