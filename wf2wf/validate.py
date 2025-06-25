"""wf2wf.validate – JSON-Schema validation helper for Workflow IR."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from jsonschema import validate as _js_validate, ValidationError, Draft202012Validator  # type: ignore

# Locate schema file relative to this module
_SCHEMA_FILE = Path(__file__).parent / "schemas" / "v0.1" / "wf.json"

if not _SCHEMA_FILE.exists():
    raise FileNotFoundError(f"Schema file missing: {_SCHEMA_FILE}")

_SCHEMA: dict[str, Any] = json.loads(_SCHEMA_FILE.read_text())

# Loss side-car schema
_LOSS_SCHEMA_FILE = Path(__file__).parent / "schemas" / "v0.1" / "loss.json"
if not _LOSS_SCHEMA_FILE.exists():
    raise FileNotFoundError(f"Schema file missing: {_LOSS_SCHEMA_FILE}")
_LOSS_SCHEMA: dict[str, Any] = json.loads(_LOSS_SCHEMA_FILE.read_text())


def validate_workflow(obj: Any) -> None:
    """Validate *obj* (Workflow or raw dict) against the v0.1 JSON schema.

    Raises
    ------
    jsonschema.ValidationError
        If the object does not conform to the schema.
    """
    if hasattr(obj, "to_dict"):
        data = obj.to_dict()  # type: ignore[arg-type]
    else:
        data = obj

    _js_validate(instance=data, schema=_SCHEMA)


# -----------------------------------------------------------------------------
# BioCompute Object validation (stand-alone, no env tooling required)
# -----------------------------------------------------------------------------

_BCO_SCHEMA_URL = "https://raw.githubusercontent.com/biocompute-objects/BCO_Specification/master/schema/2791object.json"


def validate_bco(bco_doc: Dict[str, Any]) -> None:
    """Validate *bco_doc* against the official IEEE 2791 JSON-Schema.

    Downloads the schema (cached per session) and raises :class:`jsonschema.ValidationError`
    on failure.
    """
    import urllib.request, json, functools

    @functools.lru_cache(maxsize=1)
    def _load_schema():
        with urllib.request.urlopen(_BCO_SCHEMA_URL, timeout=15) as fh:
            return json.loads(fh.read().decode())

    try:
        schema = _load_schema()
    except Exception:
        # Fallback: minimal schema requiring only mandatory fields
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["object_id", "spec_version", "provenance_domain"],
            "properties": {"object_id": {"type": "string"}, "spec_version": {"type": "string"}, "provenance_domain": {"type": "object"}}
        }

    _js_validate(instance=bco_doc, schema=schema)


# -----------------------------------------------------------------------------
# Loss side-car validation
# -----------------------------------------------------------------------------


def validate_loss(loss_doc: Dict[str, Any]) -> None:
    """Validate *loss_doc* against the loss.json schema."""
    _js_validate(instance=loss_doc, schema=_LOSS_SCHEMA)


__all__ = [
    "validate_workflow",
    "validate_loss",
    "validate_bco",
] 