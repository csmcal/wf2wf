# examples/retries.smk
# A workflow for testing the 'retries' directive.

rule all:
    input: "C.txt"

rule A_will_fail_once:
    output: "A.txt"
    retries: 2
    shell:
        """
        # This will fail the first time it's run
        if [ ! -f {output}.tmp ]; then
            touch {output}.tmp
            echo "A is failing..."
            exit 1
        else
            echo "A is succeeding on retry." > {output}
            rm {output}.tmp
        fi
        """

rule B:
    input:  "A.txt"
    output: "B.txt"
    shell:  "cat {input} > {output}; echo 'B ran.' >> {output}"

rule C_no_retry:
    input:  "B.txt"
    output: "C.txt"
    retries: 0 # Explicitly no retries
    shell:  "cat {input} > {output}; echo 'C ran.' >> {output}"
