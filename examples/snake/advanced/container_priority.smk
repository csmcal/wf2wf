# This rule has both a conda directive and an explicit container.
# The converter should prioritize the explicit container.
rule container_override:
    output: "container_test.txt"
    container: "docker://python:3.9-slim"
    conda: "environment.yaml"
    shell: "echo 'This job should run in python:3.9-slim' > {output}"

rule all:
    input: "container_test.txt"
