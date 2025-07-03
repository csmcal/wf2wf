from wf2wf.core import TypeSpec, ParameterSpec, RequirementSpec
import pytest


def test_union_parsing():
    ts = TypeSpec.parse(["File", "Directory", "null"])
    assert ts.type == "union"
    assert ts.nullable is True
    assert len(ts.members) == 2
    # Validation should pass
    ts.validate()


def test_record_and_enum_validation():
    record = TypeSpec.parse({"type": "record", "fields": {"x": "int", "y": "float"}})
    record.validate()

    enum = TypeSpec.parse({"type": "enum", "symbols": ["A", "B", "C"]})
    enum.validate()


def test_secondary_files_deep():
    p = ParameterSpec(
        id="sample", type="File", secondary_files=["^.bai", ".tbi", "foo/*/bar"]
    )
    assert len(p.secondary_files) == 3


def test_requirement_validation():
    good_docker = RequirementSpec(
        class_name="DockerRequirement", data={"dockerPull": "ubuntu:20.04"}
    )
    good_docker.validate()

    bad_docker = RequirementSpec(class_name="DockerRequirement", data={})
    with pytest.raises(ValueError):
        bad_docker.validate()

    good_res = RequirementSpec(class_name="ResourceRequirement", data={"coresMin": 2})
    good_res.validate()

    bad_res = RequirementSpec(class_name="ResourceRequirement", data={"unsupported": 1})
    with pytest.raises(ValueError):
        bad_res.validate()
