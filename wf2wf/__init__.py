"""
wf2wf - Workflow-to-Workflow Converter

A Python package for converting workflows between different formats using
a unified intermediate representation (IR). Supports Snakemake, HTCondor DAGMan,
and other workflow engines.

Author: wf2wf development team
License: MIT
"""

__version__ = "1.0.0"
__author__ = "Christopher McAllester"
__email__ = "cmcallester@gmail.com"
__description__ = "Convert workflows between different formats using a unified intermediate representation"

# Package metadata
__all__ = ["__version__", "__author__", "__email__", "__description__"]


def get_version():
    """Return the current package version."""
    return __version__


def get_package_info():
    """Return package information dictionary."""
    return {
        "name": "wf2wf",
        "version": __version__,
        "author": __author__,
        "email": __email__,
        "description": __description__,
        "url": "https://github.com/csmcal/wf2wf",
        "license": "MIT",
    }
