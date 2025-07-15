import os
import shutil
import subprocess
from pathlib import Path
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("WF2WF_WET", "0") != "1",
    reason="Wet-run tests require WF2WF_WET=1 and external tools installed",
)

def _have_tool(name: str) -> bool:
    """Return True if *name* exists on PATH and, for docker, the daemon is reachable."""
    if shutil.which(name) is None:
        return False
    if name == "docker":
        try:
            subprocess.check_output([
                "docker", "info"], stderr=subprocess.STDOUT, timeout=10
            )
        except Exception:
            return False
    return True

from wf2wf.importers import snakemake as sm_importer
from wf2wf.core import Workflow

class TestSnakemakeImporterDockerCondaIntegration:
    """Test Snakemake importer with Docker/Conda integration.
    These tests require Docker and/or Conda to be available.
    They are marked as wet/integration tests and can be skipped in basic CI.
    """

    @pytest.mark.integration
    @pytest.mark.skipif(not _have_tool("docker"), reason="Docker not available")
    def test_docker_container_workflow(self, tmp_path):
        """Test importing a workflow with Docker containers."""
        # Create a simple Snakefile with Docker container
        snakefile = tmp_path / "docker_test.smk"
        snakefile.write_text("""
rule test_docker:
    input: "input.txt"
    output: "output.txt"
    container: "docker://ubuntu:20.04"
    shell: "echo 'docker test' > {output}"
        """)
        # Create input file
        input_file = tmp_path / "input.txt"
        input_file.write_text("test input")
        # Import workflow
        workflow = sm_importer.to_workflow(snakefile, workdir=tmp_path)
        # Basic validation
        assert isinstance(workflow, Workflow)
        assert "test_docker" in workflow.tasks
        workflow.validate()

    @pytest.mark.integration
    @pytest.mark.skipif(not _have_tool("conda") and not _have_tool("mamba"), reason="Conda not available")
    def test_conda_environment_workflow(self, tmp_path):
        """Test importing a workflow with Conda environments."""
        # Create a simple Snakefile with Conda environment
        snakefile = tmp_path / "conda_test.smk"
        snakefile.write_text("""
rule test_conda:
    input: "input.txt"
    output: "output.txt"
    conda: "environment.yaml"
    shell: "echo 'conda test' > {output}"
        """)
        # Create environment file
        env_file = tmp_path / "environment.yaml"
        env_file.write_text("""
name: test_env
channels:
  - conda-forge
dependencies:
  - python=3.9
        """)
        # Create input file
        input_file = tmp_path / "input.txt"
        input_file.write_text("test input")
        # Import workflow
        workflow = sm_importer.to_workflow(snakefile, workdir=tmp_path)
        # Basic validation
        assert isinstance(workflow, Workflow)
        assert "test_conda" in workflow.tasks
        workflow.validate() 