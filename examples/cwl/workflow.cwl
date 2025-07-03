#!/usr/bin/env cwl-runner

cwlVersion: v1.2
class: Workflow

doc: |
  Demo CWL workflow for wf2wf testing.
  This workflow demonstrates data preparation, analysis, and reporting steps.

label: "CWL Demo Workflow"

requirements:
  - class: SubworkflowFeatureRequirement
  - class: ScatterFeatureRequirement
  - class: StepInputExpressionRequirement
  - class: InlineJavascriptRequirement

inputs:
  input_data:
    type: File
    doc: "Raw input data file"

  analysis_threshold:
    type: float
    default: 0.05
    doc: "Statistical threshold for analysis"

  max_iterations:
    type: int
    default: 1000
    doc: "Maximum number of iterations"

  output_dir:
    type: string
    default: "results"
    doc: "Output directory name"

outputs:
  prepared_data:
    type: File
    outputSource: prepare_data/processed_file
    doc: "Processed data file"

  analysis_results:
    type: File
    outputSource: analyze_data/results_file
    doc: "Analysis results"

  final_report:
    type: File
    outputSource: generate_report/report_file
    doc: "Final analysis report"

steps:
  prepare_data:
    run: tools/prepare_data.cwl
    in:
      input_file: input_data
      output_name:
        valueFrom: "prepared_data.txt"
    out: [processed_file]

  analyze_data:
    run: tools/analyze_data.cwl
    in:
      input_file: prepare_data/processed_file
      threshold: analysis_threshold
      max_iter: max_iterations
      output_name:
        valueFrom: "analysis_results.json"
    out: [results_file]

  generate_report:
    run: tools/generate_report.cwl
    in:
      data_file: prepare_data/processed_file
      results_file: analyze_data/results_file
      output_dir: output_dir
      output_name:
        valueFrom: "final_report.html"
    out: [report_file]
