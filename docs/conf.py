"""Sphinx configuration for wf2wf documentation."""
from __future__ import annotations

import datetime
import importlib.metadata as _importlib
from pathlib import Path

# -- Project information -----------------------------------------------------
project = "wf2wf"
author = "wf2wf contributors"

_release = _importlib.version("wf2wf")
version = _release

# -- General configuration ---------------------------------------------------
extensions = [
    "myst_parser",  # Markdown support
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.autosectionlabel",
    "sphinx_click",
]

myst_enable_extensions = ["colon_fence", "deflist", "html_image"]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Options for HTML output -------------------------------------------------
html_theme = "furo"
html_title = f"wf2wf {version} Documentation"

html_static_path = ["_static"]

# -- Path setup --------------------------------------------------------------
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1])) 