# Changelog

All notable changes to the ASP specification and tooling will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Restructured repository to separate schema definition from Python SDK
- Moved JSON schemas to `spec/draft/` as the versioned contract
- Moved Pydantic models to root `models/` directory
- Validation now uses JSON schema files, not Pydantic models
- Added `tools/` directory for build scripts

### Added
- `CONTRIBUTING.md` with contribution guidelines
- `CHANGELOG.md` for tracking changes
- `rfcs/` directory for design proposals
- `make check` command to run all validations
- Schema integrity checking in CI

## [0.1.0] - Initial Release

### Added
- ASP specification format (DESIGN.md)
- Pydantic models for Analysis, Universe, and Insight
- JSON Schema generation
- CLI with commands: init, validate, info, universe, viz, schema
- Two-stage validation (schema + semantic)
- Workflow integration (CWL parameter generation)
- Example iris classification analysis
