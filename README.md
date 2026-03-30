# ASTRA - Agentic Schema for Transparent Research Analysis

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](https://opensource.org/licenses/Apache-2.0)

A declarative specification format for scientific analyses that can be executed by AI agents.

## What is ASTRA?

ASTRA defines **what** a scientific analysis should produce, not **how** to compute it. The schema is defined in [LinkML](https://linkml.io/) — a single source of truth that generates validators, vocabulary, and Python models.

Analyses are authored as compact YAML files (`astra.yaml`) and can be exported to [RO-Crate](https://www.researchobject.org/ro-crate/) for FAIR publishing.

```
astra.yaml (compact, agent-friendly)  ←→  RO-Crate (FAIR, interoperable)
         ↑                                        ↑
   LinkML Schema ──generates──→ JSON Schema + JSON-LD Context + Pydantic Models
```

## Quick Start

```bash
pip install astra

# Create a new analysis
astra init my-analysis
cd my-analysis

# Edit astra.yaml, then validate
astra validate

# View structure
astra info
astra viz

# Export to RO-Crate for publishing
astra export rocrate -o my-crate/
```

## Example

```yaml
name: iris_classification
astra_version: "1.0"
label: Iris Classification Study

inputs:
  - name: iris_data
    type: data
    source: sklearn.datasets.load_iris

outputs:
  - name: accuracy
    type: metric
    recipe:
      command: python src/evaluate.py
      depends_on: [trained_model]

decisions:
  scaling:
    label: Feature Scaling
    default: standard
    options:
      standard: { label: StandardScaler }
      minmax: { label: MinMaxScaler, incompatible_with: [model.svm] }
  model:
    label: Classification Model
    default: random_forest
    options:
      svm: { label: SVM, requires: [scaling.standard] }
      random_forest: { label: Random Forest }

universes:
  baseline:
    description: Default configuration
    selections:
      - decision: scaling
        option: standard
      - decision: model
        option: random_forest
```

## Key Concepts

- **Analysis** — Self-similar node with inputs, outputs, decisions, sub-analyses
- **Decision** — A choice point with multiple options
- **Universe** — One complete set of decisions (one path through the decision space)
- **Multiverse** — All valid decision combinations (for transparency, not exhaustive search)
- **Insight** — A scientific claim backed by evidence (paper quotes or analysis artifacts)
- **Recipe** — A build rule for producing an output

## Python API

```python
from astra import load_yaml, get_decision, export_rocrate

data = load_yaml("my-analysis")
scaling = get_decision(data, "scaling")
export_rocrate(data, "my-crate/")
```

## Architecture

```
src/astra/schema/astra.yaml    ← LinkML schema (single source of truth)
src/astra/schema/generated/    ← JSON Schema, JSON-LD context, Pydantic models
src/astra/loader.py            ← YAML loading + validation
src/astra/helpers.py           ← Dict-based query helpers
src/astra/export.py            ← YAML → RO-Crate transformer
src/astra/crate.py             ← RO-Crate engine (internal)
src/astra/cli.py               ← CLI commands
src/astra/papers/              ← Paper downloading and caching
src/astra/verification/        ← PDF quote verification
```

## Documentation

- [Design Document](DESIGN.md) — Architecture and data model
- [Examples](examples/) — Complete working examples

## License

Apache 2.0
