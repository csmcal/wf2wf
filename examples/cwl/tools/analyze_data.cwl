#!/usr/bin/env cwl-runner

cwlVersion: v1.2
class: CommandLineTool

doc: "Analyze processed data with statistical methods"
label: "Data Analysis Tool"

requirements:
  - class: DockerRequirement
    dockerPull: "python:3.9-slim"
  - class: ResourceRequirement
    coresMin: 4
    ramMin: 8192
    tmpdirMin: 2048
  - class: InitialWorkDirRequirement
    listing:
      - entryname: analyze_script.py
        entry: |
          import sys
          import json
          import random

          def analyze_data(input_file, threshold, max_iter, output_file):
              # Read processed data
              with open(input_file, 'r') as f:
                  data = f.read()

              # Simulate analysis
              results = {
                  "input_file": input_file,
                  "threshold": threshold,
                  "max_iterations": max_iter,
                  "data_length": len(data),
                  "analysis_score": random.uniform(0.1, 1.0),
                  "significant": random.choice([True, False]),
                  "iterations_used": random.randint(10, max_iter)
              }

              # Write results
              with open(output_file, 'w') as f:
                  json.dump(results, f, indent=2)

              print(f"Analysis completed. Results saved to {output_file}")
              return results

          if __name__ == "__main__":
              analyze_data(sys.argv[1], float(sys.argv[2]), int(sys.argv[3]), sys.argv[4])

baseCommand: ["python3", "analyze_script.py"]

arguments:
  - $(inputs.input_file.path)
  - $(inputs.threshold)
  - $(inputs.max_iter)
  - $(inputs.output_name)

inputs:
  input_file:
    type: File
    doc: "Processed data file to analyze"

  threshold:
    type: float
    doc: "Statistical threshold for analysis"

  max_iter:
    type: int
    doc: "Maximum number of iterations"

  output_name:
    type: string
    doc: "Name for the output results file"

outputs:
  results_file:
    type: File
    outputBinding:
      glob: $(inputs.output_name)
    doc: "Analysis results in JSON format"

stdout: analyze_data.log
