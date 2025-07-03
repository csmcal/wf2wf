# examples/error.smk
# A workflow with a Python syntax error.

rule all:
    input: "a.txt"

rule A:
    output: "a.txt"
    shell: "echo 'A' > {output}"

    This is a syntax error.
