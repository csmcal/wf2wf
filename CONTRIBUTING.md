# Contributing to `wf2wf`

Thanks for taking the time to contribute!  This document explains the preferred workflow for working on the project.

---

## 1. Getting the code

```bash
git clone https://github.com/your-org/wf2wf.git
cd wf2wf
```

## 2. Preparing a development environment

We recommend a virtual-env or Conda env.

```bash
python -m venv .venv
source .venv/bin/activate

# Install the package in *editable* mode plus dev tools
pip install -e .[dev]

# Install the pre-commit hooks so they run on every `git commit`
pre-commit install
```

## 3. Running the test-suite

```bash
pytest -q   # quick run
pytest -n auto   # run in parallel if pytest-xdist is available
```

A single test can be run with:

```bash
pytest tests/test_core/test_core_features.py::TestCoreFeatures::test_workflow_validation
```

Code coverage:

```bash
pytest --cov=wf2wf --cov-report=term-missing
```

## 4. Style & static checks

The repository uses **ruff** for formatting and linting:

```bash
ruff check wf2wf tests
ruff format wf2wf tests
```

These run automatically in CI and via the pre-commit hooks.

## 5. Making changes

1. Create a feature branch off `main`.
2. Make your changes and add tests.
3. Ensure `pytest` and `pre-commit run --all` pass.
4. Update `CHANGELOG.md` under the **Unreleased** section.
5. Open a Pull Request (PR) on GitHub.

PRs are automatically built on Linux, macOS and Windows against Python 3.9-3.12.

## 6. Version Management & Releasing (maintainers)

We use [bumpver](https://github.com/mbarkhau/bumpver) for automated version management. See [`docs/developer/versioning.md`](docs/developer/versioning.md) for detailed instructions.

**Quick release process:**

```bash
# 1. Make changes and commit them
git add . && git commit -m "Add new feature"

# 2. Bump version (patch/minor/major)
bumpver update --minor

# 3. Push tag to trigger CI/CD release
git push origin main --tags
```

The GitHub Actions workflow automatically builds and publishes to PyPI for tagged releases.

## 7. Code of Conduct

Please note we adhere to the [Contributor Covenant](https://www.contributor-covenant.org/).  By participating you agree to abide by its terms.

## Quickstart for Contributors

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

# 5. Lint & format
$ ruff check wf2wf
$ ruff format wf2wf
```

All metadata lives in `pyproject.toml`. Use `bumpver` for version management - **do not** manually edit version numbers. New features must update `CHANGELOG.md` under **Unreleased**.
