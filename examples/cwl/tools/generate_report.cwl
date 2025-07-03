#!/usr/bin/env cwl-runner

cwlVersion: v1.2
class: CommandLineTool

doc: "Generate final analysis report"
label: "Report Generation Tool"

requirements:
  - class: DockerRequirement
    dockerPull: "python:3.9-slim"
  - class: ResourceRequirement
    coresMin: 1
    ramMin: 2048
    tmpdirMin: 512
  - class: InitialWorkDirRequirement
    listing:
      - entryname: report_script.py
        entry: |
          import sys
          import json
          from datetime import datetime

          def generate_report(data_file, results_file, output_dir, output_file):
              # Read input files
              with open(data_file, 'r') as f:
                  data_content = f.read()

              with open(results_file, 'r') as f:
                  results = json.load(f)

              # Generate HTML report
              html_content = f"""
              <!DOCTYPE html>
              <html>
              <head>
                  <title>Analysis Report</title>
                  <style>
                      body {{ font-family: Arial, sans-serif; margin: 40px; }}
                      .header {{ background-color: #f0f0f0; padding: 20px; }}
                      .section {{ margin: 20px 0; }}
                      .result {{ background-color: #e8f4f8; padding: 10px; }}
                  </style>
              </head>
              <body>
                  <div class="header">
                      <h1>Data Analysis Report</h1>
                      <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                  </div>

                  <div class="section">
                      <h2>Input Data Summary</h2>
                      <p>Data length: {len(data_content)} characters</p>
                      <p>First 100 characters: {data_content[:100]}...</p>
                  </div>

                  <div class="section">
                      <h2>Analysis Results</h2>
                      <div class="result">
                          <p><strong>Threshold:</strong> {results['threshold']}</p>
                          <p><strong>Max Iterations:</strong> {results['max_iterations']}</p>
                          <p><strong>Iterations Used:</strong> {results['iterations_used']}</p>
                          <p><strong>Analysis Score:</strong> {results['analysis_score']:.4f}</p>
                          <p><strong>Significant:</strong> {results['significant']}</p>
                      </div>
                  </div>

                  <div class="section">
                      <h2>Conclusion</h2>
                      <p>Analysis completed successfully with {'significant' if results['significant'] else 'non-significant'} results.</p>
                      <p>Output directory: {output_dir}</p>
                  </div>
              </body>
              </html>
              """

              # Write report
              with open(output_file, 'w') as f:
                  f.write(html_content)

              print(f"Report generated: {output_file}")

          if __name__ == "__main__":
              generate_report(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])

baseCommand: ["python3", "report_script.py"]

arguments:
  - $(inputs.data_file.path)
  - $(inputs.results_file.path)
  - $(inputs.output_dir)
  - $(inputs.output_name)

inputs:
  data_file:
    type: File
    doc: "Processed data file"

  results_file:
    type: File
    doc: "Analysis results file"

  output_dir:
    type: string
    doc: "Output directory name"

  output_name:
    type: string
    doc: "Name for the output report file"

outputs:
  report_file:
    type: File
    outputBinding:
      glob: $(inputs.output_name)
    doc: "Final HTML report"

stdout: generate_report.log
