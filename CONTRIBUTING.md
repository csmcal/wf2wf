# Contributing to `snake2dagman`

Thanks for taking the time to contribute!  This document explains the preferred workflow for working on the project.

---

## 1. Getting the code

```bash
git clone https://github.com/your-org/snake2dagman.git
cd snake2dagman
```

## 2. Preparing a development environment

We recommend a virtual-env or Conda env.

```bash
python -m venv .venv
source .venv/bin/activate

# Install the package in *editable* mode plus dev tools
pip install -e .
pip install -r requirements-dev.txt

# Install the pre-commit hooks so they run on every `git commit`
pre-commit install
```

## 3. Running the test-suite

```bash
pytest -n auto   # run in parallel if pytest-xdist is available
```

A single test can be run with:

```bash
pytest tests/test_conversions.py::TestConversions::test_linear_workflow_conversion
```

Code coverage:

```bash
pytest --cov=snake2dagman --cov-report=term-missing
```

## 4. Style & static checks

The repository uses **Black** and **isort** for formatting and **flake8** / **mypy** for linting:

```bash
black snake2dagman tests
isort snake2dagman tests
flake8 snake2dagman tests
mypy snake2dagman
```

These run automatically in CI and via the pre-commit hooks.

## 5. Making changes

1. Create a feature branch off `main`.
2. Make your changes and add tests.
3. Ensure `pytest` and `pre-commit run --all` pass.
4. Update `CHANGELOG.md` (if present).
5. Open a Pull Request (PR) on GitHub.

PRs are automatically built on Linux, macOS and Windows against the latest three Python versions.

## 6. Releasing (maintainers)

```bash
# bump version with bumpver or similar
git tag vX.Y.Z
python -m build
python -m twine upload dist/*
```

## 7. Code of Conduct

Please note we adhere to the [Contributor Covenant](https://www.contributor-covenant.org/).  By participating you agree to abide by its terms.

## Quickstart for Contributors *(updated 2025-06-25)*

```bash
# 1. Fork + clone
$ git clone git@github.com:YOUR_USERNAME/wf2wf.git
$ cd wf2wf

# 2. Install dev dependencies & pre-commit hooks
$ pip install -e .[dev]
$ pre-commit install

# 3. Run test suite
$ pytest -q

# 4. Build wheel / sdist locally
$ python -m build

# 5. Lint
$ ruff check wf2wf
```

All metadata lives in `pyproject.toml`; do **not** bump version in `setup.py` (legacy).  New features must update `CHANGELOG.md` under **Unreleased**.
