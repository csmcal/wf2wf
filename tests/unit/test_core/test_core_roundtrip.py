"""Test round-trip serialization of workflows."""

import json
import sys
import importlib.util
from pathlib import Path

import pytest

from wf2wf.core import Task, Workflow, ParameterSpec, EnvironmentSpecificValue
from wf2wf.exporters import cwl as cwl_exporter
from wf2wf.importers import cwl as cwl_importer

proj_root = Path(__file__).resolve().parents[1]

# Ensure the *package* version of wf2wf is imported, not the CLI module.
if "wf2wf" not in sys.modules:
    init_py = proj_root / "__init__.py"
    spec = importlib.util.spec_from_file_location("wf2wf", init_py)
    wf2wf_pkg = importlib.util.module_from_spec(spec)
    sys.modules["wf2wf"] = wf2wf_pkg  # type: ignore[assignment]
    assert spec and spec.loader  # for mypy
    spec.loader.exec_module(wf2wf_pkg)  # type: ignore[arg-type]

from wf2wf.validate import validate_workflow


def minimal_workflow() -> Workflow:
    wf = Workflow(name="demo")
    wf.add_task(
        Task(
            id="step_a",
            command=EnvironmentSpecificValue("echo A", ["shared_filesystem"]),
            outputs=[ParameterSpec(id="a.txt", type="File")],
        )
    )
    wf.add_task(
        Task(
            id="step_b",
            command=EnvironmentSpecificValue("echo B", ["shared_filesystem"]),
            inputs=[ParameterSpec(id="a.txt", type="File")],
            outputs=[ParameterSpec(id="b.txt", type="File")],
            cpu=EnvironmentSpecificValue(2, ["shared_filesystem"]),
            mem_mb=EnvironmentSpecificValue(512, ["shared_filesystem"]),
        )
    )
    wf.add_edge("step_a", "step_b")
    return wf


def test_json_roundtrip(tmp_path):
    wf = minimal_workflow()

    # Validate before write
    validate_workflow(wf)

    # Write to disk
    file_path = tmp_path / "demo.json"
    wf.save_json(file_path)

    # Reload
    wf2 = Workflow.load_json(file_path)

    # Validate reloaded object
    validate_workflow(wf2)

    # Compare dict representations (ordering independent)
    assert wf.to_dict() == wf2.to_dict()
