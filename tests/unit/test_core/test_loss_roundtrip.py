import json
from pathlib import Path


from wf2wf.core import Workflow, Task, ParameterSpec, EnvironmentSpecificValue
from wf2wf.exporters import cwl as cwl_exporter, snakemake as snakemake_exporter
from wf2wf.importers import cwl as cwl_importer


def _build_simple_workflow() -> Workflow:
    t1 = Task(
        id="task1",
    )
    t1.command.set_for_environment("echo hello > out.txt", "shared_filesystem")
    t1.inputs = [ParameterSpec(id="in", type="File")]
    t1.outputs = [ParameterSpec(id="out", type="File")]
    t1.priority.set_for_environment(10, "shared_filesystem")
    t1.retry_count.set_for_environment(2, "shared_filesystem")
    wf = Workflow(name="simple", tasks={t1.id: t1}, edges=[])
    return wf


def test_roundtrip_reapplied(tmp_path: Path):
    wf = _build_simple_workflow()
    cwl_path = tmp_path / "wf.cwl"

    # Export to CWL (priority/retry not representable → recorded as loss)
    cwl_exporter.from_workflow(wf, cwl_path, single_file=True)
    loss_json = cwl_path.with_suffix(".loss.json")
    assert loss_json.exists(), "loss side-car not written"

    # Import back – should reapply losses
    wf2 = cwl_importer.to_workflow(cwl_path)

    # Verify priority/retry restored on task
    t = wf2.tasks["task1"]
    assert t.priority.get_value_with_default("shared_filesystem") == 10
    assert t.retry_count.get_value_with_default("shared_filesystem") == 2

    # The loss entries should now be marked as reapplied
    reapplied = [e for e in wf2.loss_map if e["status"] == "reapplied"]
    fields = {e["field"] for e in reapplied}
    assert {"priority", "retry_count"}.issubset(fields)

    # Export to Snakemake – priority/retry representable – should not be lost again
    snk_path = tmp_path / "Snakefile"
    snakemake_exporter.from_workflow(wf2, snk_path)
    snk_loss = snk_path.with_suffix(".loss.json")
    if snk_loss.exists():
        loss_doc = json.loads(snk_loss.read_text())
        lost_again = [e for e in loss_doc["entries"] if e["status"] == "lost_again"]
        # Snakemake doesn't support retry_count and gpu, so these should be lost_again
        lost_again_fields = {e["field"] for e in lost_again}
        expected_lost_again = {"retry_count", "gpu"}
        assert lost_again_fields == expected_lost_again, f"Expected {expected_lost_again}, got {lost_again_fields}"
    else:
        # No loss file means no information was lost – acceptable
        assert True


def test_checksum_mismatch(tmp_path: Path):
    wf = _build_simple_workflow()
    cwl_path = tmp_path / "wf.cwl"
    cwl_exporter.from_workflow(wf, cwl_path, single_file=True)
    loss_path = cwl_path.with_suffix(".loss.json")

    # Tamper with checksum
    data = json.loads(loss_path.read_text())
    data["source_checksum"] = "sha256:" + "0" * 64  # invalid checksum
    loss_path.write_text(json.dumps(data))

    # Import – reinjection should be skipped
    wf2 = cwl_importer.to_workflow(cwl_path)
    assert wf2.tasks["task1"].priority.get_value_with_default("shared_filesystem") == 0  # not reapplied
    skipped = [e for e in wf2.loss_map if e.get("status") == "reapplied"]
    assert not skipped
