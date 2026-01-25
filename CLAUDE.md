# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ASP (Agentic Science Protocol) is a declarative specification format for scientific analyses that can be executed by AI agents. It separates **what** you want to learn from **how** to compute it through a structured YAML-based specification.

**Key principle**: The specification says WHAT, not HOW. AI agents read the spec and generate the implementation.

## Repository Structure

```
agentic-science-protocol/
├── spec/                          # THE SPECIFICATION (versioned)
│   └── draft/                     # Working version (becomes 1.0/ at release)
│       ├── analysis.schema.json
│       ├── universe.schema.json
│       └── insights.schema.json
│   # 1.0/, 1.1/, 2.0/, etc. created at release (immutable once released)
│
├── .claude-plugin/                # Claude Code plugin marketplace (at repo root)
│   └── marketplace.json           # Marketplace definition
│
├── claude/                        # Claude Code plugin implementations
│   └── asp/                       # ASP plugin
│       ├── .claude-plugin/
│       │   └── plugin.json        # Plugin manifest
│       └── skills/
│           └── asp/
│               └── SKILL.md       # Skill instructions
│
├── models/                        # Pydantic models (dev only, NOT installed)
│   ├── __init__.py
│   ├── analysis.py                # Source of truth for analysis schema
│   ├── universe.py                # Source of truth for universe schema
│   └── insight.py                 # Source of truth for insights schema
│
├── examples/                      # Example projects
│   └── iris/                      # Full example analysis
│       ├── asp.yaml
│       └── universes/
│
├── src/asp/                       # Python SDK/CLI (installed package)
│   ├── __init__.py                # Public API exports
│   ├── cli.py                     # Click-based CLI
│   ├── helpers.py                 # Dict-based utilities
│   ├── validation/                # Loads from spec/draft/ (dev) or bundled (prod)
│   │   ├── schema.py              # JSON schema validation
│   │   └── semantic.py            # Semantic validation
│   ├── models/                    # Pydantic models (for workflow module)
│   └── workflow/                  # CWL integration
│   # Note: asp/spec/ created at build time with bundled schemas
│
├── tools/                         # Build scripts (dev only)
│   └── generate_schemas.py        # models/ → spec/draft/
│
├── tests/
│   └── fixtures/                  # Test fixtures (also in examples/)
│
└── docs/
```

## Architecture

### Key Design Principles

1. **JSON schemas are the contract** - Released versions (e.g., `spec/1.0/`) are immutable
2. **Pydantic models are the source** - `models/` generates schemas, NOT installed
3. **Schemas not in source tree** - `spec/draft/` bundled at build time, loaded directly in dev
4. **Validation is dict-based** - No Pydantic models in validation path
5. **Workflow can use Pydantic** - CWL integration uses models internally

### Core Components

1. **Specification** (`spec/`)
   - Versioned JSON schemas defining the ASP format
   - `spec/v1/` is immutable once released
   - `spec/draft/` is the working version

2. **Schema Generation** (`models/`)
   - Pydantic models that generate JSON schemas
   - **Dev only** - not installed as part of the package
   - Run `python tools/generate_schemas.py` after changes

3. **Validation** (`src/asp/validation/`)
   - `schema.py`: JSON schema validation (loads bundled schemas)
   - `semantic.py`: Semantic validation (dict-based)
   - Two-stage validation: schema first, then semantic checks

4. **CLI** (`src/asp/cli.py`)
   - Built with Click and Rich for terminal UI
   - Commands: init, validate, info, universe, viz, schema
   - Uses `find_analysis_file()` to locate `asp.yaml`

5. **Helpers** (`src/asp/helpers.py`)
   - Dict-based utilities: `load_yaml`, `get_decision`, `get_default_universe`
   - No Pydantic model dependencies

### Key Concepts

- **Analysis**: Defines problem statement, inputs, outputs, and decisions
- **Decision**: A choice point with multiple options (e.g., "which scaling method?")
- **Universe**: One complete set of decisions (one option per decision)
- **Multiverse**: The space of all valid decision combinations
- **Insight**: Scientific knowledge from papers or prior analyses, with precise evidence
- **Constraints**: `incompatible_with` and `requires` relationships between decision options

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
pytest --cov=asp tests/

# Validate an example
asp validate examples/iris/asp.yaml
```

### Schema Management
```bash
# Generate schemas from Pydantic models (after modifying models/)
python tools/generate_schemas.py

# Export bundled schemas to files
asp schema export

# View a schema
asp schema show analysis
```

### Linting and Type Checking
```bash
ruff check src/ tests/
ruff format src/ tests/
mypy src/
```

## Project Structure Created by `asp init`

When users create a new analysis with `asp init my-analysis`:

```
my-analysis/
├── asp.yaml              # Analysis specification (edit this)
├── .gitignore
├── universes/
│   └── baseline.yaml     # Default universe (decision selections)
├── workflows/            # Generated workflows
├── steps/                # Reusable workflow steps
├── results/              # Execution outputs (gitignored)
├── .claude/              # Claude Code configuration
│   └── settings.json     # Auto-installs ASP plugin from marketplace
```

The `settings.json` configures Claude Code to automatically install the ASP plugin from the marketplace when the project is opened.

## Important Design Patterns

### 1. Schema Generation Workflow
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
from asp.validation import validate_analysis_schema, validate_analysis_file

# Stage 1: Schema validation (structure, types)
schema_errors = validate_analysis_schema(file)

# Stage 2: Semantic validation (references, constraints)
semantic_errors = validate_analysis_file(file)
```

### 3. Dict-Based API
```python
from asp.helpers import load_yaml, get_decision, get_default_universe

# Load and work with dicts directly
data = load_yaml("asp.yaml")
decision = get_decision(data, "preprocessing")
defaults = get_default_universe(data)
```

### 4. Constraint Validation
Constraints are validated in `semantic.py`:
- `incompatible_with`: Lists of "decision.option" pairs that cannot coexist
- `requires`: Lists of "decision.option" pairs that must be selected together
- Universe validation checks these constraints

### 5. Evidence-Based Decisions
Decisions can reference insights as evidence:
```yaml
decisions:
  scaling:
    options:
      standard:
        evidence:
          - insight: compute_scaling  # References insights.compute_scaling
```

## Testing Philosophy

### Test Fixtures (`tests/fixtures/`)
- `valid/`: Valid analysis and universe files for testing
- `invalid/`: Files with specific validation errors (each tests one rule)

### Test Organization
- `test_models.py`: Pydantic model validation
- `test_schemas.py`: JSON schema validation
- `test_validation.py`: Schema and semantic validation
- `test_insight.py`: Insight model and evidence validation
- `test_cli.py`: CLI commands

## Common Development Tasks

### Adding a New Field to Analysis Schema
1. Add field to Pydantic model in `models/analysis.py`
2. Run `python tools/generate_schemas.py`
3. Add test fixture and test case if needed
4. Update `tests/fixtures/` with new field usage

### Adding a New Validation Rule
1. For schema validation: Add Pydantic validator to model in `models/`
2. For semantic validation: Add check to `src/asp/validation/semantic.py`
3. Create test fixture in `tests/fixtures/invalid/`
4. Add test case in `tests/test_validation.py`

### Releasing a New Schema Version

ASP uses **Major.Minor** versioning for the specification:
- **Major bump (1.x → 2.0)**: Breaking changes - old files won't validate
- **Minor bump (1.0 → 1.1)**: New optional fields only - old files still valid
- **Immutable**: Released versions are never modified

Release process:
1. Ensure `spec/draft/` schemas are finalized
2. Copy `spec/draft/` to `spec/X.Y/` (e.g., `spec/1.0/`)
3. Add `spec/X.Y/README.md` with version notes
4. Tag the release (e.g., `git tag v1.0.0`)
5. The X.Y schemas are **immutable** after release

The `version` field in asp.yaml must match a released spec version:
```yaml
version: "1.0"  # Must match a spec/X.Y/ directory
```

## Configuration

### pyproject.toml Settings
- Python >=3.11 required
- Ruff: line-length = 100, target-version = "py311"
- MyPy: strict mode enabled
- Versioning: Uses hatch-vcs (version from git tags)
- Schema bundling: `spec/draft/` bundled into `asp/spec/` at build time

### Dependencies
- Core: click, pyyaml, jsonschema, pydantic, rich
- Dev: pytest, pytest-cov, ruff, mypy, types-*

## Key Conventions

1. **ID patterns**: Use `^[a-z][a-z0-9_]*$` (lowercase, underscores, starts with letter)
2. **Version format**: `^\d+\.\d+$` - Major.Minor (e.g., "1.0", "1.1", "2.0")
3. **Constraint references**: Use "decision.option" format (e.g., "scaling.standard")
4. **DOI format**: Pattern `10\.\d{4,}/.*` for paper references
5. **Exclude none in YAML**: When serializing, use `exclude_none=True` to keep YAML clean

## Design Documents

- **DESIGN.md**: Complete specification of the ASP format
- **README.md**: User-facing documentation and quick start
- **claude/asp/skills/asp/SKILL.md**: Skill instructions for working with ASP
