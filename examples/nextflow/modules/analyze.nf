process ANALYZE_DATA {
    tag "analyze_${processed_file.baseName}"

    container 'rocker/r-ver:4.2.0'

    cpus 4
    memory '8.GB'
    disk '20.GB'
    accelerator 1, type: 'nvidia-tesla-k80'

    conda 'environments/r.yml'

    publishDir "${params.output_dir}/analysis", mode: 'copy'

    errorStrategy 'retry'
    maxRetries 2

    input:
    path processed_file

    output:
    path "analysis_results.txt", emit: results
    path "plots.png", emit: plots

    script:
    """
    echo "Analyzing data from ${processed_file}"

    # R analysis script
    Rscript -e "
    cat('Starting analysis...\\n')
    data <- readLines('${processed_file}')
    cat('Data loaded:', length(data), 'lines\\n')

    # Simple analysis
    results <- paste('ANALYZED:', data, collapse='\\n')
    writeLines(results, 'analysis_results.txt')

    # Create dummy plot
    png('plots.png', width=800, height=600)
    plot(1:10, 1:10, main='Analysis Results')
    dev.off()

    cat('Analysis complete\\n')
    "

    echo "Analysis completed for ${processed_file}"
    """
}
