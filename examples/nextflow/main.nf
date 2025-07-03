#!/usr/bin/env nextflow

/*
 * Demo Nextflow workflow for wf2wf testing
 * Features: processes, channels, containers, resources, conda environments
 */

nextflow.enable.dsl=2

// Parameters
params.input_data = "data/raw_data.txt"
params.output_dir = "results"
params.threads = 4
params.memory = "8.GB"

// Include modules
include { PREPARE_DATA } from './modules/prepare.nf'
include { ANALYZE_DATA } from './modules/analyze.nf'
include { GENERATE_REPORT } from './modules/report.nf'

workflow {
    // Create input channel
    input_ch = Channel.fromPath(params.input_data)

    // Process data through pipeline
    PREPARE_DATA(input_ch)
    ANALYZE_DATA(PREPARE_DATA.out)
    GENERATE_REPORT(ANALYZE_DATA.out)

    // Emit final output
    GENERATE_REPORT.out.view()
}

workflow.onComplete {
    println "Pipeline completed at: $workflow.complete"
    println "Execution status: ${ workflow.success ? 'OK' : 'failed' }"
}
