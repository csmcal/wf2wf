"""Integration-style test exercising Snakemake importer ➜ DAGMan exporter path.

We mock out external `snakemake` CLI calls so that no real Snakemake
installation is required.
"""

from unittest.mock import patch, MagicMock
import sys
import pathlib

# Ensure local package import
proj_root = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(proj_root))

from wf2wf.importers import snakemake as sm_importer
from wf2wf.exporters import dagman as dag_exporter
from wf2wf.core import Workflow


LINEAR_DOT_OUTPUT = """digraph snakemake_dag {
0 [label=\"rule rule_a\"];
1 [label=\"rule rule_b\"];
2 [label=\"rule rule_c\"];
0 -> 1
1 -> 2
}\n"""

LINEAR_DRYRUN_OUTPUT = """Building DAG of jobs...
rule rule_a:
    input: start.txt
    output: A.txt
    jobid: 0
    resources: tmpdir=</tmp>
rule rule_b:
    input: A.txt
    output: B.txt
    jobid: 1
    resources: tmpdir=</tmp>
rule rule_c:
    input: B.txt
    output: C.txt
    jobid: 2
    resources: tmpdir=</tmp>
Nothing to be done.\n"""


def _mock_run(cmd, capture_output=False, text=False, check=False, **kwargs):
    """Return canned stdout for --dag and --dry-run commands."""
    m = MagicMock()
    " ".join(cmd)
    if "--dag" in cmd:
        m.stdout = LINEAR_DOT_OUTPUT
        m.stderr = ""
        m.returncode = 0
    elif "--dry-run" in cmd:
        m.stdout = LINEAR_DRYRUN_OUTPUT
        m.stderr = ""
        m.returncode = 0
    else:
        m.stdout = ""
        m.stderr = ""
        m.returncode = 0
    return m


@patch("wf2wf.importers.snakemake.shutil.which", lambda x: "/usr/bin/snakemake")
@patch("wf2wf.importers.snakemake.subprocess.run", side_effect=_mock_run)
def test_linear_pipeline(mock_subproc_run, tmp_path):
    # Arrange – copy sample Snakefile
    snakefile = proj_root / "examples" / "snake" / "basic" / "linear.smk"

    # Snakemake workflow expects a start.txt, create placeholder
    (tmp_path / "start.txt").write_text("dummy\n")

    # Act – import to Workflow
    wf: Workflow = sm_importer.to_workflow(str(snakefile), workdir=str(tmp_path))

    # Simple structural checks
    assert len(wf.tasks) == 3
    # assert any(t.id == "rule_a_0" or t.id.startswith("rule_a") for t in wf.tasks.values())

    # Check edges in IR
    def _clean(s: str) -> str:
        return s.replace("rule ", "").replace("rule_", "", 1)

    edges = {(_clean(e.parent), _clean(e.child)) for e in wf.edges}
    assert ("a_0", "b_1") in edges or ("rule_a_0", "rule_b_1") in {
        (e.parent, e.child) for e in wf.edges
    }

    # Export to DAGMan
    dag_path = tmp_path / "linear.dag"
    dag_exporter.from_workflow(wf, dag_path, workdir=tmp_path)

    # Assert outputs
    assert dag_path.exists()
    txt = dag_path.read_text()

    # Condor job names are sanitized task IDs; verify dependency line exists
    assert (
        "PARENT rule_a_0 CHILD rule_b_1" in txt
        or "PARENT rule_rule_a_0 CHILD rule_rule_b_1" in txt
    )

    # Add new test
    # ... (existing code)

    # ... (rest of the existing code)
