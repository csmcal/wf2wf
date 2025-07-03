import os
import shutil
import subprocess
import json
from pathlib import Path
import pytest
import importlib

from types import SimpleNamespace

pytestmark = pytest.mark.skipif(
    os.environ.get("WF2WF_WET", "0") != "1",
    reason="Wet-run tests require WF2WF_WET=1 and the full toolchain installed",
)


def _have_tool(name: str) -> bool:
    """Return True if *name* exists on PATH and, for docker, the daemon is reachable."""
    if shutil.which(name) is None:
        return False

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

    # Set env var so subprocesses inherit cache path
    monkeypatch.setenv("WF2WF_CACHE_DIR", str(cache_root))

    env_mod = importlib.import_module("wf2wf.environ")
    monkeypatch.setattr(env_mod, "_CACHE_DIR", cache_root, raising=False)
    monkeypatch.setattr(
        env_mod, "_INDEX_FILE", cache_root / "env_index.json", raising=False
    )

    yield SimpleNamespace(cache=cache_root)


def test_conda_to_image_pipeline(tmp_path: Path, _isolate_cache):
    """Full end-to-end build: conda-lock → OCI → SBOM → SIF."""

    # Skip early if essential external tools are missing
    required = ["conda-lock", "micromamba", "docker", "syft", "apptainer"]
    missing = [t for t in required if not _have_tool(t)]
    if missing:
        import warnings

        warnings.warn(
            f"Wet-run skipped: missing external tools: {', '.join(missing)}",
            RuntimeWarning,
            stacklevel=2,
        )
        pytest.skip("External tools unavailable")

    # ------------------------------------------------------------------
    # 1. Create tiny Conda env YAML and Snakefile in temp dir
    # ------------------------------------------------------------------
    env_yaml = tmp_path / "env.yaml"
    env_yaml.write_text(
        """
        name: test
        channels:
          - defaults
        dependencies:
          - python=3.11
        """
    )

    snakefile = tmp_path / "Snakefile"
    snakefile.write_text(
        f"""
rule test:
    input:
        "input.txt"
    output:
        "output.txt"
    conda:
        "{env_yaml.name}"
    shell:
        "cp {{input}} {{output}}"
"""
    )

    # Dummy input file
    (tmp_path / "input.txt").write_text("hello\n")

    # ------------------------------------------------------------------
    # 2. Run wf2wf convert with real build flags
    # ------------------------------------------------------------------
    out_ga = tmp_path / "flow.ga"

    cmd = [
        "wf2wf",
        "convert",
        "--input",
        str(snakefile),
        "--in-format",
        "snakemake",
        "--out",
        str(out_ga),
        "--out-format",
        "galaxy",
        "--auto-env",
        "build",
        "--push-registry",
        "",  # local daemon only
        "--confirm-push",
        "--sbom",
        "--apptainer",
        "--platform",
        "linux/amd64",
    ]

    env = os.environ.copy()
    env["WF2WF_ENVIRON_DRYRUN"] = "0"

    subprocess.check_call(cmd, env=env)

    # ------------------------------------------------------------------
    # 3. Assert artefacts exist: GA file, SBOM json & SIF under cache
    # ------------------------------------------------------------------
    assert out_ga.exists(), "Galaxy workflow not generated"

    from wf2wf.environ import _CACHE_DIR

    sboms = list(_CACHE_DIR.glob("*.sbom.json"))
    sifs = list((_CACHE_DIR / "sif").glob("*.sif"))

    assert sboms, "SBOM file missing"
    assert sifs, "SIF file missing"

    # ------------------------------------------------------------------
    # 4. Verify SBOM/SIF paths are embedded in Galaxy workflow JSON
    # ------------------------------------------------------------------
    ga_doc = json.loads(out_ga.read_text())
    steps = ga_doc.get("steps", {})
    assert steps, "No steps in GA doc"

    found_sif = found_sbom = False
    for st in steps.values():
        if "wf2wf_sif" in st:
            found_sif = True
        if "wf2wf_sbom" in st:
            found_sbom = True

    assert found_sif, "SIF reference not embedded in Galaxy step"
    assert found_sbom, "SBOM reference not embedded in Galaxy step"

    # Ensure no artefacts leaked into project root
    repo_root = Path.cwd()
    leaks = list(repo_root.glob("*.tar.gz")) + list(repo_root.glob("*.sif"))
    assert not leaks, f"Artefacts leaked into repo root: {leaks}"
