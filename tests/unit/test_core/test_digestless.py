import json
import importlib
import shutil


def test_generate_sbom_digestless(monkeypatch, tmp_path):
    """generate_sbom should work when image ref is just a tag (no digest)."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("WF2WF_CACHE_DIR", str(cache_dir))
    env_mod = importlib.reload(importlib.import_module("wf2wf.environ"))
    generate_sbom = env_mod.generate_sbom

    # Ensure syft absent to exercise stub path but with tag reference
    monkeypatch.setattr(
        shutil,
        "which",
        lambda n: None if n == "syft" else shutil.which(n),
        raising=False,
    )

    ref = "myorg/myimg:latest"  # tag only
    sbom = generate_sbom(ref, dry_run=False)
    data = json.loads(sbom.read_text())
    assert data["name"] == ref
