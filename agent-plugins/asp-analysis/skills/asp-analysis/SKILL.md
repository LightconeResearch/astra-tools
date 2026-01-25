---
name: asp-analysis
description: Work with ASP (Agentic Science Protocol) analyses. Use when creating new analyses, extracting insights from papers, validating specifications, or managing universes. Triggers on mentions of ASP, analysis specs, scientific insights, paper extraction, or decision documentation.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(asp:*), Bash(python:*)
---

# ASP Analysis Skill

Help users work with the Agentic Science Protocol (ASP) - a declarative specification format for scientific analyses.

## Quick Reference

### CLI Commands
```bash
asp init <directory>              # Create new analysis project
asp validate asp.yaml             # Validate analysis specification
asp validate universes/foo.yaml   # Validate universe
asp info                          # Show analysis summary
asp info --decisions              # Show decision details
asp universe generate -n baseline # Generate universe from defaults
asp universe check universes/x.yaml  # Check universe constraints
asp viz                           # Visualize decision space
asp schema show analysis          # Show JSON schema

# Workflow Integration
asp workflow run universes/baseline.yaml --cwl main.cwl  # Run workflow
asp workflow run universes/x.yaml --cwl main.cwl -o out/ # Run with output dir
asp workflow validate --cwl main.cwl         # Validate CWL mapping
asp workflow show --cwl main.cwl             # Show parameter mapping table
asp params universes/baseline.yaml           # Output CWL parameters to stdout
```

## Core Concepts

### Analysis Structure
An ASP analysis (`asp.yaml`) contains:
- **analysis**: name, problem statement, inputs, outputs
- **decisions**: choices that define the analysis methodology
- **insights**: scientific knowledge from papers or prior analyses

### Insights
Insights are discrete units of scientific knowledge with precise provenance:
- **From papers**: Referenced by DOI with figure/quote/table evidence
- **From analyses**: Referenced by analysis ID with metric/output evidence

### Universes
A universe is a complete set of decisions - one option per decision point.

### Inputs
Inputs define the data sources for an analysis. Each input has:
- **id**: Unique identifier (used as CWL parameter name)
- **type**: `data`, `analysis`, or `literature`
- **source**: Where to get the data (file path or URL)

```yaml
inputs:
  - id: training_data
    type: data
    source: "data/train.csv"           # Local file path

  - id: remote_data
    type: data
    source:
      type: url
      url: "https://example.com/data.csv"  # Remote URL
```

When running workflows, inputs are resolved to CWL File parameters:
- **Local files** → `{class: File, path: "..."}`
- **URLs** → `{class: File, location: "https://..."}`

**Important**: CWL/cwltool natively handles remote file downloads. When you specify a URL, cwltool automatically downloads the file at runtime. Do NOT implement custom download code - just pass the URL in the `location` field and let cwltool handle it.

## Creating a New Analysis

When the user wants to create a new ASP analysis:

1. Use `asp init` to scaffold the project:
```bash
asp init my-analysis -n "Analysis Name" -p "Problem statement"
```

2. Edit `asp.yaml` to define:
   - Inputs (data sources, literature)
   - Outputs (metrics, figures, reports)
   - Decisions (methodology choices)

3. Add insights from relevant papers to support decisions

4. Validate with `asp validate asp.yaml`

## Extracting Insights from Papers

When the user provides a paper (PDF, DOI, or description) to extract insights:

### Step 1: Identify the Paper
Get the DOI. Format: `10.XXXX/...` (e.g., `10.1038/s41586-023-06221-2`)

### Step 2: Read the Current Analysis
Check `asp.yaml` to understand:
- What problem is being solved?
- What decisions need evidence?
- What inputs/outputs are defined?

### Step 3: Extract Relevant Insights
For each insight relevant to the analysis:

```yaml
insights:
  insight_id:  # lowercase_with_underscores
    claim: "One sentence stating what we learned"
    source:
      doi: "10.1234/paper-doi"
    evidence:
      # For figures:
      - figure: "Figure 3a"
        caption: "Description of what it shows"
      # For quotes:
      - quote: "Exact text from the paper"
        location: "Section 2.1, p.5"
      # For tables:
      - table: "Table 1"
        location: "row 3, accuracy column"
        value: "0.92"
      # For equations:
      - equation: "Equation 7"
        expression: "L = (C/C_0)^α"
      # For numerical results:
      - result: "accuracy improvement"
        location: "Section 4.2"
        value: "15%"
    scope: "Context where this applies (optional)"
```

### Step 4: Link to Decisions
Reference insights in decision options:

```yaml
decisions:
  method_choice:
    options:
      method_a:
        label: "Method A"
        evidence:
          - insight: insight_id  # Reference the insight
```

### Step 5: Validate
```bash
asp validate asp.yaml
```

## Example: Complete Insight Extraction

Given a paper about neural scaling laws:

```yaml
# In asp.yaml
insights:
  compute_scaling:
    claim: "Language model loss scales as a power law with compute budget"
    source:
      doi: "10.48550/arXiv.2001.08361"
    evidence:
      - figure: "Figure 1"
        caption: "Loss vs compute showing power law relationship"
      - quote: "We find L(C) ∝ C^{−0.050}"
        location: "Section 2.1, p.3"
      - equation: "Equation 1.1"
        expression: "L(C) = (C_c/C)^{α_C}"
    scope: "Transformer models on language modeling tasks"

  model_efficiency:
    claim: "Larger models are more sample-efficient, reaching same loss with fewer tokens"
    source:
      doi: "10.48550/arXiv.2001.08361"
    evidence:
      - figure: "Figure 4"
        caption: "Sample efficiency curves for different model sizes"
      - quote: "Larger models reach the same loss with fewer samples"
        location: "Section 3.2"
    scope: "Fixed compute budget scenarios"

decisions:
  model_size:
    label: "Model Size Selection"
    type: method
    importance: 1
    rationale: "Model size affects both performance and efficiency"
    default: large
    options:
      small:
        label: "Small Model (125M)"
        description: "Faster training, lower performance ceiling"
      large:
        label: "Large Model (1.3B)"
        description: "Better sample efficiency, higher performance"
        evidence:
          - insight: compute_scaling
          - insight: model_efficiency
```

## Insight Types by Source

### From Papers (doi)
Use these evidence types:
- `figure`: Reference to a figure
- `quote`: Direct quote with location
- `table`: Table reference with specific value
- `equation`: Mathematical expression
- `result`: Numerical finding

### From Prior Analyses (analysis)
Use these evidence types:
- `metric`: Named metric with value
- `output`: Reference to output artifact

```yaml
insights:
  prior_finding:
    claim: "StandardScaler outperforms MinMaxScaler on this dataset"
    source:
      analysis: "our-org/preprocessing-study"
      version: "1.2.0"
      universe: "baseline"
    evidence:
      - metric:
          name: "accuracy"
          value: { standard: 0.94, minmax: 0.89 }
      - output: "figures/scaler_comparison.png"
```

## Validation Checklist

Before finalizing an analysis, verify:

1. **Schema compliance**: `asp validate asp.yaml`
2. **All decisions have defaults**: Required for universe generation
3. **Insights have valid DOIs**: Pattern `10.XXXX/...`
4. **Evidence references exist**: Insights referenced in evidence must be defined
5. **Constraint references valid**: `incompatible_with` and `requires` point to real options

## Common Patterns

### Adding a New Decision
```yaml
decisions:
  new_decision:
    label: "Human-readable Label"
    type: method  # or: data, parameter
    importance: 3  # 1=critical, 5=minor
    rationale: "Why this decision matters"
    default: option_a
    options:
      option_a:
        label: "Option A"
        description: "What this option does"
      option_b:
        label: "Option B"
        description: "Alternative approach"
        incompatible_with: ["other_decision.some_option"]
```

### Adding Literature Input
```yaml
analysis:
  inputs:
    - id: smith2023
      type: literature
      description: "Smith et al. 2023 - Methodology paper"
```

### Creating a New Universe
```bash
asp universe generate -n experiment1 -d "Testing hypothesis X"
```

Then edit `universes/experiment1.yaml` to customize decisions.

## File Locations

```
my-analysis/
├── asp.yaml              # Main analysis specification
├── universes/            # Decision selections (source of truth for CWL params)
│   ├── baseline.yaml     # Default configuration
│   └── experiment1.yaml  # Alternative configuration
├── workflows/            # CWL workflow definitions
│   └── main.cwl          # Main workflow
├── steps/                # ALL workflow implementation goes here
│   ├── io/               # Data loading steps (.cwl + scripts)
│   ├── preprocessing/    # Preprocessing steps
│   ├── models/           # Model training steps
│   └── evaluation/       # Evaluation steps
├── insights/             # Optional: separate insight files
└── results/              # Execution outputs (gitignored)
```

**Important**:
- All implementation code (Python, R, shell scripts) must be placed in the `steps/` folder alongside their CWL definitions. Do not create a separate `scripts/` folder.
- Universes are the source of truth for CWL parameters. Use `asp workflow run` to execute workflows directly from universes, or `asp params` to inspect the generated parameters.

## Building CWL Workflows from ASP Analyses

When an ASP analysis is specified, you need to build a corresponding CWL workflow that:
1. Accepts parameters matching the ASP decisions AND inputs
2. Produces outputs matching the ASP output definitions
3. Implements the computational steps implied by the analysis

### Workflow Construction Process

#### Step 1: Analyze the ASP Specification

Read `asp.yaml` and identify:
- **Inputs**: Data sources → CWL `File` inputs (auto-resolved from sources)
- **Outputs**: Results the workflow must produce
- **Decisions**: Parameters that control workflow behavior

#### Step 2: Design CWL Input Parameters

**For ASP inputs** (type: data), create CWL File inputs using the input ID:
```yaml
# ASP input
inputs:
  - id: training_data
    type: data
    source: "data/train.csv"

# CWL input (use same ID)
inputs:
  training_data:
    type: File
    doc: "Training dataset"
```

**For ASP decisions**, create CWL parameters following naming conventions:

| ASP Decision Pattern | CWL Input Design |
|---------------------|------------------|
| Decision with simple `value` (int/float/str) | Single input named `{decision_id}` |
| Decision with dict `value` | Multiple inputs named `{decision_id}_{key}` |
| Decision without `value` field | Single input named `{decision_id}` (receives option_id as string) |

**Example:** Given this ASP decision:
```yaml
decisions:
  preprocessing:
    options:
      standard:
        label: "StandardScaler"
        value:
          method: "standard"
          with_mean: true
```

Create these CWL inputs:
```yaml
inputs:
  preprocessing_method:
    type: string
    doc: "Preprocessing method (standard, minmax, none)"
  preprocessing_with_mean:
    type: boolean?
    doc: "Whether to center data before scaling"
```

#### Step 3: Map ASP Outputs to CWL Outputs

For each ASP output, create a corresponding CWL output:

| ASP Output Type | CWL Output Type |
|----------------|-----------------|
| `metric` (dtype: float) | `type: float` or `type: File` (JSON) |
| `metric` (dtype: int) | `type: int` or `type: File` (JSON) |
| `figure` | `type: File` with appropriate format |
| `table` | `type: File` (CSV, JSON, etc.) |
| `model` | `type: File` (joblib, pickle, etc.) |
| `report` | `type: File` (markdown, PDF, etc.) |

#### Step 4: Implement Workflow Steps

Create the main workflow in `workflows/main.cwl`:

```yaml
cwlVersion: v1.2
class: Workflow

inputs:
  input_data:
    type: File
  preprocessing_method:
    type: string
  model_type:
    type: string
  test_size:
    type: float

outputs:
  accuracy:
    type: float
    outputSource: evaluate/accuracy
  trained_model:
    type: File
    outputSource: train/model

steps:
  preprocess:
    run: steps/preprocessing/preprocess.cwl
    in:
      data: input_data
      method: preprocessing_method
    out: [processed_data]

  train:
    run: steps/models/train.cwl
    in:
      data: preprocess/processed_data
      model_type: model_type
    out: [model]

  evaluate:
    run: steps/evaluation/evaluate.cwl
    in:
      model: train/model
      test_size: test_size
    out: [accuracy]
```

#### Step 5: Create Step Implementations

Each step in `steps/` contains both the CWL definition and its implementation script:

```
steps/
├── preprocessing/
│   ├── preprocess.cwl      # CWL CommandLineTool definition
│   └── preprocess.py       # Python implementation
├── models/
│   ├── train.cwl
│   └── train.py
└── evaluation/
    ├── evaluate.cwl
    └── evaluate.py
```

Example step (`steps/preprocessing/preprocess.cwl`):
```yaml
cwlVersion: v1.2
class: CommandLineTool
baseCommand: [python, preprocess.py]

requirements:
  InitialWorkDirRequirement:
    listing:
      - entryname: preprocess.py
        entry: $(inputs.script)

inputs:
  script:
    type: File
    default:
      class: File
      location: preprocess.py
  data:
    type: File
    inputBinding: { prefix: --data }
  method:
    type: string
    inputBinding: { prefix: --method }

outputs:
  processed_data:
    type: File
    outputBinding: { glob: "processed_*.csv" }
```

### Complete Example: ASP to CWL

Given this ASP analysis:
```yaml
# asp.yaml
analysis:
  name: "Classification Study"
  inputs:
    - id: dataset
      type: data
  outputs:
    - id: accuracy
      type: metric
      dtype: float
      primary: true
    - id: model
      type: model

decisions:
  scaling:
    type: method
    default: standard
    options:
      standard:
        value: { method: "standard", with_mean: true }
      minmax:
        value: { method: "minmax", with_mean: false }
      none:
        value: { method: "none" }

  classifier:
    type: method
    default: rf
    options:
      rf:
        label: "Random Forest"
      svm:
        label: "SVM"
        requires: [scaling.standard]

  test_split:
    type: parameter
    default: split_20
    options:
      split_20:
        value: 0.2
      split_30:
        value: 0.3
```

Build this CWL workflow:
```yaml
# workflows/main.cwl
cwlVersion: v1.2
class: CommandLineTool
baseCommand: [python, run_analysis.py]

inputs:
  # Data input
  dataset:
    type: File
    inputBinding: { prefix: --dataset }

  # From 'scaling' decision (dict value)
  scaling_method:
    type: string
    inputBinding: { prefix: --scaling-method }
  scaling_with_mean:
    type: boolean?
    inputBinding: { prefix: --scaling-with-mean }

  # From 'classifier' decision (no value field)
  classifier:
    type: string
    inputBinding: { prefix: --classifier }

  # From 'test_split' decision (simple value)
  test_split:
    type: float
    inputBinding: { prefix: --test-split }

outputs:
  accuracy:
    type: float
    outputBinding:
      glob: results/accuracy.txt
      loadContents: true
      outputEval: $(parseFloat(self[0].contents))
  model:
    type: File
    outputBinding:
      glob: results/model.joblib
```

### Validation Workflow

After building your CWL workflow:

```bash
# 1. Validate CWL syntax only (uses cwltool)
asp workflow validate --cwl workflows/main.cwl --syntax-only

# 2. Validate CWL syntax + ASP decision mapping
asp workflow validate --cwl workflows/main.cwl

# 3. View the parameter mapping table
asp workflow show --cwl workflows/main.cwl

# 4. Run workflow with a universe
asp workflow run universes/baseline.yaml --cwl workflows/main.cwl

# 5. Run with output directory
asp workflow run universes/baseline.yaml --cwl workflows/main.cwl -o results/baseline/
```

The `asp workflow validate` command performs two checks:
1. **CWL syntax validation** using cwltool (validates against CWL specification)
2. **ASP mapping validation** (ensures decisions map to CWL parameters)

### How Inputs and Decisions Map to CWL

When you run `asp workflow run` or `asp params`, ASP generates CWL parameters from:

1. **Decisions** (from universe): Maps to CWL parameters based on naming conventions
2. **Inputs** (from asp.yaml): Maps `type: data` inputs to CWL File parameters

Example generated parameters:
```yaml
# From decisions (universe selections)
preprocessing: standard
model: rf
test_split: 0.2

# From inputs (asp.yaml sources)
training_data:
  class: File
  path: data/train.csv
```

The CWL workflow must have matching input parameters:
```yaml
inputs:
  preprocessing:
    type: string
  model:
    type: string
  test_split:
    type: float
  training_data:
    type: File
```

## Tips

1. **Start with the problem**: Write a clear problem statement before defining decisions
2. **One insight per finding**: Don't combine multiple findings in one insight
3. **Precise evidence**: Include page numbers, figure labels, exact quotes
4. **Link insights to decisions**: Every decision option should ideally have supporting evidence
5. **Use scope**: Clarify when an insight applies (dataset, model type, conditions)
6. **Add value fields**: When integrating with CWL, add explicit `value` fields to options
