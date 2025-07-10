from pathlib import Path
from wf2wf.environ import build_or_reuse_env_image, _load_index


def test_reuse(tmp_path: Path, monkeypatch):
    # Create simple YAML
    yaml_path = tmp_path / "env.yml"
    yaml_path.write_text("name: t\nchannels:[defaults]\ndependencies:[python]")

    # First build (dry-run) -> should build new image
    res1 = build_or_reuse_env_image(yaml_path, cache_dir=tmp_path, dry_run=True)
    _load_index()
    assert res1["digest"].startswith("sha256:")

    # Second call should reuse
    res2 = build_or_reuse_env_image(yaml_path, cache_dir=tmp_path, dry_run=True)
    assert res1 == res2
