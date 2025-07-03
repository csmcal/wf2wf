from pathlib import Path
from wf2wf.environ import prepare_env, generate_lock_hash


def test_prepare_env(tmp_path: Path):
    # Create simple conda YAML
    yaml_path = tmp_path / "env.yml"
    yaml_content = """
    name: test
    channels:
      - defaults
    dependencies:
      - python=3.11
    """
    yaml_path.write_text(yaml_content)

    res = prepare_env(yaml_path, cache_dir=tmp_path)
    # Verify artefacts
    lock_hash = generate_lock_hash(yaml_path)
    assert res["lock_hash"] == lock_hash
    assert res["lock_file"].exists()
    assert res["tarball"].exists()

    # Idempotency
    res2 = prepare_env(yaml_path, cache_dir=tmp_path)
    assert res2["tarball"] == res["tarball"]
