# examples/scatter_gather.smk
# A workflow demonstrating a scatter-gather pattern.

SAMPLES = ["a", "b"]
CHUNKS = ["1", "2"]

rule all:
    input: "results/all_merged.txt"

# Scatter: process each chunk of each sample
rule process_chunk:
    output: "processed/{sample}_{chunk}.txt"
    shell:  "echo 'processed {wildcards.sample} chunk {wildcards.chunk}' > {output}"

# Gather: merge the processed chunks for each sample
rule merge_sample_chunks:
    input:  expand("processed/{{sample}}_{chunk}.txt", chunk=CHUNKS)
    output: "merged/{sample}.txt"
    shell:  "cat {input} > {output}"

# Final Gather: merge all sample results
rule merge_all:
    input:  expand("merged/{sample}.txt", sample=SAMPLES)
    output: "results/all_merged.txt"
    shell:  "cat {input} > {output}"
