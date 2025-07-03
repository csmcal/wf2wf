"""Sphinx configuration for wf2wf documentation."""

from __future__ import annotations

import importlib.metadata as _importlib
from pathlib import Path

# -- Project information -----------------------------------------------------
project = "wf2wf"
author = "wf2wf contributors"

try:
    _release = _importlib.version("wf2wf")
    version = _release
except _importlib.PackageNotFoundError:
    # Fallback for development builds
    version = "dev"

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

# Prefix document path to section labels to avoid duplicates
autosectionlabel_prefix_document = True

# -- Options for HTML output -------------------------------------------------
html_theme = "furo"
html_title = f"wf2wf {version} Documentation"

# Better UX options
html_theme_options = {
    "sidebar_hide_name": True,
    "light_logo": "",
    "dark_logo": "",
    "navigation_with_keys": True,
}

html_static_path = ["_static"]
# -- Path setup --------------------------------------------------------------
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

