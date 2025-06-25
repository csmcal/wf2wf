# tests/test_environ/test_buildx_remote_cache.py
import tempfile, tarfile, shutil
from pathlib import Path
from wf2wf.environ import build_oci_image


def _tarball(tmp: Path) -> Path:
    t = tmp / "env.tar.gz"
    with tarfile.open(t, "w:gz") as tf:
        f = tmp / "dummy.txt"
        f.write_text("x")
        tf.add(f, arcname="dummy.txt")
    return t


def test_buildx_remote_cache_dry_run(tmp_path, monkeypatch):
    tarball = _tarball(tmp_path)
    # Pretend docker exists, but keep dry_run=True
    monkeypatch.setattr(shutil, "which",
                        lambda n: "/usr/bin/docker" if n == "docker" else shutil.which(n),
                        raising=False)

    tag, digest = build_oci_image(
        tarball,
        backend="buildx",
        build_cache="example.com/cache:wf2wf",
        dry_run=True,
    )
    assert tag.startswith("wf2wf/env:")
    assert digest.startswith("sha256")