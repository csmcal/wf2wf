from pathlib import Path
import yaml
from wf2wf.core import Workflow, ProvenanceSpec, Task
from wf2wf.exporters import cwl as cwl_exporter


def test_structured_provenance_export(tmp_path):
    # Build workflow with namespaced extras
    prov = ProvenanceSpec(extras={
        "prov:wasGeneratedBy": "wf2wf-unit",
        "schema:author": "Alice"
    })
    wf = Workflow(name="prov_test", provenance=prov)
    out_path = tmp_path / "prov.cwl"

    cwl_exporter.from_workflow(wf, out_file=out_path, single_file=True, structure_prov=True)

    doc = yaml.safe_load(out_path.read_text().split("\n",2)[-1])
    # Expect nested blocks
    assert "prov" in doc and isinstance(doc["prov"], dict)
    assert doc["prov"]["wasGeneratedBy"] == "wf2wf-unit"
    assert "schema" in doc and doc["schema"]["author"] == "Alice" 