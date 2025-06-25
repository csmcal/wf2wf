import os
import shutil
import subprocess
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("WF2WF_WET", "0") != "1",
    reason="Wet-run tests require WF2WF_WET=1 and external tools installed",
)


def _have_tool(name: str) -> bool:
    """Return True if *name* exists on PATH and, for docker, the daemon is reachable."""
    # Check binary exists
    if shutil.which(name) is None:
        return False

    # Additional connectivity test for Docker
    if name == "docker":
        try:
            subprocess.check_output(
                ["docker", "info"], stderr=subprocess.STDOUT, timeout=10
            )
        except Exception:
            return False

    return True


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Redirect wf2wf cache (~/.cache/wf2wf) into the test temp directory."""
    cache_root = tmp_path / "wf2wf_cache"
    cache_root.mkdir()

    # Ensure subprocesses also use the same cache by setting env variable
    monkeypatch.setenv("WF2WF_CACHE_DIR", str(cache_root))
    # For the current process (already imported modules) also patch attributes
    import importlib

    env_mod = importlib.import_module("wf2wf.environ")
    monkeypatch.setattr(env_mod, "_CACHE_DIR", cache_root, raising=False)
    monkeypatch.setattr(env_mod, "_INDEX_FILE", cache_root / "env_index.json", raising=False)

    yield SimpleNamespace(cache=cache_root)


def test_buildx_pipeline_without_sif(tmp_path: Path, _isolate_cache):
    """Build OCI image with Docker Buildx, generate SBOM, no Apptainer."""

    required = ["docker", "conda-lock", "micromamba", "syft"]
    missing = [t for t in required if not _have_tool(t)]
    if missing:
        import warnings

        warnings.warn(
            f"Wet-run skipped: missing external tools: {', '.join(missing)}",
            RuntimeWarning,
        )
        pytest.skip("External tools unavailable")

    # Create minimal env yaml & Snakefile
    env_yaml = tmp_path / "env.yaml"
    env_yaml.write_text(
        """
        name: test
        channels: [defaults]
        dependencies: [python=3.11]
        """
    )

    snakefile = tmp_path / "Snakefile"
    snakefile.write_text(
        f"""
rule buildx_test:
    input:
        "in.txt"
    output:
        "out.txt"
    conda:
        "{env_yaml.name}"
    shell:
        "cp {{input}} {{output}}"
"""
    )

    (tmp_path / "in.txt").write_text("hello\n")

    out_cwl = tmp_path / "flow.cwl"  # use CWL export for variety

    wf2wf_bin = shutil.which("wf2wf")
    cmd = (
        [wf2wf_bin]
        if wf2wf_bin
        else [sys.executable, "-m", "wf2wf"]
    ) + [
        "convert",
        "--input",
        str(snakefile),
        "--in-format",
        "snakemake",
        "--out",
        str(out_cwl),
        "--out-format",
        "cwl",
        "--auto-env",
        "build",
        "--sbom",
        "--platform",
        "linux/amd64",
    ]

    env = os.environ.copy()
    env["WF2WF_ENVIRON_DRYRUN"] = "0"

    subprocess.check_call(cmd, env=env)

    # Assertions
    assert out_cwl.exists(), "CWL workflow not generated"

    from wf2wf.environ import _CACHE_DIR

    sboms = list(_CACHE_DIR.glob("*.sbom.json"))
    assert sboms, "SBOM not generated"

    # Ensure no SIFs (since we didn't request --apptainer)
    sifs = list((_CACHE_DIR / "sif").glob("*.sif"))
    assert not sifs, "Unexpected SIF generated"

    # Verify SBOM reference embedded in CWL (simple text check)
    cwl_text = out_cwl.read_text()
    assert "wf2wf_sbom" in cwl_text, "SBOM hint missing in CWL output" 