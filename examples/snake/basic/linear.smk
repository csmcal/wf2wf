# examples/linear.smk
# A simple, linear workflow: A -> B -> C

rule all:
    input: "C.txt"

rule rule_a:
    input: "start.txt"
    output: "A.txt"
    shell: "echo 'A' > {output}"

rule rule_b:
    input:  "A.txt"
    output: "B.txt"
    shell: "cat {input} > {output}; echo 'B' >> {output}"

rule rule_c:
    input:  "B.txt"
    output: "C.txt"
    shell: "cat {input} > {output}; echo 'C' >> {output}"
