#!/usr/bin/env cwl-runner
cwlVersion: v1.2
class: Workflow

label: "Advanced Features Demo"
doc: |
  CWL workflow demonstrating scatter/gather and conditional execution (when).

requirements:
  - class: ScatterFeatureRequirement
  - class: StepInputExpressionRequirement
  - class: InlineJavascriptRequirement
  - class: SubworkflowFeatureRequirement
  - class: ConditionalWhenRequirement

inputs:
  samples:
    type:
      type: array
      items: File
    doc: "Sample FASTQ files"
  run_optional:
    type: boolean
    default: false
    doc: "Whether to run the optional summarisation step"

outputs:
  summary:
    type: File
    outputSource: summarise/summary_file

steps:
  preprocess:
    run: tools/prepare_data.cwl
    in:
      input_file: samples
    out: [processed_file]
    scatter: input_file
    scatterMethod: dotproduct

  summarise:
    run: tools/generate_report.cwl
    in:
      data_file: preprocess/processed_file
    out: [summary_file]
    when: "$context.run_optional == true"
