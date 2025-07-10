# tests/test_environ/test_syft_failure.py
import importlib
import subprocess
import json
import shutil


def test_syft_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("WF2WF_CACHE_DIR", str(tmp_path))
    env_mod = importlib.reload(importlib.import_module("wf2wf.environ"))
    generate_sbom = env_mod.generate_sbom

    # Make syft lookup succeed but the call fail
    monkeypatch.setattr(
        shutil, "which", lambda n: "/usr/bin/syft" if n == "syft" else shutil.which(n)
    )

    def fail(*a, **k):
        raise subprocess.CalledProcessError(1, a)

    monkeypatch.setattr(subprocess, "check_call", fail)

    sbom = generate_sbom("busybox:latest", dry_run=False)
    data = json.loads(sbom.read_text())
    assert data["packages"] == []
