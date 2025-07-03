#!/usr/bin/env cwl-runner

cwlVersion: v1.2
class: Workflow

label: "Comprehensive Bioinformatics Analysis Pipeline"
doc: "Advanced workflow demonstrating CWL v1.2.1 features for fidelity testing"

author:
  - "orcid:0000-0000-0000-0001"
version: "2.0.0"
license: "MIT"
doi: "10.1000/example.doi"
keywords: ["genomics", "variant-calling", "quality-control", "bioinformatics"]
intent: ["http://edamontology.org/operation_0004"]

requirements:
  - class: ScatterFeatureRequirement
  - class: ConditionalWhen
  - class: StepInputExpressionRequirement
  - class: MultipleInputFeatureRequirement

hints:
  - class: NetworkAccess
    networkAccess: true
  - class: LoadListingRequirement
    loadListing: deep_listing

inputs:
  input_reads:
    type: File[]
    label: "Input FASTQ Files"
    doc: "Array of FASTQ files for analysis"
    format: "http://edamontology.org/format_1930"
    secondaryFiles:
      - .fai
      - .amb

  reference_genome:
    type: File
    label: "Reference Genome"
    doc: "Reference genome FASTA file"
    format: "http://edamontology.org/format_1929"
    secondaryFiles:
      - .fai
      - .dict

  quality_threshold:
    type: float
    label: "Quality Threshold"
    doc: "Minimum quality score threshold"
    default: 0.8

  run_variant_calling:
    type: boolean
    label: "Run Variant Calling"
    doc: "Whether to perform variant calling step"
    default: true

  analysis_config:
    type:
      type: record
      fields:
        - name: mode
          type: string
          doc: "Analysis mode (fast/comprehensive)"
        - name: max_iterations
          type: int
          doc: "Maximum number of iterations"
        - name: enable_filters
          type: boolean
          doc: "Enable quality filters"
    label: "Analysis Configuration"
    doc: "Complex configuration object"

outputs:
  qc_reports:
    type: File[]
    label: "Quality Control Reports"
    doc: "HTML reports from quality control analysis"
    outputSource: quality_control/qc_report

  aligned_reads:
    type: File[]
    label: "Aligned Reads"
    doc: "BAM files with aligned reads"
    outputSource: alignment/aligned_bam

  variant_calls:
    type: File?
    label: "Variant Calls"
    doc: "VCF file with called variants (optional)"
    outputSource: variant_calling/variants_vcf

steps:
  quality_control:
    label: "Quality Control Analysis"
    doc: "Assess sequencing data quality using FastQC"
    run: "#fastqc_tool"
    scatter: input_reads
    scatterMethod: dotproduct
    in:
      input_file: input_reads
      threads:
        valueFrom: $(runtime.cores)
    out: [qc_report, qc_data]

    requirements:
      - class: ResourceRequirement
        coresMin: 4
        ramMin: 4096
        tmpdirMin: 2048
      - class: DockerRequirement
        dockerPull: "biocontainers/fastqc:v0.11.9_cv8"

    hints:
      - class: TimeLimit
        timelimit: 1800

  trimming:
    label: "Read Trimming"
    doc: "Trim low-quality bases and adapters"
    run: "#trimmomatic_tool"
    scatter: input_reads
    scatterMethod: dotproduct
    in:
      input_file: input_reads
      quality_threshold: quality_threshold
      min_length:
        valueFrom: $(36)
    out: [trimmed_reads]

    requirements:
      - class: ResourceRequirement
        coresMin: 2
        ramMin: 2048
      - class: DockerRequirement
        dockerPull: "biocontainers/trimmomatic:0.39--1"

  alignment:
    label: "Read Alignment"
    doc: "Align reads to reference genome using BWA-MEM"
    run: "#bwa_mem_tool"
    scatter: trimmed_reads
    scatterMethod: dotproduct
    in:
      reads: trimming/trimmed_reads
      reference: reference_genome
      threads:
        valueFrom: $(runtime.cores)
      sample_name:
        valueFrom: $(inputs.reads.nameroot)
    out: [aligned_bam, alignment_stats]

    requirements:
      - class: ResourceRequirement
        coresMin: 8
        ramMin: 16384
        tmpdirMin: 20480
      - class: DockerRequirement
        dockerPull: "biocontainers/bwa:0.7.17--hed695b0_7"
      - class: EnvironmentVarRequirement
        envDef:
          - envName: "BWA_THREADS"
            envValue: "$(runtime.cores)"

  variant_calling:
    label: "Variant Calling"
    doc: "Call variants using GATK HaplotypeCaller"
    run: "#gatk_haplotypecaller_tool"
    when: $(inputs.run_calling)
    scatter: aligned_bam
    scatterMethod: dotproduct
    in:
      input_bam: alignment/aligned_bam
      reference: reference_genome
      run_calling: run_variant_calling
      min_base_quality:
        valueFrom: $(20)
    out: [variants_vcf, calling_stats]

    requirements:
      - class: ResourceRequirement
        coresMin: 4
        ramMin: 8192
      - class: DockerRequirement
        dockerPull: "broadinstitute/gatk:4.2.6.1"

    hints:
      - class: NetworkAccess
        networkAccess: true

$graph:
  - class: CommandLineTool
    id: "#fastqc_tool"
    label: "FastQC Quality Control"
    doc: "Quality control analysis for high throughput sequence data"

    baseCommand: ["fastqc"]

    arguments:
      - "--outdir"
      - "."
      - "--format"
      - "fastq"

    inputs:
      input_file:
        type: File
        inputBinding:
          position: 1
      threads:
        type: int
        inputBinding:
          prefix: "--threads"

    outputs:
      qc_report:
        type: File
        outputBinding:
          glob: "*_fastqc.html"
      qc_data:
        type: File
        outputBinding:
          glob: "*_fastqc.zip"

    requirements:
      - class: DockerRequirement
        dockerPull: "biocontainers/fastqc:v0.11.9_cv8"

  - class: CommandLineTool
    id: "#trimmomatic_tool"
    label: "Trimmomatic Read Trimming"
    doc: "Flexible read trimming tool for Illumina NGS data"

    baseCommand: ["trimmomatic", "SE"]

    inputs:
      input_file:
        type: File
        inputBinding:
          position: 1
      quality_threshold:
        type: float
        inputBinding:
          position: 3
          prefix: "TRAILING:"
          separate: false
      min_length:
        type: int
        inputBinding:
          position: 4
          prefix: "MINLEN:"
          separate: false

    arguments:
      - position: 2
        valueFrom: "$(inputs.input_file.nameroot)_trimmed.fastq"

    outputs:
      trimmed_reads:
        type: File
        outputBinding:
          glob: "*_trimmed.fastq"

    requirements:
      - class: DockerRequirement
        dockerPull: "biocontainers/trimmomatic:0.39--1"

  - class: CommandLineTool
    id: "#bwa_mem_tool"
    label: "BWA-MEM Alignment"
    doc: "Fast and accurate short read aligner"

    baseCommand: ["bwa", "mem"]

    inputs:
      reference:
        type: File
        inputBinding:
          position: 1
        secondaryFiles:
          - .amb
          - .ann
          - .bwt
          - .pac
          - .sa
      reads:
        type: File
        inputBinding:
          position: 2
      threads:
        type: int
        inputBinding:
          prefix: "-t"
      sample_name:
        type: string

    stdout: "$(inputs.sample_name).sam"

    outputs:
      aligned_bam:
        type: File
        outputBinding:
          glob: "*.sam"
      alignment_stats:
        type: File
        outputBinding:
          glob: "*.stats"

    requirements:
      - class: DockerRequirement
        dockerPull: "biocontainers/bwa:0.7.17--hed695b0_7"
      - class: ResourceRequirement
        coresMin: 8
        ramMin: 16384

  - class: CommandLineTool
    id: "#gatk_haplotypecaller_tool"
    label: "GATK HaplotypeCaller"
    doc: "Call germline SNPs and indels via local re-assembly of haplotypes"

    baseCommand: ["gatk", "HaplotypeCaller"]

    inputs:
      input_bam:
        type: File
        inputBinding:
          prefix: "-I"
        secondaryFiles:
          - .bai
      reference:
        type: File
        inputBinding:
          prefix: "-R"
        secondaryFiles:
          - .fai
          - .dict
      min_base_quality:
        type: int
        inputBinding:
          prefix: "--min-base-quality-score"

    arguments:
      - prefix: "-O"
        valueFrom: "$(inputs.input_bam.nameroot).vcf"

    outputs:
      variants_vcf:
        type: File
        outputBinding:
          glob: "*.vcf"
      calling_stats:
        type: File
        outputBinding:
          glob: "*.stats"

    requirements:
      - class: DockerRequirement
        dockerPull: "broadinstitute/gatk:4.2.6.1"
      - class: ResourceRequirement
        coresMin: 4
        ramMin: 8192
