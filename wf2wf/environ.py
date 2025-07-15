"""wf2wf.environ – environment-build helpers (Phase 2)

This initial slice implements §9.2.1-9.2.2 of the design draft:
    • Generate a deterministic *lock hash* from a Conda YAML file.
    • Create a relocatable tarball (stand-in for conda-pack) so downstream
      exporters can reference a stable artefact even where Conda tooling is
      unavailable in the test environment.

Real micromamba/conda-pack execution will be wired in later; for now we
simulate the build while preserving the critical interface and metadata.
"""

from __future__ import annotations

import hashlib
import tarfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Callable
import json
import subprocess
import os
import tempfile
import random
import string
import shutil
import time
import itertools
import textwrap
import logging
import re

import yaml

from wf2wf.core import Task, Workflow, EnvironmentSpecificValue, CheckpointSpec, LoggingSpec, SecuritySpec, NetworkingSpec, MetadataSpec

logger = logging.getLogger(__name__)

__all__ = [
    "generate_lock_hash",
    "prepare_env",
    "pack_conda_environment",
    "generate_conda_activation_script",
    "OCIBuilder",
    "DockerBuildxBuilder",
    "BuildahBuilder",
    "build_oci_image",
    "generate_sbom",
    "convert_to_sif",
    "build_or_reuse_env_image",
    "prune_cache",
    "is_docker_available",
    "check_docker_image_exists",
    "build_docker_image_from_conda_env",
    "push_docker_image",
    "build_and_push_conda_env_images",
    "convert_docker_images_to_apptainer",
    "normalize_container_spec",
    "extract_sbom_path",
    "extract_sif_path",
    "extract_sbom_digest",
    "format_container_for_target_format",
    "get_environment_metadata",
    "EnvironmentManager",
    "detect_and_parse_environments",
    "infer_missing_environments",
    "prompt_for_missing_environments",
    "build_environment_images",
    "adapt_environments_for_target",
]


_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "wf2wf" / "envs"
# Allow overriding cache directory (helps test isolation and CI sandboxing)
_CACHE_DIR = Path(os.getenv("WF2WF_CACHE_DIR", str(_DEFAULT_CACHE_DIR))).expanduser()
_INDEX_FILE = _CACHE_DIR / "env_index.json"


def is_docker_available() -> bool:
    """Check if Docker is both installed and the daemon is running."""
    if not shutil.which("docker"):
        return False
    
    try:
        subprocess.run(
            ["docker", "info"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            timeout=5
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_docker_image_exists(image_url: str, *, verbose: bool = False) -> bool:
    """Check if a Docker image exists in a remote registry using docker manifest inspect."""
    if not is_docker_available():
        if verbose:
            print("Docker not available, cannot check image existence")
        return False
    
    try:
        subprocess.run(
            ["docker", "manifest", "inspect", image_url],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def build_docker_image_from_conda_env(
    env_yaml_path: Path,
    image_url: str,
    *,
    verbose: bool = False,
    debug: bool = False,
    dry_run: bool = False,
) -> bool:
    """
    Build a Docker image from a conda environment YAML file.
    
    Args:
        env_yaml_path: Path to the conda environment YAML file
        image_url: Full Docker image URL (registry/repo:tag)
        verbose: Enable verbose output
        debug: Enable debug output
        dry_run: If True, only show what would be done without actually building
        
    Returns:
        True if build was successful, False otherwise
    """
    if not is_docker_available():
        print("❌ Docker not available. Cannot build image.")
        return False
    
    if dry_run:
        print(f"DRY RUN: Would build Docker image {image_url} from {env_yaml_path}")
        return True
    
    print(f"Building Docker image: {image_url}")
    
    # Create temporary build context
    with tempfile.TemporaryDirectory() as build_context:
        build_context_path = Path(build_context)
        
        if debug:
            print(f"DEBUG: Using build context: {build_context_path}")
        
        # Copy env file to build context
        shutil.copy(env_yaml_path, build_context_path)
        
        # Generate Dockerfile
        dockerfile_content = f"""
FROM continuumio/miniconda3:latest

# Copy the environment file
COPY {env_yaml_path.name} /tmp/environment.yml

# Create the conda environment
RUN conda env create -f /tmp/environment.yml

# Make RUN commands use the new environment
SHELL ["conda", "run", "-n", "{env_yaml_path.stem}", "/bin/bash", "-c"]

# The code to run when container is started
ENTRYPOINT ["conda", "run", "-n", "{env_yaml_path.stem}"]
"""
        
        dockerfile_path = build_context_path / "Dockerfile"
        dockerfile_path.write_text(textwrap.dedent(dockerfile_content))
        
        if debug:
            print(f"DEBUG: Generated Dockerfile at {dockerfile_path}")
            print(f"DEBUG: Dockerfile contents:\n{dockerfile_path.read_text()}")
        
        # Build the image
        try:
            build_cmd = ["docker", "build", "-t", image_url, "."]
            if debug:
                print(f"DEBUG: Build command: {' '.join(build_cmd)}")
            
            proc = subprocess.Popen(
                build_cmd,
                cwd=build_context_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            
            if verbose or debug:
                for line in iter(proc.stdout.readline, ""):
                    prefix = "DEBUG: " if debug else "    "
                    print(f"{prefix}{line.strip()}")
            else:
                proc.communicate()  # Wait for completion without showing output
            
            proc.wait()
            if proc.returncode != 0:
                print(f"❌ Docker build failed for {image_url}")
                return False
            
            print(f"✅ Docker build successful: {image_url}")
            return True
            
        except Exception as e:
            print(f"❌ Unexpected error during Docker build: {e}")
            if debug:
                import traceback
                print(f"DEBUG: Full traceback:\n{traceback.format_exc()}")
            return False


def push_docker_image(
    image_url: str,
    *,
    verbose: bool = False,
    debug: bool = False,
    dry_run: bool = False,
) -> bool:
    """
    Push a Docker image to a registry.
    
    Args:
        image_url: Full Docker image URL (registry/repo:tag)
        verbose: Enable verbose output
        debug: Enable debug output
        dry_run: If True, only show what would be done without actually pushing
        
    Returns:
        True if push was successful, False otherwise
    """
    if not is_docker_available():
        print("❌ Docker not available. Cannot push image.")
        return False
    
    if dry_run:
        print(f"DRY RUN: Would push Docker image {image_url}")
        return True
    
    print(f"Pushing Docker image: {image_url}")
    
    try:
        push_cmd = ["docker", "push", image_url]
        if debug:
            print(f"DEBUG: Push command: {' '.join(push_cmd)}")
        
        proc = subprocess.Popen(
            push_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        
        if verbose or debug:
            for line in iter(proc.stdout.readline, ""):
                prefix = "DEBUG: " if debug else "    "
                print(f"{prefix}{line.strip()}")
        else:
            proc.communicate()  # Wait for completion without showing output
        
        proc.wait()
        if proc.returncode != 0:
            print(f"❌ Docker push failed for {image_url}")
            print(f"Please ensure you are logged in to the registry and have push permissions.")
            return False
        
        print(f"✅ Docker push successful: {image_url}")
        return True
        
    except Exception as e:
        print(f"❌ Unexpected error during Docker push: {e}")
        if debug:
            import traceback
            print(f"DEBUG: Full traceback:\n{traceback.format_exc()}")
        return False


def build_and_push_conda_env_images(
    conda_envs: Dict[str, Dict[str, Any]],
    docker_registry: str,
    workflow_name: str = "workflow",
    *,
    verbose: bool = False,
    debug: bool = False,
    dry_run: bool = False,
) -> bool:
    """
    Build and push Docker images for multiple conda environments.
    
    Args:
        conda_envs: Dictionary mapping env paths to env info (with 'hash' key)
        docker_registry: Docker registry URL
        workflow_name: Name to use for the repository
        verbose: Enable verbose output
        debug: Enable debug output
        dry_run: If True, only show what would be done without actually building/pushing
        
    Returns:
        True if all operations were successful, False otherwise
    """
    if not conda_envs:
        if verbose:
            print("No conda environments found to build.")
        return True
    
    if verbose:
        print(f"Building Docker images for {len(conda_envs)} conda environments")
        print(f"Registry: {docker_registry}")
    
    # Sanitize workflow name for Docker repository
    repo_name = "".join(c for c in workflow_name.lower() if c.isalnum() or c in "-_")
    if not repo_name:
        repo_name = "workflow"
    
    success_count = 0
    total_count = len(conda_envs)
    
    for original_yaml_path, env_info in conda_envs.items():
        env_hash = env_info["hash"]
        image_name = f"{docker_registry}/{repo_name}"
        image_tag = env_hash
        full_image_url = f"{image_name}:{image_tag}"
        env_info["docker_image_url"] = full_image_url
        
        print(f"Processing environment '{Path(original_yaml_path).name}':")
        print(f"  Target image: {full_image_url}")
        
        if debug:
            print(f"DEBUG: Environment hash: {env_hash}")
            print(f"DEBUG: Repository name: {repo_name}")
        
        # Check if image already exists
        if check_docker_image_exists(full_image_url, verbose=verbose):
            print("  ✔ Image already exists in registry. Skipping build.")
            success_count += 1
            continue
        
        # Build the image
        if not build_docker_image_from_conda_env(
            Path(original_yaml_path),
            full_image_url,
            verbose=verbose,
            debug=debug,
            dry_run=dry_run,
        ):
            return False
        
        # Push the image
        if not push_docker_image(
            full_image_url,
            verbose=verbose,
            debug=debug,
            dry_run=dry_run,
        ):
            return False
        
        success_count += 1
    
    if verbose:
        print(f"✅ Successfully processed {success_count}/{total_count} environments")
    
    return success_count == total_count


def generate_lock_hash(env_yaml: Path) -> str:
    """Return **sha256** digest hex string of the Conda YAML *env_yaml*.

    The digest is calculated over the *normalised* file contents (strip CRLF,
    remove comment lines), ensuring platform-independent hashes.
    """
    txt = env_yaml.read_text(encoding="utf-8")
    norm = "\n".join(
        line for line in txt.splitlines() if not line.strip().startswith("#")
    )
    digest = hashlib.sha256(norm.encode()).hexdigest()
    return digest


# ---------------------------------------------------------------------------
# Data helper
# ---------------------------------------------------------------------------


class EnvBuildResult(Dict[str, Any]):
    """Typed dict holding build artefact information."""

    lock_hash: str  # sha256 hex of env YAML
    lock_file: Path  # path to lock file (currently original YAML copy)
    tarball: Path  # path to relocatable tarball


def prepare_env(
    env_yaml: Union[str, Path],
    *,
    cache_dir: Optional[Path] = None,
    verbose: bool = False,
    dry_run: Optional[bool] = None,
) -> EnvBuildResult:
    """Simulate environment build pipeline and return artefact locations.

    1. Compute lock hash from *env_yaml*.
    2. Copy YAML to a content-addressed location `<hash>.yaml` inside *cache_dir*.
    3. Create a tar.gz containing the YAML as a placeholder for a conda-pack
       archive and place it next to the lock file.

    The function is **idempotent**: repeated calls with the same YAML content
    return the same paths without rebuilding.
    """

    env_yaml = Path(env_yaml).expanduser().resolve()
    if not env_yaml.exists():
        raise FileNotFoundError(env_yaml)

    # Determine effective dry-run flag: explicit parameter overrides env var
    if dry_run is None:
        dry_run = os.environ.get("WF2WF_ENVIRON_DRYRUN", "1") != "0"

    cache_dir = cache_dir or _CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    lock_hash = generate_lock_hash(env_yaml)
    lock_file = cache_dir / f"{lock_hash}.yaml"
    tarball = cache_dir / f"{lock_hash}.tar.gz"

    if not lock_file.exists():
        lock_file.write_bytes(env_yaml.read_bytes())
        if verbose:
            print(f"[environ] cached YAML → {lock_file}")

    if tarball.exists():
        return EnvBuildResult(lock_hash=lock_hash, lock_file=lock_file, tarball=tarball)

    # ------------------------------------------------------------------
    # Real build path (requires tooling) unless dry_run
    # ------------------------------------------------------------------

    if dry_run:
        # Minimal tarball placeholder with YAML inside
        with tarfile.open(tarball, "w:gz") as tf:
            tf.add(lock_file, arcname="environment.yaml")
        return EnvBuildResult(lock_hash=lock_hash, lock_file=lock_file, tarball=tarball)

    # Check required tools
    have_conda_lock = shutil.which("conda-lock") is not None
    have_micromamba = shutil.which("micromamba") is not None
    have_conda_pack = shutil.which("conda-pack") is not None

    if not (have_conda_lock and have_micromamba and have_conda_pack):
        if verbose:
            print("[environ] Required tools missing; falling back to stub build")
        with tarfile.open(tarball, "w:gz") as tf:
            tf.add(lock_file, arcname="environment.yaml")
        return EnvBuildResult(lock_hash=lock_hash, lock_file=lock_file, tarball=tarball)

    try:
        # 1. conda-lock -> lock.yml
        lock_yaml = cache_dir / f"{lock_hash}.lock.yml"
        if not lock_yaml.exists():
            cmd_lock = [
                "conda-lock",
                "lock",
                "-f",
                str(env_yaml),
                "-p",
                "linux-64",
                "--filename-template",
                str(lock_yaml),
            ]
            subprocess.check_call(cmd_lock)
            if verbose:
                print(f"[environ] generated conda-lock → {lock_yaml}")

        # 2. micromamba create
        prefix_dir = cache_dir / f"{lock_hash}_prefix"
        if not prefix_dir.exists():
            cmd_mm = [
                "micromamba",
                "create",
                "--yes",
                "-p",
                str(prefix_dir),
                "-f",
                str(lock_yaml),
            ]
            subprocess.check_call(cmd_mm)
            if verbose:
                print(f"[environ] realised env prefix → {prefix_dir}")

        # 3. conda-pack
        cmd_pack = [
            "conda-pack",
            "-p",
            str(prefix_dir),
            "-o",
            str(tarball),
        ]
        subprocess.check_call(cmd_pack)
        if verbose:
            print(f"[environ] packed env → {tarball}")

    except subprocess.CalledProcessError as exc:
        if verbose:
            print(f"[environ] build failed ({exc}); falling back to stub tarball")
        if not tarball.exists():
            with tarfile.open(tarball, "w:gz") as tf:
                tf.add(lock_file, arcname="environment.yaml")

    return EnvBuildResult(lock_hash=lock_hash, lock_file=lock_file, tarball=tarball)


def pack_conda_environment(
    env_yaml_path: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    *,
    verbose: bool = False,
    dry_run: bool = False,
) -> Optional[Path]:
    """
    Package a conda environment using conda-pack for portable deployment.
    
    This function creates a portable tarball of a conda environment that can be
    transferred to HTCondor execution nodes and unpacked/activated during job execution.
    
    Args:
        env_yaml_path: Path to the conda environment YAML file
        output_dir: Directory to save the packaged environment (defaults to same dir as YAML)
        verbose: Enable verbose output
        dry_run: If True, only show what would be done without actually packaging
        
    Returns:
        Path to the created .tar.gz file, or None if packaging failed
        
    Raises:
        RuntimeError: If conda-pack is not available or packaging fails
    """
    env_yaml_path = Path(env_yaml_path)
    
    if not env_yaml_path.exists():
        raise FileNotFoundError(f"Conda environment file not found: {env_yaml_path}")
    
    # Check if conda-pack is available
    if not shutil.which("conda-pack"):
        raise RuntimeError(
            "conda-pack not found. Install it with: conda install -c conda-forge conda-pack"
        )
    
    # Determine output directory and filename
    if output_dir is None:
        output_dir = env_yaml_path.parent
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract environment name from YAML file
    try:
        with open(env_yaml_path, 'r') as f:
            env_data = yaml.safe_load(f)
        env_name = env_data.get('name', env_yaml_path.stem)
    except Exception as e:
        if verbose:
            logger.warning(f"Could not parse environment name from {env_yaml_path}: {e}")
        env_name = env_yaml_path.stem
    
    output_file = output_dir / f"{env_name}.tar.gz"
    
    if dry_run:
        print(f"DRY RUN: Would package conda environment from {env_yaml_path}")
        print(f"  Environment name: {env_name}")
        print(f"  Output file: {output_file}")
        return output_file
    
    if verbose:
        print(f"Packaging conda environment: {env_name}")
        print(f"  Source: {env_yaml_path}")
        print(f"  Output: {output_file}")
    
    try:
        # First, create the environment from the YAML file
        create_cmd = ["conda", "env", "create", "-f", str(env_yaml_path)]
        if verbose:
            print(f"Creating environment: {' '.join(create_cmd)}")
        
        result = subprocess.run(
            create_cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        if verbose:
            print("Environment created successfully")
        
        # Then package the environment using conda-pack
        pack_cmd = [
            "conda-pack", 
            "-n", env_name,
            "--dest-prefix", "$ENVDIR",
            "-o", str(output_file)
        ]
        
        if verbose:
            print(f"Packaging environment: {' '.join(pack_cmd)}")
        
        result = subprocess.run(
            pack_cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        if verbose:
            print(f"Environment packaged successfully: {output_file}")
            print(f"File size: {output_file.stat().st_size / (1024*1024):.1f} MB")
        
        return output_file
        
    except subprocess.CalledProcessError as e:
        error_msg = f"Failed to package conda environment: {e}"
        if e.stdout:
            error_msg += f"\nstdout: {e.stdout}"
        if e.stderr:
            error_msg += f"\nstderr: {e.stderr}"
        raise RuntimeError(error_msg)
    
    except Exception as e:
        raise RuntimeError(f"Unexpected error packaging conda environment: {e}")


def generate_conda_activation_script(
    env_name: str,
    command: str,
    *,
    script_path: Optional[Union[str, Path]] = None,
) -> Path:
    """
    Generate a bash script that unpacks and activates a conda environment for HTCondor jobs.
    
    This function creates a script that follows the CHTC best practices for conda
    environment activation in HTCondor jobs.
    
    Args:
        env_name: Name of the conda environment (without .tar.gz extension)
        command: The command to run after activating the environment
        script_path: Path to save the script (defaults to {env_name}_script.sh)
        
    Returns:
        Path to the generated script
    """
    if script_path is None:
        script_path = Path(f"{env_name}_script.sh")
    else:
        script_path = Path(script_path)
    
    script_content = f"""#!/bin/bash

# Exit on any error
set -e

# Environment setup
ENVNAME={env_name}
export ENVDIR=$ENVNAME

# Create environment directory and unpack
mkdir $ENVDIR
tar -xzf $ENVNAME.tar.gz -C $ENVDIR

# Activate the conda environment
. $ENVDIR/bin/activate

# Run the specified command
{command}
"""
    
    script_path.write_text(script_content)
    script_path.chmod(0o755)  # Make executable
    
    return script_path


# ---------------------------------------------------------------------------
# 9.2.3 – OCI image build abstraction (initial stub)
# ---------------------------------------------------------------------------


class OCIBuilder:
    """Protocol-like base class for OCI builders."""

    def build(
        self,
        tarball: Path,
        tag: str,
        labels: Optional[Dict[str, str]] = None,
        *,
        push: bool = False,
        build_cache: Optional[str] = None,
    ) -> str:  # noqa: D401
        """Build image, optionally push, and return digest (sha256:...)."""
        raise NotImplementedError


def _prompt_tool_start(tool_name: str, interactive: bool) -> str:
    """Prompt the user for action when tool is not available. Returns 'start', 'dry_run', or 'abort'."""
    import click
    try:
        from wf2wf import prompt as _prompt
    except ImportError:
        def _prompt(*args, **kwargs):
            return "dry_run"
    if not interactive:
        click.echo(f"⚠ {tool_name} is not available. Skipping container build (dry run).", err=True)
        return "dry_run"
    
    click.echo(f"⚠ {tool_name} is not available or not running.")
    click.echo(f"{tool_name} is required for container operations.")
    
    # Check if tool is installed and running
    if tool_name.lower() == "docker":
        tool_installed = is_docker_available()
    else:
        tool_installed = shutil.which(tool_name.lower()) is not None
    
    if tool_installed:
        click.echo(f"\n{tool_name} is installed but not running.")
        click.echo("To start:")
        if tool_name.lower() == "docker":
            click.echo("  • macOS: Start Docker Desktop application")
            click.echo("  • Linux: sudo systemctl start docker")
            click.echo("  • Windows: Start Docker Desktop application")
        elif tool_name.lower() == "podman":
            click.echo("  • Linux: sudo systemctl start podman")
            click.echo("  • Or run: podman machine start (for rootless)")
        elif tool_name.lower() == "buildah":
            click.echo("  • Linux: sudo systemctl start buildah")
        elif tool_name.lower() == "apptainer":
            click.echo("  • Linux: module load apptainer or install via your package manager")
        
        if _prompt.ask(f"Would you like to attempt starting {tool_name}?", default=True):
            return "start"
        elif _prompt.ask("Would you like to proceed in dry-run mode (no real container build)?", default=True):
            return "dry_run"
        else:
            return "abort"
    else:
        click.echo(f"\n{tool_name} is not installed.")
        click.echo("To install:")
        if tool_name.lower() == "docker":
            click.echo("  • Visit https://docs.docker.com/get-docker/")
        elif tool_name.lower() == "podman":
            click.echo("  • Linux: sudo dnf install podman or sudo apt install podman")
            click.echo("  • macOS: brew install podman")
        elif tool_name.lower() == "buildah":
            click.echo("  • Linux: sudo dnf install buildah or sudo apt install buildah")
        elif tool_name.lower() == "apptainer":
            click.echo("  • Visit https://apptainer.org/docs/admin/main/installation.html")
        
        if _prompt.ask("Would you like to proceed in dry-run mode (no real container build)?", default=True):
            return "dry_run"
        else:
            return "abort"

def _attempt_start_tool(tool_name: str) -> bool:
    """Attempt to start the specified tool daemon. Returns True if successful, False otherwise."""
    import subprocess
    import time
    
    try:
        if tool_name.lower() == "docker":
            # Check if Docker is already running
            if is_docker_available():
                return True  # Already running
            
            # Try to start Docker daemon
            start_commands = [
                ["sudo", "systemctl", "start", "docker"],
                ["sudo", "service", "docker", "start"],
                ["open", "-a", "Docker"],  # macOS
            ]
            
            for cmd in start_commands:
                try:
                    if shutil.which(cmd[0]):
                        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
                        # Wait a moment for daemon to start
                        time.sleep(3)
                        # Verify it's running
                        if is_docker_available():
                            return True
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                    continue
                    
        elif tool_name.lower() == "podman":
            # Try to start Podman
            if shutil.which("podman"):
                # Check if Podman is already running
                try:
                    subprocess.run(["podman", "info"], check=True, capture_output=True, timeout=5)
                    return True  # Already running
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    pass
            
            # Try to start Podman
            start_commands = [
                ["sudo", "systemctl", "start", "podman"],
                ["podman", "machine", "start"],
                ["podman", "system", "connection", "default", "podman-machine-default-rootless"],
            ]
            
            for cmd in start_commands:
                try:
                    if shutil.which(cmd[0]):
                        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
                        # Wait a moment for daemon to start
                        time.sleep(3)
                        # Verify it's running
                        subprocess.run(["podman", "info"], check=True, capture_output=True, timeout=5)
                        return True
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                    continue
                    
        elif tool_name.lower() == "buildah":
            # Try to start Buildah
            if shutil.which("buildah"):
                # Check if Buildah is already working
                try:
                    subprocess.run(["buildah", "version"], check=True, capture_output=True, timeout=5)
                    return True  # Already working
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    pass
            
            # Try to start Buildah
            start_commands = [
                ["sudo", "systemctl", "start", "buildah"],
                ["sudo", "service", "buildah", "start"],
            ]
            
            for cmd in start_commands:
                try:
                    if shutil.which(cmd[0]):
                        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
                        # Wait a moment for daemon to start
                        time.sleep(3)
                        # Verify it's working
                        subprocess.run(["buildah", "version"], check=True, capture_output=True, timeout=5)
                        return True
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                    continue
                    
    except Exception:
        pass
    
    return False

class DockerBuildxBuilder(OCIBuilder):
    """Tiny wrapper around `docker buildx build` (dry-run by default)."""

    def __init__(self, *, dry_run: bool = True, interactive: bool = False):
        self.dry_run = dry_run or (os.environ.get("WF2WF_ENVIRON_DRYRUN") == "1")
        self.interactive = interactive

    def build(
        self,
        tarball: Path,
        tag: str,
        labels: Optional[Dict[str, str]] = None,
        *,
        push: bool = False,
        build_cache: Optional[str] = None,
        platform: str = "linux/amd64",
    ) -> str:
        labels = labels or {}
        context_dir = Path(tempfile.mkdtemp(prefix="wf2wf_img_"))
        dockerfile = context_dir / "Dockerfile"
        dockerfile.write_text(
            "FROM scratch\n# placeholder layer for conda-pack tar\nADD env.tar.gz /opt/env\n"
        )
        env_tar_path = context_dir / "env.tar.gz"
        try:
            shutil.copy2(tarball, env_tar_path)
        except Exception:
            env_tar_path.write_bytes(tarball.read_bytes())

        cmd = [
            "docker",
            "buildx",
            "build",
            "-f",
            str(dockerfile),
            "-t",
            tag,
            "--platform",
            platform,
        ]
        if push:
            cmd.append("--push")
        else:
            cmd.append("--load")
        for k, v in labels.items():
            cmd += ["--label", f"{k}={v}"]
        cmd.append(str(context_dir))
        if build_cache:
            cmd += [
                "--cache-from",
                f"type=registry,ref={build_cache}",
                "--cache-to",
                f"type=registry,ref={build_cache},mode=max",
            ]
        if self.dry_run or not is_docker_available():
            if not is_docker_available():
                should_proceed = _prompt_tool_start("Docker", self.interactive)
                if should_proceed == "start":
                    # Try to start the tool daemon
                    if _attempt_start_tool("Docker"):
                        click.echo("✅ Docker started successfully. Proceeding with real container build.")
                        self.dry_run = False
                    else:
                        click.echo("❌ Failed to start Docker. Proceeding in dry-run mode.")
                        self.dry_run = True
                elif should_proceed == "dry_run":
                    # User chose dry-run mode
                    self.dry_run = True
                else: # should_proceed == "abort"
                    raise click.ClickException("Docker not available. Aborting as requested.")
            fake_digest = hashlib.sha256((tag + str(tarball)).encode()).hexdigest()
            return f"sha256:{fake_digest}"
        subprocess.check_call(cmd)
        try:
            insp = subprocess.check_output(
                [
                    "docker",
                    "inspect",
                    tag,
                    "--format",
                    "{{index .RepoDigests 0}}",
                ]
            )
            ref = insp.decode().strip()
            digest = ref.split("@", 1)[1] if "@" in ref else tag
        except subprocess.CalledProcessError as e:
            digest = tag
        return digest


# ---------------------------------------------------------------------------
# Buildah / Podman backend (optional, Linux + rootless friendly)
# ---------------------------------------------------------------------------


class BuildahBuilder(OCIBuilder):
    """Wrapper around *buildah* / *podman build* for sites that prefer it."""

    def __init__(self, *, tool: Optional[str] = None, dry_run: bool = True, interactive: bool = False):
        self.tool = tool or (shutil.which("buildah") and "buildah" or "podman")
        self.dry_run = dry_run or (os.environ.get("WF2WF_ENVIRON_DRYRUN") == "1")
        self.interactive = interactive

    def build(
        self,
        tarball: Path,
        tag: str,
        labels: Optional[Dict[str, str]] = None,
        *,
        push: bool = False,
        build_cache: Optional[str] = None,
        platform: str = "linux/amd64",
    ) -> str:  # noqa: D401
        if not self.tool or not shutil.which(self.tool):
            tool_name = self.tool or "buildah/podman"
            should_proceed = _prompt_tool_start(tool_name, self.interactive)
            if should_proceed == "start":
                # Try to start the tool daemon
                if _attempt_start_tool(tool_name):
                    click.echo(f"✅ {tool_name} started successfully. Proceeding with real container build.")
                    self.dry_run = False
                else:
                    click.echo(f"❌ Failed to start {tool_name}. Proceeding in dry-run mode.")
                    self.dry_run = True
            elif should_proceed == "dry_run":
                # User chose dry-run mode
                self.dry_run = True
            else: # should_proceed == "abort"
                raise click.ClickException(f"{tool_name} not available. Aborting as requested.")
        labels = labels or {}
        context_dir = Path(tempfile.mkdtemp(prefix="wf2wf_img_"))
        dockerfile = context_dir / "Containerfile"
        dockerfile.write_text("FROM scratch\nADD env.tar.gz /opt/env\n")
        env_tar_path = context_dir / "env.tar.gz"
        try:
            shutil.copy2(tarball, env_tar_path)
        except Exception:
            env_tar_path.write_bytes(tarball.read_bytes())
        cmd = [self.tool, "build", "-f", str(dockerfile), "-t", tag]
        for k, v in labels.items():
            cmd += ["--label", f"{k}={v}"]
        cmd.append(str(context_dir))
        if push:
            if self.tool == "buildah":
                cmd.append("--push")
        if self.dry_run or not shutil.which(self.tool):
            return f"sha256:{hashlib.sha256((tag + str(tarball)).encode()).hexdigest()}"
        subprocess.check_call(cmd)
        if push and self.tool == "podman":
            subprocess.check_call(["podman", "push", tag])
        try:
            insp = subprocess.check_output(
                [
                    "docker",
                    "inspect",
                    tag,
                    "--format",
                    "{{index .RepoDigests 0}}",
                ]
            )
            ref = insp.decode().strip()
            digest = ref.split("@", 1)[1] if "@" in ref else tag
        except subprocess.CalledProcessError:
            digest = tag
        return digest


def build_oci_image(
    tarball: Path,
    *,
    tag_prefix: str = "wf2wf/env",
    backend: str = "buildx",
    push: bool = False,
    platform: str = "linux/amd64",
    build_cache: Optional[str] = None,
    dry_run: bool = True,
    interactive: bool = False,
) -> tuple[str, str]:
    """High-level helper that picks a builder backend and returns (tag, digest)."""

    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    tag = f"{tag_prefix}:{rand}"
    labels = {"org.wf2wf.lock.sha256": hashlib.sha256(tarball.read_bytes()).hexdigest()}

    if backend == "buildx":
        builder = DockerBuildxBuilder(dry_run=dry_run, interactive=interactive)
    elif backend == "buildah":
        builder = BuildahBuilder(dry_run=dry_run, interactive=interactive)
    else:
        raise ValueError(f"Unsupported backend '{backend}'")

    # Note: current builder implementations ignore platform/build_cache but parameters are reserved
    digest = builder.build(
        tarball, tag, labels, push=push, build_cache=build_cache, platform=platform
    )
    return tag, digest


# ---------------------------------------------------------------------------
# 9.2.4 – SBOM generation & Apptainer conversion (stubs)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# SBOM helper wrapper
# ---------------------------------------------------------------------------


class SBOMInfo:
    """Lightweight wrapper holding SBOM *path* and *digest*.

    The instance behaves like :class:`pathlib.Path` for common filesystem
    operations via ``__getattr__`` pass-through so existing code and tests that
    expect a Path continue to work unchanged.  Additional attribute
    :pyattr:`digest` provides the *sha256* digest (``sha256:<hex>``).
    """

    __slots__ = ("_path", "digest")

    def __init__(self, path: Path, digest: str):
        self._path = Path(path)
        self.digest = digest

    # ------------------------------------------------------------------
    # Path-like behaviour
    # ------------------------------------------------------------------

    def __getattr__(self, item):  # Delegate missing attrs to underlying Path
        return getattr(self._path, item)

    def __str__(self):
        return str(self._path)

    def __fspath__(self):  # os.fspath support
        return str(self._path)

    # Equality semantics – compare underlying Path
    def __eq__(self, other):  # type: ignore[override]
        if isinstance(other, SBOMInfo):
            return self._path == other._path and self.digest == other.digest
        if isinstance(other, (str, Path)):
            return self._path == Path(other)
        return NotImplemented

    def __hash__(self):  # type: ignore[override]
        return hash((self._path, self.digest))


def generate_sbom(
    image_ref: str, out_dir: Optional[Path] = None, *, dry_run: bool = True
) -> SBOMInfo:
    """Generate an SPDX SBOM for *image_ref* and return :class:`SBOMInfo`.

    In dry-run mode (the default during unit tests) this creates a minimal
    JSON file containing the image reference and a fake package list.
    """
    out_dir = out_dir or _CACHE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    sbom_path = out_dir / f"{image_ref.replace('/', '_').replace(':', '_')}.sbom.json"

    if sbom_path.exists():
        digest = "sha256:" + hashlib.sha256(sbom_path.read_bytes()).hexdigest()
        return SBOMInfo(sbom_path, digest)

    if dry_run or not shutil.which("syft"):
        sbom_path.write_text(
            json.dumps(
                {
                    "spdxVersion": "SPDX-2.3",
                    "name": image_ref,
                    "packages": [
                        {
                            "name": "example",
                            "versionInfo": "0.0.0",
                            "licenseConcluded": "NOASSERTION",
                        }
                    ],
                },
                indent=2,
            )
        )
        digest = "sha256:" + hashlib.sha256(sbom_path.read_bytes()).hexdigest()
        return SBOMInfo(sbom_path, digest)

    # Real syft call – may require syft installation
    try:
        subprocess.check_call(
            [
                "syft",
                "packages",
                image_ref,
                "-o",
                "spdx-json",
                "--file",
                str(sbom_path),
            ],
            timeout=120,
        )
        digest = "sha256:" + hashlib.sha256(sbom_path.read_bytes()).hexdigest()
        return SBOMInfo(sbom_path, digest)
    except Exception as exc:
        # Gracefully degrade: write a minimal stub SBOM so downstream steps can continue.
        sbom_path.write_text(
            json.dumps(
                {
                    "spdxVersion": "SPDX-2.3",
                    "name": image_ref,
                    "packages": [],
                    "_generatedBy": f"wf2wf fallback due to syft error: {exc}",
                },
                indent=2,
            )
        )
        digest = "sha256:" + hashlib.sha256(sbom_path.read_bytes()).hexdigest()
        return SBOMInfo(sbom_path, digest)


def convert_to_sif(
    image_ref: str, *, sif_dir: Optional[Path] = None, dry_run: bool = True
) -> Path:
    """Convert OCI *image_ref* to Apptainer SIF file.

    Uses `spython` if available; otherwise simulates by touching a file.
    """
    sif_dir = sif_dir or _CACHE_DIR / "sif"
    sif_dir.mkdir(parents=True, exist_ok=True)
    safe_name = image_ref.replace("/", "_").replace(":", "_")
    sif_path = sif_dir / f"{safe_name}.sif"

    if sif_path.exists():
        return sif_path

    if dry_run or not shutil.which("apptainer"):
        sif_path.write_bytes(b"SIF_DRYRUN")
        return sif_path

    try:
        from spython.main import Client as _spython  # type: ignore
    except ImportError:
        # Fallback to system apptainer
        subprocess.check_call(
            ["apptainer", "build", str(sif_path), f"docker://{image_ref}"]
        )
        return sif_path

    _spython.build(f"docker://{image_ref}", sif_path)
    return sif_path


def convert_docker_images_to_apptainer(
    conda_envs: Dict[str, Dict[str, Any]],
    sif_dir: Union[str, Path],
    *,
    verbose: bool = False,
    debug: bool = False,
    dry_run: bool = False,
) -> bool:
    """
    Convert Docker images to Apptainer SIF files for multiple conda environments.
    
    Args:
        conda_envs: Dictionary mapping env paths to env info (with 'hash' and 'docker_image_url' keys)
        sif_dir: Directory to store SIF files
        verbose: Enable verbose output
        debug: Enable debug output
        dry_run: If True, only show what would be done without actually converting
        
    Returns:
        True if all conversions were successful, False otherwise
    """
    print("--- Starting Apptainer Conversion Phase ---")
    
    # Check for apptainer/singularity executable
    apptainer_cmd = shutil.which("apptainer") or shutil.which("singularity")
    if not apptainer_cmd:
        print(
            "WARNING: 'apptainer' or 'singularity' command not found. "
            "Container conversion to SIF format will be skipped. "
            "To enable SIF conversion, install Apptainer: "
            "'conda install -c conda-forge apptainer' or "
            "'pip install apptainer' or install SingularityCE."
        )
        return False
    
    if verbose:
        print(f"INFO: Using {Path(apptainer_cmd).name} for container conversion")
    
    sif_path = Path(sif_dir)
    sif_path.mkdir(parents=True, exist_ok=True)
    print(f"Storing .sif files in: {sif_path.resolve()}")
    
    if not conda_envs:
        if verbose:
            print("INFO: No conda environments found for conversion")
        return True
    
    if verbose:
        print(f"INFO: Converting {len(conda_envs)} Docker images to Apptainer format")
    
    success_count = 0
    total_count = len(conda_envs)
    
    for env_info in conda_envs.values():
        docker_image_url = env_info.get("docker_image_url")
        if not docker_image_url:
            if debug:
                print(f"DEBUG: Skipping environment without Docker image URL: {env_info}")
            continue
        
        sif_filename = f"{env_info['hash']}.sif"
        target_sif_path = sif_path / sif_filename
        env_info["apptainer_sif_path"] = str(target_sif_path)
        
        print(f"Processing image '{docker_image_url}':")
        print(f"  Target .sif file: {target_sif_path}")
        
        if debug:
            print(f"DEBUG: Environment hash: {env_info['hash']}")
            print(f"DEBUG: SIF filename: {sif_filename}")
        
        if target_sif_path.exists():
            print("  ✔ .sif file already exists. Skipping conversion.")
            if debug:
                print(f"DEBUG: Existing file size: {target_sif_path.stat().st_size} bytes")
            success_count += 1
            continue
        
        if dry_run:
            print(f"DRY RUN: Would convert {docker_image_url} to {target_sif_path}")
            success_count += 1
            continue
        
        print(f"  Converting with '{Path(apptainer_cmd).name}'...")
        try:
            # Command: apptainer build target.sif docker://user/image:tag
            build_cmd = [
                apptainer_cmd,
                "build",
                "--force",
                str(target_sif_path),
                f"docker://{docker_image_url}",
            ]
            if debug:
                print(f"DEBUG: Apptainer command: {' '.join(build_cmd)}")
            
            proc = subprocess.Popen(
                build_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            if verbose or debug:
                for line in iter(proc.stdout.readline, ""):
                    prefix = "DEBUG: " if debug else "    "
                    print(f"{prefix}{line.strip()}")
            else:
                proc.communicate()  # Wait for completion without showing output
            
            proc.wait()
            if proc.returncode != 0:
                print(f"  ✗ ERROR: Apptainer build failed for {docker_image_url}. See output above.")
                # Don't exit, just warn and continue. The Docker image can still be used.
            else:
                print("  ✔ Conversion successful.")
                if debug and target_sif_path.exists():
                    print(f"DEBUG: Created SIF file size: {target_sif_path.stat().st_size} bytes")
                success_count += 1
                
        except Exception as e:
            print(f"  ✗ ERROR: An unexpected error occurred during Apptainer conversion: {e}")
            if debug:
                import traceback
                print(f"DEBUG: Full traceback:\n{traceback.format_exc()}")
    
    if verbose:
        print(f"✅ Successfully converted {success_count}/{total_count} images")
    
    print("--- Apptainer Conversion Phase Complete ---\n")
    return success_count == total_count


# ---------------------------------------------------------------------------
# Environment utility functions for exporters
# ---------------------------------------------------------------------------

def normalize_container_spec(container_spec: str) -> str:
    """
    Normalize container specification by removing docker:// prefix.
    
    Args:
        container_spec: Container specification (e.g., "docker://image:tag" or "image:tag")
        
    Returns:
        Normalized container specification without docker:// prefix
    """
    if container_spec.startswith("docker://"):
        return container_spec[9:]  # Remove docker:// prefix
    return container_spec


def extract_sbom_path(env_vars: Optional[Dict[str, str]]) -> Optional[str]:
    """
    Extract SBOM path from environment variables.
    
    Args:
        env_vars: Environment variables dictionary
        
    Returns:
        SBOM path if present, None otherwise
    """
    if not env_vars:
        return None
    return env_vars.get("WF2WF_SBOM")


def extract_sif_path(env_vars: Optional[Dict[str, str]]) -> Optional[str]:
    """
    Extract SIF path from environment variables.
    
    Args:
        env_vars: Environment variables dictionary
        
    Returns:
        SIF path if present, None otherwise
    """
    if not env_vars:
        return None
    return env_vars.get("WF2WF_SIF")


def extract_sbom_digest(env_vars: Optional[Dict[str, str]]) -> Optional[str]:
    """
    Extract SBOM digest from environment variables.
    
    Args:
        env_vars: Environment variables dictionary
        
    Returns:
        SBOM digest if present, None otherwise
    """
    if not env_vars:
        return None
    return env_vars.get("WF2WF_SBOM_DIGEST")


def format_container_for_target_format(
    container_spec: str, 
    target_format: str
) -> str:
    """
    Format container specification for a specific target format.
    
    Args:
        container_spec: Container specification
        target_format: Target format (e.g., "docker", "singularity", "cwl", "wdl", etc.)
        
    Returns:
        Formatted container specification for the target format
    """
    normalized = normalize_container_spec(container_spec)
    
    # Format-specific handling
    if target_format.lower() in ["cwl", "wdl", "nextflow", "snakemake"]:
        # These formats typically expect just the image name without docker:// prefix
        return normalized
    elif target_format.lower() in ["dagman", "galaxy"]:
        # These formats might need the full specification
        return container_spec
    else:
        # Default to normalized form
        return normalized


def get_environment_metadata(env_vars: Optional[Dict[str, str]]) -> Dict[str, Optional[str]]:
    """
    Extract all environment-related metadata from environment variables.
    
    Args:
        env_vars: Environment variables dictionary
        
    Returns:
        Dictionary containing SBOM path, SIF path, and SBOM digest
    """
    return {
        "sbom_path": extract_sbom_path(env_vars),
        "sif_path": extract_sif_path(env_vars),
        "sbom_digest": extract_sbom_digest(env_vars),
    }


# ---------------------------------------------------------------------------
# Registry probing & image cache (Phase 2 §9.2.3 – step 2)
# ---------------------------------------------------------------------------


def _load_index() -> Dict[str, Any]:
    if _INDEX_FILE.exists():
        try:
            return json.loads(_INDEX_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_index(data: Dict[str, Any]):
    _INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    _INDEX_FILE.write_text(json.dumps(data, indent=2))


def _image_exists_locally(tag_or_digest: str) -> bool:
    if not is_docker_available():
        return False
    try:
        out = subprocess.check_output(
            [
                "docker",
                "images",
                "--no-trunc",
                "--format",
                "{{.Repository}}@{{.Digest}}",
            ]
        )
        return tag_or_digest in out.decode()
    except subprocess.CalledProcessError:
        return False


def _probe_remote_registries(
    lock_hash: str, registries: Optional[List[str]] = None, *, dry_run: bool = True
) -> Optional[str]:
    """Return image digest if an image with *lock_hash* label exists in any *registries*.

    The implementation is intentionally lightweight: in *dry_run* mode we always
    return *None*.  A real implementation could query *skopeo search* or GHCR
    API but that exceeds unit-test constraints.
    """
    if dry_run or not registries or not shutil.which("skopeo"):
        return None

    import json
    import subprocess

    for reg in registries:
        repo = f"{reg}/wf2wf/env"
        try:
            # List tags (may be many – limit to 50 for speed)
            out = subprocess.check_output(
                ["skopeo", "list-tags", f"docker://{repo}", "--format", "json"]
            )
            tags = json.loads(out).get("Tags", [])[:50]
            for tag in tags:
                ref = f"{repo}:{tag}"
                cfg = subprocess.check_output(
                    ["skopeo", "inspect", "--config", f"docker://{ref}"]
                )
                labels = json.loads(cfg).get("config", {}).get("Labels", {}) or {}
                if labels.get("org.wf2wf.lock.sha256") == lock_hash:
                    # Found matching image – return digest reference
                    insp = subprocess.check_output(
                        ["skopeo", "inspect", f"docker://{ref}"]
                    )
                    digest = json.loads(insp).get("Digest")
                    if digest:
                        return f"{repo}@{digest}"
        except subprocess.CalledProcessError:
            continue  # ignore registry errors and try next

    return None


def build_or_reuse_env_image(
    env_yaml: Union[str, Path],
    *,
    registry: Optional[str] = None,
    push: bool = False,
    backend: str = "buildx",
    dry_run: bool = True,
    build_cache: Optional[str] = None,
    cache_dir: Optional[Path] = None,
    interactive: bool = False,
) -> Dict[str, str]:
    """High-level helper: build image for *env_yaml* unless identical hash already indexed.

    Returns dict with keys ``tag`` and ``digest``.
    """

    cache_dir = cache_dir or _CACHE_DIR
    build_res = prepare_env(
        env_yaml, cache_dir=cache_dir, verbose=False, dry_run=dry_run
    )
    lock_hash = build_res["lock_hash"]
    tarball: Path = build_res["tarball"]

    index = _load_index()

    # 1. Check local index/cache
    if lock_hash in index and index[lock_hash].get("digest"):
        entry = index[lock_hash]
        if dry_run or _image_exists_locally(entry["digest"]):
            return entry  # reuse

    # 2. Probe remote registries (CLI + env)
    registries: list[str] = []
    if registry:
        registries.append(registry)
    env_reg = os.environ.get("WF2WF_REGISTRIES")
    if env_reg:
        registries.extend([r.strip() for r in env_reg.split(",") if r.strip()])

    probe_digest = _probe_remote_registries(
        lock_hash, registries or None, dry_run=dry_run
    )
    if probe_digest:
        entry = {"tag": probe_digest, "digest": probe_digest}
        index[lock_hash] = entry
        _save_index(index)
        return entry

    # Need to build
    tag_prefix = f"{registry}/wf2wf/env" if registry else "wf2wf/env"
    tag, digest = build_oci_image(
        tarball,
        tag_prefix=tag_prefix,
        backend=backend,
        push=push,
        build_cache=build_cache,
        dry_run=dry_run,
        interactive=interactive,
    )

    entry = {"tag": tag, "digest": digest}
    index[lock_hash] = entry
    _save_index(index)
    return entry


# ---------------------------------------------------------------------------
# Cache prune helper (Phase 2 §9.2.6)
# ---------------------------------------------------------------------------


def prune_cache(*, days: int = 60, min_free_gb: int = 5, verbose: bool = False):
    """Remove cache entries older than *days* if disk free space below threshold.

    Very lightweight implementation; only checks tarballs & SIF files.
    """
    now = time.time()
    cutoff = now - days * 86400

    freed = 0
    for p in itertools.chain(_CACHE_DIR.rglob("*.tar.gz"), _CACHE_DIR.rglob("*.sif")):
        try:
            if p.stat().st_mtime < cutoff:
                size = p.stat().st_size
                p.unlink()
                freed += size
                if verbose:
                    print(f"[prune] removed {p} ({size/1e6:.1f} MB)")
        except FileNotFoundError:
            pass

    if verbose and freed:
        print(f"[prune] freed {freed/1e9:.2f} GB")

# ---------------------------------------------------------------------------
# Environment Manager for Workflow Importers
# ---------------------------------------------------------------------------

class EnvironmentManager:
    """
    Comprehensive environment and container management for workflow importers.
    
    This class provides unified environment handling across all importers,
    including detection, parsing, validation, and interactive prompting.
    """
    
    def __init__(self, interactive: bool = False, verbose: bool = False):
        """
        Initialize the environment manager.
        
        Args:
            interactive: Enable interactive prompting for environment specifications
            verbose: Enable verbose logging
        """
        self.interactive = interactive
        self.verbose = verbose
        
        # Configure logging
        if verbose:
            logging.getLogger(__name__).setLevel(logging.DEBUG)
    
    def detect_and_parse_environments(
        self, 
        workflow: Workflow, 
        source_format: str,
        source_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Detect and parse environment specifications from workflow data.
        
        Args:
            workflow: Workflow object to analyze
            source_format: Source format name
            source_path: Path to source file (for relative path resolution)
            
        Returns:
            Dictionary containing detected environment information
        """
        detected_envs = {
            'containers': set(),
            'conda_environments': set(),
            'environment_files': set(),
            'environment_metadata': {},
            'missing_environments': [],
            'environment_warnings': []
        }
        
        for task in workflow.tasks.values():
            task_env_info = self._analyze_task_environment(task, source_path)
            
            # Collect containers
            if task_env_info['container']:
                detected_envs['containers'].add(task_env_info['container'])
            
            # Collect conda environments
            if task_env_info['conda']:
                detected_envs['conda_environments'].add(task_env_info['conda'])
            
            # Collect environment files
            if task_env_info['environment_file']:
                detected_envs['environment_files'].add(task_env_info['environment_file'])
            
            # Check for missing environments
            if not task_env_info['container'] and not task_env_info['conda']:
                detected_envs['missing_environments'].append(task.id)
            
            # Collect warnings
            detected_envs['environment_warnings'].extend(task_env_info['warnings'])
        
        # Add environment metadata
        detected_envs['environment_metadata'] = {
            'source_format': source_format,
            'source_path': str(source_path) if source_path else None,
            'total_tasks': len(workflow.tasks),
            'tasks_with_environments': len(workflow.tasks) - len(detected_envs['missing_environments']),
            'tasks_without_environments': len(detected_envs['missing_environments'])
        }
        
        return detected_envs
    
    def _analyze_task_environment(
        self, 
        task: Task, 
        source_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Analyze environment specifications for a single task.
        
        Args:
            task: Task to analyze
            source_path: Path to source file (for relative path resolution)
            
        Returns:
            Dictionary containing task environment information
        """
        env_info = {
            'container': None,
            'conda': None,
            'environment_file': None,
            'warnings': [],
            'metadata': {}
        }
        
        # Check for container specifications
        container = task.container.get_value_for('shared_filesystem')
        if container:
            env_info['container'] = normalize_container_spec(container)
            env_info['metadata']['container_source'] = 'explicit'
        
        # Check for conda specifications
        conda = task.conda.get_value_for('shared_filesystem')
        if conda:
            env_info['conda'] = conda
            env_info['metadata']['conda_source'] = 'explicit'
            
            # Check if conda spec is a file path
            if self._is_environment_file(conda):
                env_info['environment_file'] = conda
                
                # Resolve relative paths
                if source_path and not Path(conda).is_absolute():
                    resolved_path = source_path.parent / conda
                    if resolved_path.exists():
                        env_info['environment_file'] = str(resolved_path)
                    else:
                        env_info['warnings'].append(f"Environment file not found: {resolved_path}")
        
        # Check for environment variables that might indicate environment info
        env_vars = task.env_vars.get_value_for('shared_filesystem') or {}
        if env_vars:
            env_info['metadata']['environment_variables'] = env_vars
            
            # Extract environment metadata
            env_metadata = get_environment_metadata(env_vars)
            if env_metadata:
                env_info['metadata'].update(env_metadata)
        
        # Check for advanced environment features
        if task.checkpointing.get_value_for('shared_filesystem'):
            env_info['metadata']['checkpointing'] = True
        
        if task.logging.get_value_for('shared_filesystem'):
            env_info['metadata']['logging'] = True
        
        if task.security.get_value_for('shared_filesystem'):
            env_info['metadata']['security'] = True
        
        if task.networking.get_value_for('shared_filesystem'):
            env_info['metadata']['networking'] = True
        
        return env_info
    
    def _is_environment_file(self, spec: str) -> bool:
        """
        Check if a specification is an environment file.
        
        Args:
            spec: Environment specification string
            
        Returns:
            True if the specification appears to be a file path
        """
        if not spec:
            return False
        
        # Check for container specifications first (these are not files)
        container_prefixes = ['docker://', 'container://', 'singularity://', 'apptainer://']
        if any(spec.startswith(prefix) for prefix in container_prefixes):
            return False
        
        # Check for common environment file extensions
        env_extensions = ['.yml', '.yaml', '.txt', '.lock']
        if any(spec.endswith(ext) for ext in env_extensions):
            return True
        
        # Check for path separators (but not for container specs)
        if '/' in spec or '\\' in spec:
            # Additional check: if it looks like a container image (has : but no file extension)
            if ':' in spec and not any(spec.endswith(ext) for ext in env_extensions):
                return False
            return True
        
        return False
    
    def infer_missing_environments(
        self, 
        workflow: Workflow, 
        source_format: str
    ) -> None:
        """
        Infer missing environment specifications based on workflow content.
        
        Args:
            workflow: Workflow to analyze
            source_format: Source format name
        """
        logger.info("Inferring missing environment specifications...")
        
        for task in workflow.tasks.values():
            self._infer_task_environment(task, source_format)
    
    def _infer_task_environment(self, task: Task, source_format: str) -> None:
        """
        Infer environment for a single task.
        
        Args:
            task: Task to analyze
            source_format: Source format name
        """
        # Skip if task already has environment specification
        if (task.container.get_value_for('shared_filesystem') or 
            task.conda.get_value_for('shared_filesystem')):
            return
        
        # Try to infer from command
        command = task.command.get_value_for('shared_filesystem')
        if command:
            # Try to infer container
            container = self._infer_container_from_command(command)
            if container:
                task.container.set_for_environment(container, 'shared_filesystem')
                logger.info(f"Inferred container '{container}' for task '{task.id}'")
            
            # Try to infer conda environment
            conda_env = self._infer_conda_environment_from_command(command)
            if conda_env:
                task.conda.set_for_environment(conda_env, 'shared_filesystem')
                logger.info(f"Inferred conda environment '{conda_env}' for task '{task.id}'")
    
    def _infer_container_from_command(self, command: str) -> Optional[str]:
        """
        Infer container specification from command.
        
        Args:
            command: Command string
            
        Returns:
            Inferred container specification or None
        """
        if not command:
            return None
        
        # Check for machine learning frameworks first (more specific)
        if re.search(r'tensorflow', command, re.IGNORECASE):
            return "tensorflow/tensorflow:latest"
        if re.search(r'pytorch', command, re.IGNORECASE):
            return "pytorch/pytorch:latest"
        
        # Check for bioinformatics tools
        bio_tools = ['blast', 'fastqc', 'bwa', 'samtools', 'gatk', 'bcftools']
        for tool in bio_tools:
            if re.search(rf'\b{tool}\b', command, re.IGNORECASE):
                return "biocontainers/bioconductor_docker:latest"
        
        # Check for Python commands (more flexible pattern)
        if re.search(r'python', command, re.IGNORECASE):
            # Try to extract version if present
            version_match = re.search(r'python\s+(\d+\.\d+)', command, re.IGNORECASE)
            if version_match:
                version = version_match.group(1)
                return f"python:{version}"
            return "python:3.9"
        
        # Check for R commands
        if re.search(r'rscript', command, re.IGNORECASE):
            return "rocker/r-base:latest"
        
        # Check for Perl
        if re.search(r'perl', command, re.IGNORECASE):
            return "perl:latest"
        
        # Check for Java
        if re.search(r'java', command, re.IGNORECASE):
            return "openjdk:latest"
        
        # Default for general Linux commands
        if re.search(r'echo|cat|grep|sed|awk|sort|uniq', command, re.IGNORECASE):
            return "ubuntu:latest"
        
        return None
    
    def _infer_conda_environment_from_command(self, command: str) -> Optional[str]:
        """
        Infer conda environment from command.
        
        Args:
            command: Command string
            
        Returns:
            Inferred conda environment or None
        """
        if not command:
            return None
        
        # Look for common conda environment patterns
        conda_patterns = [
            r'conda\s+activate\s+(\w+)',
            r'source\s+activate\s+(\w+)',
            r'conda\s+run\s+-n\s+(\w+)',
        ]
        
        for pattern in conda_patterns:
            match = re.search(pattern, command, re.IGNORECASE)
            if match:
                return match.group(1)
        
        # Look for common tool patterns that suggest conda environments
        if re.search(r'python', command, re.IGNORECASE):
            return "environment.yml"
        
        if re.search(r'rscript', command, re.IGNORECASE):
            return "r_environment.yml"
        
        # Check for bioinformatics tools
        bio_tools = ['blast', 'fastqc', 'bwa', 'samtools', 'gatk', 'bcftools']
        for tool in bio_tools:
            if re.search(rf'\b{tool}\b', command, re.IGNORECASE):
                return "bioinformatics.yml"
        
        return None
    
    def prompt_for_missing_environments(
        self, 
        workflow: Workflow, 
        source_format: str
    ) -> None:
        """
        Prompt user for missing environment specifications.
        
        Args:
            workflow: Workflow to process
            source_format: Source format name
        """
        if not self.interactive:
            return
        
        logger.info("Prompting for missing environment specifications...")
        
        for task in workflow.tasks.values():
            task_id = task.id
            
            # Skip if task already has environment specification
            if (task.container.get_value_for('shared_filesystem') or 
                task.conda.get_value_for('shared_filesystem')):
                continue
            
            # Prompt for environment type
            response = self._prompt_user(
                f"Task '{task_id}' has no environment specification. "
                f"Choose environment type:\n"
                f"  1. None (system default)\n"
                f"  2. Container (Docker/Singularity)\n"
                f"  3. Conda environment\n"
                f"Enter choice (1/2/3): ",
                default="1",
                validation_func=self._validate_environment_choice
            )
            
            if response == "2":
                # Prompt for container
                container = self._prompt_user(
                    f"Enter container specification for task '{task_id}' "
                    f"(e.g., python:3.9, tensorflow/tensorflow:latest): ",
                    default="python:3.9"
                )
                if container:
                    task.container.set_for_environment(container, 'shared_filesystem')
                    logger.info(f"Set container '{container}' for task '{task_id}'")
            
            elif response == "3":
                # Prompt for conda environment
                conda_env = self._prompt_user(
                    f"Enter conda environment for task '{task_id}' "
                    f"(e.g., bioinformatics, env.yml): ",
                    default=""
                )
                if conda_env:
                    task.conda.set_for_environment(conda_env, 'shared_filesystem')
                    logger.info(f"Set conda environment '{conda_env}' for task '{task_id}'")
    
    def build_environment_images(
        self, 
        workflow: Workflow,
        registry: Optional[str] = None,
        push: bool = False,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Build environment images for workflow tasks.
        
        Args:
            workflow: Workflow to process
            registry: Docker registry for pushing images
            push: Whether to push images to registry
            dry_run: Whether to perform actual builds
            
        Returns:
            Dictionary containing build results
        """
        results = {
            'built_images': [],
            'failed_images': [],
            'skipped_images': []
        }
        
        for task in workflow.tasks.values():
            task_id = task.id
            
            # Check for conda environment files
            conda_env = task.conda.get_value_for('shared_filesystem')
            if conda_env and self._is_environment_file(conda_env):
                try:
                    env_path = Path(conda_env)
                    if not env_path.is_absolute():
                        # Assume relative to current directory
                        env_path = Path.cwd() / conda_env
                    
                    if env_path.exists():
                        # Build image from conda environment
                        image_name = f"{task_id}-env"
                        if registry:
                            image_url = f"{registry}/{image_name}:latest"
                        else:
                            image_url = f"{image_name}:latest"
                        
                        success = build_docker_image_from_conda_env(
                            env_path,
                            image_url,
                            verbose=self.verbose,
                            dry_run=dry_run
                        )
                        
                        if success:
                            results['built_images'].append({
                                'task_id': task_id,
                                'image_url': image_url,
                                'source': str(env_path)
                            })
                            
                            # Update task with built image
                            task.container.set_for_environment(image_url, 'shared_filesystem')
                        else:
                            results['failed_images'].append({
                                'task_id': task_id,
                                'image_url': image_url,
                                'source': str(env_path)
                            })
                    else:
                        results['skipped_images'].append({
                            'task_id': task_id,
                            'reason': f"Environment file not found: {env_path}"
                        })
                except Exception as e:
                    results['failed_images'].append({
                        'task_id': task_id,
                        'reason': str(e)
                    })
        
        return results
    
    def adapt_environments_for_target(
        self, 
        workflow: Workflow, 
        target_format: str
    ) -> None:
        """
        Adapt environment specifications for target format.
        
        Args:
            workflow: Workflow to adapt
            target_format: Target format name
        """
        logger.info(f"Adapting environments for target format: {target_format}")
        
        for task in workflow.tasks.values():
            self._adapt_task_environment_for_target(task, target_format)
    
    def _adapt_task_environment_for_target(self, task: Task, target_format: str) -> None:
        """
        Adapt task environment for target format.
        
        Args:
            task: Task to adapt
            target_format: Target format name
        """
        # Adapt container specifications
        container = task.container.get_value_for('shared_filesystem')
        if container:
            adapted_container = format_container_for_target_format(container, target_format)
            if adapted_container != container:
                task.container.set_for_environment(adapted_container, 'shared_filesystem')
                logger.info(f"Adapted container '{container}' to '{adapted_container}' for {target_format}")
        
        # Adapt conda specifications
        conda = task.conda.get_value_for('shared_filesystem')
        if conda:
            # For some formats, conda environments might need to be converted to containers
            if target_format in ['dagman', 'nextflow'] and self._is_environment_file(conda):
                # Suggest building container from conda environment
                logger.info(f"Consider building container from conda environment '{conda}' for {target_format}")
    
    def _prompt_user(
        self, 
        message: str, 
        default: str = "", 
        validation_func: Optional[Callable] = None
    ) -> str:
        """
        Prompt user for input with validation.
        
        Args:
            message: Message to display
            default: Default value
            validation_func: Optional validation function
            
        Returns:
            User input or default value
        """
        try:
            import click
            
            # Use click for better UX if available
            if default:
                message = f"{message} [{default}]: "
            else:
                message = f"{message}: "
            
            while True:
                response = click.prompt(message, default=default, show_default=False)
                
                if validation_func:
                    try:
                        validation_func(response)
                    except ValueError as e:
                        click.echo(f"Invalid input: {e}")
                        continue
                
                return response
                
        except ImportError:
            # Fallback to basic input
            if default:
                message = f"{message} [{default}]: "
            else:
                message = f"{message}: "
            
            while True:
                response = input(message).strip()
                if not response and default:
                    response = default
                
                if validation_func:
                    try:
                        validation_func(response)
                    except ValueError as e:
                        print(f"Invalid input: {e}")
                        continue
                
                return response
    
    def _validate_environment_choice(self, value: str) -> None:
        """
        Validate environment choice input.
        
        Args:
            value: String to validate
            
        Raises:
            ValueError: If validation fails
        """
        valid_choices = ['1', '2', '3']
        if value not in valid_choices:
            raise ValueError("Please enter a valid choice (1/2/3)")
    
    def _is_valid_container_spec(self, spec: str) -> bool:
        """
        Check if a container specification is valid.
        
        Args:
            spec: Container specification string
            
        Returns:
            True if the specification appears valid
        """
        if not spec:
            return False
        
        # Basic validation patterns
        patterns = [
            r'^[a-zA-Z0-9][a-zA-Z0-9._-]*/[a-zA-Z0-9][a-zA-Z0-9._-]*:[a-zA-Z0-9._-]+$',  # registry/repo:tag
            r'^[a-zA-Z0-9][a-zA-Z0-9._-]*:[a-zA-Z0-9._-]+$',  # repo:tag
            r'^[a-zA-Z0-9][a-zA-Z0-9._-]*$',  # just repo name
        ]
        
        return any(re.match(pattern, spec) for pattern in patterns)


# ---------------------------------------------------------------------------
# Convenience functions for backward compatibility
# ---------------------------------------------------------------------------

def detect_and_parse_environments(workflow: Workflow, source_format: str, **kwargs) -> Dict[str, Any]:
    """Convenience function for detecting and parsing environments."""
    manager = EnvironmentManager(**kwargs)
    return manager.detect_and_parse_environments(workflow, source_format)


def infer_missing_environments(workflow: Workflow, source_format: str, **kwargs) -> None:
    """Convenience function for inferring missing environments."""
    manager = EnvironmentManager(**kwargs)
    manager.infer_missing_environments(workflow, source_format)


def prompt_for_missing_environments(workflow: Workflow, source_format: str, **kwargs) -> None:
    """Convenience function for prompting for missing environments."""
    manager = EnvironmentManager(**kwargs)
    manager.prompt_for_missing_environments(workflow, source_format)


def build_environment_images(workflow: Workflow, **kwargs) -> Dict[str, Any]:
    """Convenience function for building environment images."""
    manager = EnvironmentManager(**kwargs)
    return manager.build_environment_images(workflow)


def adapt_environments_for_target(workflow: Workflow, target_format: str, **kwargs) -> None:
    """Convenience function for adapting environments for target format."""
    manager = EnvironmentManager(**kwargs)
    manager.adapt_environments_for_target(workflow, target_format)