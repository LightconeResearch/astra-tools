---
name: reference
description: ASP (Agentic Science Protocol) - declarative specification format for scientific analyses. Background knowledge for working with ASP projects.
user-invocable: false
allowed-tools: Read, Glob, Grep, Bash(asp:*)
---

# ASP Reference

Background knowledge for working with ASP analyses. This skill loads automatically when working with ASP projects.

## What is ASP?

ASP (Agentic Science Protocol) is a **declarative specification format** for scientific analyses. It describes:

- What we want to learn (problem statement)
- What we have to work with (inputs)
- What we want to produce (outputs)
- What choices need to be made (decisions)

**Key principle**: The spec says WHAT, not HOW. The agent generates the implementation.

```
ASP Analysis    →   LLM Agent    →   CWL Workflow   →   Results
(what we want)      (generates)      + Parameters
```

## The Multiverse Concept

A **universe** is one complete set of decisions — a single path through the decision space that fully specifies an analysis. Running one universe produces results that answer the problem statement.

The **multiverse** is the space of all valid decision combinations. Its purpose is **transparency and traceability**, not exhaustive search:

1. **Document the path taken**: Which decisions were made and why
2. **Document paths not taken**: What alternatives existed
3. **Enable exploration**: User can ask "what if we chose differently?"
4. **Check robustness**: Optionally run alternative universes to see if conclusions hold

A well-specified analysis should answer its problem statement with a **single universe**. The multiverse exists to show the researcher's choices transparently.

## Agent Commands

| Command | Purpose |
|---------|---------|
| `/asp:new` | Create a new analysis project — scope research question, define `asp.yaml` |
| `/asp:build [chunk]` | Build and run analysis chunks |
| `/asp:insights` | Extract insights from papers and add evidence to decisions |

### Workflow

```
/asp:new  →  /asp:insights  →  /asp:build <chunk>  →  /asp:build <next_chunk>  → ...
```

Run `/asp:build` for each chunk in turn. Use `/asp:insights` when you need to add literature support.

## Core Components

### Inputs

What the analysis has to work with:

| Type | Description |
|------|-------------|
| `data` | Raw data files (CSV, FITS, Parquet) |
| `analysis` | Results from previous ASP analyses |
| `literature` | Published papers (for evidence) |

```yaml
inputs:
  - id: training_data
    type: data
    source: "data/train.csv"

  - id: smith2023
    type: literature
    description: "Smith et al. 2023 - Methodology paper"
```

### Outputs

What the analysis should produce:

| Type | Description |
|------|-------------|
| `metric` | Numeric/categorical value (accuracy, p-value) |
| `figure` | Visualization |
| `table` | Structured tabular data |
| `data` | Processed data files |
| `model` | Trained model artifacts |
| `report` | Summary addressing problem statement |

A `report` type output is special — it should address the problem statement and synthesize findings.

### Decisions

All decisions live under chunks. Each decision has:

- **label**: Human-readable name
- **type**: Category (`data`, `method`, `parameter`)
- **importance**: 1 (critical) to 5 (implementation detail)
- **rationale**: Why this decision exists
- **options**: The possible choices
- **default**: The default option for baseline universes

Options can have:
- **evidence**: References to insights that support this choice
- **constraints**: `incompatible_with`, `requires` (scoped to same chunk)
- **value**: Configuration parameters for CWL mapping

### Constraints

Options can declare constraints on other options within the same chunk:

```yaml
chunks:
  main:
    decisions:
      scaling:
        options:
          minmax:
            incompatible_with: ["model.svm"]  # Can't use with SVM

      feature_selection:
        options:
          pca:
            requires: ["scaling.standard"]  # PCA needs standardized data
```

- `incompatible_with`: Cannot be selected together
- `requires`: Must also be selected

## Chunks

Every analysis has `chunks` in `asp.yaml`. All decisions live under chunks. A simple analysis uses a single `main` chunk. Complex analyses have multiple chunks.

### Single Chunk (Simple Analysis)

```yaml
chunks:
  main:
    decisions:
      scaling:
        label: "Feature Scaling"
        type: method
        default: standard
        options:
          standard:
            label: "StandardScaler"
          minmax:
            label: "MinMaxScaler"
```

The `main` chunk inherits `problem` and `success_criteria` from the analysis, and its outputs are the analysis-level `outputs`.

### Multiple Chunks (Complex Analysis)

```yaml
chunks:
  build_mocks:
    problem: "Generate realistic mock catalogs."
    decisions:
      noise_model:
        label: "Noise Model"
        type: method
        default: heteroscedastic
        options:
          homoscedastic: { label: "Homoscedastic" }
          heteroscedastic: { label: "Heteroscedastic" }
    artefacts:
      - id: mock_catalog
        type: data

  train_network:
    problem: "Train SBI neural network on mock catalog."
    decisions:
      architecture:
        label: "Network Architecture"
        type: method
        default: maf
        options:
          maf: { label: "Masked Autoregressive Flow" }
          npe: { label: "Neural Posterior Estimation" }
```

Non-main chunks set their own `problem`, `success_criteria`, and `artefacts`.

## Evidence-Based Decisions

Decisions can reference insights as evidence, creating traceable chains:

```yaml
insights:
  scaling_study:
    id: scaling_study
    claim: "MinMax scaling improves tree model performance on bounded features"
    # ... sources and evidence

chunks:
  main:
    decisions:
      scaling:
        options:
          minmax:
            label: "MinMaxScaler"
            evidence:
              - insight: scaling_study  # References the insight
```

This creates: Evidence → Insight → Decision → Output traceability.

## Composability

Analyses can use other analyses as inputs:

```yaml
inputs:
  - id: preprocessing_study
    type: analysis
    ref: "analyses/preprocessing_comparison"
    version: "v1.2"
    use_outputs: [best_method, performance_table]
```

This enables:
- **Analysis pipelines**: Output of A feeds into B
- **Evidence chains**: Conclusions from one study inform decisions in another
- **Incremental research**: Build on previous work formally

## Universes

A universe is a complete set of decisions organized by chunk:

```yaml
# universes/baseline.yaml
id: baseline
description: "Standard configuration"

chunks:
  main:
    scaling: standard
    model: random_forest
```

Generate and manage universes:
```bash
asp universe generate -n baseline    # Generate from defaults
asp universe check universes/x.yaml  # Check constraints
```

## Quick Reference

### CLI Commands

```bash
# Validation
asp validate asp.yaml             # Validate analysis specification
asp validate universes/foo.yaml   # Validate universe
asp verify asp.yaml               # Verify insight evidence exists

# Information
asp info                          # Show analysis summary
asp info --decisions              # Show decision details

# Universes
asp universe generate -n baseline # Generate universe from defaults
asp universe check universes/x.yaml  # Check universe constraints

# Workflow Integration
asp workflow run universes/baseline.yaml --cwl main.cwl
asp workflow validate --cwl main.cwl
asp params universes/baseline.yaml   # Output CWL parameters

# Schema
asp schema show analysis          # Show JSON schema
```

## File Locations

```
my-analysis/
├── asp.yaml              # Full spec with chunks defined inline
├── universes/
│   └── baseline.yaml     # Decision selections organized by chunk
├── workflows/            # CWL workflow definitions
│   └── main.cwl
├── steps/                # Workflow implementation
├── results/              # Execution outputs (gitignored)
└── .claude/
```

Chunks are defined inline in `asp.yaml`. The `steps/` structure depends on chunk count:
- **Single chunk**: Implementation goes directly in `steps/`
- **Multiple chunks**: Each chunk gets `steps/<chunk_name>/`

## Workflow Integration

For detailed guidance on building CWL workflows from ASP analyses, see [workflow-guide.md](workflow-guide.md).

Key points:
- ASP inputs map to CWL `File` inputs using the same ID
- ASP decisions map to CWL parameters (naming depends on `value` structure)
- Use `asp workflow validate` to check CWL matches ASP spec
- Use `asp workflow run` to execute with a universe
