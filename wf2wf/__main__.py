#!/usr/bin/env python3
"""
Entry point for running wf2wf as a module: python -m wf2wf
"""

from .cli import cli, simple_main

if __name__ == '__main__':
    try:
        import click
        cli()
    except ImportError:
        simple_main() 