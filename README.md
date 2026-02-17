# ASP - Agentic Science Protocol

Part of [Lightcone Research](https://github.com/LightconeResearch/lightcone.dev) — install all tools with:
```bash
curl -fsSL https://lightconeresearch.github.io/lightcone.dev/install.sh | bash
```

---

A declarative specification format for scientific analyses that can be executed by AI agents.

## What is ASP?

ASP is the **core specification** for describing scientific analyses. It separates **what** you want to learn from **how** to compute it:

- **Inputs** - Data, previous analyses
- **Outputs** - Metrics, figures, tables, data, reports
- **Decisions** - The choices that define your analysis
- **Insights** - Evidence from papers with quote verification
- **Constraints** - Relationships between decision options
- **Recipes** - Optional build rules for producing outputs

ASP makes no prescription about execution frameworks. The specification defines *what* to compute; execution is handled by the agentic layer.

```
ASP (this package)  =  Schema, validation, insights, evidence verification, CLI
Prism (agent layer) =  Claude Code skills, project scaffolding, remote/HPC config
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
asp init my-analysis
cd my-analysis

# Edit asp.yaml to define your analysis
# Then validate it
asp validate asp.yaml
```

For full agentic scaffolding with Claude Code integration, use `prism init` instead.

## Quick Example

```yaml
version: "1.0"
name: "Iris Classification Study"

inputs:
  - id: iris_data
    type: data
    source: "sklearn.datasets.load_iris"

outputs:
  - id: accuracy
    type: metric
    description: "Classification accuracy on held-out test set"

  - id: confusion_matrix
    type: figure
    description: "Confusion matrix heatmap"

  - id: conclusion
    type: report
    description: "Summary of findings"

decisions:
  scaling:
    label: "Feature Scaling"
    type: method
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
    default: random_forest
    options:
      svm:
        label: "Support Vector Machine"
        requires: ["scaling.standard"]
      random_forest:
        label: "Random Forest"
      logistic:
        label: "Logistic Regression"

recipes:
  train:
    command: python src/train.py
    outputs: [accuracy, confusion_matrix, conclusion]
```

See [examples/iris/](examples/iris/) for a complete working example.

## CLI Commands

```bash
# Project setup
asp init my-analysis               # Create minimal scaffold
asp init my-analysis --no-git      # Skip git initialization

# Validation
asp validate asp.yaml              # Validate analysis specification
asp validate universes/baseline.yaml  # Validate universe against spec
asp validate asp.yaml --verify-evidence  # Verify evidence quotes

# Exploration
asp info                           # Show analysis summary
asp info --decisions               # Show decision details
asp viz                            # Visualize decision space (ASCII)
asp viz --format mermaid           # Mermaid diagram

# Universe management
asp universe generate --name baseline  # Generate universe from defaults
asp universe check universes/foo.yaml  # Check universe constraints

# Schema utilities
asp schema export                  # Export JSON schemas
asp schema show analysis           # Print schema to stdout

# Paper management
asp paper add <doi>                # Cache a paper
asp paper list                     # List cached papers
asp paper verify-quote <doi> -q "text"  # Verify a quote
asp paper verify-quotes <doi>      # Verify multiple quotes (JSON stdin)
```

## Project Structure

An ASP project created with `asp init` has this minimal structure:

```
my-analysis/
├── asp.yaml              # Analysis specification (source of truth)
├── .gitignore            # Git ignore rules
├── src/                  # Analysis code
└── universes/            # Universe definitions (decision selections)
    └── baseline.yaml
```

Use `prism init` for full agentic scaffolding (Claude Code config, scripts, HPC targets).

## Design Principles

1. **Declarative** - Spec says WHAT, not HOW
2. **ASP is source of truth** - Implementations are derived from ASP
3. **Self-similar** - Every level has the same structure; sub-analyses are valid analyses
4. **Transparent** - All decisions and alternatives documented
5. **Composable** - Analyses build on each other
6. **Evidence-linked** - Decisions cite supporting evidence
7. **Reproducible** - Precise provenance and verification

## Documentation

See [DESIGN.md](DESIGN.md) for the complete specification.

## License

Apache 2.0
