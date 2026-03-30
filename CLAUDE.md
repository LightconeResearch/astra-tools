# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ASTRA (Agentic Schema for Transparent Research Analysis) is a declarative specification format for scientific analyses, implemented as an **RO-Crate 1.2 Profile**.

**Key principle**: The specification says WHAT, not HOW. AI agents read the spec and generate the implementation.

**Architecture**:
- **ASTRA** (this repo) = RO-Crate profile, validation, evidence verification, Python SDK, CLI
- **Prism** (separate repo) = agentic layer: Claude Code skills, project scaffolding, remote/HPC config
- **Prism-UI** (separate repo) = visual UI: VS Code extension for viewing/editing ASTRA analyses

## Repository Structure

```
ASTRA/
├── examples/                      # Example projects (RO-Crate format)
│   ├── iris/                      # Simple analysis
│   │   └── ro-crate-metadata.json
│   └── iris_pipeline/             # Nested analysis with subcrates
│       ├── ro-crate-metadata.json
│       ├── feature_extraction/
│       │   └── ro-crate-metadata.json
│       └── classification/
│           └── ro-crate-metadata.json
│
├── src/astra/                     # Python SDK/CLI (installed package)
│   ├── __init__.py                # Public API: ASTRACrate
│   ├── crate.py                   # Core: ASTRACrate class (RO-Crate wrapper)
│   ├── vocabulary.py              # ASTRA vocabulary: types, properties, JSON-LD context
│   ├── cli.py                     # Click-based CLI
│   ├── validation/
│   │   └── semantic.py            # Semantic validation (cross-refs, constraints)
│   ├── papers/                    # Paper downloading and caching
│   └── verification/              # PDF processing and insight verification
│
└── tests/
    ├── test_crate.py              # Core SDK tests
    ├── test_evidence_verification.py
    └── test_unicode_matching.py
```

## Architecture

### Key Design Principles

1. **RO-Crate native** — Every analysis IS a valid RO-Crate. `ro-crate-metadata.json` is the spec.
2. **Schema.org reuse** — Custom ASTRA types use schema.org supertypes. Standard properties are used wherever possible.
3. **Self-similar nesting** — Sub-analyses are subcrate directories, each a standalone RO-Crate.
4. **No execution framework** — ASTRA defines what, not how. Execution is handled by Prism.
5. **Agent-friendly** — Designed for AI agents to read and manipulate, not primarily for humans.

### Core Components

1. **Vocabulary** (`src/astra/vocabulary.py`)
   - ASTRA RO-Crate Profile namespace and JSON-LD context
   - Custom types (Decision, Option, Universe, etc.) with schema.org supertypes
   - Custom properties for multiverse analysis concepts
   - ID builders and parsing helpers

2. **ASTRACrate** (`src/astra/crate.py`)
   - Primary API wrapping `rocrate.ROCrate`
   - Methods for all ASTRA entities: inputs, outputs, decisions, options, insights, universes
   - Subcrate management for self-similar nesting
   - Default universe generation from decision defaults

3. **Validation** (`src/astra/validation/semantic.py`)
   - Cross-reference validation (constraints, insights, recipes)
   - ID pattern validation
   - `activeWhen` condition format validation
   - Evidence source validation (doi XOR artifact)
   - Universe completeness and constraint checking
   - Recursive subcrate validation

4. **CLI** (`src/astra/cli.py`)
   - Commands: init, validate, info, viz, universe generate/check, paper *
   - Uses `find_crate_dir()` to locate nearest `ro-crate-metadata.json`

5. **Papers & Verification** (`src/astra/papers/`, `src/astra/verification/`)
   - Paper downloading and caching by DOI
   - PDF text extraction and evidence quote verification (fuzzy matching)

### Key Concepts

- **Analysis**: A self-similar node. Root is `["Dataset", "ASTRAAnalysis"]` in the RO-Crate.
- **Decision**: `["DefinedTermSet", "ASTRADecision"]` — a choice point with multiple options.
- **Option**: `["DefinedTerm", "ASTRAOption"]` — one selectable choice, with constraints.
- **Universe**: `ASTRAUniverse` — a complete set of decision selections, stored as flat entities in the root crate with `ASTRAUniverseSelection` entries.
- **Insight**: `["Claim", "ASTRAInsight"]` — a scientific claim with evidence. Used for both prior insights and findings.
- **Recipe**: `["CreateAction", "ASTRARecipe"]` — a build rule. Uses `description` for command, `object` for inputs, `result` for output.
- **Sub-analysis**: A subcrate directory with its own `ro-crate-metadata.json`.
- **Constraints**: `incompatibleWith` and `requiresOption` as `@id` references between option entities.

### RO-Crate Mapping

ASTRA reuses standard vocabulary wherever possible:

| ASTRA concept | schema.org property used |
|---|---|
| Claim text | `schema:text` (on Claim type) |
| Data source | `schema:identifier` |
| Analysis reference | `schema:isBasedOn` |
| Decision rationale | `schema:description` |
| Recipe command | `schema:description` (on CreateAction) |
| Recipe inputs | `schema:object` |
| Recipe result | `schema:result` |
| Human-readable label | `schema:alternateName` |
| Tags | `schema:keywords` |
| Timestamps | `schema:dateCreated` |

Custom ASTRA properties (no standard equivalent): `activeWhen`, `delegatesTo`, `incompatibleWith`, `requiresOption`, `hasDecision`, `hasOption`, `defaultOption`, `selectsDecision`, `selectsOption`, `outputType`, `inputType`, `inputFrom`, `outputFrom`, etc.

## Development Commands

### Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### Testing
```bash
pytest                              # Run all tests
pytest --cov=astra tests/           # With coverage
astra validate examples/iris        # Validate an example
```

### Linting
```bash
ruff check src/ tests/
ruff format src/ tests/
```

## Project Structure Created by `astra init`

```
my-analysis/
├── ro-crate-metadata.json   # Analysis spec (RO-Crate with inline universe)
├── src/                     # Analysis code
├── outputs/                 # Analysis outputs
└── .gitignore
```

## Important Design Patterns

### 1. ASTRACrate API
```python
from astra import ASTRACrate

# Create
crate = ASTRACrate("My Analysis", version="1.0")
crate.add_input("data", "data", source="path/to/data")
crate.add_output("result", "metric", recipe_command="python run.py")
crate.add_decision("method", "Method", {"a": {"label": "A"}, "b": {"label": "B"}}, default="a")
crate.generate_default_universe("baseline")
crate.write("my-analysis")

# Load and query
crate = ASTRACrate.load("my-analysis")
crate.get_decisions()
crate.get_universe_selections("baseline")
```

### 2. Validation
```python
from astra.validation import validate_analysis, validate_universe

errors = validate_analysis(crate)       # Semantic validation
errors = validate_universe("baseline", crate)  # Universe constraints
```

### 3. Self-Similar Nesting via Subcrates
```python
crate = ASTRACrate("Pipeline")
fe = crate.add_subcrate("feature_extraction", analysis_name="Feature Extraction")
fe.add_input("raw", "data", input_from="iris_data")
fe.add_output("features", "data", recipe_command="python extract.py")
fe.add_decision("method", "Method", {"pca": {"label": "PCA"}}, default="pca")

# Universe selections reference subcrate decisions with path prefixes
crate.add_universe("baseline", {
    "#decision/test_split": "#decision/test_split/option/twenty_pct",
    "feature_extraction/#decision/method": "feature_extraction/#decision/method/option/pca",
})
```

### 4. Constraint Validation
Constraints use `@id` references between option entities:
- `incompatibleWith`: Options that cannot coexist in a universe
- `requiresOption`: Options that must be selected together
- Universe validation checks these constraints

## Testing

### Test Organization
- `test_crate.py`: Core SDK tests (creation, querying, roundtrip, subcrates, universes, conditions)
- `test_evidence_verification.py`: PDF quote verification (requires `--run-network`)
- `test_unicode_matching.py`: Unicode normalization for quote matching

## Common Development Tasks

### Adding a New Field
1. Add property constant to `src/astra/vocabulary.py`
2. Add to `ASTRA_CONTEXT` dict if it's a custom ASTRA property
3. Add parameter to relevant `add_*` method in `src/astra/crate.py`
4. Add validation rule in `src/astra/validation/semantic.py` if needed
5. Add test in `tests/test_crate.py`

### Adding a New Validation Rule
1. Add check function in `src/astra/validation/semantic.py`
2. Call it from `validate_analysis()` or `validate_universe()`
3. Add test case in `tests/test_crate.py`

## Configuration

### pyproject.toml
- Python >=3.11 required
- Core deps: click, rocrate, rich, pypdf, httpx, rapidfuzz
- Dev deps: pytest, pytest-cov, ruff, mypy, pydantic, pyyaml
- Ruff: line-length = 100, target-version = "py311"

## Key Conventions

1. **ID patterns**: `^[a-z][a-z0-9_]*$` (lowercase, underscores, starts with letter)
2. **Entity @id format**: `#decision/{name}`, `#output/{name}`, `#universe/{name}`, etc.
3. **Constraint references**: `@id` references to option entities
4. **Condition format**: `decision.option` or `~decision.option` (negation), lists AND'd
5. **Subcrate paths**: `subcrate_name/#decision/name` for cross-crate references
6. **Schema.org properties**: Use standard names directly (`name`, `description`, `identifier`, etc.)

## Design Documents

- **DESIGN.md**: Architecture, multiverse concept, and RO-Crate mapping
- **README.md**: User-facing documentation and quick start
