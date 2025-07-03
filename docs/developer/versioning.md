# Version Management

This project uses [bumpver](https://github.com/mbarkhau/bumpver) for automated version management to ensure consistency across all files and streamline the release process.

## Quick Start

```bash
# Install development dependencies (includes bumpver)
pip install -e .[dev]

# Test version management (dry run)
bumpver update --dry --patch

# Bump version for a patch release
bumpver update --patch

# Update CHANGELOG.md manually (see below)
# Push the new tag to trigger CI/CD
git push origin main --tags
```

## Configuration

Version management is configured in `.bumpver.toml` and automatically updates:

- `pyproject.toml` - Package version
- `wf2wf/__init__.py` - Python module version  
- `.bumpver.toml` - Configuration file itself

**Note:** CHANGELOG.md updates are currently manual due to the complexity of the Keep a Changelog format. This ensures accuracy and allows for proper release notes.

## Usage

### Install bumpver

```bash
pip install -e .[dev]  # Installs bumpver with other dev dependencies
```

### Bump Version

Use semantic versioning commands:

```bash
# Patch release (1.0.0 → 1.0.1) - Bug fixes
bumpver update --patch

# Minor release (1.0.0 → 1.1.0) - New features, backward compatible
bumpver update --minor  

# Major release (1.0.0 → 2.0.0) - Breaking changes
bumpver update --major
```

### Update CHANGELOG.md

After running `bumpver update`, manually update the CHANGELOG.md:

1. Add a new section for the version:
   ```markdown
   ## [Unreleased]
   
   ## [1.0.1] – 2024-01-15
   ### Fixed
   - Bug fixes and improvements
   ```

2. Update the links at the bottom:
   ```markdown
   [Unreleased]: https://github.com/your-org/wf2wf/compare/v1.0.1...HEAD
   [1.0.1]: https://github.com/your-org/wf2wf/compare/v1.0.0...v1.0.1
   ```

### Test Before Release

Always test the version bump with `--dry` first:

```bash
bumpver update --dry --patch  # Shows what would change
bumpver update --patch        # Actually makes the changes
```

### Release Process

1. **Bump version:** `bumpver update --patch|minor|major`
2. **Update CHANGELOG.md:** Add release notes manually
3. **Commit changes:** `git add CHANGELOG.md && git commit -m "Update changelog for v1.0.1"`
4. **Push with tags:** `git push origin main --tags`
5. **CI/CD triggers:** Automated testing and PyPI publication

## Configuration Details

The `.bumpver.toml` file contains:

```toml
[bumpver]
current_version = "1.0.0"
version_pattern = "MAJOR.MINOR.PATCH"
commit_message = "bump version {old_version} → {new_version}"
commit = true
tag = true
push = false  # Manual push for safety

[bumpver.file_patterns]
"pyproject.toml" = [
    'version = "{version}"',
]
"wf2wf/__init__.py" = [
    '__version__ = "{version}"',
]
```

## Benefits

- **Consistency:** All version numbers stay in sync
- **Automation:** One command updates all files
- **Safety:** Dry-run mode prevents mistakes
- **Git Integration:** Automatic commits and tags
- **Semantic Versioning:** Clear version progression
- **Reproducibility:** Essential for scientific software

## Version Pattern

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** version when you make incompatible API changes
- **MINOR** version when you add functionality in a backward compatible manner  
- **PATCH** version when you make backward compatible bug fixes

## Manual Override

If you need to set a specific version:

```bash
bumpver update --set-version 2.0.0-rc1
```

## Troubleshooting

### Version Mismatch
If versions get out of sync, update `.bumpver.toml` with the correct current version and run:

```bash
bumpver update --patch  # This will sync all files
```

### Failed Commit
If bumpver fails to commit, check that all files are staged and there are no merge conflicts.

### CI/CD Issues
The release workflow requires:
- All tests passing
- Valid tag format (`v*`)
- PyPI API token configured in repository secrets 