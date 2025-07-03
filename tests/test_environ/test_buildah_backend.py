import shutil
from pathlib import Path
import tarfile

from wf2wf.environ import build_oci_image


def _make_dummy_tarball(tmp_path: Path) -> Path:
    tarball = tmp_path / "env.tar.gz"
    with tarfile.open(tarball, "w:gz") as tf:
        # add tiny file to tar
        tmp_file = tmp_path / "dummy.txt"
        tmp_file.write_text("hello")
        tf.add(tmp_file, arcname="dummy.txt")
    return tarball


def test_buildah_backend_dry_run(tmp_path, monkeypatch):
    """build_oci_image should return sensible tag+digest with buildah backend in dry-run mode."""
    tarball = _make_dummy_tarball(tmp_path)

    # Pretend buildah exists but we still run dry_run=True so no subprocesses invoked
    monkeypatch.setattr(
        shutil,
        "which",
        lambda n: "/usr/bin/buildah" if n == "buildah" else shutil.which(n),
        raising=False,
    )

    tag, digest = build_oci_image(tarball, backend="buildah", dry_run=True)

    assert tag.startswith("wf2wf/env:"), tag
    assert digest.startswith("sha256") or digest == tag
