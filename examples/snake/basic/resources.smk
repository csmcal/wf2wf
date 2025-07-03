# examples/resources.smk
# A workflow for testing resource allocation.

rule all:
    input: "C.txt"

rule A_heavy_mem:
    input: "start.txt"
    output: "A.txt"
    resources:
        mem_mb=10240 # 10GB
    shell: "echo 'heavy mem' > {output}"

rule B_heavy_disk_and_cpu:
    input: "A.txt"
    output: "B.txt"
    resources:
        disk_gb=100,
        threads=8
    shell: "echo 'heavy disk and cpu' > {output}"

rule C_mixed_resources:
    input: "B.txt"
    output: "C.txt"
    resources:
        mem_mb=1500,
        disk_mb=5000
    shell: "echo 'mixed' > {output}"
