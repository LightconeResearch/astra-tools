# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ASP (Agentic Science Protocol) is a declarative specification format for scientific analyses that can be executed by AI agents. It separates **what** you want to learn from **how** to compute it through a structured YAML-based specification.

**Key principle**: The specification says WHAT, not HOW. AI agents read the spec and generate the implementation.

## Repository Structure

```
ASP/
├── spec/                    # THE SPECIFICATION (versioned JSON schemas)
│   ├── draft/               # Working draft schemas (the contract)
│   │   ├── analysis.schema.json
│   │   ├── universe.schema.json
│   │   └── insights.schema.json
│   └── v1.0/                # Frozen at release (created by CI)
│
├── models/                  # Pydantic models (generates spec/)
│   ├── __init__.py
│   ├── analysis.py
│   ├── universe.py
│   ├── insight.py
│   └── workflow.py
│
├── asp/                     # Python SDK/CLI tooling
│   ├── __init__.py
│   ├── cli.py
│   ├── validation/          # Schema + semantic validation
│   ├── schemas/             # Schema generation utilities
│   ├── workflow/            # CWL workflow integration
│   └── ...
│
├── examples/                # Conformance test suite
│   ├── valid/               # Files that MUST pass validation
│   │   ├── iris/            # Full example project
│   │   ├── minimal.yaml
│   │   └── full.yaml
│   └── invalid/             # Files that MUST fail validation
│       ├── missing_version.yaml
│       └── ...
│
├── tools/                   # Build scripts
│   ├── generate_schemas.py
│   ├── validate_examples.py
│   └── check_schema_changes.py
│
├── rfcs/                    # Design proposals
│   └── 000-template.md
│
├── tests/                   # Unit tests
├── Makefile                 # Development commands
├── DESIGN.md                # Human-readable specification
├── CONTRIBUTING.md          # Contribution guidelines
├── CHANGELOG.md             # Version history
└── pyproject.toml           # Package configuration
```

## Key Architecture Principle

**Schema definition is separate from tooling:**

1. **`spec/`** contains the JSON Schema specification - the versioned contract
2. **`models/`** contains Pydantic models that generate the schemas
3. **`asp/`** contains Python tooling that uses the schemas

The JSON schemas in `spec/draft/` are the source of truth for validation.
Other implementations can target these schemas without depending on Python.

## Development Commands

### Using Make (Recommended)
```bash
make help          # Show all commands
make install       # Install in development mode
make schemas       # Regenerate JSON schemas from Pydantic models
make validate      # Validate all example files (uses JSON schema)
make test          # Run test suite
make lint          # Run linter (ruff)
make typecheck     # Run type checker (mypy)
make check-schemas # Check schemas are in sync with models
make check         # Run ALL checks before commit
make clean         # Remove build artifacts
```

## Schema Management

### Important: Validation Uses JSON Schema Files

Validation reads from `spec/draft/*.schema.json`, NOT from Pydantic models.
This enforces the principle that the JSON schema is the contract.

### When Modifying Models

```bash
# 1. Make changes to models/*.py
# 2. Regenerate schemas
make schemas

# 3. Review the schema changes
git diff spec/draft/

# 4. Commit both model and schema changes together
git add models/ spec/draft/
git commit -m "Add new field to Analysis model"
```

### CI Enforcement

- CI validates that committed schemas match generated schemas
- If they're out of sync, CI fails with instructions to run `make schemas`
- This ensures schema changes are intentional and reviewed

### On Release

When a version is tagged (e.g., `v1.0.0`):
1. CI copies `spec/draft/` to `spec/v1.0/`
2. The versioned schemas are immutable
3. GitHub Release includes the spec as downloadable artifacts

## Examples as Conformance Tests

### `examples/valid/`
Files that MUST pass validation:
- Document correct usage patterns
- Test the validator accepts valid files
- Serve as templates for users

### `examples/invalid/`
Files that MUST fail validation. Each file tests one validation rule.

## Key Concepts

- **Analysis**: Defines problem statement, inputs, outputs, and decisions
- **Decision**: A choice point with multiple options (e.g., "which scaling method?")
- **Universe**: One complete set of decisions (one option per decision)
- **Multiverse**: The space of all valid decision combinations
- **Insight**: Scientific knowledge from papers or prior analyses, with precise evidence
- **Constraints**: `incompatible_with` and `requires` relationships between decision options

## Two-Stage Validation

```python
# Stage 1: Schema validation (structure, types) - uses JSON schema files
schema_errors = validate_analysis_schema(file)

# Stage 2: Semantic validation (references, constraints) - uses Python
semantic_errors = validate_analysis_file(file)
```

## Common Development Tasks

### Adding a New Field to Analysis Model
1. Add field to Pydantic model in `models/analysis.py`
2. Run `make schemas` to regenerate JSON schemas
3. Review the schema diff
4. Add validation test if needed
5. Update DESIGN.md
6. Commit model + schema + docs together

### Adding a New Validation Rule
1. For schema validation: Add Pydantic validator to model
2. For semantic validation: Add check to `asp/validation/semantic.py`
3. Create test fixture in `examples/invalid/`
4. Add test case in `tests/test_validation.py`

## Configuration

### pyproject.toml
- Python >=3.11 required
- Two packages: `asp` (tooling) and `models` (schema definition)
- Versioning: Uses hatch-vcs (version from git tags)

### Dependencies
- Core: click, pyyaml, jsonschema, pydantic, rich
- Dev: pytest, pytest-cov, ruff, mypy, types-*

## Key Conventions

1. **ID patterns**: Use `^[a-z][a-z0-9_]*$` (lowercase, underscores, starts with letter)
2. **Version format**: `^\d+\.\d+$` (e.g., "1.0")
3. **Constraint references**: Use "decision.option" format (e.g., "scaling.standard")
4. **DOI format**: Pattern `10\.\d{4,}/.*` for paper references

## Design Documents

- **DESIGN.md**: Complete specification of the ASP format
- **spec/draft/README.md**: Schema versioning notes
- **CONTRIBUTING.md**: How to contribute
- **CHANGELOG.md**: Version history
- **rfcs/**: Design proposals for significant changes
