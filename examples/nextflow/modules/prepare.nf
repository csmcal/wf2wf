process PREPARE_DATA {
    tag "prepare_${input_file.baseName}"

    container 'python:3.9-slim'

    cpus 2
    memory '4.GB'
    disk '10.GB'

    conda 'environments/python.yml'

    publishDir "${params.output_dir}/prepared", mode: 'copy'

    input:
    path input_file

    output:
    path "processed_data.txt", emit: processed

    script:
    """
    echo "Preparing data from ${input_file}"
    python3 -c "
import sys
print('Processing input file: ${input_file}')
with open('${input_file}', 'r') as f:
    data = f.read()
with open('processed_data.txt', 'w') as f:
    f.write('PROCESSED: ' + data)
print('Data preparation complete')
    "
    """
}
