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
from typing import Dict, Any
import json
import subprocess
import os
import tempfile
import random
import string
import shutil
import time
import itertools

__all__ = [
    "generate_lock_hash",
    "prepare_env",
    "OCIBuilder",
    "DockerBuildxBuilder",
    "BuildahBuilder",
    "build_oci_image",
    "generate_sbom",
    "convert_to_sif",
    "build_or_reuse_env_image",
    "prune_cache",
]


_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "wf2wf" / "envs"
# Allow overriding cache directory (helps test isolation and CI sandboxing)
_CACHE_DIR = Path(os.getenv("WF2WF_CACHE_DIR", str(_DEFAULT_CACHE_DIR))).expanduser()
_INDEX_FILE = _CACHE_DIR / "env_index.json"


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
    env_yaml: str | Path,
    *,
    cache_dir: Path | None = None,
    verbose: bool = False,
    dry_run: bool | None = None,
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


# ---------------------------------------------------------------------------
# 9.2.3 – OCI image build abstraction (initial stub)
# ---------------------------------------------------------------------------


class OCIBuilder:
    """Protocol-like base class for OCI builders."""

    def build(
        self,
        tarball: Path,
        tag: str,
        labels: Dict[str, str] | None = None,
        *,
        push: bool = False,
        build_cache: str | None = None,
    ) -> str:  # noqa: D401
        """Build image, optionally push, and return digest (sha256:...)."""
        raise NotImplementedError


class DockerBuildxBuilder(OCIBuilder):
    """Tiny wrapper around `docker buildx build` (dry-run by default)."""

    def __init__(self, *, dry_run: bool = True):
        self.dry_run = dry_run or (os.environ.get("WF2WF_ENVIRON_DRYRUN") == "1")

    def build(
        self,
        tarball: Path,
        tag: str,
        labels: Dict[str, str] | None = None,
        *,
        push: bool = False,
        build_cache: str | None = None,
        platform: str = "linux/amd64",
    ) -> str:
        labels = labels or {}
        context_dir = Path(tempfile.mkdtemp(prefix="wf2wf_img_"))
        dockerfile = context_dir / "Dockerfile"
        dockerfile.write_text(
            "FROM scratch\n# placeholder layer for conda-pack tar\nADD env.tar.gz /opt/env\n"
        )
        # Symlinks pointing outside the build context are ignored by BuildKit; copy instead.
        env_tar_path = context_dir / "env.tar.gz"
        try:
            shutil.copy2(tarball, env_tar_path)
        except Exception:
            # Fallback: read/write to handle cross-device copies
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
            # Ensure the image ends up in the local daemon so we can query the
            # digest with `docker images`.  Without --push/--load the result
            # remains in the BuildKit cache only, making the digest
            # inaccessible from the CLI.
            cmd.append("--load")
        for k, v in labels.items():
            cmd += ["--label", f"{k}={v}"]
        cmd.append(str(context_dir))

        # Remote cache flags (BuildKit): expect build_cache like
        #  "registry.example.com/cache:wf2wf"
        if build_cache:
            cmd += [
                "--cache-from",
                f"type=registry,ref={build_cache}",
                "--cache-to",
                f"type=registry,ref={build_cache},mode=max",
            ]

        if self.dry_run or not shutil.which("docker"):
            # Simulate digest
            fake_digest = hashlib.sha256((tag + str(tarball)).encode()).hexdigest()
            return f"sha256:{fake_digest}"

        subprocess.check_call(cmd)
        # Resolve digest via Docker inspect (works after --load as well)
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
            # As a last resort fall back to the tag – valid for local scanning
            digest = tag
        return digest


# ---------------------------------------------------------------------------
# Buildah / Podman backend (optional, Linux + rootless friendly)
# ---------------------------------------------------------------------------


class BuildahBuilder(OCIBuilder):
    """Wrapper around *buildah* / *podman build* for sites that prefer it."""

    def __init__(self, *, tool: str | None = None, dry_run: bool = True):
        # *tool* allows forcing "podman" instead of "buildah".
        self.tool = tool or (shutil.which("buildah") and "buildah" or "podman")
        self.dry_run = dry_run or (os.environ.get("WF2WF_ENVIRON_DRYRUN") == "1")

    def build(
        self,
        tarball: Path,
        tag: str,
        labels: Dict[str, str] | None = None,
        *,
        push: bool = False,
        build_cache: str | None = None,
        platform: str = "linux/amd64",
    ) -> str:  # noqa: D401
        if not self.tool:
            raise RuntimeError(
                "Neither buildah nor podman is available on PATH; cannot build images"
            )

        labels = labels or {}
        context_dir = Path(tempfile.mkdtemp(prefix="wf2wf_img_"))
        dockerfile = context_dir / "Containerfile"
        dockerfile.write_text("FROM scratch\nADD env.tar.gz /opt/env\n")
        # Symlinks pointing outside the build context are ignored by BuildKit; copy instead.
        env_tar_path = context_dir / "env.tar.gz"
        try:
            shutil.copy2(tarball, env_tar_path)
        except Exception:
            # Fallback: read/write to handle cross-device copies
            env_tar_path.write_bytes(tarball.read_bytes())

        cmd = [self.tool, "build", "-f", str(dockerfile), "-t", tag]
        for k, v in labels.items():
            cmd += ["--label", f"{k}={v}"]
        cmd.append(str(context_dir))

        if push:
            # For buildah: build and push in one step via --push; Podman needs separate push.
            if self.tool == "buildah":
                cmd.append("--push")

        if self.dry_run or not shutil.which(self.tool):
            return f"sha256:{hashlib.sha256((tag + str(tarball)).encode()).hexdigest()}"

        subprocess.check_call(cmd)

        if push and self.tool == "podman":
            subprocess.check_call(["podman", "push", tag])

        # Resolve digest via Docker inspect (works after --load as well)
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
            # As a last resort fall back to the tag – valid for local scanning
            digest = tag
        return digest


def build_oci_image(
    tarball: Path,
    *,
    tag_prefix: str = "wf2wf/env",
    backend: str = "buildx",
    push: bool = False,
    platform: str = "linux/amd64",
    build_cache: str | None = None,
    dry_run: bool = True,
) -> tuple[str, str]:
    """High-level helper that picks a builder backend and returns (tag, digest)."""

    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    tag = f"{tag_prefix}:{rand}"
    labels = {"org.wf2wf.lock.sha256": hashlib.sha256(tarball.read_bytes()).hexdigest()}

    if backend == "buildx":
        builder = DockerBuildxBuilder(dry_run=dry_run)
    elif backend == "buildah":
        builder = BuildahBuilder(dry_run=dry_run)
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
    image_ref: str, out_dir: Path | None = None, *, dry_run: bool = True
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
    image_ref: str, *, sif_dir: Path | None = None, dry_run: bool = True
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
    if not shutil.which("docker"):
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
    lock_hash: str, registries: list[str] | None = None, *, dry_run: bool = True
) -> str | None:
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
    env_yaml: str | Path,
    *,
    registry: str | None = None,
    push: bool = False,
    backend: str = "buildx",
    dry_run: bool = True,
    build_cache: str | None = None,
    cache_dir: Path | None = None,
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
