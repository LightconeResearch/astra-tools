# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ASTRA (Agentic Schema for Transparent Research Analysis) is the **core specification** for scientific analyses. It provides schema, validation, insights, evidence verification, and a minimal CLI.

**Key principle**: The specification says WHAT, not HOW. AI agents read the spec and generate the implementation.

**Architecture**:
- **ASTRA** (this repo) = pure specification: schema, validation, insights, verification, helpers, minimal CLI
- **Prism** (separate repo) = agentic layer: Claude Code skills, project scaffolding, remote/HPC config
- **Prism-UI** (separate repo) = visual UI: VS Code extension for viewing/editing ASTRA analyses

## Repository Structure

```
ASTRA/
├── spec/                          # THE SPECIFICATION (versioned)
│   └── draft/                     # Working version (copied to X.Y/ at release)
│       ├── analysis.schema.json
│       ├── universe.schema.json
│       └── insights.schema.json
│
├── models/                        # Pydantic models (dev only, NOT installed)
│   ├── __init__.py
│   ├── analysis.py                # Source of truth for analysis schema
│   ├── universe.py                # Source of truth for universe schema
│   └── insight.py                 # Source of truth for insights schema
│
├── examples/                      # Example projects
│   └── iris/                      # Full example analysis
│       ├── astra.yaml
│       └── universes/
│
├── src/astra/                       # Python SDK/CLI (installed package)
│   ├── __init__.py                # Public API exports
│   ├── cli.py                     # Click-based CLI (spec operations only)
│   ├── helpers.py                 # Dict-based utilities
│   ├── validation/                # Loads from spec/draft/ (dev) or bundled (prod)
│   │   ├── schema.py              # JSON schema validation
│   │   └── semantic.py            # Semantic validation
│   ├── papers/                    # Paper downloading and caching
│   └── verification/              # PDF processing and insight verification
│   # Note: astra/spec/ created at build time with bundled schemas
│
├── tools/                         # Build scripts (dev only)
│   └── generate_schemas.py        # models/ → spec/draft/
│
└── tests/
    └── fixtures/                  # Test fixtures (also in examples/)
```

## Architecture

### Key Design Principles

1. **JSON schemas are the contract** - Released versions (e.g., `spec/0.0/`) are immutable
2. **Pydantic models are the source** - `models/` generates schemas, NOT installed
3. **Schemas not in source tree** - `spec/draft/` bundled at build time, loaded directly in dev
4. **Validation is dict-based** - No Pydantic models in validation path
5. **No execution framework** - ASTRA defines what, not how. Execution is handled by Prism.

### Core Components

1. **Specification** (`spec/`)
   - Versioned JSON schemas defining the ASTRA format
   - Released versions (`spec/0.0.6/`, `spec/0.0/`) are immutable
   - `spec/draft/` is the working version

2. **Schema Generation** (`models/`)
   - Pydantic models that generate JSON schemas
   - **Dev only** - not installed as part of the package
   - Run `python tools/generate_schemas.py` after changes

3. **Validation** (`src/astra/validation/`)
   - `schema.py`: JSON schema validation (loads bundled schemas)
   - `semantic.py`: Semantic validation (dict-based)
   - Two-stage validation: schema first, then semantic checks

4. **CLI** (`src/astra/cli.py`)
   - Built with Click and Rich for terminal UI
   - Commands: init, validate, info, universe, viz, schema, paper
   - Uses `find_analysis_file()` to locate `astra.yaml`
   - `init` creates a minimal scaffold (astra.yaml, universes/, src/, outputs/, .gitignore)

5. **Helpers** (`src/astra/helpers.py`)
   - Dict-based utilities: `load_yaml`, `get_decision`, `get_default_universe`
   - No Pydantic model dependencies

6. **Papers & Verification** (`src/astra/papers/`, `src/astra/verification/`)
   - Paper downloading and caching by DOI
   - PDF text extraction and evidence quote verification

### Key Concepts

- **Analysis**: A self-similar node with inputs, outputs (with optional inline recipes), decisions, insights, and optional sub-analyses. Every level has the same structure.
- **Decision**: A choice point with multiple options (e.g., "which scaling method?"). Decisions live directly on the analysis node.
- **Universe**: One complete set of decisions — one option per decision point. The universe mirrors the analysis tree structure.
- **Multiverse**: The space of all valid decision combinations
- **Insight**: Scientific knowledge from papers, with precise evidence (W3C selectors)
- **Recipe**: An inline build rule on an output (command, optional inputs/container/resources)
- **Constraints**: `incompatible_with` and `requires` relationships between decision options (scoped within an analysis node)
- **Sub-analysis**: A nested analysis under `analyses:` with its own inputs, outputs, and decisions. Inputs can reference parent inputs (`from: input_id`) or sibling outputs (`from: sibling.output_id`).

## Development Commands

### Setup
```bash
# Install for development (includes pytest, ruff, mypy)
pip install -e ".[dev]"
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=astra tests/

# Validate an example
astra validate examples/iris/astra.yaml
```

### Schema Management
```bash
# Generate schemas from Pydantic models (after modifying models/)
python tools/generate_schemas.py

# Export bundled schemas to files
astra schema export

# View a schema
astra schema show analysis
```

### Linting and Type Checking
```bash
ruff check src/ tests/
ruff format src/ tests/
mypy src/
```

## Project Structure Created by `astra init`

When users create a new analysis with `astra init my-analysis`:

```
my-analysis/
├── astra.yaml              # Analysis specification (edit this)
├── .gitignore
├── src/                  # Analysis code
├── outputs/              # Analysis outputs
└── universes/
    └── baseline.yaml     # Default universe (decision selections)
```

For full agentic scaffolding (Claude Code config, skills, scripts, venv, HPC targets), use `prism init` instead.

## Important Design Patterns

### 1. Schema Generation Workflow
**IMPORTANT**: After any changes to `models/`, you must also verify that `models/README.md` still accurately reflects the schema. Update it if any fields, types, constraints, or relationships have changed.

```bash
# 1. Modify Pydantic models in models/
# 2. Generate JSON schemas
python tools/generate_schemas.py

# 3. Schemas are written to spec/draft/
# 4. During development, validation loads directly from spec/draft/
# 5. At build time, schemas are bundled into the package via pyproject.toml
```

### 2. Two-Stage Validation
```python
from astra.validation import validate_analysis_schema, validate_analysis_file

# Stage 1: Schema validation (structure, types)
schema_errors = validate_analysis_schema(file)

# Stage 2: Semantic validation (references, constraints)
semantic_errors = validate_analysis_file(file)
```

### 3. Dict-Based API
```python
from astra.helpers import load_yaml, get_decision, get_default_universe

# Load and work with dicts directly
data = load_yaml("astra.yaml")
decision = get_decision(data, "preprocessing")
defaults = get_default_universe(data)
```

### 4. Constraint Validation
Constraints are validated in `semantic.py`, scoped within each analysis node:
- `incompatible_with`: Lists of "decision.option" pairs that cannot coexist
- `requires`: Lists of "decision.option" pairs that must be selected together
- Universe validation checks these constraints per node

### 5. Insight-Based Decisions
Decisions can reference insights:
```yaml
decisions:
  scaling:
    options:
      standard:
        insights: [compute_scaling]  # References insights.compute_scaling
```

### 6. Self-Similar Nesting
Simple analyses put decisions at the top level. Complex analyses nest sub-analyses:
```yaml
# Root level
decisions:
  method: ...

# Nested sub-analyses
analyses:
  preprocessing:
    decisions:
      scaling: ...
  training:
    decisions:
      optimizer: ...
```

Universe files mirror this structure with `decisions` and `analyses` keys.

## Testing Philosophy

### Test Fixtures (`tests/fixtures/`)
- `valid/`: Valid analysis and universe files for testing
- `invalid/`: Files with specific validation errors (each tests one rule)

### Test Organization
- `test_schemas.py`: JSON schema validation
- `test_validation.py`: Schema and semantic validation
- `test_cli.py`: CLI commands
- `test_evidence_verification.py`: Evidence verification
- `test_unicode_matching.py`: Unicode text matching

## Common Development Tasks

### Adding a New Field to Analysis Schema
1. Add field to Pydantic model in `models/analysis.py`
2. Run `python tools/generate_schemas.py`
3. Add test fixture and test case if needed
4. Update `tests/fixtures/` with new field usage

### Adding a New Validation Rule
1. For schema validation: Add Pydantic validator to model in `models/`
2. For semantic validation: Add check to `src/astra/validation/semantic.py`
3. Create test fixture in `tests/fixtures/invalid/`
4. Add test case in `tests/test_validation.py`

### Releasing a New Schema Version

ASTRA uses **semver** (Major.Minor.Patch) versioning for the specification:
- **Major bump (1.x -> 2.0)**: Breaking changes - old files won't validate
- **Minor bump (1.0 -> 1.1)**: New optional fields only - old files still valid
- **Patch bump (1.0.0 -> 1.0.1)**: Bug fixes to schemas (no field changes)
- **Immutable**: Released versions are never modified

Release process:
1. Ensure `spec/draft/` schemas are finalized
2. Copy `spec/draft/` to `spec/X.Y.Z/` (e.g., `spec/1.0.0/`)
3. Add `spec/X.Y.Z/README.md` with version notes
4. Tag the release (e.g., `git tag v1.0.0`)
5. The X.Y.Z schemas are **immutable** after release

The `version` field in astra.yaml declares which spec version the file targets:
```yaml
version: "1.0"  # Semver format validated by regex, not checked against spec/ directories
```

## Configuration

### pyproject.toml Settings
- Python >=3.11 required
- Ruff: line-length = 100, target-version = "py311"
- MyPy: strict mode enabled
- Versioning: Uses hatch-vcs (version from git tags)
- Schema bundling: `spec/draft/` bundled into `astra/spec/` at build time

### Dependencies
- Core: click, pyyaml, jsonschema, pydantic, rich, pypdf, httpx, rapidfuzz
- Dev: pytest, pytest-cov, ruff, mypy, types-*

## Key Conventions

1. **ID patterns**: Use `^[a-z][a-z0-9_]*$` (lowercase, underscores, starts with letter)
2. **Version format**: `^\d+\.\d+(\.\d+)?$` - semver (e.g., "0.0.6", "1.0", "1.0.0")
3. **Constraint references**: Use "decision.option" format (e.g., "scaling.standard")
4. **DOI format**: Pattern `10\.\d{4,}/.*` for paper references
5. **Exclude none in YAML**: When serializing, use `exclude_none=True` to keep YAML clean

## Design Documents

- **DESIGN.md**: Complete specification of the ASTRA format
- **README.md**: User-facing documentation and quick start
