from pathlib import Path
import time
import os
from wf2wf.environ import prune_cache


def test_prune(tmp_path: Path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    old_file = cache / "old.tar.gz"
    old_file.write_bytes(b"x" * 1024)
    # set mtime to 90 days ago
    old_time = time.time() - 90 * 86400
    os.utime(old_file, (old_time, old_time))

    monkeypatch.setattr("wf2wf.environ._CACHE_DIR", cache)
    prune_cache(days=60, verbose=True)
    assert not old_file.exists()
