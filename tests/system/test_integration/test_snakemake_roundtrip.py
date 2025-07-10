import pytest
import pathlib
from wf2wf.importers import snakemake as sm_importer
from wf2wf.core import Workflow

# Get the project root directory (where this test file is located)
PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent

# Collect all .smk files from the example directories
EXAMPLE_DIRS = [
    PROJECT_ROOT / "examples/snake/basic",
    PROJECT_ROOT / "examples/snake/advanced", 
    PROJECT_ROOT / "examples/snake/full_workflow",
    PROJECT_ROOT / "examples/snake/error_handling",
]

ALL_SNAKEMAKE_FILES = []
for d in EXAMPLE_DIRS:
    if d.exists():
        ALL_SNAKEMAKE_FILES.extend(sorted(str(f) for f in d.glob("*.smk")))

# Mark error-handling examples for expected failure or warning
ERROR_CASES = {
    str(PROJECT_ROOT / "examples/snake/error_handling/error.smk"),
    str(PROJECT_ROOT / "examples/snake/error_handling/circular_dep.smk"),
    str(PROJECT_ROOT / "examples/snake/error_handling/unsupported.smk"),
    str(PROJECT_ROOT / "examples/snake/error_handling/empty.smk"),
}

@pytest.mark.parametrize("snakefile", ALL_SNAKEMAKE_FILES)
def test_snakemake_import_and_roundtrip(snakefile, tmp_path):
    """
    Import each Snakemake example to IR, validate, and for non-error cases, roundtrip and check IR equivalence.
    """
    # Arrange: copy any needed input files to tmp_path
    # (For now, assume all needed files are in the example tree)
    
    # Act: Import to IR
    try:
        wf: Workflow = sm_importer.to_workflow(snakefile, workdir=tmp_path)
        wf.validate()
    except Exception as e:
        if snakefile in ERROR_CASES:
            pytest.skip(f"Known error case: {snakefile} ({e})")
        else:
            raise
    
    # For error cases, stop here
    if snakefile in ERROR_CASES:
        return
    
    # Export to JSON and re-import (roundtrip)
    wf_json = wf.to_json()
    wf2 = Workflow.from_json(wf_json)
    wf2.validate()
    
    # Check basic equivalence (structure, task count, edge count)
    assert wf.name == wf2.name
    assert set(wf.tasks.keys()) == set(wf2.tasks.keys())
    assert len(wf.edges) == len(wf2.edges)
    # Optionally, check more fields or do a deep comparison
    # (allowing for known loss-mapping if needed) 