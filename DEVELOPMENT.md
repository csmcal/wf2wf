# Development Workflow

This guide explains the development workflow and CI/CD strategy for wf2wf.

## Philosophy: Shift Left

We follow a "shift left" approach - catching issues as early as possible in the development cycle:

1. **Local pre-commit hooks** - catch formatting/linting before commit
2. **Local testing** - run tests before push
3. **CI focus** - cross-platform compatibility and integration

## Local Development Setup

### 1. Install Development Dependencies
```bash
pip install -e .[dev]
```

### 2. Install Pre-commit Hooks
```bash
pre-commit install
```

This sets up hooks that automatically run formatting and linting on every `git commit`.

### 3. Verify Setup
```bash
# Test pre-commit hooks
pre-commit run --all-files

# Run tests to ensure everything works
pytest

# Test documentation build
cd docs && python -m sphinx -b html . _build/html -W && cd ..
```

### 4. Development Workflow
```bash
# Make your changes
vim wf2wf/core.py

# Commit (pre-commit hooks run automatically)
git add .
git commit -m "Add new feature"

# Test before pushing
pytest
# OR for comprehensive testing:
pre-commit run --all-files && pytest && cd docs && python -m sphinx -b html . _build/html -W && cd ..

# Push (CI will run cross-platform tests)
git push origin feature-branch
```

## What Runs Where

### 🏠 Local (Before Commit)
**Pre-commit hooks automatically run:**
- `ruff` - Fast linting and formatting (replaces black, isort, flake8)
- `trailing-whitespace` - Remove trailing whitespace
- `end-of-file-fixer` - Ensure files end with newline
- `check-yaml/toml/json` - Validate config files

**Developer should run:**
- `pytest` - Test suite
- Manual comprehensive check (see workflow above)

### ☁️ CI (After Push)

#### Pull Requests
- **Lint job** - Runs pre-commit hooks to catch formatting issues
- **Test matrix** - Tests across Python 3.9-3.12 and Linux/macOS/Windows
- **Documentation build** - Ensures docs build correctly

#### Main Branch
- **Test matrix only** - Assumes code is already formatted
- **Documentation build** - For deployment

#### Releases (Tags)
- **Full test matrix** - Ensure compatibility
- **Documentation build** - Generate release docs
- **PyPI publish** - Automated package release

## Why This Approach?

### ❌ Old Way (Anti-pattern)
```
Developer commits → Push → CI fails on formatting → Fix → Push again
```
- Slow feedback loop
- Wastes CI resources
- Poor developer experience
- CI becomes a bottleneck

### ✅ New Way (Best Practice)
```
Pre-commit hooks catch formatting → Tests pass locally → Push → CI focuses on cross-platform issues
```
- Fast feedback (seconds vs minutes)
- Efficient CI usage
- Better developer experience
- CI focuses on what matters

## Common Workflows

### Making Changes
```bash
# 1. Make your changes
vim wf2wf/core.py

# 2. Pre-commit hooks run automatically on commit
git add .
git commit -m "Add new feature"  # Hooks run here

# 3. Test locally before pushing
pytest

# 4. Push (CI will run cross-platform tests)
git push origin feature-branch
```

### Fixing Pre-commit Issues
If pre-commit hooks fail:
```bash
# See what failed
pre-commit run --all-files

# Most issues auto-fix, just re-commit
git add .
git commit -m "Fix formatting"

# For manual fixes, check the output and fix issues
```

### Testing Across Python Versions
```bash
# Using conda/pyenv to test multiple versions locally
conda create -n wf2wf-py39 python=3.9
conda activate wf2wf-py39
pip install -e .[dev]
pytest

# Or let CI handle it - that's what it's for!
```

### Running Comprehensive Local Tests
```bash
# All checks in sequence
pre-commit run --all-files && \
pytest && \
cd docs && python -m sphinx -b html . _build/html -W && cd ..

# Or step by step for debugging
pre-commit run --all-files  # Formatting/linting
pytest                      # Tests  
cd docs                     # Documentation
python -m sphinx -b html . _build/html -W
cd ..
```

## CI Configuration Details

### Test Matrix Strategy
- **Parallel execution** - All OS/Python combinations run simultaneously
- **Fail-fast disabled** - Don't cancel other jobs if one fails
- **Coverage reporting** - Combined coverage from all platforms

### Lint Job Strategy
- **PR-only** - Only runs on pull requests, not every push to main
- **Fast feedback** - Catches formatting issues before merge
- **Separate from tests** - Doesn't slow down the test matrix

### Documentation Strategy
- **Single platform** - Only builds on Ubuntu (docs are platform-independent)
- **Artifact upload** - Saves built docs for potential deployment
- **Required for release** - Must pass before PyPI publish

## Troubleshooting

### Pre-commit Hook Failures
```bash
# Skip hooks temporarily (not recommended)
git commit --no-verify

# Fix specific hook
pre-commit run ruff --all-files

# Update hook versions
pre-commit autoupdate
```

### CI Failures
```bash
# Reproduce CI environment locally
python -m venv fresh_env
source fresh_env/bin/activate  # or fresh_env\Scripts\activate on Windows
pip install -e .[dev]
pytest

# Check specific Python version
pyenv install 3.9.18
pyenv local 3.9.18
pip install -e .[dev]
pytest
```

### Performance Issues
```bash
# Skip slow tests locally
pytest -m "not slow"

# Run tests in parallel
pytest -n auto  # Requires pytest-xdist
```

## Best Practices

### For Developers
1. **Always test locally before pushing** - run pytest at minimum
2. **Let pre-commit hooks do their job** - don't skip them with --no-verify
3. **Test one Python version locally** - let CI test the matrix
4. **Write good commit messages** - they show up in CI logs

### For Maintainers
1. **Don't merge PRs with failing lint jobs** - enforce code quality
2. **Monitor CI performance** - optimize slow tests
3. **Keep dependencies updated** - use `pre-commit autoupdate`
4. **Review coverage reports** - ensure good test coverage

## Quick Reference

### Essential Commands
```bash
# Setup (one-time)
pip install -e .[dev]
pre-commit install

# Daily workflow
git add .
git commit -m "Your message"  # Pre-commit runs automatically
pytest                        # Test before push
git push

# Maintenance
pre-commit run --all-files    # Manual formatting check
pre-commit autoupdate         # Update hook versions
pytest -v                     # Verbose test output
```

This workflow ensures high code quality while keeping development fast and CI efficient. 