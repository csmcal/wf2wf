from pathlib import Path
from wf2wf.environ import convert_to_sif, generate_sbom

def test_convert_to_sif_and_sbom(tmp_path: Path):
    image_ref = "wf2wf/env:test"
    sif = convert_to_sif(image_ref, sif_dir=tmp_path, dry_run=True)
    assert sif.exists()
    assert sif.read_bytes() == b"SIF_DRYRUN"

    sbom = generate_sbom(image_ref, out_dir=tmp_path, dry_run=True)
    assert sbom.exists()
    import json
    data = json.loads(sbom.read_text())
    assert data["name"] == image_ref 