from __future__ import annotations

"""wf2wf.config – user-config loader (TOML).

Priority order:
1. $WF2WF_CONFIG (explicit file path)
2. $XDG_CONFIG_HOME/wf2wf/config.toml (defaults to ~/.config/...)
3. ~/.wf2wf/config.toml

Access via wf2wf.config.get('section.key', default).
"""

from pathlib import Path
import os
from typing import Any, Dict, Union, Optional

try:
    import tomllib  # Python ≥3.11
except ModuleNotFoundError:  # pragma: no cover – Python <3.11 fallback
    import tomli as tomllib  # type: ignore

__all__ = ["get", "reload", "CONFIG"]


def _read_toml(path: Path) -> Dict[str, Any]:
    try:
        return tomllib.loads(path.read_text())  # type: ignore[arg-type]
    except Exception:
        return {}


_default_locations: list[Path] = []

# 1. Env override
_env = os.getenv("WF2WF_CONFIG")
if _env:
    _default_locations.append(Path(_env).expanduser())

# 2. XDG config path
xdg_config_home = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
_default_locations.append(xdg_config_home / "wf2wf" / "config.toml")

# 3. Legacy hidden dir
_default_locations.append(Path.home() / ".wf2wf" / "config.toml")


CONFIG: Dict[str, Any] = {}


def _load() -> Dict[str, Any]:
    for p in _default_locations:
        if p.is_file():
            cfg = _read_toml(p)
            if cfg:
                return cfg
    return {}


def reload() -> None:
    """Reload configuration from disk (testing helper)."""
    global CONFIG  # noqa: PLW0603 – module-level cache intentional
    CONFIG = _load()


reload()


def get(key: str, default: Optional[Any] = None) -> Any:
    """Dotted-key lookup with *default* fallback."""
    cur: Any = CONFIG
    for part in key.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part, default)
    return cur
