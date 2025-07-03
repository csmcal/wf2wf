# examples/advanced.smk
# A workflow demonstrating advanced features for testing.

configfile: "config.yaml"

rule all:
    input: "C.txt"

# Test python 'run:' block with params and config
rule python_run_block:
    output: "run_block_output.txt"
    params:
        greeting=config["greeting"]
    run:
        with open(output[0], "w") as f:
            f.write(f"{params.greeting}, this is a run block speaking.\\n")
            f.write(f"Using {threads} threads.\\n")

# Test shell command with conda env
rule conda_shell_job:
    input: "B.txt"
    output: "C.txt"
    conda: "environment.yaml"
    shell: "echo 'conda' > {output}"

# Test docker container job
rule docker_job:
    input: "A.txt"
    output: "B.txt"
    container:
        "docker://ubuntu:20.04"
    shell: "echo 'docker' > {output}"

# Test singularity container job
rule singularity_job:
    input: "start.txt"
    output: "A.txt"
    container:
        "singularity:///path/to/singularity.sif"
    shell: "echo 'singularity' > {output}"
