#!/usr/bin/env cwl-runner

cwlVersion: v1.2
class: CommandLineTool

doc: "Prepare and clean input data"
label: "Data Preparation Tool"

requirements:
  - class: DockerRequirement
    dockerPull: "python:3.9-slim"
  - class: ResourceRequirement
    coresMin: 2
    ramMin: 4096
    tmpdirMin: 1024

baseCommand: ["python3", "-c"]

arguments:
  - |
    import sys
    import json

    # Read input file
    with open('$(inputs.input_file.path)', 'r') as f:
        data = f.read()

    # Simple data processing
    processed_data = data.strip().upper()
    processed_lines = len(processed_data.split('\n'))

    # Write processed data
    with open('$(inputs.output_name)', 'w') as f:
        f.write(f"Processed data: {processed_data}\n")
        f.write(f"Total lines: {processed_lines}\n")
        f.write("Data preparation completed.\n")

    print(f"Data preparation completed. Output: $(inputs.output_name)")

inputs:
  input_file:
    type: File
    doc: "Input data file to process"

  output_name:
    type: string
    doc: "Name for the output file"

outputs:
  processed_file:
    type: File
    outputBinding:
      glob: $(inputs.output_name)
    doc: "Processed data file"

stdout: prepare_data.log
