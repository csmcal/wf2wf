from wf2wf.validate import validate_bco


def test_validate_bco_minimal():
    # Minimal valid BCO skeleton (many fields optional in schema)
    bco_doc = {
        "object_id": "urn:uuid:1234",
        "spec_version": "https://w3id.org/ieee/ieee-2791-schema/2791object.json",
        "provenance_domain": {
            "name": "demo",
            "version": "1.0",
            "created": "2025-01-01T00:00:00Z",
        },
        "usability_domain": ["demonstration"],
        "description_domain": {"keywords": ["demo"]},
        "execution_domain": {"script_driver": "bash"},
        "io_domain": {"input_subdomain": [], "output_subdomain": []},
        "parametric_domain": [],
        "error_domain": {},
    }

    # Should not raise
    validate_bco(bco_doc)
