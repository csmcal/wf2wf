from pathlib import Path
import yaml
from wf2wf.importers import cwl as cwl_importer
from wf2wf.exporters import cwl as cwl_exporter

def test_cwl_graph_options(tmp_path):
    data_dir = Path(__file__).parent.parent / "data"
    src = data_dir / "graph_workflow.cwl"
    wf = cwl_importer.to_workflow(src)

    out_path = tmp_path / "graph_opts.cwl"
    cwl_exporter.from_workflow(
        wf,
        out_file=out_path,
        graph=True,
        root_id="my_root",
        structure_prov=True,
    )

    doc = yaml.safe_load(out_path.read_text().split("\n",2)[-1])
    assert doc["$graph"][0]["id"] == "my_root"
    # provenance block optional 