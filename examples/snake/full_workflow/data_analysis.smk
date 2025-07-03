# Example Snakefile for testing snakemake_to_dag.py conversion
# This demonstrates various Snakemake features and how they translate to Condor DAG

# Configuration
configfile: "config.yaml"

# Target rule (what we want to produce)
rule all:
    input:
        "results/final_report.html",
        "results/summary_stats.txt"

# Data preprocessing rule
rule preprocess_data:
    input:
        "data/raw_data.txt"
    output:
        "data/cleaned_data.txt"
    resources:
        mem_mb=2000,
        disk_mb=5000
    threads: 1
    shell:
        """
        # Simple data cleaning
        grep -v "^#" {input} | sort > {output}
        echo "Data preprocessing completed"
        """

# Analysis rule with conda environment
rule analyze_data:
    input:
        "data/cleaned_data.txt"
    output:
        "results/analysis_output.txt",
        "results/intermediate_data.txt"
    conda:
        "envs/analysis.yaml"
    resources:
        mem_mb=4000,
        disk_mb=8000
    threads: 2
    script:
        "scripts/analyze.py"

# Statistical analysis rule
rule compute_stats:
    input:
        "results/analysis_output.txt"
    output:
        "results/statistics.json"
    resources:
        mem_mb=1000,
        disk_mb=2000
    params:
        threshold=config.get("threshold", 0.05)
    shell:
        """
        python scripts/compute_stats.py {input} {output} --threshold {params.threshold}
        """

# Summary rule that depends on multiple inputs
rule create_summary:
    input:
        stats="results/statistics.json",
        data="results/intermediate_data.txt"
    output:
        "results/summary_stats.txt"
    resources:
        mem_mb=1500
    shell:
        """
        echo "Generating summary from {input.stats} and {input.data}"
        python scripts/summarize.py {input.stats} {input.data} > {output}
        """

# Visualization rule with R script
rule create_plots:
    input:
        "results/analysis_output.txt"
    output:
        "results/plots.png"
    conda:
        "envs/r_env.yaml"
    resources:
        mem_mb=3000,
        disk_mb=4000
    threads: 1
    script:
        "scripts/create_plots.R"

# Final report generation
rule generate_report:
    input:
        plots="results/plots.png",
        stats="results/statistics.json",
        summary="results/summary_stats.txt"
    output:
        "results/final_report.html"
    resources:
        mem_mb=2000,
        disk_mb=3000
    params:
        title=config.get("report_title", "Analysis Report")
    shell:
        """
        echo "Generating final report: {params.title}"
        python scripts/generate_report.py \
            --plots {input.plots} \
            --stats {input.stats} \
            --summary {input.summary} \
            --output {output} \
            --title "{params.title}"
        """

# Example rule with benchmark
rule benchmark_analysis:
    input:
        "data/cleaned_data.txt"
    output:
        "results/benchmark_output.txt"
    benchmark:
        "benchmarks/analysis_benchmark.txt"
    resources:
        mem_mb=8000,
        disk_mb=10000
    threads: 4
    shell:
        """
        # CPU-intensive analysis for benchmarking
        python scripts/intensive_analysis.py {input} {output}
        """

# Rule with log file
rule quality_check:
    input:
        "data/cleaned_data.txt"
    output:
        "results/quality_report.txt"
    log:
        "logs/quality_check.log"
    resources:
        mem_mb=1000
    shell:
        """
        python scripts/quality_check.py {input} {output} 2> {log}
        """
