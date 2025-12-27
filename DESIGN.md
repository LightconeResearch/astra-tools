# ASP - Agentic Science Protocol

## Overview

**ASP (Agentic Science Protocol)** is a declarative specification format for scientific analyses that can be executed by AI agents. It describes:

- What we want to learn (problem statement)
- What we have to work with (inputs)
- What we want to produce (outputs)
- What choices need to be made (decisions)

Crucially, an analysis does **not** specify how to execute the computation. That is the job of an LLM/coding agent, which generates workflows from the specification.

```
┌─────────────────┐      ┌─────────────┐      ┌──────────────┐      ┌─────────┐
│ ASP Analysis    │ ───▶ │ LLM Agent   │ ───▶ │ CWL Workflow │ ───▶ │ Results │
│ (what we want)  │      │ (generates) │      │ + Parameters │      │         │
│                 │      │             │      │              │      │         │
│ - inputs        │      │             │      │ steps/       │      │ metrics │
│ - problem       │      │             │      │ workflows/   │      │ figures │
│ - outputs       │      │             │      │ scripts/     │      │ tables  │
│ - decisions     │      │             │      │              │      │ models  │
└─────────────────┘      └─────────────┘      └──────────────┘      └─────────┘
        ▲                                                                  │
        │                                                                  │
        └──────────────── previous analyses (as inputs) ───────────────────┘

Universe (decision selections) ───▶ Workflow Parameters
```

## The Multiverse Concept

A **universe** is one complete set of decisions—a single path through the decision space that fully specifies an analysis. Running one universe produces results that answer the problem statement.

The **multiverse** is the space of all valid decision combinations. Its purpose is **transparency and traceability**, not exhaustive search:

1. **Document the path taken**: Which decisions were made and why
2. **Document paths not taken**: What alternatives existed
3. **Enable exploration**: User can ask "what if we chose differently?"
4. **Check robustness**: Optionally run alternative universes to see if conclusions hold

This is fundamentally different from "grid search to find the best":

| Approach | Purpose | Runs |
|----------|---------|------|
| **Single analysis** | Answer the problem statement | 1 universe |
| **Multiverse documentation** | Show all possible paths | 0 (just documentation) |
| **Robustness check** | Verify conclusions are stable | Selected universes |
| **Full enumeration** | Exhaustive comparison (rare) | All universes |

A well-specified analysis should answer its problem statement with a **single universe**. The multiverse exists to show the researcher's choices transparently.

## Core Components

### 1. Inputs

What the analysis has to work with:

| Input Type | Description | Example |
|------------|-------------|---------|
| `data` | Raw data files | CSV, FITS, Parquet files |
| `analysis` | Results from previous analyses | Reference to another ASP analysis |
| `literature` | Published papers/evidence | DOI, URL, or local PDF |

Inputs can provide **evidence** for decisions. For example, a previous analysis might show that a particular preprocessing method works best.

### 2. Problem Statement

A clear description of what the analysis aims to achieve. This is the research question being investigated.

The problem statement:
- Should be specific enough to evaluate whether outputs address it
- Does not need to be machine-parseable (it's guidance for the agent and humans)
- Helps ensure the analysis stays focused

### 3. Outputs

What the analysis should produce. All outputs are declared upfront so we know what to expect.

| Output Type | Description | Example |
|-------------|-------------|---------|
| `metric` | A numeric or categorical value | Accuracy, p-value, AUC |
| `figure` | A visualization | Confusion matrix, ROC curve |
| `table` | Structured tabular data | Feature importances, comparison table |
| `data` | Processed data files | Predictions, transformed features |
| `model` | Trained model artifacts | Serialized classifier |
| `report` | Text/document output | Summary, conclusion |

One output can be marked as `primary: true` to indicate it's the main result for multiverse comparison.

A `report` type output is special: it should address the problem statement and synthesize findings.

### 4. Decisions

The choices that fully specify the analysis. Each decision has:

- **id**: Unique identifier for the decision
- **label**: Human-readable name
- **type**: Category (`data`, `method`, `parameter`)
- **importance**: 1 (critical) to 5 (implementation detail)
- **rationale**: Why this decision exists
- **options**: The possible choices
- **default**: (optional) The default option for baseline universes

Options can have:
- **constraints**: `incompatible_with`, `requires`
- **evidence**: References to inputs that support this choice
- **value**: Configuration parameters

### 5. Constraints

Options can declare constraints on other options:

```yaml
decisions:
  scaling:
    options:
      minmax:
        label: "MinMaxScaler"
        incompatible_with: ["model.svm"]  # Can't use with SVM

  feature_selection:
    options:
      pca:
        label: "PCA"
        requires: ["scaling.standard"]  # PCA needs standardized data
```

**Constraint types:**
- `incompatible_with`: List of `decision.option` pairs that cannot be selected together
- `requires`: List of `decision.option` pairs that must also be selected

Constraints are validated when creating universes. Invalid combinations are rejected.

### Universe

A **universe** is a complete set of decisions: one option selected for each decision point. The set of all valid universes (respecting constraints) is the **multiverse**.

```yaml
# universes/baseline.yaml
id: baseline
description: "Default configuration using standard practices"

decisions:
  scaling: standard
  model: random_forest
  test_size: split_20
  random_seed: seed_42
```

## What This Model Does NOT Include

### No Execution Order / Edges

Previous versions had edges between decision nodes representing execution order. This is removed because:

1. Decisions don't have causal relationships—the constraints (`requires`, `incompatible_with`) handle validity
2. Execution order is an implementation detail that the agent determines
3. Edges conflated "decision dependency" with "computational dependency"

### No Workflow Specification

The analysis spec is declarative. It says WHAT we want, not HOW to compute it. The agent:
1. Reads the spec
2. Understands the problem and decisions
3. Generates appropriate code/workflow
4. Executes and collects outputs

The generated workflow should be versioned (in git) but is not part of the ASP spec.

## Evidence-Based Decisions

Decisions can reference inputs as evidence:

```yaml
decisions:
  scaling:
    options:
      minmax:
        label: "Min-Max Scaling"
        evidence:
          - ref: inputs.scaling_study
            finding: "Showed 5% accuracy improvement on similar data"
          - ref: inputs.smith_2023
            finding: "Recommended for tree-based models"
```

This creates a traceable chain from evidence → decision → output.

## Composability

Analyses can use other analyses as inputs, enabling:

1. **Analysis pipelines**: Output of analysis A feeds into analysis B
2. **Evidence chains**: Conclusions from one study inform decisions in another
3. **Incremental research**: Build on previous work formally

```yaml
inputs:
  - id: preprocessing_study
    type: analysis
    ref: "analyses/preprocessing_comparison"
    version: "v1.2"
    use_outputs: [best_method, performance_table]
```

## Example Analysis Specification

```yaml
$schema: "https://asp-spec.org/v1/schema.json"
version: "1.0"

analysis:
  name: "Iris Classification Study"

  problem: |
    Build a robust classifier for the Iris dataset that accurately
    predicts species from flower measurements, suitable for use in
    a botanical identification application.

  inputs:
    - id: iris_data
      type: data
      source: "sklearn.datasets.load_iris"
      description: "Fisher's classic 150-sample, 3-class dataset"

    - id: preprocessing_study
      type: analysis
      ref: "analyses/scaling_comparison_2024"
      description: "Our previous study on scaling methods"

  outputs:
    - id: accuracy
      type: metric
      dtype: float
      range: [0, 1]
      primary: true
      description: "Classification accuracy on held-out test set"

    - id: f1_score
      type: metric
      dtype: float
      range: [0, 1]
      description: "Macro-averaged F1 score"

    - id: confusion_matrix
      type: figure
      formats: [png, svg]
      description: "Confusion matrix heatmap"

    - id: model_comparison
      type: table
      formats: [csv]
      description: "Accuracy by model and preprocessing combination"

    - id: trained_model
      type: model
      formats: [joblib]
      description: "Best performing classifier"

    - id: conclusion
      type: report
      description: "Summary of classifier performance and suitability for the application"

decisions:
  scaling:
    label: "Feature Scaling"
    type: method
    importance: 2
    rationale: "Scaling affects distance-based algorithms like SVM"
    default: standard
    options:
      none:
        label: "No Scaling"
        description: "Use raw feature values"
      standard:
        label: "StandardScaler"
        description: "Z-score normalization (mean=0, std=1)"
      minmax:
        label: "MinMaxScaler"
        description: "Scale to [0, 1] range"
        evidence:
          - ref: inputs.preprocessing_study
            finding: "Showed 3% improvement for tree models"
        incompatible_with: ["model.svm"]

  model:
    label: "Classification Model"
    type: method
    importance: 1
    rationale: "Core algorithmic choice affecting accuracy and interpretability"
    default: random_forest
    options:
      svm:
        label: "Support Vector Machine"
        description: "Maximum margin classifier"
      random_forest:
        label: "Random Forest"
        description: "Ensemble of decision trees"
      logistic:
        label: "Logistic Regression"
        description: "Linear classifier with probabilistic output"

  test_size:
    label: "Test Set Proportion"
    type: parameter
    importance: 3
    rationale: "Trade-off between training data and evaluation reliability"
    default: small
    options:
      small:
        label: "20%"
        value: 0.2
      medium:
        label: "30%"
        value: 0.3

  random_seed:
    label: "Random Seed"
    type: parameter
    importance: 4
    rationale: "For reproducibility and stability testing"
    default: seed_42
    options:
      seed_42:
        label: "42"
        value: 42
      seed_123:
        label: "123"
        value: 123
```

## Execution Model

### Single Universe Execution (typical)

Given an analysis spec and a universe (set of decisions):

1. **Parse** the spec and validate the universe against constraints
2. **Agent generates** implementation code based on the decisions
3. **Execute** the code
4. **Collect** declared outputs (metrics, artifacts, conclusion)
5. **Store** the execution record linking universe → results

The result is a complete analysis that answers the problem statement.

### Multiverse Exploration (optional)

If the user wants to check robustness or explore alternatives:

1. **Select** alternative universes to run (user choice or sampling)
2. **Execute** each selected universe
3. **Compare** results across universes
4. **Generate** multiverse summary (specification curve, sensitivity analysis)

## Workflow Integration

While the analysis spec is declarative, execution requires concrete workflows. This section describes how ASP analyses connect to CWL workflows.

### Design Principles

1. **One workflow per branch**: Each Git branch has its own CWL workflow file
2. **Shared steps**: Reusable CWL steps live on `main` and are shared across branches
3. **Universe = parameters**: Different universes are realized by changing workflow parameters, not workflow structure
4. **Precise provenance**: Inputs must be specified with enough detail for reproducibility
5. **Output verification**: Execution must produce at least the outputs declared in the analysis

### Directory Structure

```
my-analysis/
├── asp.yaml                     # Analysis spec (declarative)
├── universes/
│   ├── baseline.yaml            # Universe definitions
│   └── robust.yaml
│
├── steps/                       # Reusable CWL steps (shared across branches)
│   ├── io/
│   │   ├── load_sklearn.cwl     # Load from sklearn datasets
│   │   └── load_file.cwl        # Load from file/URL
│   ├── preprocessing/
│   │   ├── scale.cwl            # Parameterized scaling
│   │   └── feature_select.cwl   # Parameterized feature selection
│   ├── models/
│   │   ├── train_sklearn.cwl    # Train any sklearn model (parameterized)
│   │   └── train_pytorch.cwl    # Train PyTorch model (added by DL branch)
│   └── evaluation/
│       ├── metrics.cwl          # Calculate metrics
│       └── visualize.cwl        # Generate figures
│
├── workflows/
│   ├── main.cwl                 # Workflow for main branch
│   └── params/
│       ├── baseline.yaml        # Parameters for baseline universe
│       └── robust.yaml          # Parameters for robust universe
│
├── scripts/                     # Python implementations
│   ├── scale.py
│   ├── train_sklearn.py
│   └── ...
│
├── .asp/
│   └── branches.yaml            # Branch metadata
│
└── results/                     # Execution outputs (gitignored)
```

On a different branch (e.g., `deep-learning`):
```
# Additional files on deep-learning branch:
├── steps/
│   └── models/
│       └── train_pytorch.cwl    # New step (merge back to main when stable)
│
├── workflows/
│   ├── deep-learning.cwl        # Branch-specific workflow
│   └── params/
│       └── baseline.yaml        # DL-specific parameters
│
└── asp.yaml                     # Extended with DL-specific decisions
```

### How Decisions Map to Workflows

Decisions have different impacts on workflow configuration:

| Decision Type | Workflow Impact | How to Handle |
|---------------|-----------------|---------------|
| Pure parameter | Change input value | Same step, different param |
| Method selection | Same step, different behavior | Parameterized step |
| Algorithm choice | Different step entirely | Conditional step in workflow |
| Fundamental approach | Different workflow structure | Different branch |

**Example: Mapping decisions to CWL parameters**

Analysis decision:
```yaml
decisions:
  scaling:
    options:
      standard:
        label: "StandardScaler"
        value:
          method: "standard"
      minmax:
        label: "MinMaxScaler"
        value:
          method: "minmax"
```

CWL step (parameterized):
```yaml
# steps/preprocessing/scale.cwl
class: CommandLineTool
baseCommand: [python, scripts/scale.py]

inputs:
  data:
    type: File
    inputBinding: { prefix: --input }
  method:
    type: string?
    inputBinding: { prefix: --method }
    default: null

outputs:
  scaled_data:
    type: File
    outputBinding: { glob: scaled_data.csv }
```

Universe parameters:
```yaml
# workflows/params/baseline.yaml
scaling_method: "standard"
model_type: "random_forest"
test_size: 0.2
random_state: 42
```

### Universe to Parameters Mapping

A universe file specifies decision selections:

```yaml
# universes/baseline.yaml
decisions:
  scaling: standard
  model: random_forest
  test_size: split_20
  random_seed: seed_42
```

The system extracts `value` fields from selected options to generate workflow parameters:

```yaml
# Generated: workflows/params/baseline.yaml
# From universe: baseline
# Generated at: 2025-01-15T10:00:00Z

scaling_method: "standard"      # from decisions.scaling.options.standard.value.method
model_type: "random_forest"     # from decisions.model (option id)
test_size: 0.2                  # from decisions.test_size.options.split_20.value
random_state: 42                # from decisions.random_seed.options.seed_42.value
```

This mapping can be:
- **Automatic**: ASP generates params from universe + analysis spec
- **Manual**: User maintains params files directly (for complex cases)
- **Hybrid**: Auto-generate with manual overrides

### Input Provenance

For reproducibility, inputs must be precisely specified:

```yaml
inputs:
  # External URL with checksum
  - id: iris_data
    type: data
    source:
      type: url
      url: "https://archive.ics.uci.edu/ml/datasets/iris/iris.csv"
      checksum:
        algorithm: sha256
        value: "abc123..."

  # S3 with version
  - id: genomic_data
    type: data
    source:
      type: s3
      bucket: "my-research-bucket"
      key: "data/samples.parquet"
      version_id: "abc123"
      region: "us-east-1"

  # sklearn dataset (deterministic)
  - id: iris_sklearn
    type: data
    source:
      type: sklearn
      dataset: "iris"
      # No checksum needed - sklearn datasets are versioned

  # Output from another ASP analysis
  - id: preprocessed_features
    type: analysis
    source:
      type: asp
      analysis: "preprocessing_study"
      version: "v1.0"           # Git tag
      output: "cleaned_data"    # Output id from that analysis
      execution: "baseline_001" # Specific execution (optional)
```

The CWL workflow receives resolved paths:

```yaml
# Workflow inputs (resolved at runtime)
inputs:
  iris_data:
    class: File
    location: "https://archive.ics.uci.edu/ml/datasets/iris/iris.csv"
    checksum: "sha256$abc123..."
```

### Branch-Specific Workflows

When decisions require fundamentally different workflow structures, use branches:

**Main branch workflow** (`workflows/main.cwl`):
```yaml
class: Workflow
inputs:
  - id: data
  - id: scaling_method
  - id: model_type
  - id: test_size
  - id: random_state

steps:
  load:
    run: ../steps/io/load_sklearn.cwl
    in: { dataset: data }
    out: [data]

  preprocess:
    run: ../steps/preprocessing/scale.cwl
    in:
      data: load/data
      method: scaling_method
    out: [scaled_data]

  train:
    run: ../steps/models/train_sklearn.cwl
    in:
      data: preprocess/scaled_data
      model_type: model_type
      random_state: random_state
    out: [model, predictions]

  evaluate:
    run: ../steps/evaluation/metrics.cwl
    in:
      predictions: train/predictions
    out: [accuracy, f1_score, confusion_matrix]
```

**Deep-learning branch workflow** (`workflows/deep-learning.cwl`):
```yaml
class: Workflow
inputs:
  - id: data
  - id: scaling_method
  - id: architecture      # NEW decision
  - id: optimizer         # NEW decision
  - id: learning_rate     # NEW decision
  - id: epochs            # NEW decision
  - id: random_state

steps:
  load:
    run: ../steps/io/load_sklearn.cwl  # Same step
    in: { dataset: data }
    out: [data]

  preprocess:
    run: ../steps/preprocessing/scale.cwl  # Same step
    in:
      data: load/data
      method: scaling_method
    out: [scaled_data]

  train:
    run: ../steps/models/train_pytorch.cwl  # DIFFERENT step
    in:
      data: preprocess/scaled_data
      architecture: architecture
      optimizer: optimizer
      learning_rate: learning_rate
      epochs: epochs
      random_state: random_state
    out: [model, predictions]

  evaluate:
    run: ../steps/evaluation/metrics.cwl  # Same step
    in:
      predictions: train/predictions
    out: [accuracy, f1_score, confusion_matrix]
```

Note how `load`, `preprocess`, and `evaluate` steps are shared—only `train` differs.

### Step Reuse Strategy

Steps should be designed for reuse:

1. **Parameterize generously**: A single `train_sklearn.cwl` handles all sklearn models via `model_type` parameter
2. **Keep steps focused**: One step = one responsibility
3. **Merge new steps to main**: When a branch creates a useful step, merge it back so other branches can use it
4. **Version steps carefully**: Breaking changes to steps affect all workflows using them

```
Step lifecycle:
1. Branch creates new step (e.g., train_pytorch.cwl)
2. Step is tested and refined on branch
3. Step is merged to main (available to all branches)
4. Other branches can now use the step
```

### Output Verification

After execution, verify that declared outputs were produced:

```yaml
# Analysis declares:
outputs:
  - id: accuracy
    type: metric
    dtype: float
    range: [0, 1]
  - id: confusion_matrix
    type: figure
    formats: [png, svg]
```

Execution produces:
```yaml
# executions/baseline_001.yaml
metrics:
  accuracy: 0.967       # ✓ matches declared metric
  f1_score: 0.965       # ✓ bonus metric (allowed)

artifacts:
  confusion_matrix: "results/baseline_001/confusion_matrix.png"  # ✓ matches declared artifact
```

Verification checks:
- [ ] All declared metrics are present
- [ ] Metric values are within declared ranges
- [ ] All declared artifacts exist at their paths
- [ ] Artifact formats match declared formats

### Environment Specification

Each workflow should declare its environment:

```yaml
# workflows/main.cwl
requirements:
  DockerRequirement:
    dockerPull: "ghcr.io/my-org/my-analysis:v1.0"
  # OR
  SoftwareRequirement:
    packages:
      - package: python
        version: ["3.10", "3.11"]
      - package: scikit-learn
        version: ["1.3.0"]
```

Alternatively, use a separate environment file:

```yaml
# environment.yaml
python: "3.11"
packages:
  - scikit-learn==1.3.0
  - pandas>=2.0
  - matplotlib>=3.7

docker:
  base: "python:3.11-slim"
  # OR
  image: "ghcr.io/my-org/my-analysis:v1.0"
```

## Versioning and Lifecycle

An analysis evolves over time. Git provides the foundation for tracking this evolution.

### The Analysis Lifecycle

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│  Draft  │ ──▶ │ Evolve  │ ──▶ │ Execute │ ──▶ │ Iterate │ ──▶ │Finalize │
└─────────┘     └─────────┘     └─────────┘     └─────────┘     └─────────┘
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
   commit         commits        execution       commits          tag
   (initial)    (add decisions)   record       (refine)        (v1.0)
```

**Key principle**: The analysis definition evolves through Git commits. Discovering a new decision point during execution is normal—just add it and commit.

### What Git Mechanisms Map To

| Concept | Git Mechanism | When to Use |
|---------|---------------|-------------|
| **Analysis evolution** | Commits on branch | Adding/modifying decisions as you work |
| **Universe** | File (`universes/baseline.yaml`) | Different selections within same analysis |
| **Alternative approach** | Branch | Fundamentally different methodology |
| **Completed analysis** | Tag | Marking a milestone (submission, publication) |
| **Parallel exploration** | Worktree | Running multiple branches simultaneously |

### Branches: When Analysis Paths Diverge

A Git branch is appropriate when you're exploring a **fundamentally different approach** that might introduce its own decision points:

```
main (classical ML)
  │
  ├── scaling, model (svm/rf), cv_strategy...
  │
  │   ──── git branch deep-learning ────▶
  │                                        │
  │                                        ├── adds: architecture, optimizer,
  │                                        │         learning_rate, epochs...
  │                                        │
  │                                        └── different decision space
  │
  └── continues with classical approach
```

Branches are NOT for choosing different options within the same analysis—that's what universes are for.

### Worktrees: Parallel Execution

Git worktrees allow multiple branches to be checked out simultaneously, each in its own directory:

```bash
# Main analysis
my-analysis/                    # main branch
├── asp.yaml
├── universes/
│   └── baseline.yaml
└── results/

# Create worktree for alternative approach
git worktree add ../my-analysis-deep-learning deep-learning

# Now both exist on filesystem
my-analysis/                    # main branch
my-analysis-deep-learning/      # deep-learning branch

# Run them in parallel, compare results
```

This enables:
- Running different analytical approaches simultaneously
- Keeping results isolated per approach
- Easy comparison across approaches

### Tags: Marking Complete Analyses

Tags mark significant milestones:

```bash
# Analysis submitted to journal
git tag -a v1.0-submitted -m "Analysis as submitted to Nature Methods"

# After reviewer response
git tag -a v1.1-revision -m "Addressed reviewer comments on scaling method"

# Published version
git tag -a v1.1-published -m "Final published version"
```

A tagged analysis should be reproducible: the tag points to a specific commit of the analysis definition, and execution records reference that commit.

### Execution Records and Versioning

When a universe is executed, the record captures:

```yaml
# executions/baseline_001.yaml
id: baseline_001
universe: baseline
commit: "abc123def"  # Git commit of analysis definition
branch: "main"

status: completed
started_at: "2025-01-15T10:00:00Z"

metrics:
  accuracy: 0.967
artifacts:
  confusion_matrix: "results/baseline_001/confusion_matrix.png"
```

This creates a complete audit trail: you can always see which version of the analysis produced which results.

### Discovering New Decisions During Execution

A common scenario: while running an analysis, you realize there's a decision you didn't anticipate.

**Workflow:**
1. You're running the baseline universe
2. You notice: "Wait, should we handle class imbalance? That's a decision!"
3. Add the new decision to `asp.yaml`
4. Commit: "Add class_imbalance decision point"
5. Update universe files to include the new decision
6. Continue execution

The analysis definition evolves as you learn. This is expected and tracked naturally by Git.

### Branch Metadata

To track the relationship between branches and decisions, maintain `.asp/branches.yaml`:

```yaml
# .asp/branches.yaml
branches:
  deep-learning:
    description: "Exploring neural network approaches"
    diverged_from: main
    diverged_at: "abc123"  # commit hash
    new_decisions:
      - architecture
      - optimizer
      - learning_rate
    created_by:
      agent: claude-opus-4
      timestamp: "2025-01-15T10:00:00Z"

  bayesian:
    description: "Bayesian inference approach"
    diverged_from: main
    diverged_at: "def456"
    new_decisions:
      - prior_distribution
      - mcmc_sampler
```

This provides semantic context for why branches exist.

## CLI Commands

The ASP CLI provides tools for working with analyses:

```bash
# Validate an analysis specification
asp validate asp.yaml
asp validate universes/baseline.yaml

# Show analysis information
asp info
asp info --decisions
asp info --universes

# List valid universes
asp universes --count
asp universes --list

# Generate baseline universe from defaults
asp universe generate --name baseline

# Generate workflow parameters from universe
asp params universes/baseline.yaml -o workflows/params/baseline.yaml

# Visualize decision space
asp viz --format mermaid
asp viz --format ascii

# Run an analysis (invokes agent)
asp run universes/baseline.yaml

# Compare executions
asp compare executions/baseline_001.yaml executions/robust_001.yaml
```

## Schema Reference

### Analysis Schema (asp.yaml)

```yaml
$schema: "https://asp-spec.org/v1/schema.json"
version: "1.0"

analysis:
  name: string                    # Required: Human-readable name
  description: string             # Optional: Detailed description
  authors: [string]               # Optional: List of authors
  tags: [string]                  # Optional: Tags for categorization

  problem: string                 # Required: Problem statement

  inputs:                         # Required: List of inputs
    - id: string                  # Unique identifier
      type: data|analysis|literature
      source: object              # Source specification
      description: string

  outputs:                        # Required: List of outputs
    - id: string                  # Unique identifier
      type: metric|figure|table|data|model|report
      dtype: float|int|bool|string  # For metrics
      range: [min, max]           # For numeric metrics
      formats: [string]           # For artifacts
      primary: boolean            # Main output for comparison
      description: string

decisions:                        # Required: Map of decisions
  decision_id:
    label: string                 # Human-readable name
    type: data|method|parameter
    importance: 1-5               # 1=critical, 5=implementation detail
    rationale: string             # Why this decision exists
    default: option_id            # Default option for baseline
    options:
      option_id:
        label: string             # Human-readable name
        description: string
        value: any                # Configuration value
        evidence: [object]        # Supporting evidence
        incompatible_with: [string]  # "decision.option" pairs
        requires: [string]        # "decision.option" pairs
```

### Universe Schema (universes/*.yaml)

```yaml
$schema: "https://asp-spec.org/v1/universe.schema.json"

id: string                        # Unique identifier
description: string               # What this universe represents

decisions:                        # Map of decision_id -> option_id
  scaling: standard
  model: random_forest
  test_size: split_20
```

### Execution Schema (executions/*.yaml)

```yaml
$schema: "https://asp-spec.org/v1/execution.schema.json"

id: string                        # Unique execution identifier
universe: string                  # Universe that was executed
commit: string                    # Git commit of analysis definition
branch: string                    # Git branch

status: pending|running|completed|failed
started_at: datetime
ended_at: datetime

runner:
  type: local|cwl|wdl|snakemake|argo-workflows
  run_id: string                  # ID from workflow engine
  host: string                    # Execution host

inputs: [string]                  # Input file paths used

metrics:                          # Metric values (metric_id -> value)
  accuracy: 0.967
  f1_score: 0.965

artifacts:                        # Artifact paths (artifact_id -> path)
  confusion_matrix: "results/baseline_001/confusion_matrix.png"
  trained_model: "results/baseline_001/model.joblib"

agent:
  type: string                    # Agent type (e.g., claude-opus-4)
  session: string                 # Session identifier

error:                            # Present if status=failed
  message: string
  step: string                    # Step where error occurred
```

## Open Questions

1. **Agent instructions**: Should the spec include hints for the agent about implementation preferences? Or is the problem statement sufficient?

2. **Semantic validation**: How do we validate that outputs actually address the problem statement? (Syntactic validation—checking outputs exist—is straightforward.)

3. **Caching**: If a decision doesn't affect certain outputs, can we cache and reuse? This requires understanding which decisions affect which workflow steps.

4. **Step versioning**: How do we handle breaking changes to shared steps? Semantic versioning? Step-level tags?

5. **Cross-branch comparison**: How do we compare results between branches that have different decision spaces?

## Benefits of This Model

1. **Declarative**: Spec says WHAT, not HOW
2. **Transparent**: All decisions and alternatives are documented
3. **Composable**: Analyses can build on each other
4. **Evidence-linked**: Decisions can cite supporting evidence
5. **Agent-friendly**: Clear structure for LLM to understand and implement
6. **Goal-oriented**: Problem statement keeps analysis focused
7. **Single-analysis first**: One universe answers the question; multiverse is for exploration
8. **Reproducible**: Precise input provenance and execution records ensure reproducibility
