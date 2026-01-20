"""ASP Schema Reference template for Claude Code skill."""

SCHEMA_REFERENCE_CONTENT = """\
# ASP Schema Reference

## Analysis Schema (`asp.yaml`)

```yaml
version: "1.0"  # Required

analysis:
  name: string              # Required
  description: string       # Optional
  problem: string           # Required: What question are we answering?

  inputs:
    - id: string            # lowercase_with_underscores
      type: data|analysis|literature
      description: string

  outputs:
    - id: string
      type: metric|figure|table|data|model|report
      dtype: float|int|bool|string  # For metrics
      primary: boolean      # Is this the main output?
      description: string

decisions:
  decision_id:
    label: string           # Human-readable name
    type: data|method|parameter
    importance: 1-5         # 1=critical, 5=minor
    rationale: string       # Why this decision matters
    default: string         # Default option ID
    options:
      option_id:
        label: string
        description: string
        evidence:
          - insight: string  # Reference to insight ID
        incompatible_with: ["decision.option"]  # Can't coexist
        requires: ["decision.option"]           # Must coexist

insights:
  insight_id:
    claim: string           # What we learned (1-2 sentences)
    source:
      doi: string           # Paper: 10.XXXX/...
      # OR
      analysis: string      # Prior analysis reference
    evidence:
      # For papers: figure, quote, table, equation, result
      # For analyses: metric, output
    scope: string           # When/where this applies
```

## Universe Schema (`universes/*.yaml`)

```yaml
id: string                  # lowercase-with-hyphens
description: string
decisions:
  decision_id: option_id    # One selection per decision
```

## Evidence Types

### Paper Sources (doi)
```yaml
- figure: "Figure 3a"
  caption: "Description"
- quote: "Exact text"
  location: "Section 2.1, p.5"
- table: "Table 1"
  value: "0.92"
- equation: "Equation 7"
  expression: "L = f(x)"
- result: "Finding description"
  value: 0.15
```

### Analysis Sources (analysis)
```yaml
- metric:
    name: "accuracy"
    value: 0.94
- output: "path/to/output.png"
```

## ID Patterns

| Field | Pattern | Example |
|-------|---------|---------|
| IDs | `^[a-z][a-z0-9_]*$` | `primary_data` |
| Universe ID | `^[a-z][a-z0-9_-]*$` | `experiment-1` |
| DOI | `^10\\.\\d{4,}/.*$` | `10.1038/s41586-023-06221-2` |
| Constraint ref | `decision.option` | `model.svm` |
"""
