from pathlib import Path
from wf2wf.environ import build_oci_image


def test_build_oci_image(tmp_path: Path):
    # Create dummy tarball
    tarball = tmp_path / "dummy.tar.gz"
    tarball.write_bytes(b"dummy")

    tag, digest = build_oci_image(tarball, dry_run=True)
    assert tag.startswith("wf2wf/env:")
    assert digest.startswith("sha256:")
