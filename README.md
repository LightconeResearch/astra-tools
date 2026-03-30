# ASTRA - Agentic Schema for Transparent Research Analysis

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![RO-Crate 1.2](https://img.shields.io/badge/RO--Crate-1.2-blue)](https://www.researchobject.org/ro-crate/specification/1.2/)

A declarative specification format for scientific analyses, implemented as an [RO-Crate](https://www.researchobject.org/ro-crate/) profile.

## What is ASTRA?

ASTRA defines **what** a scientific analysis should produce, not **how** to compute it. AI agents read the specification and generate the implementation.

Every ASTRA analysis is a valid **RO-Crate** (Research Object Crate) — a standard for packaging research data with FAIR metadata. ASTRA extends RO-Crate with vocabulary for multiverse analysis concepts: decisions, options, universes, and constraints.

```
ASTRA (this package)  =  RO-Crate profile, validation, evidence verification, CLI
Prism (agent layer)   =  Claude Code skills, project scaffolding, remote/HPC config
```

## Key Concepts

- **Analysis** — A self-similar node with inputs, outputs, decisions, and optional sub-analyses. Every ASTRA project directory is an RO-Crate.
- **Decision** — A choice point with multiple options (e.g., "which scaling method?")
- **Universe** — One complete set of decisions. Running a universe produces the declared outputs.
- **Multiverse** — The space of all valid decision combinations. Its purpose is transparency, not exhaustive search.
- **Sub-analysis** — A nested analysis as a subcrate directory. Sub-analyses have the same structure as the root.
- **Insight** — A scientific claim backed by evidence (paper quotes or analysis artifacts)

## Quick Start

```bash
pip install astra

# Create a new analysis (generates ro-crate-metadata.json)
astra init my-analysis
cd my-analysis

# Validate
astra validate

# View structure
astra info
astra viz
```

## Project Structure

An ASTRA project is an RO-Crate directory:

```
my-analysis/
├── ro-crate-metadata.json    # Analysis specification (the RO-Crate)
├── src/                      # Analysis code
├── outputs/                  # Analysis outputs
└── .gitignore
```

For nested analyses, sub-analyses are subcrate directories:

```
my-pipeline/
├── ro-crate-metadata.json    # Root analysis + universes
├── feature_extraction/       # Sub-analysis (subcrate)
│   └── ro-crate-metadata.json
├── classification/           # Sub-analysis (subcrate)
│   └── ro-crate-metadata.json
└── src/
```

## Python API

```python
from astra import ASTRACrate

# Create an analysis
crate = ASTRACrate("My Analysis", version="1.0")
crate.add_input("data", "data", source="path/to/data.csv")
crate.add_output("accuracy", "metric", recipe_command="python src/evaluate.py")

crate.add_decision("model", "Model Choice", {
    "svm": {"label": "SVM", "requires": ["scaling.standard"]},
    "rf": {"label": "Random Forest"},
}, default="rf")

crate.generate_default_universe("baseline")
crate.write("my-analysis")

# Load and query
crate = ASTRACrate.load("my-analysis")
print(crate.get_decisions())
print(crate.get_universe_selections("baseline"))
```

## CLI Commands

```bash
# Project setup
astra init my-analysis           # Create RO-Crate scaffold

# Validation
astra validate                   # Validate current directory
astra validate path/to/crate     # Validate specific crate

# Exploration
astra info                       # Show analysis summary
astra info --decisions           # Show decisions only
astra viz                        # Visualize analysis tree

# Universe management
astra universe generate          # Generate default universe
astra universe check baseline    # Check universe constraints

# Paper management
astra paper add <doi>            # Download and cache a paper
astra paper list                 # List cached papers
astra paper verify-quote <doi> -q "text"  # Verify a quote in PDF
```

## RO-Crate Profile

ASTRA extends RO-Crate 1.2 with custom vocabulary for multiverse analysis. Standard schema.org types are used as supertypes wherever possible:

| ASTRA Type | schema.org Supertype | Purpose |
|---|---|---|
| `ASTRAAnalysis` | `Dataset` | Root or sub-analysis node |
| `ASTRADecision` | `DefinedTermSet` | Decision point with options |
| `ASTRAOption` | `DefinedTerm` | One choice within a decision |
| `ASTRAInsight` | `Claim` | Scientific insight with evidence |
| `ASTRARecipe` | `CreateAction` | Build rule for an output |
| `ASTRAInput` | `FormalParameter` | Analysis input |
| `ASTRAOutput` | `FormalParameter` | Analysis output |
| `ASTRAUniverse` | *(novel)* | Complete set of decision selections |

ASTRA reuses standard properties from schema.org (`name`, `description`, `identifier`, `isBasedOn`, `text`, `version`) and the Workflow Run Crate vocabulary where applicable.

## Design Principles

1. **Declarative** — Spec says WHAT, not HOW
2. **RO-Crate native** — Every analysis is a valid, FAIR research object
3. **Self-similar** — Every level has the same structure; sub-analyses are valid standalone crates
4. **Transparent** — All decisions and alternatives documented
5. **Evidence-linked** — Decisions cite supporting evidence with W3C selectors
6. **Composable** — Analyses build on each other via subcrates

## Documentation

- [Design Document](DESIGN.md) — Architecture, rationale, and RO-Crate mapping
- [Examples](examples/) — Complete working examples

## License

Apache 2.0
