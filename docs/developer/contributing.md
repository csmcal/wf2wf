# Contributing Guide

We welcome pull requests!  Please follow these steps:

1. Fork the repository and create a feature branch.
2. Install dev dependencies: `pip install -e .[dev]`.
3. Run `pre-commit install` to enable linters.
4. Add or update **tests** – we aim for >95 % coverage.
5. Ensure `pytest -q` passes.
6. Submit a PR; GitHub Actions will run the test & docs matrix.

## Coding style
* `ruff` enforces import order & flake-like rules.
* Type hints are mandatory for new code.

## Docs
All docs live under `docs/` and are built by Sphinx.  Add a new `.md` page and reference it in `_toc.yml`.
