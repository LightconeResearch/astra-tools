# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ASP (Agentic Science Protocol) is a declarative specification format for scientific analyses that can be executed by AI agents. It separates **what** you want to learn from **how** to compute it through a structured YAML-based specification.

**Key principle**: The specification says WHAT, not HOW. AI agents read the spec and generate the implementation.

## Architecture

### Core Components

1. **Pydantic Models** (`src/asp/models/`)
   - `analysis.py`: Analysis, Input, Output, Decision, Option, Evidence, Source models
   - `universe.py`: Universe model (decision selections)
   - `insight.py`: Insight model (scientific knowledge with provenance)
   - These models are the **source of truth** for the specification format
   - JSON schemas are auto-generated from these models

2. **Validation** (`src/asp/validation/`)
   - `schema.py`: JSON schema validation
   - `semantic.py`: Semantic validation (constraints, references, evidence)
   - Two-stage validation: schema first, then semantic checks

3. **CLI** (`src/asp/cli.py`)
   - Built with Click and Rich for terminal UI
   - Commands: init, validate, info, universe, viz, schema
   - Uses `find_analysis_file()` to locate `asp.yaml` in current or parent directories

4. **Schemas** (`src/asp/schemas/`)
   - Auto-generated JSON schemas from Pydantic models
   - Exported to `schemas/` directory

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

# Run specific test file
pytest tests/test_validation.py

# Run specific test
pytest tests/test_validation.py::test_validate_universe_incompatible
```

### Linting and Type Checking
```bash
# Format and lint with ruff
ruff check src/ tests/
ruff format src/ tests/

# Type check with mypy
mypy src/
```

### Schema Management
```bash
# Export JSON schemas (run after modifying Pydantic models)
asp schema export

# View a schema
asp schema show analysis
```

## Project Structure Created by `asp init`

When users create a new analysis with `asp init my-analysis`:

```
my-analysis/
├── asp.yaml              # Analysis specification (edit this)
├── README.md
├── .gitignore
├── universes/
│   └── baseline.yaml     # Default universe (decision selections)
├── workflows/            # Generated workflows (not in spec)
│   └── params/           # Workflow parameters per universe
├── steps/                # Reusable workflow steps
│   ├── io/
│   ├── preprocessing/
│   ├── models/
│   └── evaluation/
├── scripts/              # Implementation scripts
├── results/              # Execution outputs (gitignored)
└── .asp/
    └── branches.yaml     # Branch metadata
```

## Important Design Patterns

### 1. Pydantic Models as Source of Truth
- **Never manually edit JSON schemas** - they are auto-generated
- After modifying models in `src/asp/models/`, run `asp schema export`
- All validation rules belong in Pydantic model validators

### 2. Two-Stage Validation
```python
# Stage 1: Schema validation (structure, types)
schema_errors = validate_analysis_schema(file)

# Stage 2: Semantic validation (references, constraints)
semantic_errors = validate_analysis_file(file)
```

### 3. Constraint Validation
Constraints are validated in `semantic.py`:
- `incompatible_with`: Lists of "decision.option" pairs that cannot coexist
- `requires`: Lists of "decision.option" pairs that must be selected together
- Universe validation checks these constraints

### 4. Evidence-Based Decisions
Decisions can reference insights as evidence:
```yaml
decisions:
  scaling:
    options:
      standard:
        evidence:
          - insight: compute_scaling  # References insights.compute_scaling
```

### 5. Insights with Precise Provenance
Insights capture scientific knowledge with traceable evidence:
- From papers: DOI + figure/quote/table/equation/result
- From analyses: analysis ID + metric/output

## Testing Philosophy

### Test Fixtures (`tests/fixtures/`)
- `valid/`: Valid analysis and universe files
- `invalid/`: Files with specific validation errors
- Each invalid fixture tests one validation rule

### Test Organization
- `test_models.py`: Pydantic model validation
- `test_schemas.py`: JSON schema generation
- `test_validation.py`: Schema and semantic validation
- `test_insight.py`: Insight model and evidence validation
- `test_cli.py`: CLI commands

### Adding New Validation Rules
1. Add validator to Pydantic model or semantic validation
2. Create test fixture in `tests/fixtures/invalid/`
3. Add test case in `test_validation.py`

## Common Development Tasks

### Adding a New Field to Analysis Model
1. Add field to Pydantic model in `src/asp/models/analysis.py`
2. Run `asp schema export` to regenerate schemas
3. Add validation test if needed
4. Update documentation in DESIGN.md

### Adding a New CLI Command
1. Add command function to `src/asp/cli.py`
2. Use Click decorators: `@main.command()` or `@group.command()`
3. Use Rich console for pretty output
4. Add test in `test_cli.py` using Click's testing utilities

### Adding a New Validation Rule
1. For schema validation: Add Pydantic validator to model
2. For semantic validation: Add check to `validation/semantic.py`
3. Create test fixture demonstrating the error
4. Test both detection and error message clarity

## Git Workflow Integration

### Analysis Evolution
- Analysis definitions evolve through Git commits
- Branches represent fundamentally different approaches (e.g., classical ML vs deep learning)
- Tags mark milestones (submission, publication)
- Worktrees enable parallel execution of different branches

### Execution Records
Execution records capture which version of the analysis produced which results:
```yaml
id: baseline_001
universe: baseline
commit: "abc123def"  # Git commit of analysis definition
branch: "main"
```

## Configuration

### pyproject.toml Settings
- Python >=3.11 required
- Ruff: line-length = 100, target-version = "py311"
- MyPy: strict mode enabled
- Versioning: Uses hatch-vcs (version from git tags)

### Dependencies
- Core: click, pyyaml, jsonschema, pydantic, rich
- Dev: pytest, pytest-cov, ruff, mypy, types-*

## ASP Skill for Claude Code

There's a Claude Code skill at `.claude/skills/asp-analysis/` that helps with:
- Creating new analyses
- Extracting insights from papers
- Validating specifications
- Managing universes

When working on ASP-specific tasks, consider using this skill.

## Design Documents

- **DESIGN.md**: Complete specification of the ASP format
- **README.md**: User-facing documentation and quick start
- **.claude/skills/asp-analysis/SKILL.md**: Skill instructions for working with ASP

## Key Conventions

1. **ID patterns**: Use `^[a-z][a-z0-9_]*$` (lowercase, underscores, starts with letter)
2. **Version format**: `^\d+\.\d+$` (e.g., "1.0")
3. **Constraint references**: Use "decision.option" format (e.g., "scaling.standard")
4. **DOI format**: Pattern `10\.\d{4,}/.*` for paper references
5. **Exclude none in YAML**: When serializing, use `exclude_none=True` to keep YAML clean

## Future Directions

Per DESIGN.md, the current focus is the **specification format itself**:
- Pydantic models as source of truth
- JSON schema generation
- Validation tooling
- Decision space visualization

**Future work** (not yet implemented):
- Workflow generation by AI agents
- Execution engine integration
- Multiverse analysis tools
- Results comparison across universes
