import json
from wf2wf.core import Workflow, Task, ResourceSpec
from wf2wf.exporters import cwl as cwl_exporter


def test_loss_report_generation(tmp_path):
    task = Task(id="gpu_task", resources=ResourceSpec(gpu=1, gpu_mem_mb=1024))
    wf = Workflow(name="lossy", tasks={task.id: task})

    out_file = tmp_path / "wf.cwl"
    cwl_exporter.from_workflow(wf, out_file=out_file, single_file=True, verbose=False)

    loss_path = out_file.with_suffix(".loss.json")
    assert loss_path.exists(), "Loss report not generated"
    doc = json.loads(loss_path.read_text())
    entries = doc["entries"]
    assert any("GPU resource" in e["reason"] for e in entries)
