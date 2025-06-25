import json
from pathlib import Path

from wf2wf.core import Workflow, Task, ParameterSpec
from wf2wf.exporters import load as load_exporter


def _dummy_workflow() -> Workflow:
    wf = Workflow(name="dummy", version="1.0", doc="Example workflow")
    # Inputs / outputs
    wf.inputs.append(ParameterSpec(id="input_file", type="File"))
    wf.outputs.append(ParameterSpec(id="result_file", type="File"))

    # Single task
    task = Task(id="step_1", command="echo hello > result.txt")
    task.inputs.append(ParameterSpec(id="input_file", type="File"))
    task.outputs.append(ParameterSpec(id="result_file", type="File"))
    wf.add_task(task)
    return wf


def test_bco_export(tmp_path: Path):
    wf = _dummy_workflow()
    out_path = tmp_path / "workflow.bco.json"

    bco_exporter = load_exporter('bco')
    bco_exporter.from_workflow(wf, out_path)

    # Verify file written and basic structure
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert data["$schema"].startswith("https://")
    assert data["provenance_domain"]["name"] == "dummy"
    assert data["io_domain"]["input_subdomain"][0]["id"] == "input_file"
    assert data["io_domain"]["output_subdomain"][0]["id"] == "result_file"
    # New domains
    assert data["parametric_domain"][0]["param"] == "input_file"
    assert len(data["usability_domain"]) > 0 


def test_bco_with_cwl_package(tmp_path: Path):
    wf = _dummy_workflow()
    bco_path = tmp_path / "wf.bco.json"

    bco_exporter = load_exporter('bco')
    bco_exporter.from_workflow(wf, bco_path, include_cwl=True, package=True)

    # Verify files
    assert bco_path.exists()
    cwl_path = bco_path.with_suffix('.cwl')
    assert cwl_path.exists()
    pkg_path = bco_path.with_suffix('.tar.gz')
    assert pkg_path.exists()


def test_fda_submission_bundle(tmp_path: Path):
    """Smoke‐test generation of FDA submission package."""
    from wf2wf.exporters.bco import generate_fda_submission_package

    wf = _dummy_workflow()
    tar_path = tmp_path / "submission.tar.gz"

    out = generate_fda_submission_package(wf, tar_path, verbose=True)

    # Verify
    assert out.exists()
    import tarfile

    with tarfile.open(out, "r:gz") as tar:
        members = [m.name for m in tar.getmembers()]
        assert any(name.endswith(".bco.json") for name in members)
        assert any(name.endswith(".cwl") for name in members)
        assert "validation.txt" in members
        assert "README.txt" in members 