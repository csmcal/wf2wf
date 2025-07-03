cwlVersion: v1.2
$graph:
  - id: main_wf
    class: Workflow
    inputs:
      input_file: File
    outputs:
      result:
        type: File
        outputSource: step1/outfile
    steps:
      step1:
        run: tool_echo
        in:
          infile: input_file
        out: [outfile]
  - id: tool_echo
    class: CommandLineTool
    baseCommand: [echo]
    inputs:
      infile:
        type: File
        inputBinding:
          position: 1
    outputs:
      outfile:
        type: File
        outputBinding:
          glob: "$(inputs.infile.nameroot).out"
