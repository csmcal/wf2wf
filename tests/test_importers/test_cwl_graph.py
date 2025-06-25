from pathlib import Path
from wf2wf.importers import cwl as cwl_importer


def test_cwl_graph_import(tmp_path):
    data_dir = Path(__file__).parent.parent / "data"
    wf_path = data_dir / "graph_workflow.cwl"
    wf = cwl_importer.to_workflow(wf_path)

    # Basic assertions
    assert wf.name
    assert len(wf.tasks) == 1
    assert "step1" in wf.tasks
    # Workflow input preserved
    assert any(p.id == "input_file" for p in wf.inputs) 