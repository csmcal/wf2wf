#!/usr/bin/env python3
"""
Entry point for running wf2wf as a module: python -m wf2wf
"""

from .cli import cli, simple_main

if __name__ == "__main__":
    import importlib.util
    
    if importlib.util.find_spec("click") is not None:
        cli()
    else:
        simple_main()
