"""wf2wf.exporters.dagman – Workflow IR ➜ HTCondor DAGMan (stub)

TODO:
    • Move `write_condor_dag`, `generate_job_scripts`, container helpers, etc.
      from `wf2wf.py` into this exporter module.
"""

from __future__ import annotations

import os
import re
import json
import shutil
import hashlib
import subprocess
import tempfile
import textwrap
import sys
from collections import defaultdict, namedtuple
from pathlib import Path
from typing import Any, Dict, List

from wf2wf.core import Workflow, Task, ResourceSpec, EnvironmentSpec
from wf2wf.loss import (
    reset as loss_reset,
    write as loss_write,
    record as loss_record,
    prepare,
    as_list,
    compute_checksum,
)


def from_workflow(
    wf: Workflow,
    out_file: str | Path,
    *,
    workdir: str | Path | None = None,
    scripts_dir: str | Path | None = None,
    default_memory: str = "2GB",
    default_disk: str = "2GB",
    default_cpus: int = 1,
    inline_submit: bool = False,
    verbose: bool = False,
    debug: bool = False,
    **opts: Any,
) -> None:  # noqa: D401,E501
    """Serialise *wf* into HTCondor DAGMan files.

    Parameters
    ----------
    wf : Workflow
        In-memory workflow IR.
    out_file : str | Path
        Target `.dag` file path.  Auxiliary submit and script files are written
        next to it unless *scripts_dir* is specified.
    workdir : str | Path, optional
        Initial working directory for Condor jobs.  Defaults to the directory
        containing *out_file* if not provided.
    scripts_dir : str | Path, optional
        Directory for generated wrapper scripts.  Defaults to a sibling of the
        DAG file named ``scripts``.
    default_memory / default_disk / default_cpus : str/int
        Fallback Condor resource requests when a Task lacks explicit values.
    inline_submit : bool
        If True, embed submit descriptions inline in the DAG file instead of
        creating separate .sub files (default: False).
    verbose, debug : bool
        Toggle console output and extra debugging messages.
    """

    # Prepare repeat-loss detection, then reset buffer
    prepare(wf.loss_map)
    loss_reset()

    # ------------------------------------------------------------------
    # Resolve paths & directories
    # ------------------------------------------------------------------

    out_path = Path(out_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    scripts_dir = Path(scripts_dir) if scripts_dir else out_path.with_name("scripts")
    scripts_dir.mkdir(parents=True, exist_ok=True)

    workdir = Path(workdir) if workdir else out_path.parent

    if verbose:
        print(f"[wf2wf.dagman] Writing DAG to {out_path}")
        print(f"  scripts_dir = {scripts_dir}")
        print(f"  workdir     = {workdir}")

    # Loss recording basics
    for task in wf.tasks.values():
        if task.scatter:
            loss_record(
                f"/tasks/{task.id}/scatter",
                "scatter",
                task.scatter.scatter,
                "DAGMan has no scatter primitive",
                "user",
            )
        if task.when:
            loss_record(
                f"/tasks/{task.id}/when",
                "when",
                task.when,
                "Conditional when lost in DAGMan",
                "user",
            )

        # Secondary files not preserved in DAGMan submit
        for param_list in (task.inputs, task.outputs):
            for p in param_list:
                if getattr(p, "secondary_files", None):
                    loss_record(
                        f"/tasks/{task.id}/{ 'inputs' if param_list is task.inputs else 'outputs' }/{p.id}/secondary_files",
                        "secondary_files",
                        p.secondary_files,
                        "HTCondor DAGMan has no concept of secondary files",
                        "user",
                    )

    # ------------------------------------------------------------------
    # 1) Write wrapper shell scripts (one per task)
    # ------------------------------------------------------------------

    script_paths: Dict[str, Path] = {}

    for task in wf.tasks.values():
        script_file = scripts_dir / f"{_sanitize_condor_job_name(task.id)}.sh"
        _write_task_wrapper_script(task, script_file)
        script_paths[task.id] = script_file

    if verbose:
        print(f"  wrote {len(script_paths)} wrapper scripts → {scripts_dir}")

    # Report hook action for scripts dir as artefact
    try:
        from wf2wf import report as _rpt

        _rpt.add_artefact(out_path)
        _rpt.add_action("Exported DAGMan workflow")
    except ImportError:
        pass

    # Ensure logs dir
    (workdir / "logs").mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # 2) Generate DAG & submit-description blocks
    # ------------------------------------------------------------------

    _write_dag_file(
        wf,
        out_path,
        script_paths,
        workdir=workdir,
        default_memory=default_memory,
        default_disk=default_disk,
        default_cpus=default_cpus,
        inline_submit=inline_submit,
    )

    # after generating files, write loss map (may be empty)
    loss_write(
        out_path.with_suffix(".loss.json"),
        target_engine="dagman",
        source_checksum=compute_checksum(wf),
    )
    wf.loss_map = as_list()


def prepare_conda_setup_jobs(dag_info, conda_prefix, verbose=False, debug=False):
    """
    Identifies unique conda environments and prepares setup jobs for them.
    Modifies dag_info in place.
    """
    if verbose:
        print("INFO: Preparing conda environment setup jobs...")

    conda_envs = {}
    for job in dag_info["jobs"].values():
        env_spec = job.get("conda_env_spec")
        if (
            env_spec
            and Path(env_spec).is_file()
            and (env_spec.endswith(".yaml") or env_spec.endswith(".yml"))
        ):
            env_path = Path(env_spec).resolve()
            if env_path not in conda_envs:
                try:
                    content = env_path.read_bytes()
                    env_hash = hashlib.sha256(content).hexdigest()[:16]
                    env_install_path = Path(conda_prefix) / env_hash
                    conda_envs[env_path] = {
                        "hash": env_hash,
                        "install_path": str(env_install_path),
                        "setup_job_name": f"conda_env_setup_{env_hash}",
                    }
                    if debug:
                        print(f"DEBUG: Added conda env {env_path} with hash {env_hash}")
                except FileNotFoundError:
                    if verbose:
                        print(
                            f"WARNING: Could not find conda env file {env_path}. Cannot create setup job."
                        )

    dag_info["conda_envs"] = conda_envs
    if verbose:
        if conda_envs:
            print(
                f"INFO: Identified {len(conda_envs)} unique conda environments to be created."
            )
            for env_path, env_info in conda_envs.items():
                print(f"  - {env_path.name} -> {env_info['install_path']}")
        else:
            print("INFO: No conda environments found requiring setup jobs.")

    if debug:
        print(
            f"DEBUG: conda_envs structure: {json.dumps(conda_envs, indent=2, default=str)}"
        )


def _generate_dockerfile(env_yaml_path, build_context_dir):
    """Generates a simple Dockerfile for a given conda environment file."""
    dockerfile_content = f"""
FROM continuumio/miniconda3:latest
COPY {env_yaml_path.name} /tmp/environment.yaml
RUN conda env create -f /tmp/environment.yaml
"""
    dockerfile_path = build_context_dir / "Dockerfile"
    dockerfile_path.write_text(textwrap.dedent(dockerfile_content))
    return dockerfile_path


def build_and_push_docker_images(dag_info, docker_registry, verbose=False, debug=False):
    """
    Builds and pushes Docker images for conda environments if they don't exist in the remote registry.
    Modifies dag_info in-place.
    """
    print("\n--- Starting Docker Image Build Phase ---")
    conda_envs = dag_info.get("conda_envs", {})
    if not conda_envs:
        print("No conda environments found to build.")
        return

    if verbose:
        print(f"INFO: Building Docker images for {len(conda_envs)} conda environments")
        print(f"  Registry: {docker_registry}")

    for original_yaml_path, env_info in conda_envs.items():
        env_hash = env_info["hash"]
        # Construct the image name and tag
        # Use a sanitized version of the snakefile name as the repo name for consistency
        repo_name = _sanitize_condor_job_name(
            Path(dag_info.get("snakefile", "workflow")).stem
        )
        image_name = f"{docker_registry}/{repo_name}"
        image_tag = env_hash
        full_image_url = f"{image_name}:{image_tag}"
        env_info["docker_image_url"] = full_image_url

        print(f"Processing environment '{original_yaml_path.name}':")
        print(f"  Target image: {full_image_url}")

        if debug:
            print(f"DEBUG: Environment hash: {env_hash}")
            print(f"DEBUG: Repository name: {repo_name}")

        # 1. Check if image exists remotely
        try:
            if verbose:
                print("  Checking for remote manifest...")
            # Use docker manifest inspect to check remote without pulling
            subprocess.run(
                ["docker", "manifest", "inspect", full_image_url],
                check=True,
                capture_output=True,
                text=True,
            )
            if debug:
                print("DEBUG: Manifest found, image exists")
            print("  ✔ Image already exists in registry. Skipping build.")
            continue
        except subprocess.CalledProcessError as e:
            if verbose:
                print("  Image not found in registry. Proceeding with build and push.")
            if debug:
                print(f"DEBUG: Manifest check failed with code {e.returncode}")

        # 2. Create build context
        with tempfile.TemporaryDirectory() as build_context:
            build_context_path = Path(build_context)
            if debug:
                print(f"DEBUG: Using build context: {build_context_path}")

            # Copy env file to build context
            shutil.copy(original_yaml_path, build_context_path)
            # Generate Dockerfile
            dockerfile_path = _generate_dockerfile(
                original_yaml_path, build_context_path
            )

            if debug:
                print(f"DEBUG: Generated Dockerfile at {dockerfile_path}")
                with open(dockerfile_path, "r") as f:
                    print(f"DEBUG: Dockerfile contents:\n{f.read()}")

            # 3. Build the image
            print("  Building Docker image...")
            try:
                build_cmd = ["docker", "build", "-t", full_image_url, "."]
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
                    print(
                        f"  ✗ ERROR: Docker build failed for {full_image_url}. See output above."
                    )
                    sys.exit(1)
                print("  ✔ Build successful.")
            except Exception as e:
                print(
                    f"  ✗ ERROR: An unexpected error occurred during docker build: {e}"
                )
                if debug:
                    import traceback

                    print(f"DEBUG: Full traceback:\n{traceback.format_exc()}")
                sys.exit(1)

            # 4. Push the image
            print("  Pushing image to registry...")
            try:
                push_cmd = ["docker", "push", full_image_url]
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
                    print(f"  ✗ ERROR: Docker push failed for {full_image_url}.")
                    print(
                        f"  Please ensure you are logged in to '{docker_registry}' and have push permissions."
                    )
                    sys.exit(1)
                print("  ✔ Push successful.")
            except Exception as e:
                print(
                    f"  ✗ ERROR: An unexpected error occurred during docker push: {e}"
                )
                if debug:
                    import traceback

                    print(f"DEBUG: Full traceback:\n{traceback.format_exc()}")
                sys.exit(1)

    print("--- Docker Image Build Phase Complete ---\n")


def convert_docker_to_apptainer(dag_info, sif_dir, verbose=False, debug=False):
    """
    Converts Docker images (that were just built) to local Apptainer .sif files.
    Modifies dag_info in-place.
    """
    print("--- Starting Apptainer Conversion Phase ---")
    # Check for apptainer/singularity executable
    apptainer_cmd = shutil.which("apptainer") or shutil.which("singularity")
    if not apptainer_cmd:
        print(
            "WARNING: 'apptainer' or 'singularity' command not found. Skipping conversion."
        )
        return

    if verbose:
        print(f"INFO: Using {Path(apptainer_cmd).name} for container conversion")

    sif_path = Path(sif_dir)
    sif_path.mkdir(parents=True, exist_ok=True)
    print(f"Storing .sif files in: {sif_path.resolve()}")

    conda_envs = dag_info.get("conda_envs", {})
    if not conda_envs:
        if verbose:
            print("INFO: No conda environments found for conversion")
        return

    if verbose:
        print(f"INFO: Converting {len(conda_envs)} Docker images to Apptainer format")

    for env_info in conda_envs.values():
        docker_image_url = env_info.get("docker_image_url")
        if not docker_image_url:
            if debug:
                print(
                    f"DEBUG: Skipping environment without Docker image URL: {env_info}"
                )
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
                print(
                    f"DEBUG: Existing file size: {target_sif_path.stat().st_size} bytes"
                )
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
                print(
                    f"  ✗ ERROR: Apptainer build failed for {docker_image_url}. See output above."
                )
                # Don't exit, just warn and continue. The Docker image can still be used.
            else:
                print("  ✔ Conversion successful.")
                if debug and target_sif_path.exists():
                    print(
                        f"DEBUG: Created SIF file size: {target_sif_path.stat().st_size} bytes"
                    )
        except Exception as e:
            print(
                f"  ✗ ERROR: An unexpected error occurred during Apptainer conversion: {e}"
            )
            if debug:
                import traceback

                print(f"DEBUG: Full traceback:\n{traceback.format_exc()}")

    print("--- Apptainer Conversion Phase Complete ---\n")


def generate_job_scripts(dag_info, output_dir="scripts", verbose=False, debug=False):
    """Generate individual wrapper scripts for each Snakemake job."""
    abs_output_dir = Path(output_dir).resolve()
    abs_output_dir.mkdir(parents=True, exist_ok=True)
    script_paths = {}

    if not dag_info or "jobs" not in dag_info:
        print("WARNING: No jobs found in dag_info. Cannot generate job scripts.")
        return script_paths

    # --- Generate Conda Env Setup Scripts (if any) ---
    conda_envs = dag_info.get("conda_envs", {})
    for original_yaml_path, env_info in conda_envs.items():
        setup_job_name = env_info["setup_job_name"]
        setup_script_path = abs_output_dir / f"{setup_job_name}.sh"
        script_paths[setup_job_name] = str(
            setup_script_path
        )  # Add to script paths for DAG writing

        if verbose:
            print(
                f"  Generating conda setup script for {original_yaml_path.name} at {setup_script_path}"
            )

        with open(setup_script_path, "w") as f:
            f.write("#!/bin/bash\n")
            f.write("set -euo pipefail\n\n")
            f.write(
                f"# snake2dagman: Conda environment setup script for {original_yaml_path.name}\n"
            )
            f.write(
                "# This script creates the environment in a shared location if it doesn't already exist.\n\n"
            )
            f.write(f"ENV_PREFIX=\"{env_info['install_path']}\"\n")
            f.write(f'ENV_YAML="{original_yaml_path}"\n\n')

            f.write(
                "# Check if environment already exists to make this job idempotent\n"
            )
            f.write('if [ -f "${ENV_PREFIX}/bin/python" ]; then\n')
            f.write(
                '    echo "Conda environment already exists at ${ENV_PREFIX}. Nothing to do."\n'
            )
            f.write("    exit 0\n")
            f.write("fi\n\n")

            f.write('echo "Creating conda environment at ${ENV_PREFIX}..."\n')
            f.write(
                "# Use --force to overwrite a potentially corrupted/incomplete environment\n"
            )
            f.write(
                'conda env create --prefix "${ENV_PREFIX}" --file "${ENV_YAML}" --force\n'
            )
            f.write('echo "Conda environment creation complete."\n')

        os.chmod(setup_script_path, 0o755)

    # --- Generate Job-Specific Scripts ---
    for job_uid, job_details in dag_info["jobs"].items():
        sh_script_filename = f"{job_details['condor_job_name']}.sh"
        sh_script_path = abs_output_dir / sh_script_filename
        script_paths[job_uid] = str(sh_script_path)

        if verbose:
            print(
                f"  Generating script for job UID {job_uid} (Rule: {job_details['rule_name']}) at {sh_script_path}"
            )

        if debug:
            print(
                f"DEBUG: Generating script for job {job_uid}, Details: {json.dumps(job_details, indent=4, default=str)}"
            )

        # --- Determine the core command for the job ---
        core_command = ""
        shell_cmd = job_details.get("shell_command")
        script_file = job_details.get("script_file")

        if shell_cmd:
            core_command = shell_cmd
        elif script_file:
            interpreter = ""
            if script_file.lower().endswith(".py"):
                interpreter = "python"
            elif script_file.lower().endswith(".r") or script_file.lower().endswith(
                ".R"
            ):
                interpreter = "Rscript"
            elif script_file.lower().endswith(".sh"):
                interpreter = "bash"

            if interpreter:
                core_command = f"{interpreter} {script_file}"
            else:
                # Add a warning note to the script itself if interpreter is unknown
                with open(sh_script_path, "a") as f:  # Append warning to the top
                    f.write(
                        f"# WARNING: Could not determine interpreter for script: {script_file}\n"
                    )
                core_command = script_file
        elif job_details.get("is_run"):
            run_code = job_details.get("run_block_code")
            # Check for None or empty string
            if run_code is not None:
                py_script_filename = f"{job_details['condor_job_name']}_run.py"
                py_script_path = abs_output_dir / py_script_filename

                generate_run_block_script(
                    py_script_path,
                    job_uid,
                    job_details,
                    run_code,
                    dag_info.get("config", {}),
                    debug=debug,
                )
                core_command = f"python {py_script_path}"
            else:
                core_command = (
                    f"echo \"'run:' block for {job_uid} was empty. No action taken.\""
                )
        elif job_details.get("is_notebook"):
            core_command = f'echo "Notebook execution placeholder for {job_uid}. See Snakemake docs."'
        elif job_details.get("is_wrapper"):
            core_command = f'echo "Wrapper execution placeholder for {job_uid}."'
        else:
            core_command = (
                f"echo 'Job placeholder for {job_uid} - no command or script found.'"
            )

        # --- Write the final .sh wrapper script ---
        with open(sh_script_path, "w") as f:
            f.write("#!/bin/bash\n")
            f.write(f"# snake2dagman wrapper script for Snakemake job UID: {job_uid}\n")
            f.write(f"# Rule: {job_details['rule_name']}\n")
            if job_details["wildcards_dict"]:
                f.write(f"# Wildcards: {json.dumps(job_details['wildcards_dict'])}\n")
            f.write("# Generated automatically - review and modify as needed\n\n")

            f.write("# Set shell to fail on errors\n")
            f.write("set -euo pipefail\n\n")

            conda_env_spec = job_details.get("conda_env_spec")

            # Docker auto-build takes precedence for jobs with conda envs
            auto_docker_image = None
            auto_sif_path = None
            if conda_env_spec and conda_envs:
                env_path = Path(conda_env_spec).resolve()
                if env_path in conda_envs:
                    auto_docker_image = conda_envs[env_path].get("docker_image_url")
                    auto_sif_path = conda_envs[env_path].get("apptainer_sif_path")

            # Check if auto-setup is enabled and this job has a recognized conda env file
            conda_setup_info = None
            if conda_envs and conda_env_spec:
                conda_setup_info = conda_envs.get(Path(conda_env_spec).resolve())

            # Priority: 1. Explicit container, 2. Auto-container, 3. Conda env, 4. Vanilla
            is_explicitly_containerized = job_details.get("is_containerized", False)

            if is_explicitly_containerized or auto_sif_path or auto_docker_image:
                f.write("# This job runs inside a container.\n")
                f.write(
                    "# The environment is pre-configured, so no conda activation is needed here.\n\n"
                )
                f.write(f"{core_command}\n")
            elif conda_setup_info:
                # Automatic setup is active for this environment
                env_install_path = conda_setup_info["install_path"]
                f.write("# This job uses a conda environment with automatic setup.\n")
                f.write(
                    f"# The environment is expected to be at: {env_install_path}\n\n"
                )
                f.write(
                    f"conda run --prefix {env_install_path} --no-capture-output bash -c $'\\\n{core_command}\n'\n"
                )

            elif conda_env_spec:
                # Manual setup path (auto-setup not enabled or env not a file)
                f.write(
                    "# This job uses a Conda environment. The command is wrapped with 'conda run'.\n"
                )
                f.write(
                    "# CRITICAL: You must ensure the environment exists on the execute node.\n"
                )
                f.write(
                    "# To enable automatic environment creation, use --auto-conda-setup and --conda-prefix.\n\n"
                )

                if Path(conda_env_spec).is_file() and (
                    conda_env_spec.endswith(".yaml") or conda_env_spec.endswith(".yml")
                ):
                    f.write(f"# The environment is defined by: {conda_env_spec}\n")
                    f.write(
                        "# You must create this environment and provide its path.\n"
                    )
                    f.write(
                        "# Example: conda env create -f {conda_env_spec} -p ./my_conda_envs/{job_details['rule_name']}_env\n"
                    )
                    f.write(
                        "\n# snake2dagman is assuming you have a pre-existing environment and will attempt to run with it.\n"
                    )
                    f.write(
                        "# For automatic creation, use --auto-conda-setup and --conda-prefix\n"
                    )
                    f.write(
                        f"conda run --prefix {conda_env_spec} --no-capture-output bash -c $'\\\n{core_command}\n'\n"
                    )

                else:  # Assumed to be a named environment
                    f.write(
                        f"# The environment is specified by name: {conda_env_spec}\n"
                    )
                    f.write(
                        "# This named environment must be available on the Condor execute nodes.\n"
                    )
                    f.write(
                        "\n# Using 'conda run' with the specified environment name.\n"
                    )
                    # Use bash -c to properly handle complex commands
                    f.write(
                        f"conda run -n {conda_env_spec} --no-capture-output bash -c $'\\\n{core_command}\n'\n"
                    )
            else:  # No conda environment
                f.write("# This job does not specify a Conda environment.\n")
                f.write("# Ensure all required tools are in the job's PATH.\n\n")
                f.write(f"{core_command}\n")

            f.write("\n\n# Job completed successfully\n")
            f.write(
                f"echo 'Job UID {job_uid} (Rule: {job_details['rule_name']}) completed successfully'\n"
            )

        os.chmod(sh_script_path, 0o755)  # Make script executable

    if verbose:
        print(f"INFO: Generated {len(script_paths)} job scripts in {abs_output_dir}")
    return script_paths


def generate_run_block_script(
    script_path, job_uid, job_details, run_code, config_dict, debug=False
):
    """Generates a standalone Python script from a Snakemake 'run' block."""

    def format_for_source(value):
        """Formats a Python value into a string of its source code representation."""
        if isinstance(value, (str, int, float, bool, type(None))):
            return repr(value)
        if isinstance(value, list):
            return f"[{', '.join(format_for_source(v) for v in value)}]"
        if isinstance(value, tuple):
            return f"({', '.join(format_for_source(v) for v in value)},)"
        if isinstance(value, set):
            return f"set([{', '.join(format_for_source(v) for v in value)}])"
        if isinstance(value, dict):
            return f"{{{', '.join(f'{format_for_source(k)}: {format_for_source(v)}' for k, v in value.items())}}}"

        # For Snakemake's IOFile objects, just get their string representation (the path)
        type_str = str(type(value))
        if "snakemake.io.IOFile" in type_str or "snakemake.io.Wildcards" in type_str:
            return repr(str(value))

        try:
            # Fallback for other object types.
            # We can't know if it's safe, so we represent it as a string with a prominent warning.
            return f'"""{str(value)}"""  # snake2dagman: UNABLE_TO_SERIALIZE. Original type was <{type(value).__name__}>'
        except Exception as e:
            return f'"<SERIALIZATION_FAILED: {e}>"'

    # --- Preamble and object reconstruction ---
    preamble = [
        "#!/usr/bin/env python3",
        "# -*- coding: utf-8 -*-",
        f"# Standalone Python script generated by snake2dagman for job UID: {job_uid}",
        f"# Original rule: {job_details['rule_name']}",
        "# WARNING: This is an experimental feature. Review and test this script carefully.",
        "# It attempts to reconstruct the Snakemake environment for a 'run:' block.",
        "# Complex params functions or objects may not be converted correctly.",
        "\nimport sys",
        "from pathlib import Path",
        "from collections import namedtuple",
        "\n# --- Mock Snakemake objects ---",
        "# Create a mock 'snakemake' object that contains the necessary attributes",
        "class Snakemake: pass",
        "snakemake = Snakemake()",
        "\n# --- Reconstructing Snakemake objects ---",
    ]

    # --- Input, Output, Log ---
    # These can be accessed by index (e.g. output[0]) or by name (e.g. output.myfile)
    for obj_name in ["input", "output", "log"]:
        items = job_details.get(f"{obj_name}s", job_details.get(obj_name, []))
        if items:
            # Sanitize keys for namedtuple: must be valid identifiers
            keys = [re.sub(r"[^a-zA-Z0-9_]", "_", Path(item).stem) for item in items]
            # Ensure keys are unique
            final_keys = []
            for k in keys:
                new_key = k
                i = 1
                while new_key in final_keys:
                    new_key = f"{k}_{i}"
                    i += 1
                final_keys.append(new_key)

            try:
                Tuple = namedtuple(obj_name.capitalize(), final_keys)
                instance = Tuple(*items)
                preamble.append(f"snakemake.{obj_name} = {instance!r}")
            except (ValueError, TypeError):
                # Fallback to simple list if keys are not valid identifiers or other issues
                preamble.append(
                    f"# WARNING: Could not create namedtuple for '{obj_name}'. Falling back to list."
                )
                preamble.append(f"snakemake.{obj_name} = {[str(f) for f in items]}")
        else:
            preamble.append(f"snakemake.{obj_name} = []")

    preamble.append(f"snakemake.threads = {job_details['threads']}")
    preamble.append(f"snakemake.rule = '{job_details['rule_name']}'")

    # Config
    preamble.append(f"snakemake.config = {format_for_source(config_dict)}")

    # Wildcards
    wildcards_dict = job_details.get("wildcards_dict", {})
    if wildcards_dict:
        # Sort keys to ensure consistent order
        sorted_keys = sorted(wildcards_dict.keys())
        Wildcards = namedtuple("Wildcards", sorted_keys)
        # Create an instance with repr() to get a nice string representation
        wildcards_instance = Wildcards(**{k: wildcards_dict[k] for k in sorted_keys})
        preamble.append(f"snakemake.wildcards = {wildcards_instance!r}")
    else:
        preamble.append("snakemake.wildcards = None")

    # Resources
    resources_dict = job_details.get("resources", {})
    if resources_dict:
        public_resources = {
            k: v
            for k, v in resources_dict.items()
            if not k.startswith("_") and k.isidentifier()
        }
        if public_resources:
            sorted_keys = sorted(public_resources.keys())
            Resources = namedtuple("Resources", sorted_keys)
            resources_instance = Resources(
                **{k: public_resources[k] for k in sorted_keys}
            )
            preamble.append(f"snakemake.resources = {resources_instance!r}")
        else:
            preamble.append(
                "snakemake.resources = None # No public, valid-identifier resources found"
            )
    else:
        preamble.append("snakemake.resources = None")

    # Params
    params_dict = job_details.get("params_dict", {})
    if params_dict:
        valid_keys = sorted([k for k in params_dict.keys() if k.isidentifier()])
        invalid_keys = [k for k in params_dict.keys() if not k.isidentifier()]

        if invalid_keys:
            preamble.append(
                f"# WARNING: The following keys in 'params' are not valid Python identifiers and have been skipped for dot-notation access: {invalid_keys}"
            )

        if valid_keys:
            # Create a dictionary of values for the namedtuple constructor
            params_values = {k: params_dict[k] for k in valid_keys}
            # Use the custom formatter to serialize the params dictionary
            params_as_dict_str = f"{{{', '.join(f'{repr(k)}: {format_for_source(v)}' for k, v in params_values.items())}}}"

            # Create a namedtuple for dot-notation access
            Params = namedtuple("Params", valid_keys)
            try:
                params_instance = Params(**params_values)
                preamble.append(f"snakemake.params = {params_instance!r}")
            except Exception:
                # If creating the namedtuple fails (e.g., due to unhashable types), fall back to a simple dictionary.
                preamble.append(
                    "# WARNING: Could not create dot-accessible `params` object. Falling back to a dictionary."
                )
                preamble.append(f"snakemake.params = {params_as_dict_str}")
        else:
            preamble.append("snakemake.params = None")
    else:
        preamble.append("snakemake.params = None")

    # --- Final script content ---
    # The user's code might expect to access via global names OR snakemake.<attr>
    # So we define both for compatibility.
    final_definitions = [
        "\n# For compatibility, creating global references to snakemake object attributes",
        "input = snakemake.input",
        "output = snakemake.output",
        "log = snakemake.log",
        "threads = snakemake.threads",
        "wildcards = snakemake.wildcards",
        "params = snakemake.params",
        "resources = snakemake.resources",
        "config = snakemake.config",
        "rule = snakemake.rule",
    ]

    script_content = (
        "\n".join(preamble + final_definitions)
        + "\n\n# --- Original 'run' block code ---\n"
        + run_code
    )

    if debug:
        print(
            f"\n--- GENERATED PYTHON SCRIPT for {job_uid} ---\n{script_content}\n-----------------------------------\n"
        )

    with open(script_path, "w") as f:
        f.write(script_content)

    os.chmod(script_path, 0o755)


def write_condor_dag(
    dag_info,
    output_file,
    script_paths,
    workdir,
    default_memory,
    default_disk,
    default_cpus,
    config,
    verbose=False,
    debug=False,
):
    """Write the Condor DAG file based on job-centric dag_info."""

    if not dag_info or "jobs" not in dag_info:
        print(
            "ERROR: No job information found in dag_info. Cannot write Condor DAG file."
        )
        return

    if verbose:
        print(f"INFO: Writing Condor DAG file to {output_file}")
        print(f"  Jobs to write: {len(dag_info['jobs'])}")
        print(
            f"  Default resources: {default_memory} memory, {default_disk} disk, {default_cpus} CPUs"
        )

    conda_envs = dag_info.get("conda_envs", {})
    if debug:
        print(f"DEBUG: Found {len(conda_envs)} conda environments")
        print(f"DEBUG: Script paths available: {len(script_paths)}")
        print(f"DEBUG: Config: {json.dumps(config, indent=2)}")

    with open(output_file, "w") as f:
        f.write(
            "# Condor DAG file generated from Snakemake workflow using snake2dagman\n"
        )
        f.write("# This DAG is job-centric, reflecting individual Snakemake jobs.\n")
        f.write("# Review and modify as needed before submission\n\n")

        # --- Write Conda Env Setup Job Descriptions (if any) ---
        if conda_envs:
            f.write("# --- Conda Environment Setup Jobs ---\n")
            # Only create setup jobs if auto-docker-build is NOT enabled
            auto_docker_build_enabled = any(
                env.get("docker_image_url") for env in conda_envs.values()
            )

            if verbose:
                print(f"INFO: Auto-docker build enabled: {auto_docker_build_enabled}")

            if not auto_docker_build_enabled:
                if verbose:
                    print(
                        f"INFO: Writing {len(conda_envs)} conda environment setup jobs"
                    )
                for env_info in conda_envs.values():
                    setup_job_name = env_info["setup_job_name"]
                    submit_desc_name = f"{setup_job_name}_desc"
                    f.write(f"SUBMIT-DESCRIPTION {submit_desc_name} {{\n")
                    f.write("    universe = vanilla\n")
                    f.write(f"    executable = {script_paths[setup_job_name]}\n")
                    f.write(f"    log = logs/{setup_job_name}.log\n")
                    f.write(f"    output = logs/{setup_job_name}.out\n")
                    f.write(f"    error = logs/{setup_job_name}.err\n")
                    f.write(
                        "    # This job should be lightweight, but give it some reasonable resources\n"
                    )
                    f.write("    request_memory = 1GB\n")
                    f.write("    request_disk = 5GB\n")
                    f.write("}\n\n")

                    if debug:
                        print(
                            f"DEBUG: Wrote setup job description for {setup_job_name}"
                        )
            else:
                f.write(
                    "# Auto-Docker build is enabled; conda setup jobs are not needed for containerized jobs.\n\n"
                )

        # --- Write Main Job Descriptions ---
        f.write("# --- Main Workflow Job Descriptions ---\n")
        if verbose:
            print(f"INFO: Writing {len(dag_info['jobs'])} main job descriptions")

        for job_uid, job_details in dag_info["jobs"].items():
            condor_job_name = job_details["condor_job_name"]

            if debug:
                print(f"DEBUG: Processing job {job_uid} ({condor_job_name})")
                print(
                    f"DEBUG: Job details: {json.dumps(job_details, indent=2, default=str)}"
                )

            # Per-task overrides
            mem_req = default_memory

            # For disk, convert back to GB if it's a round number of GB
            if job_details["resources"].disk_mb > 0:
                if job_details["resources"].disk_mb % 1024 == 0:
                    disk_req = f"{job_details['resources'].disk_mb // 1024}GB"
                else:
                    disk_req = f"{job_details['resources'].disk_mb}MB"
            else:
                disk_req = default_disk

            cpu_req = (
                job_details["resources"].cpu
                if job_details["resources"].cpu > 1
                else default_cpus
            )

            # GPU: Check for GPU resources
            gpu_request = job_details["resources"].get("gpu", 0)
            gpu_mem_mb = job_details["resources"].get("gpu_mem_mb")
            gpu_capability = job_details["resources"].get("gpu_capability")

            if debug:
                print(
                    f"DEBUG: Resource requests for {condor_job_name}: {mem_req} memory, {disk_req} disk, {cpu_req} CPUs, {gpu_request} GPUs"
                )

            submit_desc_name = (
                f"{condor_job_name}_desc"  # Unique name for submit description
            )

            f.write(
                f"# Submit description for Snakemake job UID: {job_uid} (Rule: {job_details['rule_name']})\n"
            )
            f.write(f"SUBMIT-DESCRIPTION {submit_desc_name} {{\n")

            # --- Universe and Container settings ---
            is_containerized = job_details.get("is_containerized", False)
            # This is the container URL from the original snakefile.
            container_img_url = job_details.get("container_img_url")
            container_img_path = job_details.get(
                "container_img_path"
            )  # This is for pre-converted SIFs
            conda_env_spec = job_details.get("conda_env_spec")

            # Docker auto-build takes precedence for jobs with conda envs
            auto_docker_image = None
            auto_sif_path = None
            if conda_env_spec and conda_envs:
                env_path = Path(conda_env_spec).resolve()
                if env_path in conda_envs:
                    auto_docker_image = conda_envs[env_path].get("docker_image_url")
                    auto_sif_path = conda_envs[env_path].get("apptainer_sif_path")

            if debug:
                print(f"DEBUG: Container settings for {condor_job_name}:")
                print(f"  is_containerized: {is_containerized}")
                print(f"  container_img_url: {container_img_url}")
                print(f"  auto_docker_image: {auto_docker_image}")
                print(f"  auto_sif_path: {auto_sif_path}")

            # Priority: 1. Explicit container, 2. Auto-container, 3. Vanilla
            if is_containerized and container_img_url:
                f.write(
                    "    # This job is containerized using an explicit directive from the Snakefile.\n"
                )
                if "docker://" in container_img_url:
                    docker_image = container_img_url.split("docker://")[-1]
                    f.write("    universe = docker\n")
                    f.write(f"    docker_image = {docker_image}\n")
                elif "singularity" in container_img_url:
                    sif_path = container_img_url.split("://")[-1]
                    f.write("    universe = vanilla\n")
                    f.write(f'    +SingularityImage = "{sif_path}"\n')
                else:  # Assume Singularity for others (shub, library, local file)
                    f.write("    universe = vanilla\n")
                    if container_img_path:
                        f.write(f'    +SingularityImage = "{container_img_path}"\n')
                    else:
                        f.write(
                            f"    # WARNING: Singularity image path not found for URL: {container_img_url}\n"
                        )
                        f.write(
                            '    # +SingularityImage = "/path/to/your/image.sif" # PLEASE SPECIFY\n'
                        )
            elif auto_sif_path:
                f.write(
                    "    # This job is containerized using an auto-converted Apptainer/Singularity image.\n"
                )
                f.write("    universe = vanilla\n")
                f.write(f'    +SingularityImage = "{auto_sif_path}"\n')
            elif auto_docker_image:
                f.write(
                    "    # This job is containerized using an auto-built Docker image.\n"
                )
                f.write("    universe = docker\n")
                f.write(f"    docker_image = {auto_docker_image}\n")
            else:
                f.write("    universe = vanilla\n")

            script_to_run = script_paths.get(job_uid)
            if script_to_run:
                f.write(f"    executable = {script_to_run}\n")
            else:
                f.write(
                    f"    executable = /bin/echo # ERROR: Script not found for {job_uid}\n"
                )
                f.write(
                    f'    arguments = "Error: Executable script for job UID {job_uid} was not generated."\n'
                )
                if debug:
                    print(f"DEBUG: WARNING - No script found for job {job_uid}")

            # Set the initial working directory to match Snakemake's workdir
            if workdir:
                f.write(f"    initialdir = {workdir}\n")

            # Log, output, error file naming
            f.write(f"    log = logs/{condor_job_name}_$(Cluster).$(Process).log\n")
            f.write(f"    output = logs/{condor_job_name}_$(Cluster).$(Process).out\n")
            f.write(f"    error = logs/{condor_job_name}_$(Cluster).$(Process).err\n")

            # File transfer settings
            f.write("    should_transfer_files = YES\n")
            f.write("    when_to_transfer_output = ON_EXIT\n")

            # Resource requests
            f.write(f"    request_memory = {mem_req}\n")
            f.write(f"    request_disk = {disk_req}\n")
            f.write(f"    request_cpus = {cpu_req}\n")

            # GPU resource requests
            if gpu_request > 0:
                f.write(f"    request_gpus = {gpu_request}\n")
                if gpu_mem_mb is not None:
                    f.write(f"    request_gpu_memory = {gpu_mem_mb}MB\n")
                if gpu_capability is not None:
                    f.write(f"    gpus_minimum_capability = {gpu_capability}\n")

            # ------------------------------------------------------------------
            # Custom Condor attributes provided via config (e.g. from CLI
            # --condor-attributes or a .snake2dagman.json file).  These are
            # written verbatim so that both standard attributes (e.g.
            #  'requirements', 'rank') and custom classads starting with '+' are
            # supported.
            # ------------------------------------------------------------------
            custom_attrs = config.get("condor_attributes", {}) if config else {}
            for attr_key, attr_val in custom_attrs.items():
                # Preserve the key exactly as provided.  Attribute values are
                # written without additional quoting so that callers can pass
                # strings, numbers or classad expressions as they need.
                f.write(f"    {attr_key} = {attr_val}\n")

            # Handle extra resource attributes
            if job_details["resources"].extra:
                for key, value in job_details["resources"].extra.items():
                    f.write(f"    {key} = {value}\n")

            # Warnings about file transfer
            f.write("    # WARNING: Review and modify file transfer settings.\n")
            f.write("    # transfer_input_files = file1, path/to/file2\n")
            f.write(
                "    # Ensure all necessary input files, scripts, and potentially conda envs (if not on shared FS) are transferred.\n"
            )
            f.write("}\n\n")

        # --- Write Job Definitions ---
        f.write("# --- Job Definitions ---\n")
        # Conda Setup Jobs
        if conda_envs:
            auto_docker_build_enabled = any(
                env.get("docker_image_url") for env in conda_envs.values()
            )
            if not auto_docker_build_enabled:
                for env_info in conda_envs.values():
                    setup_job_name = env_info["setup_job_name"]
                    f.write(f"JOB {setup_job_name} {setup_job_name}_desc\n")

        # Main Workflow Jobs
        for job_uid, job_details in dag_info["jobs"].items():
            condor_job_name = job_details["condor_job_name"]
            submit_desc_name = f"{condor_job_name}_desc"
            f.write(f"JOB {condor_job_name} {submit_desc_name}\n")

        f.write("\n")

        # Write retry directives
        f.write("# Automatic Retries (if specified in the Snakemake rule)\n")
        any_retries_written = False
        for job_uid, job_details in dag_info["jobs"].items():
            if job_details.get("retries", 0) > 0:
                condor_job_name = job_details["condor_job_name"]
                retries = job_details["retries"]
                f.write(f"RETRY {condor_job_name} {retries}\n")
                any_retries_written = True
                if debug:
                    print(
                        f"DEBUG: Added retry directive for {condor_job_name}: {retries} retries"
                    )
        if not any_retries_written:
            f.write("# No jobs with retries specified.\n")
        f.write("\n")

        # Write parent-child relationships
        f.write("# Dependencies (parent-child relationships between Condor jobs)\n")

        # Add dependencies on conda setup jobs first
        if conda_envs:
            f.write("# Dependencies for jobs on their respective conda environments\n")
            auto_docker_build_enabled = any(
                env.get("docker_image_url") for env in conda_envs.values()
            )

            if not auto_docker_build_enabled:
                conda_deps_written = 0
                for job_uid, job_details in dag_info["jobs"].items():
                    env_spec = job_details.get("conda_env_spec")
                    if env_spec:
                        env_path = Path(env_spec).resolve()
                        if env_path in conda_envs:
                            setup_job_name = conda_envs[env_path]["setup_job_name"]
                            child_job_name = job_details["condor_job_name"]
                            f.write(f"PARENT {setup_job_name} CHILD {child_job_name}\n")
                            conda_deps_written += 1
                            if debug:
                                print(
                                    f"DEBUG: Added conda dependency: {setup_job_name} -> {child_job_name}"
                                )
                if verbose:
                    print(
                        f"INFO: Wrote {conda_deps_written} conda environment dependencies"
                    )
            f.write("\n")

        # Add original workflow dependencies
        f.write("# Dependencies from the original Snakemake workflow\n")
        if "job_dependencies" in dag_info and dag_info["job_dependencies"]:
            any_deps_written = False
            workflow_deps_written = 0
            for job_uid, dep_uids in dag_info["job_dependencies"].items():
                if dep_uids:
                    child_condor_job_name = dag_info["jobs"][job_uid]["condor_job_name"]
                    for parent_uid in dep_uids:
                        if parent_uid in dag_info["jobs"]:
                            parent_condor_job_name = dag_info["jobs"][parent_uid][
                                "condor_job_name"
                            ]
                            f.write(
                                f"PARENT {parent_condor_job_name} CHILD {child_condor_job_name}\n"
                            )
                            any_deps_written = True
                            workflow_deps_written += 1
                            if debug:
                                print(
                                    f"DEBUG: Added workflow dependency: {parent_condor_job_name} -> {child_condor_job_name}"
                                )
            if not any_deps_written:
                f.write("# No explicit dependencies found between generated jobs.\n")
            elif verbose:
                print(f"INFO: Wrote {workflow_deps_written} workflow dependencies")
        else:
            f.write(
                "# No dependency information found - all jobs may run in parallel if not constrained by resources.\n"
            )
            f.write(
                "# WARNING: This may not be correct - review your Snakemake workflow and the generated DAG.\n"
            )

        if verbose:
            print(
                f"INFO: Successfully wrote {len(dag_info['jobs'])} job definitions to {output_file}"
            )

        if debug:
            print(
                f"DEBUG: DAG file writing complete. File size: {Path(output_file).stat().st_size} bytes"
            )


def print_conversion_warnings(dag_info, script_paths, verbose=False, debug=False):
    """Print comprehensive warnings about the conversion process."""
    print("\n" + "=" * 60)
    print("SNAKE2DAGMAN - CONVERSION WARNINGS AND MANUAL STEPS REQUIRED")
    print("=" * 60)

    if not dag_info or not dag_info.get("jobs"):
        print("  No job information available to generate specific warnings.")
        print("=" * 60)
        return

    if verbose:
        print(f"INFO: Analyzing {len(dag_info['jobs'])} jobs for conversion warnings")

    # Gather unique rule properties for warnings
    conda_rules_info = defaultdict(list)
    script_rules_info = defaultdict(list)
    shell_rules_info = defaultdict(list)
    run_block_rules = set()
    notebook_rules = set()
    wrapper_rules = set()
    dynamic_rules = set()
    pipe_rules = set()
    has_auto_conda_setup = "conda_envs" in dag_info and dag_info["conda_envs"]

    for job_uid, job_details in dag_info["jobs"].items():
        rule_name = job_details["rule_name"]
        if job_details.get("conda_env_spec"):
            conda_rules_info[rule_name].append(job_details["conda_env_spec"])
        if job_details.get("script_file"):
            script_rules_info[rule_name].append(job_details["script_file"])
        if job_details.get("shell_command") and job_details.get(
            "is_shell"
        ):  # Ensure it's an actual shell rule
            shell_rules_info[rule_name].append(
                job_uid
            )  # Just note the rule has shell jobs
        if job_details.get("is_run"):
            run_block_rules.add(rule_name)
        if job_details.get("is_notebook"):
            notebook_rules.add(rule_name)
        if job_details.get("is_wrapper"):
            wrapper_rules.add(rule_name)
        if job_details.get("has_dynamic_input") or job_details.get(
            "has_dynamic_output"
        ):
            dynamic_rules.add(rule_name)
        if job_details.get("has_pipe_output"):
            pipe_rules.add(rule_name)

    if debug:
        print("DEBUG: Warning analysis results:")
        print(f"  Conda rules: {len(conda_rules_info)}")
        print(f"  Script rules: {len(script_rules_info)}")
        print(f"  Shell rules: {len(shell_rules_info)}")
        print(f"  Run block rules: {len(run_block_rules)}")
        print(f"  Notebook rules: {len(notebook_rules)}")
        print(f"  Wrapper rules: {len(wrapper_rules)}")
        print(f"  Dynamic rules: {len(dynamic_rules)}")
        print(f"  Pipe rules: {len(pipe_rules)}")

    print("\n1. CONDA ENVIRONMENTS:")
    if has_auto_conda_setup:
        print(
            "   → AUTOMATIC SETUP ENABLED: Conda environments will be created by dedicated setup jobs."
        )
        print(
            "   → The `--conda-prefix` directory MUST be on a shared filesystem accessible to all nodes."
        )
        print(
            "   → Jobs have been made children of their corresponding environment setup job."
        )
        if verbose:
            conda_envs = dag_info.get("conda_envs", {})
            print(
                f"   → {len(conda_envs)} unique conda environments will be automatically set up."
            )
    elif conda_rules_info:
        print("   Rules with Conda environments detected:")
        for rule, env_specs in conda_rules_info.items():
            unique_specs = sorted(list(set(env_specs)))
            print(f"     - Rule '{rule}': uses {', '.join(unique_specs)}")
        print(
            "   → MANUAL SETUP REQUIRED: You must ensure conda environments are activated correctly."
        )
        print("   → To automate this, run again with `--auto-conda-setup`")
    else:
        if verbose:
            print("   → No conda environments detected in this workflow.")

    print("   → GPU resources can be specified in detail:")
    print("     - `gpu=N` -> `request_gpus = N`")
    print("     - `gpu_capability=Y` -> `gpus_minimum_capability = Y`")
    print(
        "   → For site-specific attributes (e.g., `+WantGPULab`), add a 'condor_attributes' section"
    )
    print("     to your `.wf2wf.json` file. These are applied to all jobs.")
    print(
        "   → Some resource keywords are not automatically translated to Condor equivalents."
    )

    print("\n4. CONTAINERIZATION:")
    auto_sif_enabled = any(
        env.get("apptainer_sif_path") for env in dag_info.get("conda_envs", {}).values()
    )
    auto_docker_enabled = any(
        env.get("docker_image_url") for env in dag_info.get("conda_envs", {}).values()
    )

    if auto_docker_enabled:
        print(
            "   → Auto-Docker build is enabled: Docker images will be built and pushed."
        )
        if auto_sif_enabled:
            print(
                "   → Apptainer/Singularity images will also be created from Docker images."
            )
    else:
        print(
            "   → Auto-Docker build is NOT enabled: Docker images will not be built automatically."
        )

    if verbose:
        containerized_jobs = sum(
            1 for job in dag_info["jobs"].values() if job.get("is_containerized")
        )
        print(f"   → {containerized_jobs} jobs use explicit container directives.")

    print("\n5. Submit DAG: `condor_submit_dag your_dag_file.dag`")
    print("=" * 60)


def _workflow_to_dag_info(wf: Workflow) -> Dict[str, Any]:
    """Translate *wf* into the historical ``dag_info`` mapping.

    This helper means we can continue to reuse the original script/dag writing
    logic without a risky full rewrite.  When the exporter stabilises we can
    drop the legacy format entirely.
    """

    jobs: Dict[str, Dict[str, Any]] = {}

    # Job details ------------------------------------------------------
    for idx, (tid, task) in enumerate(wf.tasks.items()):
        rule_name = task.id
        uid = task.id  # Keep same id for now

        resources = (
            task.resources
            if isinstance(task.resources, ResourceSpec)
            else ResourceSpec()
        )
        env = (
            task.environment
            if isinstance(task.environment, EnvironmentSpec)
            else EnvironmentSpec()
        )

        job_dict: Dict[str, Any] = {
            "rule_name": rule_name,
            "condor_job_name": _sanitize_condor_job_name(rule_name),
            "wildcards_dict": {},
            "inputs": task.inputs,
            "outputs": task.outputs,
            "log_files": [],
            "shell_command": task.command,
            "threads": resources.threads or resources.cpu,
            "resources": {
                k: v for k, v in resources.__dict__.items() if not k.startswith("_")
            },
            "conda_env_spec": env.conda,
            "container_img_url": env.container,
            "is_shell": bool(task.command and not task.script),
            "is_script": bool(task.script),
            "is_run": False,
            "is_notebook": False,
            "is_wrapper": False,
            "is_containerized": bool(env.container),
            "script_file": task.script,
            "run_block_code": None,
            "retries": task.retry,
            "params_dict": task.params,
            "benchmark_file": None,
            "container_img_path": None,
        }

        jobs[uid] = job_dict

    # Dependencies ------------------------------------------------------
    job_deps: Dict[str, List[str]] = {}
    for edge in wf.edges:
        parent = edge.parent
        child = edge.child
        job_deps.setdefault(child, []).append(parent)

    return {
        "jobs": jobs,
        "job_dependencies": job_deps,
        "snakefile": wf.name,
        "config": wf.config,
    }


_unsafe_re = re.compile(r"[^a-zA-Z0-9_.-]")


def _sanitize_condor_job_name(name: str) -> str:
    """Return a HTCondor-friendly job name by replacing unsafe characters."""

    return _unsafe_re.sub("_", name)


# ---------------------------------------------------------------------------
# New minimalist generator helpers (no legacy dag_info)
# ---------------------------------------------------------------------------


def _write_task_wrapper_script(task: Task, path: Path):
    """Create a minimal bash wrapper that executes the task command or script."""

    shebang = "#!/usr/bin/env bash"
    cmd = ""
    if task.command:
        cmd = task.command
    elif task.script:
        # Pick interpreter based on extension
        ext = Path(task.script).suffix.lower()
        if ext == ".py":
            cmd = f"python {task.script}"
        elif ext in {".r"}:
            cmd = f"Rscript {task.script}"
        else:
            cmd = f"bash {task.script}"
    else:
        cmd = "echo 'No command defined'"

    script_text = f"{shebang}\nset -euo pipefail\n\n# Auto-generated by wf2wf\n{cmd}\n"
    path.write_text(script_text)
    path.chmod(0o755)


def _write_dag_file(
    wf: Workflow,
    dag_path: Path,
    script_paths: Dict[str, Path],
    *,
    workdir: Path,
    default_memory: str,
    default_disk: str,
    default_cpus: int,
    inline_submit: bool = False,
):
    """Write the main DAG file with workflow metadata preservation."""

    lines = []

    # Add header with workflow metadata for round-trip preservation
    lines.append("# HTCondor DAGMan file generated by wf2wf")
    lines.append(f"# Original workflow name: {wf.name}")
    lines.append(f"# Original workflow version: {wf.version}")
    if wf.meta:
        lines.append(f"# Workflow metadata: {json.dumps(wf.meta)}")
    lines.append("")

    # Generate job definitions
    for task in wf.tasks.values():
        job_name = _sanitize_condor_job_name(task.id)
        script_path = script_paths[task.id]

        if inline_submit:
            # Generate inline submit description
            submit_content = _generate_submit_content(
                task, script_path, workdir, default_memory, default_disk, default_cpus
            )
            lines.append(f"JOB {job_name} {{")
            lines.extend([f"    {line}" for line in submit_content])
            lines.append("}")
        else:
            # Use external submit file
            submit_file = f"{job_name}.sub"
            lines.append(f"JOB {job_name} {submit_file}")

        # Add retry if specified
        if task.retry > 0:
            lines.append(f"RETRY {job_name} {task.retry}")

        # Add priority if specified
        if task.priority != 0:
            lines.append(f"PRIORITY {job_name} {task.priority}")

        lines.append("")  # Add spacing between jobs

    # Generate dependencies
    if wf.edges:
        lines.append("# Dependencies")
        for edge in wf.edges:
            parent_name = _sanitize_condor_job_name(edge.parent)
            child_name = _sanitize_condor_job_name(edge.child)
            lines.append(f"PARENT {parent_name} CHILD {child_name}")

    # Write DAG file
    dag_path.write_text("\n".join(lines) + "\n")

    # Write submit files for each job only if not using inline submit
    if not inline_submit:
        for task in wf.tasks.values():
            job_name = _sanitize_condor_job_name(task.id)
            submit_file = dag_path.parent / f"{job_name}.sub"
            _write_submit_file(
                task,
                submit_file,
                script_paths[task.id],
                workdir,
                default_memory,
                default_disk,
                default_cpus,
            )


def _write_submit_file(
    task: Task,
    submit_path: Path,
    script_path: Path,
    workdir: Path,
    default_memory: str,
    default_disk: str,
    default_cpus: int,
):
    """Write a Condor submit file for a task."""

    # Generate submit content using the shared function
    lines = _generate_submit_content(
        task, script_path, workdir, default_memory, default_disk, default_cpus
    )

    # Write to file
    submit_path.write_text("\n".join(lines) + "\n")


def _parse_memory_string(memory_str: str) -> int:
    """Parse memory string like '2GB' into MB."""
    memory_str = memory_str.upper().strip()

    if memory_str.endswith("GB"):
        return int(float(memory_str[:-2]) * 1024)
    elif memory_str.endswith("MB"):
        return int(float(memory_str[:-2]))
    elif memory_str.endswith("KB"):
        return int(float(memory_str[:-2]) / 1024)
    else:
        # Assume MB if no unit
        return int(float(memory_str))


def _generate_submit_content(
    task: Task,
    script_path: Path,
    workdir: Path,
    default_memory: str,
    default_disk: str,
    default_cpus: int,
) -> List[str]:
    """Generate submit file content as a list of lines for inline submission."""

    job_name = _sanitize_condor_job_name(task.id)

    # Extract resource requirements
    resources = (
        task.resources if isinstance(task.resources, ResourceSpec) else ResourceSpec()
    )
    environment = (
        task.environment
        if isinstance(task.environment, EnvironmentSpec)
        else EnvironmentSpec()
    )

    # Build submit file content
    lines = [
        f"# Submit description for {task.id}",
        f"executable = {script_path}",
        "",
        "# Resource requirements",
        f"request_cpus = {resources.cpu or default_cpus}",
        f"request_memory = {resources.mem_mb or _parse_memory_string(default_memory)}MB",
        f"request_disk = {resources.disk_mb or _parse_memory_string(default_disk)}MB",
    ]

    # Add GPU requirements if specified
    if resources.gpu and resources.gpu > 0:
        lines.append(f"request_gpus = {resources.gpu}")

    # Handle extra resource attributes
    if resources.extra:
        for key, value in resources.extra.items():
            lines.append(f"{key} = {value}")

    lines.extend(
        [
            "",
            "# I/O and logging",
            f"output = logs/{job_name}.out",
            f"error = logs/{job_name}.err",
            f"log = logs/{job_name}.log",
            "",
            "# Job settings",
        ]
    )

    # Determine universe and container settings
    if environment.container:
        container = environment.container
        if container.startswith("docker://"):
            # Docker universe
            lines.append("universe = docker")
            lines.append(f"docker_image = {container[9:]}")  # Remove docker:// prefix
        elif container.endswith(".sif") or "/singularity/" in container:
            # Singularity/Apptainer with vanilla universe
            lines.append("universe = vanilla")
            lines.append(f'+SingularityImage = "{container}"')
        else:
            # Assume Docker if not clearly Singularity
            lines.append("universe = docker")
            lines.append(f"docker_image = {container}")
    else:
        # Default to vanilla universe for conda or no container
        lines.append("universe = vanilla")

        # Add conda environment setup if specified
        if environment.conda:
            # Note: In practice, conda environments would be handled by wrapper scripts
            # or pre-job setup, but we can add a comment for clarity
            lines.append(f"# Conda environment: {environment.conda}")

    lines.extend(
        [
            "should_transfer_files = YES",
            "when_to_transfer_output = ON_EXIT",
            "",
            "# Submit the job",
            "queue",
        ]
    )

    # ------------------------------------------------------------------
    # Inject environment variables (e.g. WF2WF_SBOM, WF2WF_SIF)
    # ------------------------------------------------------------------

    if environment.env_vars:
        env_assignments = [f"{k}={v}" for k, v in environment.env_vars.items()]
        env_str = ",".join(env_assignments).replace('"', r"\"")
        lines.append(f'environment = "{env_str}"')

    return lines
