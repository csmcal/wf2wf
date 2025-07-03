# examples/unsupported.smk
# A workflow for testing detection of unsupported features like dynamic() and pipe().

rule all:
    input: dynamic("final_{i}.txt")

rule make_files:
    input: "start.txt"
    output: dynamic("file_{i}.txt")
    shell: "touch {output}"

rule dynamic_producer:
    output: dynamic("dynamic_out_{i}.txt" for i in range(2))
    shell: "touch {output}"

rule pipe_job:
    input: "start.txt"
    output: pipe("piped_output.txt")
    shell: "cat {input} > {output}"

rule consumer:
    input:
        dynamic("dynamic_out_{i}.txt" for i in range(2)),
        "piped_output.txt"
    output: "final.txt"
    shell: "cat {input} > {output}"
