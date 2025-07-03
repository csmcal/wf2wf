# examples/localrules.smk
# A workflow demonstrating local rules that should run on the submit node,
# not be submitted to Condor compute nodes.

# Specify which rules should run locally
localrules: all, cleanup, prepare_config

rule all:
    input: "results/final_output.txt"

# Local rule: configuration preparation (should run on submit node)
rule prepare_config:
    output: "config/runtime_config.json"
    shell:
        """
        mkdir -p config
        echo '{{"timestamp": "'$(date)'", "user": "'$USER'"}}' > {output}
        """

# Compute-intensive rule (should be submitted to Condor)
rule heavy_computation:
    input: "config/runtime_config.json"
    output: "results/computation_result.txt"
    resources:
        mem_mb=8000,
        disk_gb=10
    threads: 4
    shell:
        """
        echo "Running heavy computation with config from {input}"
        sleep 5  # Simulate computation
        echo "Computation complete at $(date)" > {output}
        """

# Local rule: final cleanup and summary (should run on submit node)
rule cleanup:
    input: "results/computation_result.txt"
    output: "results/final_output.txt"
    shell:
        """
        echo "Finalizing results..."
        cp {input} {output}
        echo "Cleanup completed at $(date)" >> {output}
        """
