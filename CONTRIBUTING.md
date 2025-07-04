# Contributing to `wf2wf`

Thanks for taking the time to contribute!  This document explains the preferred workflow for working on the project.

---

## 1. Getting the code

```bash
git clone https://github.com/csmcal/wf2wf.git
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

## 8. New Features: Configuration Analysis and Interactive Mode

When contributing to wf2wf, be aware of the new configuration analysis and interactive mode features that help users convert between different workflow execution environments.

### Key Concepts

**Shared Filesystem vs Distributed Computing:**
- **Shared Filesystem Workflows** (Snakemake, CWL, Nextflow): Assume all files accessible on shared filesystem, minimal resource specs
- **Distributed Computing Workflows** (HTCondor/DAGMan): Require explicit file transfer, resource allocation, and container specifications

### Configuration Analysis Features

When converting workflows, wf2wf automatically detects:
- Missing resource requirements (memory, disk, CPU)
- Missing container/conda specifications
- Missing retry policies for error handling
- File transfer mode requirements

### Interactive Mode

The `--interactive` flag enables guided prompts:
```bash
wf2wf convert -i Snakefile -o workflow.dag --interactive
```

This prompts users to:
- Add default resource specifications
- Specify container environments
- Configure retry policies
- Review file transfer modes

### Testing New Features

When adding new configuration analysis features:
1. Add tests in `tests/test_cli/test_unified_cli.py`
2. Test both interactive and non-interactive modes
3. Verify configuration analysis appears in conversion reports
4. Test smart defaults are applied correctly

### Documentation Updates

New features should be documented in:
- `README.md` - Overview and examples
- `DESIGN.md` - Technical design and implementation
- `docs/user_guide/file_transfers.md` - Detailed user guide
- `CONTRIBUTING.md` - This section for contributors

See the existing implementation in `wf2wf/cli.py` and `wf2wf/report.py` for examples of how to integrate new configuration analysis features.
