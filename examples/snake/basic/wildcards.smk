# examples/wildcards.smk
# A workflow demonstrating simple wildcard expansion.
# This should generate 3 mapping jobs and 3 calling jobs.

SAMPLES = ["a", "b", "c"]

rule all:
    input: expand("variants/{sample}.vcf", sample=SAMPLES)

rule map_reads:
    input: "raw/{sample}.fq"
    output: "mapped/{sample}.bam"
    shell: "echo 'mapping {input}' > {output}"

rule call_variants:
    input: "mapped/{sample}.bam"
    output: "variants/{sample}.vcf"
    shell: "echo 'calling variants for {input}' > {output}"
