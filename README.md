# ASP - Agentic Science Protocol

A declarative specification format for scientific analyses that can be executed by AI agents.

## What is ASP?

ASP separates **what** you want to learn from **how** to compute it. You describe:

- **Problem statement** - The research question
- **Inputs** - Data, previous analyses, literature
- **Outputs** - Metrics, figures, tables, models
- **Decisions** - The choices that define your analysis

An AI agent reads the spec and generates the implementation (CWL workflows, scripts, etc.).

```
┌─────────────────┐      ┌─────────────┐      ┌──────────────┐      ┌─────────┐
│ ASP Analysis    │ ───▶ │ LLM Agent   │ ───▶ │ CWL Workflow │ ───▶ │ Results │
│ (what we want)  │      │ (generates) │      │ + Parameters │      │         │
└─────────────────┘      └─────────────┘      └──────────────┘      └─────────┘
```

## Key Concepts

**Universe**: A complete set of decisions—one option selected for each decision point. Running a universe produces results that answer your problem statement.

**Multiverse**: The space of all valid decision combinations. Its purpose is transparency and traceability, not exhaustive search. Document the path taken, the paths not taken, and optionally check robustness.

**Evidence-based decisions**: Link decisions to supporting evidence from previous analyses or literature.

**Composability**: Use outputs from one analysis as inputs to another.

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

## Directory Structure

```
my-analysis/
├── asp.yaml                # Analysis specification
├── universes/
│   └── baseline.yaml       # Universe definitions
├── steps/                  # Reusable CWL steps
├── workflows/
│   └── main.cwl            # Generated workflow
├── scripts/                # Python implementations
└── results/                # Execution outputs
```

## CLI Commands

```bash
asp validate asp.yaml                  # Validate specification
asp validate universes/baseline.yaml   # Validate universe against spec
asp info                               # Show analysis summary
asp info --decisions                   # Show decision space
asp universe generate --name baseline  # Generate universe from defaults
asp viz --format mermaid               # Visualize decision space
```

## Project Scope

This project currently focuses on the **specification format** itself:

- Schema definition for analysis specs (`asp.yaml`)
- Schema definition for universes (`universes/*.yaml`)
- Validation tooling
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

MIT
