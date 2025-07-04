#!/usr/bin/env python3
"""
Example demonstrating file transfer modes for distributed computing environments.

This example shows how wf2wf handles file transfers between shared filesystem 
workflows (like Snakemake) and distributed computing workflows (like HTCondor/DAGMan).
"""

from pathlib import Path
from wf2wf.core import Workflow, Task, ParameterSpec

def create_example_workflow():
    """Create a workflow demonstrating different file transfer modes."""
    
    wf = Workflow(name="file_transfer_example", version="1.0")
    
    # Task 1: Data preprocessing
    # This task demonstrates various file transfer scenarios
    preprocess_task = Task(
        id="preprocess_data",
        command="python preprocess.py --input {input} --output {output}",
        inputs=[
            # Regular input file - will be transferred (auto mode)
            "raw_data.txt",
            
            # Reference genome - on shared storage, no transfer needed  
            ParameterSpec(
                id="/shared/genomes/hg38.fa",
                type="File",
                transfer_mode="shared",
                doc="Reference genome on shared storage"
            ),
            
            # Configuration file - must be transferred
            ParameterSpec(
                id="config.yaml",
                type="File", 
                transfer_mode="always",
                doc="Configuration file that must be transferred"
            ),
            
            # Temporary index file - local only, no transfer
            ParameterSpec(
                id="temp_index.tmp",
                type="File",
                transfer_mode="never",
                doc="Temporary index file, local only"
            ),
        ],
        outputs=[
            # Processed data - will be transferred back
            "processed_data.txt",
            
            # Results stored on shared storage
            ParameterSpec(
                id="/shared/results/preprocessed.bam",
                type="File", 
                transfer_mode="shared",
                doc="Results stored on shared storage"
            ),
            
            # Debug log - local only
            ParameterSpec(
                id="debug.log",
                type="File",
                transfer_mode="never", 
                doc="Debug log, stays local"
            ),
        ]
    )
    wf.add_task(preprocess_task)
    
    # Task 2: Analysis
    # This task shows how intermediate files are handled
    analysis_task = Task(
        id="analyze_data",
        command="python analyze.py --input {input} --output {output}",
        inputs=[
            # Input from previous task - will be transferred
            "processed_data.txt",
            
            # Analysis script - must be transferred
            ParameterSpec(
                id="analysis_script.py",
                type="File",
                transfer_mode="always",
                doc="Analysis script that must be available on compute node"
            ),
        ],
        outputs=[
            # Final results - always transfer back
            ParameterSpec(
                id="final_results.json",
                type="File",
                transfer_mode="always",
                doc="Final analysis results"
            ),
            
            # Summary report - auto transfer
            "summary_report.txt",
        ]
    )
    wf.add_task(analysis_task)
    
    # Add dependency
    wf.add_edge("preprocess_data", "analyze_data")
    
    return wf

def main():
    """Demonstrate the workflow and conversion process."""
    
    print("Creating example workflow with file transfer specifications...")
    wf = create_example_workflow()
    
    # Save as JSON IR
    json_path = Path("file_transfer_example.json")
    wf.save_json(json_path)
    print(f"Saved workflow to: {json_path}")
    
    # Convert to DAGMan to show file transfer handling
    dag_path = Path("file_transfer_example.dag")
    
    try:
        from wf2wf.exporters.dagman import from_workflow
        from_workflow(wf, dag_path)
        print(f"Converted to DAGMan: {dag_path}")
        
        # Show the file transfer specifications
        print("\nFile Transfer Analysis:")
        print("=" * 50)
        
        # Read submit files to show transfer specifications
        submit_files = list(dag_path.parent.glob("*.sub"))
        for submit_file in submit_files:
            print(f"\n{submit_file.name}:")
            content = submit_file.read_text()
            
            # Extract transfer specifications
            for line in content.split('\n'):
                if line.startswith('transfer_input_files'):
                    print(f"  Input files to transfer: {line.split('=', 1)[1].strip()}")
                elif line.startswith('transfer_output_files'):
                    print(f"  Output files to transfer: {line.split('=', 1)[1].strip()}")
        
        print("\nTransfer Mode Summary:")
        print("- 'auto' and 'always' files are included in transfer lists")
        print("- 'shared' files are assumed to be on shared storage")
        print("- 'never' files are local only and not transferred")
        
    except ImportError as e:
        print(f"DAGMan exporter not available: {e}")
    
    print(f"\nExample files created:")
    print(f"- {json_path} (IR format)")
    if dag_path.exists():
        print(f"- {dag_path} (DAGMan format)")
        print(f"- *.sub files (HTCondor submit files)")

if __name__ == "__main__":
    main() 