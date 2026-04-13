# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ASTRA (Agentic Schema for Transparent Research Analysis) is the **Python CLI and SDK** for working with ASTRA analysis specifications. It provides validation, paper management, evidence verification, and exploration utilities.

**Architecture**:
- **astra-spec** ([separate repo](https://github.com/LightconeResearch/astra-spec)) = the specification: LinkML schemas, generated data models
- **ASTRA** (this repo) = tooling layer: validation, CLI, helpers, paper management, evidence verification
- **Prism** (separate repo) = agentic layer: Claude Code skills, project scaffolding, remote/HPC config
- **Prism-UI** (separate repo) = visual UI: VS Code extension for viewing/editing ASTRA analyses

Both `astra-spec` and this package share the `astra` Python namespace via implicit namespace packages (PEP 420). There is **no** `src/astra/__init__.py`.

## Repository Structure

```
ASTRA/
├── src/astra/                     # NO __init__.py (namespace package)
│   ├── cli.py                     # Click-based CLI
│   ├── helpers.py                 # Dict-based utilities
│   ├── validation/
│   │   ├── schema.py              # Pydantic model validation (models from astra-spec)
│   │   └── semantic.py            # Semantic cross-reference validation
│   ├── papers/                    # Paper downloading and caching
│   └── verification/              # PDF processing and insight verification
│
├── examples/                      # Example projects
│   ├── iris/                      # Simple flat analysis
│   └── iris_pipeline/             # Nested analysis with sub-analyses
│
└── tests/
    └── fixtures/                  # Test fixtures
```

## Key Design Principles

1. **astra-spec owns the specification** - LinkML schemas and Pydantic models
2. **This repo owns the tooling** - validation, CLI, paper management
3. **Namespace sharing** - Both packages provide modules under `astra.*`
4. **Two-stage validation** - Pydantic (structural) then semantic (cross-references)

## Core Components

1. **Validation** (`src/astra/validation/`)
   - `schema.py`: Structural validation using Pydantic models from `astra.datamodel`
   - `semantic.py`: Cross-reference validation (IDs, constraints, universe coverage)

2. **CLI** (`src/astra/cli.py`)
   - Built with Click and Rich
   - Commands: init, validate, info, universe, viz, schema, paper

3. **Helpers** (`src/astra/helpers.py`)
   - Dict-based utilities: `load_yaml`, `get_decision`, `get_default_universe`

4. **Papers & Verification** (`src/astra/papers/`, `src/astra/verification/`)
   - Paper downloading and caching by DOI
   - PDF text extraction and evidence quote verification

## Development Commands

### Setup
```bash
# Install for development (includes pytest, ruff, mypy)
pip install -e ".[dev]"
```

### Testing
```bash
pytest
pytest --cov=astra tests/
astra validate examples/iris/astra.yaml
```

### Linting
```bash
ruff check src/ tests/
ruff format src/ tests/
mypy src/
```

## Important Design Patterns

### 1. Two-Stage Validation
```python
from astra.validation import validate_analysis_schema, validate_analysis_file

# Stage 1: Schema validation (structure, types)
schema_errors = validate_analysis_schema(file)

# Stage 2: Semantic validation (references, constraints)
semantic_errors = validate_analysis_file(file)
```

### 2. Dict-Based API
```python
from astra.helpers import load_yaml, get_decision, get_default_universe

data = load_yaml("astra.yaml")
decision = get_decision(data, "preprocessing")
defaults = get_default_universe(data)
```

### 3. Universe Format
Universe decisions use a compact dict (decision ID → option ID):
```yaml
decisions:
  scaling: standard
  model: random_forest
```

### 4. Namespace Package
Both `astra-spec` and this package contribute to the `astra` namespace:
```python
from astra.datamodel import Analysis    # from astra-spec
from astra.helpers import load_yaml     # from this package
from astra.validation import validate_analysis_file  # from this package
```

## Common Development Tasks

### Adding a New Validation Rule
1. For semantic validation: Add check to `src/astra/validation/semantic.py`
2. Create test fixture in `tests/fixtures/invalid/`
3. Add test case in `tests/test_validation.py`

## Configuration

### pyproject.toml
- Python >=3.11
- Ruff: line-length = 100, target-version = "py311"
- MyPy: strict mode
- Versioning: hatch-vcs (from git tags)

### Dependencies
- Core: astra-spec, click, pyyaml, rich, pypdf, httpx, rapidfuzz
- Dev: pytest, pytest-cov, ruff, mypy

## Key Conventions

1. **ID patterns**: `^[a-z][a-z0-9_]*$`
2. **Version format**: `^\d+\.\d+(\.\d+)?$`
3. **Constraint references**: `decision.option` format (e.g., "scaling.standard")
4. **DOI format**: `10\.\d{4,}/.*`
