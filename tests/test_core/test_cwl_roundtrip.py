import json
from pathlib import Path

from wf2wf.importers import cwl as cwl_importer
from wf2wf.exporters import cwl as cwl_exporter


def test_cwl_roundtrip_advanced(tmp_path: Path):
    """Import advanced CWL, export again, re-import and check key features."""
    src_path = Path(__file__).parent.parent.parent / "examples" / "cwl" / "advanced_features.cwl"
    wf = cwl_importer.to_workflow(src_path, preserve_metadata=True)

    # Ensure advanced features were parsed
    assert any(t.when for t in wf.tasks.values())
    assert any(t.scatter for t in wf.tasks.values())

    out_path = tmp_path / "roundtrip.cwl"
    cwl_exporter.from_workflow(wf, out_path, single_file=True)

    wf2 = cwl_importer.to_workflow(out_path, preserve_metadata=True)

    # Basic structural equivalence
    assert len(wf2.tasks) == len(wf.tasks)
    assert len(wf2.inputs) == len(wf.inputs)
    assert len(wf2.outputs) == len(wf.outputs)

    # Check that at least one conditional and scatter survived
    assert any(t.when for t in wf2.tasks.values())
    assert any(t.scatter for t in wf2.tasks.values()) 