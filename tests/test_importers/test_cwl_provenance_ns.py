import textwrap
from pathlib import Path
from wf2wf.importers import cwl as cwl_importer
from wf2wf.exporters import cwl as cwl_exporter


def test_cwl_provenance_namespace(tmp_path):
    cwl_text = textwrap.dedent(
        """
        cwlVersion: v1.2
        class: CommandLineTool
        id: tool_ns
        baseCommand: echo
        inputs: []
        outputs: []
        prov:wasGeneratedBy: wf2wf-test
        schema:author: John Doe
        """
    )
    cwl_path = tmp_path / "namespaced.cwl"
    cwl_path.write_text(cwl_text)

    wf = cwl_importer.to_workflow(cwl_path)

    # extras captured
    assert wf.provenance and wf.provenance.extras["prov:wasGeneratedBy"] == "wf2wf-test"
    assert wf.provenance.extras["schema:author"] == "John Doe"

    # round-trip export should include keys
    out_path = tmp_path / "roundtrip.cwl"
    cwl_exporter.from_workflow(wf, out_file=out_path)
    out_content = out_path.read_text()
    assert "prov:wasGeneratedBy" in out_content
    assert "schema:author" in out_content 