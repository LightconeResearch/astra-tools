# ASP Schema Reference

Detailed schema information for ASP specifications.

## Analysis Schema (`asp.yaml`)

```yaml
$schema: "https://asp-spec.org/v1/schema.json"  # Optional
version: "1.0"  # Required: format X.Y

analysis:
  name: string              # Required: Human-readable name
  description: string       # Optional: Detailed description
  authors: [string]         # Optional: List of authors
  tags: [string]            # Optional: Categorization tags
  problem: string           # Required: Problem statement

  inputs:                   # Required: List of inputs
    - id: string            # Required: lowercase_with_underscores
      type: data|analysis|literature  # Required
      source: string|Source # Optional: Where to get the data
      ref: string           # Optional: Analysis reference (for type: analysis)
      version: string       # Optional: Version of referenced analysis
      use_outputs: [string] # Optional: Specific outputs to use
      description: string   # Optional

  outputs:                  # Required: List of outputs
    - id: string            # Required: lowercase_with_underscores
      type: metric|figure|table|data|model|report  # Required
      dtype: float|int|bool|string  # Optional: For metrics
      range: [min, max]     # Optional: Valid range for metrics
      formats: [string]     # Optional: File formats (png, csv, etc.)
      primary: boolean      # Optional: Is this the main output?
      description: string   # Optional

decisions:                  # Optional: Map of decision_id -> Decision
  decision_id:
    label: string           # Required: Human-readable name
    type: data|method|parameter  # Required
    importance: 1-5         # Optional: 1=critical, 5=minor (default: 3)
    rationale: string       # Optional: Why this decision exists
    default: string         # Optional: Default option ID
    options:                # Required: Map of option_id -> Option
      option_id:
        label: string       # Required: Human-readable name
        description: string # Optional
        value: any          # Optional: Configuration value
        evidence:           # Optional: Supporting evidence
          - insight: string # Reference to insight ID
          # OR legacy format:
          - ref: string     # Reference to input (inputs.xxx)
            finding: string # What the evidence shows
        incompatible_with: [string]  # Optional: ["decision.option", ...]
        requires: [string]  # Optional: ["decision.option", ...]

insights:                   # Optional: Map of insight_id -> Insight
  insight_id:
    claim: string           # Required: What we learned (1-2 sentences)
    source:                 # Required: One of:
      doi: string           # Paper DOI (10.XXXX/...)
      # OR
      analysis: string      # Analysis reference
      version: string       # Optional: Analysis version
      universe: string      # Optional: Specific universe
    evidence: [Evidence]    # Optional: Supporting evidence
    scope: string           # Optional: When/where this applies
```

## Evidence Types

### For Paper Sources (doi)

```yaml
# Figure evidence
- figure: "Figure 3a"
  caption: "Optional description"

# Quote evidence
- quote: "Exact text from paper"
  location: "Section 2.1, p.5"

# Table evidence
- table: "Table 1"
  location: "row 3"
  value: "0.92"

# Equation evidence
- equation: "Equation 7"
  expression: "L = f(x)"

# Result evidence
- result: "Description of finding"
  location: "Section 4"
  value: 0.15
```

### For Analysis Sources (analysis)

```yaml
# Metric evidence
- metric:
    name: "accuracy"
    value: 0.94  # or {option_a: 0.94, option_b: 0.89}

# Output evidence
- output: "path/to/output.png"
```

## Universe Schema (`universes/*.yaml`)

```yaml
$schema: "https://asp-spec.org/v1/universe.schema.json"  # Optional
id: string                  # Required: lowercase-with-hyphens
description: string         # Optional
decisions:                  # Required: Map of decision_id -> option_id
  preprocessing: standard
  model: rf
  test_split: split_20
```

## Insights Collection Schema (`insights/*.yaml`)

For standalone insight files:

```yaml
$schema: "https://asp-spec.org/v1/insights.schema.json"  # Optional
insights:
  insight_id:
    claim: string
    source:
      doi: string
    evidence: [...]
    scope: string
```

## ID Patterns

| Field | Pattern | Example |
|-------|---------|---------|
| Input ID | `^[a-z][a-z0-9_]*$` | `primary_data`, `smith2023` |
| Output ID | `^[a-z][a-z0-9_]*$` | `accuracy`, `confusion_matrix` |
| Decision ID | lowercase_underscores | `preprocessing`, `model_choice` |
| Option ID | lowercase_underscores | `standard`, `random_forest` |
| Universe ID | `^[a-z][a-z0-9_-]*$` | `baseline`, `experiment-1` |
| Insight ID | lowercase_underscores | `scaling_law`, `efficiency_finding` |
| DOI | `^10\.\d{4,}/.*$` | `10.1038/s41586-023-06221-2` |

## Constraint References

Format: `decision_id.option_id`

```yaml
options:
  minmax:
    label: "MinMax Scaling"
    incompatible_with:
      - "model.svm"        # Can't use with SVM model
    requires:
      - "normalize.enabled" # Requires normalization to be on
```

## Validation Rules

### Schema Validation
- All required fields present
- Field types match schema
- Patterns valid (IDs, DOI, version)
- Enums have valid values

### Semantic Validation
- No duplicate input/output IDs
- Default option exists in options
- Evidence references valid insights
- Constraint references valid decision.option pairs
- Universe covers all decisions
- Universe options are valid for each decision
