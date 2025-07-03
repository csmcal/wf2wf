import yaml
from pathlib import Path

from wf2wf.core import Workflow, Task, ScatterSpec, ResourceSpec
from wf2wf.exporters.cwl import from_workflow


def _read_yaml_skip_shebang(p: Path):
    with p.open() as f:
        first = f.readline()
        if first.startswith("#!"):
            return yaml.safe_load(f.read())
        f.seek(0)
        return yaml.safe_load(f.read())


def test_export_when_and_scatter(persistent_test_output):
    # Build IR with scatter + when
    wf = Workflow(name="adv_export")

    scatter_task = Task(
        id="scatter_step",
        command="echo scatter",
        scatter=ScatterSpec(
            scatter=["input_file"], scatter_method="nested_crossproduct"
        ),
        resources=ResourceSpec(cpu=1),
    )

    when_task = Task(
        id="maybe_step",
        command="echo maybe",
        when="$context.run_optional == true",
        resources=ResourceSpec(cpu=1),
    )

    wf.add_task(scatter_task)
    wf.add_task(when_task)
    wf.add_edge("scatter_step", "maybe_step")

    out_file = persistent_test_output / "adv_export.cwl"
    from_workflow(wf, out_file, verbose=True)

    cwl_doc = _read_yaml_skip_shebang(out_file)

    # Confirm requirements present
    req_classes = {r["class"] for r in cwl_doc["requirements"]}
    assert "ConditionalWhenRequirement" in req_classes
    assert "ScatterFeatureRequirement" in req_classes

    step_scatter = cwl_doc["steps"]["scatter_step"]
    assert step_scatter["scatter"] == ["input_file"]
    assert step_scatter["scatterMethod"] == "nested_crossproduct"

    step_when = cwl_doc["steps"]["maybe_step"]
    assert step_when["when"] == "$context.run_optional == true"
