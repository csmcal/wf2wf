import importlib
from pathlib import Path


def test_cache_dir_override(tmp_path, monkeypatch):
    """wf2wf.environ should pick up WF2WF_CACHE_DIR env variable on import."""
    alt_cache = tmp_path / "custom_cache"
    monkeypatch.setenv("WF2WF_CACHE_DIR", str(alt_cache))

    env_mod = importlib.import_module("wf2wf.environ")
    importlib.reload(env_mod)

    assert env_mod._CACHE_DIR == alt_cache.expanduser() 