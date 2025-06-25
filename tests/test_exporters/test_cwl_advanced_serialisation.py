from pathlib import Path
import yaml
from wf2wf.core import Workflow, Task, ParameterSpec, TypeSpec, ScatterSpec
from wf2wf.exporters import cwl as cwl_exporter


def _roundtrip_cwl(wf: Workflow, tmp_path: Path):
    out_path = tmp_path / "wf.cwl"
    cwl_exporter.from_workflow(wf, out_file=out_path, single_file=True)
    content = yaml.safe_load(out_path.read_text().split("\n", 2)[-1])
    return content


def test_complex_type_serialisation(tmp_path):
    # Record type with name
    rec_type = TypeSpec(type="record", name="Pair", fields={
        "left": TypeSpec.parse("File"),
        "right": TypeSpec.parse("File")
    })

    wf = Workflow(name="complex_types")
    wf.inputs.append(ParameterSpec(id="reads", type=TypeSpec(type="array", items=rec_type)))

    out_doc = _roundtrip_cwl(wf, tmp_path)

    assert "$schemas" in out_doc, "$schemas block missing"
    # Reference by name inside inputs
    in_types = next(iter(out_doc["inputs"].values()))["type"]
    assert in_types == {"type": "array", "items": "Pair"} or in_types == ["null", {"type":"array","items":"Pair"}]


def test_valuefrom_and_scatter(tmp_path):
    wf = Workflow(name="valuefrom_scatter")
    task = Task(id="step1")
    ps_in = ParameterSpec(id="x", type="int", value_from="$(inputs.y * 2)")
    ps_y = ParameterSpec(id="y", type="int")
    task.inputs = [ps_in, ps_y]
    ps_out = ParameterSpec(id="out", type="int")
    task.outputs = [ps_out]
    task.scatter = ScatterSpec(scatter=["y"], scatter_method="dotproduct")
    wf.tasks = {task.id: task}
    wf.edges = []

    out_doc = _roundtrip_cwl(wf, tmp_path)

    step_def = out_doc["steps"]["step1"]
    assert step_def["scatter"] == "y", "Scatter should be scalar in shorthand form"
    assert "valueFrom" in step_def["in"]["x"], "valueFrom not emitted"


def test_secondary_files_on_workflow_output(tmp_path):
    wf = Workflow(name="sec_files")
    out_param = ParameterSpec(id="report", type="File", secondary_files=[".idx", ".stat"])
    wf.outputs.append(out_param)

    out_doc = _roundtrip_cwl(wf, tmp_path)
    report_def = out_doc["outputs"]["report"]
    assert report_def["secondaryFiles"] == [".idx", ".stat"], "secondaryFiles not preserved" 