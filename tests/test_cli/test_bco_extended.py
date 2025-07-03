import json
import subprocess
import time
import os
from pathlib import Path
import sys

import pytest

from click.testing import CliRunner

from wf2wf.cli import cli


@pytest.fixture
def minimal_bco(tmp_path):
    bco = {
        "$schema": "https://w3id.org/ieee/ieee-2791-schema/2791object.json",
        "provenance_domain": {},
        "usability_domain": [],
        "description_domain": {},
        "execution_domain": {},
        "parametric_domain": [],
        "io_domain": {},
        "error_domain": {},
    }
    path = tmp_path / "test.bco.json"
    path.write_text(json.dumps(bco, indent=2))
    return path


def _safe_read_json_with_retry(path, max_retries=5, delay=0.1):
    """Safely read JSON file with retries for Windows file locking issues."""
    for attempt in range(max_retries):
        try:
            return json.loads(path.read_text())
        except (PermissionError, OSError) as e:
            if attempt < max_retries - 1:
                time.sleep(delay * (2 ** attempt))  # Exponential backoff
                continue
            raise e


def _fake_openssl(cmd, *a, **kw):  # helper for monkeypatch
    if "-out" in cmd:
        out_idx = cmd.index("-out") + 1
        sig_path = Path(cmd[out_idx])
        # Add a small delay to prevent Windows file locking issues
        time.sleep(0.1)
        
        # Ensure parent directory exists
        sig_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write with retry logic for Windows
        max_retries = 3
        for attempt in range(max_retries):
            try:
                sig_path.write_bytes(b"sig")
                break
            except (PermissionError, OSError):
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                raise
    return 0


def test_bco_sign_generates_etag_and_attestation(monkeypatch, minimal_bco):
    runner = CliRunner()

    # Monkeypatch subprocess and version lookup
    monkeypatch.setattr(subprocess, "check_call", _fake_openssl, raising=True)

    # Mock the modern importlib.metadata.version function
    try:
        from importlib import metadata

        monkeypatch.setattr(metadata, "version", lambda _: "0.0.0")
    except ImportError:
        # Fallback for older Python versions
        try:
            import importlib_metadata

            monkeypatch.setattr(importlib_metadata, "version", lambda _: "0.0.0")
        except ImportError:
            pass  # Will fall back to "unknown" in the actual code

    key = minimal_bco.parent / "dummy.key"
    key.write_text("stub")

    # Check if we're running under coverage (which can interfere with file operations on Windows)
    running_under_coverage = 'coverage' in sys.modules or 'pytest_cov' in sys.modules
    
    # Run the CLI command
    result = runner.invoke(cli, ["bco", "sign", str(minimal_bco), "--key", str(key)])
    
    # Add extra delay for Windows file operations, especially under coverage
    if os.name == 'nt':
        delay = 1.0 if running_under_coverage else 0.5
        time.sleep(delay)
        
        # Force garbage collection to close any open handles
        import gc
        gc.collect()
        
        # Force file system sync on Windows
        try:
            os.sync()
        except AttributeError:
            pass  # sync() not available on all Windows versions
    else:
        time.sleep(0.1)
    
    assert result.exit_code == 0, f"CLI command failed: {result.output}\nException: {result.exception}"

    # Use retry logic to read the BCO file
    data = _safe_read_json_with_retry(minimal_bco)
    assert str(data.get("etag", "")).startswith("sha256:"), "etag not updated"
    ext = data.get("extension_domain", [])
    assert any(
        e.get("namespace") == "wf2wf:provenance" for e in ext
    ), "attestation ref missing"

    # Check files exist with retry logic
    sig_file = minimal_bco.with_suffix(".sig")
    intoto_file = minimal_bco.with_suffix(".intoto.json")
    
    # Wait for files to be created and released with longer timeout on Windows + coverage
    max_wait = 5.0 if (os.name == 'nt' and running_under_coverage) else 2.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        try:
            if sig_file.exists() and intoto_file.exists():
                # Try to read them to ensure they're not locked
                sig_file.read_bytes()
                intoto_file.read_text()
                break
        except (PermissionError, OSError):
            pass
        time.sleep(0.1)
    
    assert sig_file.exists(), "Signature file not created"
    assert intoto_file.exists(), "Attestation file not created"


def test_bco_diff_outputs_changes(tmp_path):
    a = {
        "$schema": "x",
        "provenance_domain": {},
        "usability_domain": [],
        "description_domain": {"overview": "old"},
        "execution_domain": {},
        "parametric_domain": [],
        "io_domain": {},
        "error_domain": {},
    }
    b = {
        "$schema": "x",
        "provenance_domain": {},
        "usability_domain": [],
        "description_domain": {"overview": "new"},
        "execution_domain": {},
        "parametric_domain": [],
        "io_domain": {},
        "error_domain": {},
    }
    pa = tmp_path / "a.json"
    pb = tmp_path / "b.json"
    pa.write_text(json.dumps(a))
    pb.write_text(json.dumps(b))

    runner = CliRunner()
    result = runner.invoke(cli, ["bco", "diff", str(pa), str(pb)])
    assert result.exit_code == 0
    assert "### description_domain" in result.output
    assert '-  "overview": "old"' in result.output
    assert '+  "overview": "new"' in result.output


def test_convert_intent_flag(tmp_path):
    # Minimal workflow JSON
    wf_json = {
        "name": "w",
        "version": "1.0",
        "tasks": {},
        "edges": [],
        "$schema": "https://wf2wf.dev/schemas/v0.1/wf.json",
    }
    inp = tmp_path / "wf.json"
    inp.write_text(json.dumps(wf_json))

    out = tmp_path / "wf.bco.json"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "convert",
            "--input",
            str(inp),
            "--in-format",
            "json",
            "--out",
            str(out),
            "--out-format",
            "bco",
            "--intent",
            "http://purl.obolibrary.org/obo/OBI_0600015",
        ],
    )
    assert result.exit_code == 0, result.output

    data = json.loads(out.read_text())
    assert "http://purl.obolibrary.org/obo/OBI_0600015" in data.get(
        "description_domain", {}
    ).get("keywords", [])
