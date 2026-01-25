# CWL Workflow Building Guide

This guide covers how to build CWL workflows from ASP analyses.

## Overview

When an ASP analysis is specified, you need to build a corresponding CWL workflow that:
1. Accepts parameters matching the ASP decisions AND inputs
2. Produces outputs matching the ASP output definitions
3. Implements the computational steps implied by the analysis

## Workflow Construction Process

### Step 1: Analyze the ASP Specification

Read `asp.yaml` and identify:
- **Inputs**: Data sources → CWL `File` inputs (auto-resolved from sources)
- **Outputs**: Results the workflow must produce
- **Decisions**: Parameters that control workflow behavior

### Step 2: Design CWL Input Parameters

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

### Step 3: Map ASP Outputs to CWL Outputs

For each ASP output, create a corresponding CWL output:

| ASP Output Type | CWL Output Type |
|----------------|-----------------|
| `metric` (dtype: float) | `type: float` or `type: File` (JSON) |
| `metric` (dtype: int) | `type: int` or `type: File` (JSON) |
| `figure` | `type: File` with appropriate format |
| `table` | `type: File` (CSV, JSON, etc.) |
| `model` | `type: File` (joblib, pickle, etc.) |
| `report` | `type: File` (markdown, PDF, etc.) |

### Step 4: Implement Workflow Steps

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

### Step 5: Create Step Implementations

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

## Complete Example: ASP to CWL

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

## Validation Workflow

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

## How Inputs and Decisions Map to CWL

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

## Remote File Handling

**Important**: CWL/cwltool natively handles remote file downloads. When you specify a URL, cwltool automatically downloads the file at runtime. Do NOT implement custom download code - just pass the URL in the `location` field:

```yaml
# For local files
training_data:
  class: File
  path: data/train.csv

# For remote URLs - cwltool handles the download
remote_data:
  class: File
  location: "https://example.com/data.csv"
```
