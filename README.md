# ASP - Agentic Science Protocol

[![CI](https://github.com/EiffL/ASP/actions/workflows/ci.yml/badge.svg)](https://github.com/EiffL/ASP/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A declarative specification format for scientific analyses that can be executed by AI agents.

## What is ASP?

ASP separates **what** you want to learn from **how** to compute it. You describe:

- **Problem statement** - The research question
- **Inputs** - Data, previous analyses, literature
- **Outputs** - Metrics, figures, tables, models
- **Decisions** - The choices that define your analysis

An AI agent reads the spec and generates the implementation (workflows, scripts, etc.).

```
┌─────────────────┐      ┌─────────────┐      ┌──────────────┐      ┌─────────┐
│ ASP Analysis    │ ───▶ │ LLM Agent   │ ───▶ │   Workflow   │ ───▶ │ Results │
│ (what we want)  │      │ (generates) │      │ + Parameters │      │         │
└─────────────────┘      └─────────────┘      └──────────────┘      └─────────┘
```

## Key Concepts

**Universe**: A complete set of decisions—one option selected for each decision point. Running a universe produces results that answer your problem statement.

**Multiverse**: The space of all valid decision combinations. Its purpose is transparency and traceability, not exhaustive search. Document the path taken, the paths not taken, and optionally check robustness.

**Evidence-based decisions**: Link decisions to supporting evidence from previous analyses or literature.

**Composability**: Use outputs from one analysis as inputs to another.

## Installation

```bash
git clone https://github.com/your-org/ASP.git
cd ASP
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

For development (includes pytest, ruff, mypy):
```bash
pip install -e ".[dev]"
```

## Quick Example

```yaml
$schema: "https://asp-spec.org/v1/schema.json"
version: "1.0"

analysis:
  name: "Iris Classification Study"

  problem: |
    Build a robust classifier for the Iris dataset that accurately
    predicts species from flower measurements.

  inputs:
    - id: iris_data
      type: data
      source: "sklearn.datasets.load_iris"

  outputs:
    - id: accuracy
      type: metric
      dtype: float
      range: [0, 1]
      primary: true

    - id: confusion_matrix
      type: figure
      formats: [png]

decisions:
  scaling:
    label: "Feature Scaling"
    type: method
    importance: 2
    default: standard
    options:
      none:
        label: "No Scaling"
      standard:
        label: "StandardScaler"
      minmax:
        label: "MinMaxScaler"
        incompatible_with: ["model.svm"]

  model:
    label: "Classification Model"
    type: method
    importance: 1
    default: random_forest
    options:
      svm:
        label: "Support Vector Machine"
      random_forest:
        label: "Random Forest"
      logistic:
        label: "Logistic Regression"
```

See [examples/iris/](examples/iris/) for a complete working example.

## CLI Commands

```bash
asp validate asp.yaml                  # Validate analysis specification
asp validate universes/baseline.yaml   # Validate universe against spec
asp info                               # Show analysis summary
asp info --decisions                   # Show decision details
asp universe generate --name baseline  # Generate universe from defaults
asp universe check universes/foo.yaml  # Check universe constraints
asp viz                                # Visualize decision space (ASCII)
asp viz --format mermaid               # Visualize as Mermaid diagram
asp schema export                      # Export JSON schemas to schemas/
asp schema show analysis               # Print analysis schema to stdout
```

## Project Structure

```
my-analysis/
├── asp.yaml                # Analysis specification
└── universes/
    └── baseline.yaml       # Universe definitions
```

## Project Scope

This project currently focuses on the **specification format** itself:

- Pydantic models as the source of truth for the specification
- JSON Schemas auto-generated from models (`asp schema export`)
- Validation tooling (schema + semantic)
- Visualization of decision spaces

Workflow generation and execution by AI agents is a future goal that builds on this foundation.

## Design Principles

1. **Declarative** - Spec says WHAT, not HOW
2. **Transparent** - All decisions and alternatives documented
3. **Composable** - Analyses build on each other
4. **Evidence-linked** - Decisions cite supporting evidence
5. **Reproducible** - Precise provenance and execution records

## Documentation

See [DESIGN.md](DESIGN.md) for the complete specification.

## License

Apache 2.0
