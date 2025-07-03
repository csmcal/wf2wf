import json
import subprocess
from pathlib import Path

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


def _fake_openssl(cmd, *a, **kw):  # helper for monkeypatch
    if "-out" in cmd:
        out_idx = cmd.index("-out") + 1
        sig_path = Path(cmd[out_idx])
        sig_path.parent.mkdir(parents=True, exist_ok=True)
        sig_path.write_bytes(b"sig")
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
    
    # Run the CLI command
    result = runner.invoke(cli, ["bco", "sign", str(minimal_bco), "--key", str(key)])
    
    assert result.exit_code == 0, f"CLI command failed: {result.output}\nException: {result.exception}"

    # Check the BCO file was updated
    data = json.loads(minimal_bco.read_text())
    assert str(data.get("etag", "")).startswith("sha256:"), "etag not updated"
    ext = data.get("extension_domain", [])
    assert any(
        e.get("namespace") == "wf2wf:provenance" for e in ext
    ), "attestation ref missing"

    # Check files exist
    sig_file = minimal_bco.with_suffix(".sig")
    intoto_file = minimal_bco.with_suffix(".intoto.json")
    
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
