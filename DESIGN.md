# ASTRA - Agentic Schema for Transparent Research Analysis

## Overview

**ASTRA (Agentic Schema for Transparent Research Analysis)** is a declarative specification format for scientific analyses that can be executed by AI agents. It describes:

- What we have to work with (inputs)
- What we want to produce (outputs)
- What choices need to be made (decisions)

Crucially, an analysis does **not** specify how to execute the computation. That is the job of an agent (e.g., Prism), which generates implementations from the specification.

```
┌─────────────────┐      ┌─────────────┐      ┌──────────────┐      ┌─────────┐
│ ASTRA Analysis    │ ───▶ │ Agent       │ ───▶ │ Implementation│ ───▶ │ Results │
│ (what we want)  │      │ (executes)  │      │ (generated)  │      │         │
│                 │      │             │      │              │      │         │
│ - inputs        │      │             │      │ scripts/     │      │ metrics │
│ - outputs       │      │             │      │ pipelines/   │      │ figures │
│ - decisions     │      │             │      │              │      │ tables  │
│                 │      │             │      │              │      │ data    │
└─────────────────┘      └─────────────┘      └──────────────┘      └─────────┘
        ▲                                                                  │
        │                                                                  │
        └──────────────── previous analyses (as inputs) ───────────────────┘

Universe (decision selections) ───▶ Execution Parameters
```

## The Multiverse Concept

A **universe** is one complete set of decisions—a single path through the decision space that fully specifies an analysis. Running one universe produces results.

The **multiverse** is the space of all valid decision combinations. Its purpose is **transparency and traceability**, not exhaustive search:

1. **Document the path taken**: Which decisions were made and why
2. **Document paths not taken**: What alternatives existed
3. **Enable exploration**: User can ask "what if we chose differently?"
4. **Check robustness**: Optionally run alternative universes to see if conclusions hold

This is fundamentally different from "grid search to find the best":

| Approach | Purpose | Runs |
|----------|---------|------|
| **Single analysis** | Produce declared outputs | 1 universe |
| **Multiverse documentation** | Show all possible paths | 0 (just documentation) |
| **Robustness check** | Verify conclusions are stable | Selected universes |
| **Full enumeration** | Exhaustive comparison (rare) | All universes |

A well-specified analysis should produce its declared outputs with a **single universe**. The multiverse exists to show the researcher's choices transparently.

## Core Components

### 1. Inputs

What the analysis has to work with:

| Input Type | Description | Example |
|------------|-------------|---------|
| `data` | Raw data files | CSV, FITS, Parquet files |
| `analysis` | Results from previous analyses | Reference to another ASTRA analysis |

Inputs of type `analysis` can reference specific outputs from another ASTRA analysis via `ref` and `use_outputs`.

### 2. Outputs

What the analysis should produce. All outputs are declared upfront so we know what to expect.

| Output Type | Description | Example |
|-------------|-------------|---------|
| `metric` | A numeric or categorical value | Accuracy, p-value, AUC |
| `figure` | A visualization | Confusion matrix, ROC curve |
| `table` | Structured tabular data | Feature importances, comparison table |
| `data` | Processed data files | Predictions, transformed features |
| `report` | Text/document output | Summary, conclusion |

A `report` type output is special: it should synthesize findings from the analysis.

### 3. Decisions

Decisions live directly on the analysis node. Each decision has:

- **label**: Human-readable name
- **rationale**: (optional) Why this decision exists
- **tags**: (optional) Tags for grouping and categorizing
- **when**: (optional) Conditional activation in `decision_id.option_id` format -- this decision only exists when the referenced option is selected
- **default**: (optional) The default option ID for baseline universes
- **options**: The possible choices (map of option ID to option spec)

Options can have:
- **label**: Human-readable name
- **description**: Detailed description of the option
- **constraints**: `incompatible_with`, `requires` (scoped to decisions at the same level)
- **insights**: References to insight IDs that support this choice
- **excluded**: Boolean flag indicating this option was considered and rejected
- **excluded_reason**: Why this option was excluded (required when `excluded` is true)

### 4. Constraints

Options can declare constraints on other options within the same analysis node:

```yaml
decisions:
  scaling:
    options:
      minmax:
        label: "MinMaxScaler"
        incompatible_with:
          - model.svm               # Can't use with SVM

  feature_selection:
    options:
      pca:
        label: "PCA"
        requires:
          - scaling.standard        # PCA needs standardized data
```

**Constraint types:**
- `incompatible_with`: List of `decision.option` pairs that cannot be selected together
- `requires`: List of `decision.option` pairs that must also be selected

Constraints are scoped within an analysis node and validated when creating universes. Invalid combinations are rejected.

### 5. Recipes

Recipes are optional inline build rules on outputs that describe how to produce them. They provide the execution contract for agents or build systems.

```yaml
outputs:
  - id: trained_model
    type: data
    description: "Best performing classifier"
    recipe:
      command: python src/train.py

  - id: accuracy
    type: metric
    description: "Classification accuracy"
    recipe:
      command: python src/evaluate.py
      inputs: [trained_model]
      resources:
        gpus: 1
        memory: "16GB"
```

Each recipe has:
- **command**: The command to execute
- **inputs**: (optional) Output IDs that must be materialized before this recipe runs
- **container**: (optional) Container image override (string or build spec with `build` key)
- **resources**: (optional) Compute requirements (cpus, memory, gpus, time_limit)

Outputs with recipes form a DAG via `inputs`. Validation checks for cycles and invalid input references.

### Universe

A **universe** is a complete set of decisions: one option selected for each decision point. The set of all valid universes (respecting constraints) is the **multiverse**.

```yaml
# universes/baseline.yaml
id: baseline
description: "Default configuration using standard practices"

decisions:
  scaling: standard
  model: random_forest
  test_size: small
  random_seed: seed_42
```

## Self-Similar Structure

The ASTRA format is **self-similar**: every analysis node has the same structure, and analyses can be nested arbitrarily deep via the `analyses` key.

### Design Principles

1. **Self-similar nodes.** Every analysis node has the same shape: inputs, outputs (with optional inline recipes), decisions, insights, and optional sub-analyses. A sub-analysis extracted to its own file is a valid analysis on its own.

2. **Flat for simple analyses.** Simple analyses put decisions directly at the top level — no nesting required.

3. **Nesting for complex analyses.** Multi-stage analyses decompose work into sub-analyses under `analyses:`, each with its own inputs, outputs, and decisions.

4. **Scoped decisions.** Each analysis node has its own decisions that are independent from other nodes. Decision IDs only need to be unique within their node. Constraints are also scoped within a node.

5. **Input wiring via `from`.** Sub-analysis inputs can reference parent inputs (`from: parent_input_id`) or sibling outputs (`from: sibling_id.output_id`).

6. **Universe mirrors tree.** The universe file mirrors the analysis tree: root-level `decisions` for root decisions, and `analyses` for sub-analysis decisions.

### Simple Analysis (flat)

```yaml
version: "1.0"
name: "Iris Classification"

inputs:
  - id: iris_data
    type: data
    source: "sklearn.datasets.load_iris"

outputs:
  - id: accuracy
    type: metric
  - id: confusion_matrix
    type: figure
  - id: conclusion
    type: report

decisions:
  scaling:
    label: "Feature Scaling"
    default: standard
    options:
      none:
        label: "No Scaling"
      standard:
        label: "StandardScaler"

  model:
    label: "Classification Model"
    default: random_forest
    options:
      svm:
        label: "SVM"
        requires:
          - scaling.standard
      random_forest:
        label: "Random Forest"
```

### Multi-Stage Analysis (nested)

```yaml
version: "1.0"
name: "SBI Cosmological Parameter Estimation"

inputs:
  - id: survey_catalog
    type: data
    source: "sn_survey_union2.1"

outputs:
  - id: posterior_contours
    type: figure
  - id: parameter_constraints
    type: table

analyses:
  build_mocks:
    description: "Generate realistic mock catalogs matching survey properties."
    success_criteria:
      - claim: "Mock catalog matches observed magnitude distribution"
    inputs:
      - id: survey_data
        type: data
        from: survey_catalog              # References parent input
    outputs:
      - id: mock_catalog
        type: data
        recipe:
          command: python src/generate_mocks.py
    decisions:
      noise_model:
        label: "Noise Model"
        default: heteroscedastic
        options:
          homoscedastic:
            label: "Homoscedastic"
          heteroscedastic:
            label: "Heteroscedastic"

  train_network:
    description: "Train SBI neural network on mock catalog."
    inputs:
      - id: training_data
        type: data
        from: build_mocks.mock_catalog    # References sibling output
    outputs:
      - id: trained_model
        type: data
        recipe:
          command: python src/train.py
          resources:
            gpus: 1
            memory: "32GB"
    decisions:
      architecture:
        label: "Network Architecture"
        default: maf
        options:
          maf:
            label: "Masked Autoregressive Flow"
          npe:
            label: "Neural Posterior Estimation"

  validate:
    description: "Validate trained model against observed data."
```

### Universe for Nested Analysis

The universe file mirrors the analysis tree structure:

```yaml
# universes/baseline.yaml
id: baseline
description: "Standard pipeline configuration"

analyses:
  build_mocks:
    decisions:
      noise_model: heteroscedastic
  train_network:
    decisions:
      architecture: maf
```

Universe validation checks that every decision in every analysis node has a selection, and that all selections respect constraints.

## What This Model Does NOT Include

### No Execution Order / Edges

Previous versions had edges between decision nodes representing execution order. This is removed because:

1. Decisions don't have causal relationships—the constraints (`requires`, `incompatible_with`) handle validity
2. Execution order is an implementation detail that the agent determines
3. Edges conflated "decision dependency" with "computational dependency"

### No Workflow Specification

The analysis spec is declarative. It says WHAT we want, not HOW to compute it. The agent:
1. Reads the spec
2. Understands the analysis and decisions
3. Generates appropriate code/workflow
4. Executes and collects outputs

The generated workflow should be versioned (in git) but is not part of the ASTRA spec.

## Insights

Insights represent scientific knowledge extracted from literature with full traceability to source material. They use W3C Web Annotation-compliant selectors for precise evidence references.

### Evidence Lifecycle

The following diagram shows the complete workflow for extracting insights from literature and linking them to analysis decisions:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        PHASE 1: LITERATURE RESEARCH                      │
│                           (Agent + Web Search)                           │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. Identify decisions needing justification                             │
│  2. Web search for relevant papers (arXiv, Semantic Scholar, etc.)       │
│  3. Collect DOIs (arXiv DOIs: 10.48550/arXiv.{id})                       │
│  4. Note relevance to specific decisions                                 │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        PHASE 2: PAPER ACQUISITION                        │
│                              (CLI)                                       │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  astra paper add 10.48550/arXiv.1706.03762 --version 7                     │
│  astra paper add 10.1038/s41586-023-06221-2                                │
│         │                                                                │
│         ▼                                                                │
│  • Resolve DOI to PDF URL (doi.org → publisher)                          │
│  • Download PDF to cache (if open access)                                │
│  • Compute SHA-256                                                       │
│  • Store metadata (title, authors, retrieved_at)                         │
│         │                                                                │
│         ▼                                                                │
│  Cache: ~/.cache/astra/papers/                                             │
│         └── 10.48550_arXiv.1706.03762_v7/                                │
│             ├── paper.pdf                                                │
│             └── meta.json  (sha256, title, doi, version, retrieved_at)   │
│                                                                          │
│  NO TEXT EXTRACTION - Agent reads PDF directly                           │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       PHASE 3: INSIGHT EXTRACTION                        │
│                        (Agent + PDF Reading)                             │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. Agent reads PDF file directly (Claude can read PDFs)                 │
│                                                                          │
│  2. Agent identifies relevant quotes, figures, tables                    │
│                                                                          │
│  3. Agent writes insight to astra.yaml:                                    │
│                                                                          │
│     insights:                                                            │
│       layer_norm_insight:                                                │
│         id: layer_norm_insight                                           │
│         claim: "Layer normalization improves training stability"         │
│         created_at: "2024-01-15T10:30:00Z"                               │
│         evidence:                                                        │
│           - id: ev1                                                      │
│             doi: "10.48550/arXiv.1706.03762"                             │
│             version: 7  # For arXiv, version matters                     │
│             quote:                                                       │
│               type: TextQuoteSelector                                    │
│               exact: "We found that layer normalization..."              │
│               prefix: "In our experiments, "  # optional                 │
│             location:                                                    │
│               type: FragmentSelector                                     │
│               page: 5                                                    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       PHASE 4: DECISION LINKING                          │
│                        (Agent)                                           │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  decisions:                                                              │
│    normalization:                                                        │
│      options:                                                            │
│        layer_norm:                                                       │
│          insights:                                                       │
│            - layer_norm_insight  # Reference to insight                  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       PHASE 5: VALIDATION (Unified)                      │
│                         (CLI - Gatekeeper)                               │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  astra validate astra.yaml --verify-evidence                                 │
│         │                                                                │
│         ▼                                                                │
│  Stage 1: Schema Validation                                              │
│    • YAML structure matches JSON schema                                  │
│    • Required fields present, types correct                              │
│         │                                                                │
│         ▼                                                                │
│  Stage 2: Semantic Validation                                            │
│    • All references resolve (Option.insights → Insight.id)               │
│    • Constraints valid (incompatible_with, requires)                     │
│         │                                                                │
│         ▼                                                                │
│  Stage 3: Evidence Verification (with caching)                           │
│    • For each evidence item:                                             │
│      - Check cache: (doi, version, quote_hash) → verified_at             │
│      - If cached and PDF unchanged → skip                                │
│      - Else: load PDF, search for quote, update cache                    │
│         │                                                                │
│    ┌────┴────┐                                                           │
│    ▼         ▼                                                           │
│  PASS      FAIL                                                          │
│    │         │                                                           │
│    │         └──► Error: "Quote not found: '...' in paper X"             │
│    │               Agent must fix and re-run                             │
│    ▼                                                                     │
│  All checks passed → Ready for commit/PR                                 │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Key insight**: The agent can write whatever evidence it wants, but `astra validate --verify-evidence` will **fail** if quotes don't exist in the PDF. No fabricated evidence can make it through the workflow.

### Insight Structure

```yaml
insights:
  layer_norm_stability:
    id: layer_norm_stability
    claim: "Layer normalization improves training stability compared to batch normalization."
    created_at: "2024-01-15T10:30:00Z"
    evidence:
      - id: ev1
        doi: "10.48550/arXiv.1706.03762"
        version: 7                          # For arXiv papers (version matters)
        quote:
          type: TextQuoteSelector
          exact: "We found that layer normalization leads to faster convergence."
          prefix: "In our ablation studies, "   # Optional: ~20-100 chars for disambiguation
          suffix: " This effect was..."         # Optional: ~20-100 chars
        location:
          type: FragmentSelector
          page: 5                            # 1-indexed page number
    scope: "Transformer architectures"       # Optional: when this applies
    tags: [transformer, normalization]       # Optional: categorization tags
```

### Evidence Types

Evidence can reference two kinds of sources:
- **Literature** (`doi`): A paper referenced by DOI, with W3C selectors pointing into the PDF
- **Analysis artifact** (`artifact`): An output produced by this analysis, referenced by output ID

Exactly one of `doi` or `artifact` must be set. At least one content selector is required:

| Selector | Purpose | Required Fields |
|----------|---------|-----------------|
| `quote` (TextQuoteSelector) | Exact text from paper | `exact` (the quote) |
| `figure` (FigureSelector) | Reference to a figure | `label` (e.g., "Figure 3a") |
| `table` (TableSelector) | Reference to a table | `label` (e.g., "Table 1") |

**Quote evidence (W3C TextQuoteSelector):**
```yaml
quote:
  type: TextQuoteSelector
  exact: "The exact quoted text from the paper"
  prefix: "Context before..."    # Optional
  suffix: "Context after..."     # Optional
```

**Figure evidence (FigureSelector):**
```yaml
figure:
  type: FigureSelector
  label: "Figure 3a"
  caption: "Optional caption text for verification"
```

**Table evidence (TableSelector):**
```yaml
table:
  type: TableSelector
  label: "Table 1"
  caption: "Optional header text"
  region: "row 3, accuracy column"  # Optional: specific region
```

### Location Hints

The `location` field (W3C FragmentSelector) provides PDF location hints:

```yaml
location:
  type: FragmentSelector
  page: 5                        # 1-indexed page number
```

### arXiv Papers

For arXiv papers, use the DOI format `10.48550/arXiv.{id}` and specify the version:

```yaml
evidence:
  - id: ev1
    doi: "10.48550/arXiv.1706.03762"
    version: 7                    # Important: arXiv papers are updated
    quote:
      type: TextQuoteSelector
      exact: "Attention is all you need."
```

### Evidence Verification

The CLI can verify that quotes exist in source PDFs:

```bash
astra validate astra.yaml --verify-evidence
```

This:
1. Checks that each paper is in the local cache (`astra paper add <doi>`)
2. Searches for exact quotes in the PDF text
3. Verifies page numbers if provided
4. Caches verification results for efficiency

**Key principle**: The agent writes evidence, but validation is the gatekeeper. Fabricated quotes will fail verification.

## Evidence-Based Decisions

Decisions reference insights (not papers directly) to create a traceable chain:

```yaml
insights:
  minmax_study:
    id: minmax_study
    claim: "MinMax scaling improves accuracy for tree-based models by 3%."
    created_at: "2024-01-15T10:00:00Z"
    evidence:
      - id: ev1
        doi: "10.1234/scaling-study"
        quote:
          type: TextQuoteSelector
          exact: "MinMax normalization yielded a 3% improvement in accuracy for Random Forest."
        location:
          type: FragmentSelector
          page: 12

decisions:
  scaling:
    label: "Feature Scaling"
    default: standard
    options:
      minmax:
        label: "Min-Max Scaling"
        insights:
          - minmax_study            # Reference to insight ID
```

This creates a traceable chain: **decision option → insight → evidence → paper (DOI)**.

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
    ref_version: "v1.2"
    use_outputs: [best_method, performance_table]
```

Within a nested analysis, sub-analyses can wire inputs from the parent or from siblings:

```yaml
analyses:
  stage_a:
    inputs:
      - id: raw_data
        type: data
        from: survey_catalog          # Parent input
    outputs:
      - id: processed
        type: data

  stage_b:
    inputs:
      - id: input_data
        type: data
        from: stage_a.processed       # Sibling output
```

## Example Analysis Specification

```yaml
$schema: "https://astra-spec.org/v1/schema.json"
version: "1.0"
name: "Iris Classification Study"

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
  - id: trained_output
    type: data
    description: "Best performing classifier"
    recipe:
      command: python src/train.py

  - id: accuracy
    type: metric
    description: "Classification accuracy on held-out test set"
    recipe:
      command: python src/evaluate.py
      inputs: [trained_output]

  - id: f1_score
    type: metric
    description: "Macro-averaged F1 score"
    recipe:
      command: python src/evaluate.py
      inputs: [trained_output]

  - id: confusion_matrix
    type: figure
    description: "Confusion matrix heatmap"
    recipe:
      command: python src/evaluate.py
      inputs: [trained_output]

  - id: model_comparison
    type: table
    description: "Accuracy by model and preprocessing combination"
    recipe:
      command: python src/evaluate.py
      inputs: [trained_output]

  - id: conclusion
    type: report
    description: "Summary of classifier performance and suitability for the application"
    recipe:
      command: python src/evaluate.py
      inputs: [trained_output]

insights:
  minmax_tree_improvement:
    id: minmax_tree_improvement
    claim: "MinMax scaling improves tree model accuracy by 3% on tabular data."
    created_at: "2024-01-15T10:00:00Z"
    evidence:
      - id: ev1
        doi: "10.1234/scaling-comparison-2024"
        quote:
          type: TextQuoteSelector
          exact: "MinMax normalization yielded a 3% improvement in accuracy for Random Forest classifiers on tabular datasets."
        location:
          type: FragmentSelector
          page: 8
    scope: "Tree-based models on tabular data"

decisions:
  scaling:
    label: "Feature Scaling"
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
        insights:
          - minmax_tree_improvement
        incompatible_with:
          - model.svm

  model:
    label: "Classification Model"
    rationale: "Core algorithmic choice affecting accuracy and interpretability"
    default: random_forest
    options:
      svm:
        label: "Support Vector Machine"
        description: "Maximum margin classifier"
        requires:
          - scaling.standard
      random_forest:
        label: "Random Forest"
        description: "Ensemble of decision trees"
      logistic:
        label: "Logistic Regression"
        description: "Linear classifier with probabilistic output"

  test_size:
    label: "Test Set Proportion"
    rationale: "Trade-off between training data and evaluation reliability"
    default: small
    options:
      small:
        label: "20%"
      medium:
        label: "30%"

  random_seed:
    label: "Random Seed"
    rationale: "For reproducibility and stability testing"
    default: seed_42
    options:
      seed_42:
        label: "42"
      seed_123:
        label: "123"
```

## Execution Model

### Single Universe Execution (typical)

Given an analysis spec and a universe (set of decisions):

1. **Parse** the spec and validate the universe against constraints
2. **Agent generates** implementation code based on the decisions
3. **Execute** the code
4. **Collect** declared outputs (metrics, artifacts, conclusion)
5. **Store** the execution record linking universe → results

The result is a complete analysis with all declared outputs produced.

### Multiverse Exploration (optional)

If the user wants to check robustness or explore alternatives:

1. **Select** alternative universes to run (user choice or sampling)
2. **Execute** each selected universe
3. **Compare** results across universes
4. **Generate** multiverse summary (specification curve, sensitivity analysis)

## Execution

ASTRA makes no prescription about execution frameworks. The specification defines *what* to compute; execution is handled by the agentic layer (e.g., Prism).


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
├── astra.yaml
├── universes/
│   └── baseline.yaml
└── outputs/

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

### Discovering New Decisions During Execution

A common scenario: while running an analysis, you realize there's a decision you didn't anticipate.

**Workflow:**
1. You're running the baseline universe
2. You notice: "Wait, should we handle class imbalance? That's a decision!"
3. Add the new decision to `astra.yaml`
4. Commit: "Add class_imbalance decision point"
5. Update universe files to include the new decision
6. Continue execution

The analysis definition evolves as you learn. This is expected and tracked naturally by Git.

## CLI Commands

The ASTRA CLI provides tools for working with specifications:

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

For full agentic scaffolding (Claude Code config, HPC targets, visual editors), use Prism: `prism init`.

## Schema Reference

### Analysis Schema (astra.yaml)

```yaml
$schema: "https://astra-spec.org/v1/analysis.schema.json"
version: "1.0"                    # Required: ASTRA spec version (major.minor)

name: string                      # Required (root): Human-readable name
description: string               # Optional: Detailed description
authors: [string]                 # Optional: List of authors
tags: [string]                    # Optional: Tags for categorization

success_criteria:                 # Optional: Structured criteria for success
  - claim: string                 # Human-readable statement of the criterion
    output: string                # Optional: output ID to check against
    condition: string             # Optional: condition (e.g., "value > 0.95")

inputs:                           # Required (root): List of inputs
  - id: string                    # Unique identifier (pattern: ^[a-z][a-z0-9_]*$)
    type: data|analysis           # Input type
    description: string           # Optional
    # For type: data
    source: string                # Optional: URI or path
    checksum:                     # Optional: integrity verification
      algorithm: sha256|sha512|md5
      value: string
    # For type: analysis
    ref: string                   # Optional: reference to another analysis
    ref_version: string           # Optional: version of referenced analysis
    use_outputs: [string]         # Optional: specific outputs to use
    # For sub-analysis inputs
    from: string                  # Optional: parent input or sibling output

outputs:                          # Required (root): List of outputs
  - id: string                    # Unique identifier (pattern: ^[a-z][a-z0-9_]*$)
    type: metric|figure|table|data|report
    description: string           # Optional
    from: string                  # Optional: which sub-analysis produces this
    recipe:                       # Optional: inline build rule
      command: string             # Required: command to execute
      inputs: [string]            # Optional: output IDs that must be materialized first
      container: string|{build}   # Optional: container image or build spec
      resources:                  # Optional: compute requirements
        cpus: int                 # >= 1
        memory: string            # e.g., "8GB"
        gpus: int                 # >= 1
        time_limit: string        # e.g., "2h"

decisions:                        # Optional: Map of decisions
  decision_id:
    label: string                 # Required: Human-readable name
    rationale: string             # Optional: Why this decision exists
    tags: [string]                # Optional: Tags for grouping
    when: string                  # Optional: "decision_id.option_id" condition
    default: option_id            # Optional: Default for baseline universes
    options:                      # Required: Map of option ID to option spec
      option_id:
        label: string             # Required: Human-readable name
        description: string       # Optional
        insights: [string]        # Optional: insight IDs supporting this option
        incompatible_with: [string]  # Optional: "decision.option" pairs
        requires: [string]        # Optional: "decision.option" pairs
        excluded: bool            # Optional: was considered and rejected
        excluded_reason: string   # Required when excluded is true

insights:                         # Optional: Map of insights
  insight_id:
    id: string                    # Unique identifier
    claim: string                 # What we learned (1-2 sentences)
    created_at: datetime          # ISO 8601 timestamp
    evidence:                     # Required: list of evidence items
      - id: string                # Evidence ID
        # Source: exactly one of doi or artifact
        doi: string               # Paper DOI (e.g., "10.48550/arXiv.1706.03762")
        artifact: string          # OR: output ID referencing a declared output
        version: int              # Optional: paper version (for arXiv, doi only)
        checksum:                 # Optional: artifact integrity (artifact only)
          algorithm: sha256|sha512|md5
          value: string
        snapshot: string          # Optional: path to immutable copy (artifact only)
        source_commit: string     # Optional: git commit (artifact only)
        # Content selectors (at least one required)
        quote:
          type: TextQuoteSelector
          exact: string           # Exact quoted text
          prefix: string          # Optional: context before
          suffix: string          # Optional: context after
        figure:
          type: FigureSelector
          label: string           # Figure label (e.g., "Figure 3a")
          caption: string         # Optional: caption text
        table:
          type: TableSelector
          label: string           # Table label (e.g., "Table 1")
          caption: string         # Optional: header text
          region: string          # Optional: specific region
        location:                 # Optional: PDF location hint
          type: FragmentSelector
          page: int               # 1-indexed page number
    derived: bool                 # Optional: true if synthesized/inferred
    scope: string                 # Optional: applicability conditions
    tags: [string]                # Optional: categorization tags
    notes: string                 # Optional: reasoning notes

container: string|{build}        # Optional: default container image for recipes

analyses:                         # Optional: Map of sub-analyses
  analysis_id:                    # Each sub-analysis has the same structure
    description: string
    parent_decisions: [string]    # Optional: parent decision IDs for constraint scoping
                                  # (handled by semantic validation, not in JSON schema)
    inputs: [...]
    outputs: [...]
    decisions: {...}
    insights: {...}
    analyses: {...}               # Can nest further
```

### Universe Schema (universes/*.yaml)

```yaml
$schema: "https://astra-spec.org/v1/universe.schema.json"

id: string                        # Unique identifier (pattern: ^[a-z][a-z0-9_-]*$)
description: string               # What this universe represents

decisions:                        # Root-level decision selections
  scaling: standard               # decision_id: selected_option_id
  model: random_forest

analyses:                         # Sub-analysis decision selections
  build_mocks:
    decisions:
      noise_model: heteroscedastic
  train_network:
    decisions:
      architecture: maf
    analyses:                     # Can nest further
      sub_step:
        decisions:
          method: option_a
```

## Open Questions

1. **Agent instructions**: Should the spec include hints for the agent about implementation preferences? Or is the description sufficient?

2. **Semantic validation**: How do we validate that outputs are meaningful? (Syntactic validation—checking outputs exist—is straightforward.)

3. **Caching**: If a decision doesn't affect certain outputs, can we cache and reuse? This requires understanding which decisions affect which workflow steps.

4. **Cross-branch comparison**: How do we compare results between branches that have different decision spaces?

## Benefits of This Model

1. **Declarative**: Spec says WHAT, not HOW
2. **Transparent**: All decisions and alternatives are documented
3. **Self-similar**: Every level has the same structure; sub-analyses are valid analyses
4. **Composable**: Analyses can build on each other
5. **Evidence-linked**: Decisions can cite supporting evidence
6. **Agent-friendly**: Clear structure for LLM to understand and implement
7. **Goal-oriented**: Outputs define what the analysis must produce
8. **Single-analysis first**: One universe answers the question; multiverse is for exploration
9. **Reproducible**: Precise input provenance and execution records ensure reproducibility
