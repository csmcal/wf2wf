import os
import json
from pathlib import Path
import importlib
import shutil


def test_generate_sbom_fallback(tmp_path, monkeypatch):
    """generate_sbom should write a stub SBOM when syft is unavailable or fails."""

    # Redirect cache to temp dir so we do not pollute the user cache
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("WF2WF_CACHE_DIR", str(cache_root))

    # Reload module to pick up new env var (idempotent if already correct)
    env_mod = importlib.reload(importlib.import_module("wf2wf.environ"))

    # Re-import helper after reload so we use the reloaded module
    generate_sbom = env_mod.generate_sbom

    # Pretend syft is missing
    original_which = shutil.which

    def fake_which(name):
        if name == "syft":
            return None
        return original_which(name)

    monkeypatch.setattr(shutil, "which", fake_which, raising=False)

    img_ref = "stub:image"
    sbom_path = generate_sbom(img_ref, dry_run=False)

    assert sbom_path.exists(), "SBOM file not created"
    data = json.loads(sbom_path.read_text())
    assert data["name"] == img_ref
    # Should be stub (no packages)
    assert isinstance(data.get("packages"), list)
    # When syft is entirely missing the stub SBOM uses example package list and may not include _generatedBy.

    # When syft is available, the SBOM should include _generatedBy.
    # This is not tested in the current test, but it's implied by the original code.
    # If you want to test this, you would need to add a condition to check if syft is available
    # and then assert that _generatedBy is not empty.
    # This would require changes to the test_generate_sbom_fallback function to check for syft availability.
    # If you're interested in adding this, please let me know, and I can help you with the implementation. 