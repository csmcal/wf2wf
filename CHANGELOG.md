# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- Initial conda-forge recipe under `recipe/`.
- Contributor Covenant `CODE_OF_CONDUCT.md`.
- GitHub issue/PR templates and security policy.
- Packaging metadata moved fully to `pyproject.toml`; `MANIFEST.in` added.
- **Configuration Analysis and Interactive Mode**: Automatic detection of missing resource requirements, container specifications, error handling, and file transfer modes when converting between shared filesystem and distributed computing workflows.
- **Interactive Prompts**: Guided assistance with `--interactive` flag to help users address configuration gaps and optimize workflows for target execution environments.
- **Smart Defaults**: Intelligent application of default resource specifications (4GB memory/disk), retry policies (2 retries), and file transfer modes based on path patterns.
- **Enhanced Conversion Reports**: Configuration analysis section in conversion reports showing potential issues and recommendations for distributed computing environments.
- **File Transfer Mode Detection**: Automatic detection of appropriate transfer modes (`auto`, `always`, `never`, `shared`) based on file path patterns and content types.

### Changed
- Version bumped to **1.0.0** aligning PyPI and future conda-forge release.
- Enhanced CLI with configuration analysis prompts and warnings for missing specifications.
- Improved report generation with detailed configuration analysis and recommendations.
- Updated documentation with comprehensive workflow conversion differences and best practices.

## [1.0.0] – 2025-06-25
### Added
- Complete loss-mapping, reporting, interactive UX, eSTAR packaging.
- HTML/Markdown report generation with diff section.
- Config system (`wf2wf.config`).
### Changed
- CLI flag refinements; global prompt helper.

[Unreleased]: https://github.com/csmcal/wf2wf/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/csmcal/wf2wf/releases/tag/v1.0.0
