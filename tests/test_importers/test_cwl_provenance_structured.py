import textwrap
from pathlib import Path
from wf2wf.importers import cwl as cwl_importer

def test_import_nested_prov(tmp_path):
    cwl_text = textwrap.dedent("""
    cwlVersion: v1.2
    class: CommandLineTool
    baseCommand: echo
    inputs: []
    outputs: []
    prov:
      wasGeneratedBy: test-pipeline
      entity: ABC123
    """)
    f = tmp_path / "nested.cwl"
    f.write_text(cwl_text)

    wf = cwl_importer.to_workflow(f)
    assert wf.provenance
    assert wf.provenance.extras["prov:wasGeneratedBy"] == "test-pipeline"
    assert wf.provenance.extras["prov:entity"] == "ABC123" 