# examples/run_block.smk
# A workflow for testing 'run:' block conversion

configfile: "config.yaml"

rule all:
    input: "final.txt"

rule python_run_block:
    output: "final.txt"
    params:
        greeting=config.get("greeting", "default_greeting")
    run:
        print(f"Got greeting: {params.greeting}")
        with open(output[0], "w") as f:
            f.write(f"The greeting was: {params.greeting}")
