# examples/checkpoint.smk
# A workflow demonstrating Snakemake checkpoints.
# Checkpoints allow dynamic determination of output files based on intermediate results.

rule all:
    input: "results/final_summary.txt"

# Initial data generation
rule generate_data:
    output: "data/input.txt"
    shell: "echo -e 'sample1\nsample2\nsample3' > {output}"

# Checkpoint: determines how many samples we have
checkpoint determine_samples:
    input: "data/input.txt"
    output: directory("samples/")
    shell:
        """
        mkdir -p {output}
        while read sample; do
            echo "Processing $sample" > {output}/$sample.txt
        done < {input}
        """

# Rule that depends on checkpoint output
rule process_sample:
    input: "samples/{sample}.txt"
    output: "processed/{sample}_result.txt"
    shell: "cp {input} {output}"

# Aggregation rule that uses checkpoint to determine inputs
rule aggregate_results:
    input:
        lambda wildcards: expand("processed/{sample}_result.txt",
                                sample=glob_wildcards("samples/{sample}.txt").sample)
    output: "results/final_summary.txt"
    shell: "cat {input} > {output}"
