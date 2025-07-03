# examples/gpu.smk
# A workflow for testing GPU resource requests.

rule all:
    input: "gpu_output.txt"

rule gpu_job:
    output: "gpu_output.txt"
    resources:
        gpu=1,
        gpu_mem_mb=24000,
        gpu_capability="8.6"
    shell: "echo 'This job needs a specific GPU' > {output}"

rule cpu_job:
    input: "gpu_output.txt"
    output: "final.txt"
    shell: "echo 'This is a CPU job' > {output}"
