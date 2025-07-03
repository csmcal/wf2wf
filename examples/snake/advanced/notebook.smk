# examples/notebook.smk
# A workflow demonstrating Jupyter notebook integration.

rule all:
    input: "results/analysis_report.html"

# Data preparation
rule prepare_data:
    output: "data/dataset.csv"
    shell:
        """
        echo "x,y,category" > {output}
        echo "1,2,A" >> {output}
        echo "3,4,B" >> {output}
        echo "5,6,A" >> {output}
        """

# Jupyter notebook analysis
rule analyze_notebook:
    input: "data/dataset.csv"
    output:
        notebook="results/analysis.ipynb",
        html="results/analysis_report.html"
    notebook: "notebooks/analysis_template.ipynb"

# Note: This example requires a notebook template at notebooks/analysis_template.ipynb
# The notebook directive is experimental and may not be fully supported by snake2dagman
