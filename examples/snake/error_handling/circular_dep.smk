rule A:
    input: "B_out.txt"
    output: "A_out.txt"
    shell: "echo 'A' > {output}"

rule B:
    input: "A_out.txt"
    output: "B_out.txt"
    shell: "echo 'B' > {output}"

rule all:
    input: "A_out.txt" # This will trigger the circular dependency check
