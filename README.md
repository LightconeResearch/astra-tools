# ASTRA - Agentic Schema for Transparent Research Analysis

[![CI](https://github.com/LightconeResearch/ASTRA/actions/workflows/ci.yml/badge.svg)](https://github.com/LightconeResearch/ASTRA/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-BSD_3--Clause-green.svg)](https://opensource.org/licenses/BSD-3-Clause)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Python CLI and SDK for working with ASTRA analysis specifications.

## What is ASTRA?

ASTRA is a declarative specification format for scientific analyses. This package provides the **tooling layer** -- validation, CLI, paper management, and evidence verification.

The specification itself is defined in [astra-spec](https://github.com/LightconeResearch/astra-spec) using LinkML schemas.

```
astra-spec            =  LinkML schemas, generated data models
ASTRA (this package)  =  Validation, CLI, helpers, evidence verification
Prism (agent layer)   =  Claude Code skills, project scaffolding, remote/HPC config
```

## Key Concepts

**Universe**: A complete set of decisions -- one option selected for each decision point. Running a universe produces the declared outputs.

**Multiverse**: The space of all valid decision combinations. Its purpose is transparency and traceability, not exhaustive search.

**Self-similar structure**: Every analysis node has the same shape (inputs, outputs, decisions). Simple analyses are flat; complex analyses nest sub-analyses under `analyses:`.

**Evidence-based decisions**: Link decisions to supporting evidence from papers, with quote verification.

**Composability**: Use outputs from one analysis as inputs to another.

## Quick Start

```bash
# Create a minimal analysis scaffold
astra init my-analysis
cd my-analysis

# Edit astra.yaml to define your analysis
# Then validate it
astra validate astra.yaml
```

For full agentic scaffolding with Claude Code integration, use `prism init` instead.

## Quick Example

See [examples/iris/](examples/iris/) for a complete working example (Iris classification with decisions for scaling and model selection).

## CLI Commands

```bash
# Project setup
astra init my-analysis               # Create minimal scaffold
astra init my-analysis --no-git      # Skip git initialization

# Validation
astra validate astra.yaml              # Validate analysis specification
astra validate universes/baseline.yaml  # Validate universe against spec
astra validate astra.yaml --verify-evidence  # Verify evidence quotes

# Exploration
astra info                           # Show analysis summary
astra info --decisions               # Show decision details
astra info --inputs                  # Show input details
astra info --outputs                 # Show output details
astra viz                            # Visualize decision space (ASCII)
astra viz --format mermaid           # Mermaid diagram

# Universe management
astra universe generate --name baseline  # Generate universe from defaults
astra universe check universes/foo.yaml  # Check universe constraints

# Schema utilities
astra schema export                  # Export JSON schemas
astra schema show analysis           # Print schema to stdout

# Paper management
astra paper add <doi>                # Download and cache a paper
astra paper add <doi> --pdf local.pdf  # Cache from local PDF
astra paper list                     # List cached papers
astra paper show <doi>               # Show paper details
astra paper path <doi>               # Print PDF path (for piping)
astra paper remove <doi>             # Remove a paper from cache
astra paper fetch-metadata <doi>     # Fetch metadata from DOI.org
astra paper fetch-metadata --all     # Fetch metadata for all cached papers
astra paper verify-quote <doi> -q "text"  # Verify a quote
astra paper verify-quotes <doi>      # Verify multiple quotes (JSON stdin)
```

## Project Structure

An ASTRA project created with `astra init` has this minimal structure:

```
my-analysis/
├── astra.yaml              # Analysis specification (source of truth)
├── .gitignore            # Git ignore rules
├── src/                  # Analysis code
├── outputs/              # Analysis outputs
└── universes/            # Universe definitions (decision selections)
    └── baseline.yaml
```

Use `prism init` for full agentic scaffolding (Claude Code config, scripts, HPC targets).

## Design Principles

1. **Declarative** - Spec says WHAT, not HOW
2. **ASTRA is source of truth** - Implementations are derived from ASTRA
3. **Self-similar** - Every level has the same structure; sub-analyses are valid analyses
4. **Transparent** - All decisions and alternatives documented
5. **Composable** - Analyses build on each other
6. **Evidence-linked** - Decisions cite supporting evidence
7. **Reproducible** - Precise provenance and verification

## Documentation

- [ASTRA Specification](https://github.com/LightconeResearch/astra-spec) - LinkML schema and format reference
- [Design Document](DESIGN.md) - Architecture, rationale, and design decisions

## License

BSD 3-Clause