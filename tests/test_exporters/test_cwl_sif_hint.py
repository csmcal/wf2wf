# tests/test_exporters/test_cwl_sif_hint.py
from wf2wf.core import Workflow, Task, EnvironmentSpec
from wf2wf.exporters.cwl import from_workflow


def test_cwl_sif_hint(tmp_path):
    wf = Workflow(name="wf")
    t = Task(
        id="t1",
        command="echo hi",
        environment=EnvironmentSpec(
            container="docker://busybox",
            env_vars={"WF2WF_SIF": "/cvmfs/imgs/abc.sif"},
        ),
    )
    wf.add_task(t)
    out = tmp_path / "wf.cwl"
    from_workflow(wf, out, tools_dir="tools", format="yaml", verbose=False)
    txt = out.read_text()
    assert "wf2wf_sif" in txt
