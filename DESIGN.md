# ASTRA Design Document

## Overview

**ASTRA (Agentic Schema for Transparent Research Analysis)** is a declarative specification format for scientific analyses, implemented as an [RO-Crate 1.2](https://www.researchobject.org/ro-crate/specification/1.2/) profile.

It describes:
- What we have to work with (inputs)
- What we want to produce (outputs)
- What choices need to be made (decisions)

An analysis does **not** specify how to execute the computation. That is the job of an agent (e.g., Prism), which reads the specification and generates implementations.

```
ASTRA Analysis (RO-Crate)  -->  Agent  -->  Implementation  -->  Results
```

## Why RO-Crate?

ASTRA is implemented as a native RO-Crate extension rather than a custom YAML format:

- **FAIR by default** — every analysis is findable, accessible, interoperable, reusable
- **Linked Data** — entities have URIs, types, and cross-references using schema.org vocabulary
- **Ecosystem interop** — Zenodo deposit, WorkflowHub, Galaxy integration work out of the box
- **Standard provenance** — `CreateAction` pattern for recipe execution provenance
- **Subcrates** — RO-Crate 1.2's nested crate support maps naturally to ASTRA's self-similar nesting

The specification file is `ro-crate-metadata.json` — a JSON-LD document with a flat `@graph` array of entities.

## The Multiverse Concept

A **universe** is one complete set of decisions — a single path through the decision space that fully specifies an analysis.

The **multiverse** is the space of all valid decision combinations. Its purpose is **transparency and traceability**, not exhaustive search:

1. **Document the path taken**: Which decisions were made and why
2. **Document paths not taken**: What alternatives existed
3. **Enable exploration**: "What if we chose differently?"
4. **Check robustness**: Optionally run alternative universes

A well-specified analysis should produce its declared outputs with a **single universe**.

## RO-Crate Profile

### Type Mapping

ASTRA entities use schema.org supertypes for interoperability, with custom ASTRA types for domain-specific semantics:

| Entity | `@type` | Purpose |
|--------|---------|---------|
| Root analysis | `["Dataset", "ASTRAAnalysis"]` | The crate root |
| Input | `["FormalParameter", "ASTRAInput"]` | Data or analysis reference |
| Output | `["FormalParameter", "ASTRAOutput"]` | Declared output |
| Recipe | `["CreateAction", "ASTRARecipe"]` | Build rule for an output |
| Decision | `["DefinedTermSet", "ASTRADecision"]` | Choice point |
| Option | `["DefinedTerm", "ASTRAOption"]` | One selectable choice |
| Insight | `["Claim", "ASTRAInsight"]` | Scientific claim with evidence |
| Evidence | `ASTRAEvidence` | Pointer to evidence source with selectors |
| Universe | `ASTRAUniverse` | Complete set of decision selections |
| Selection | `ASTRAUniverseSelection` | One decision=option binding |
| Resources | `ASTRAResources` | Compute requirements (cpus, memory, gpus) |
| Success criterion | `ASTRASuccessCriterion` | Testable success condition |

### Property Mapping

Standard schema.org properties are reused wherever possible:

| Concept | Property | Source |
|---------|----------|--------|
| Entity name | `name` | schema.org |
| Description / rationale | `description` | schema.org |
| Human label | `alternateName` | schema.org |
| Data source | `identifier` | schema.org |
| Analysis reference | `isBasedOn` | schema.org |
| Claim text | `text` | schema.org (on Claim) |
| Recipe command | `description` | schema.org (on CreateAction) |
| Recipe inputs | `object` | schema.org (on CreateAction) |
| Recipe result | `result` | schema.org (on CreateAction) |
| Tags | `keywords` | schema.org |
| Timestamp | `dateCreated` | schema.org |
| Version | `version` | schema.org |

Custom ASTRA properties for concepts with no standard equivalent:
`activeWhen`, `delegatesTo`, `incompatibleWith`, `requiresOption`, `hasDecision`, `hasOption`, `defaultOption`, `selectsDecision`, `selectsOption`, `outputType`, `inputType`, `inputFrom`, `outputFrom`, `isExcluded`, `excludedReason`, `supportsInsight`, `isDerived`, `scope`, `sourceCommit`, `hasEvidence`, `hasResources`, `condition`.

### Entity ID Convention

```
#decision/{name}                    — Decision
#decision/{dec}/option/{opt}        — Option
#input/{name}                       — Input
#output/{name}                      — Output
#output/{name}/recipe               — Recipe
#insight/{name}                     — Insight
#insight/{name}/evidence/{ev}       — Evidence
#universe/{name}                    — Universe
#universe/{name}/sel/{i}            — Universe selection
```

For subcrate references: `subcrate_name/#decision/method`

## Core Components

### 1. Inputs

What the analysis has to work with:

| Input Type | Description | Key Property |
|------------|-------------|-------------|
| `data` | Raw data | `identifier` (source path/URI) |
| `analysis` | Previous analysis | `isBasedOn` (analysis ref) |

Sub-analysis inputs use `inputFrom` to reference parent inputs (`"iris_data"`) or sibling outputs (`"feature_extraction.features"`).

### 2. Outputs

What the analysis should produce (declared upfront):

| Output Type | Description |
|-------------|-------------|
| `metric` | Numeric/categorical value (accuracy, p-value) |
| `figure` | Visualization (confusion matrix, ROC curve) |
| `table` | Structured tabular data |
| `data` | Processed data files |
| `report` | Text/document synthesis |

Outputs can have:
- **Recipe**: A `["CreateAction", "ASTRARecipe"]` build rule with command and dependencies
- **Conditional activation**: `activeWhen` condition (e.g., `"model.svm"`)
- **Provenance**: `outputFrom` for outputs sourced from sub-analyses

### 3. Decisions

Decisions are `["DefinedTermSet", "ASTRADecision"]` entities with options:

- **name**: Identifier
- **alternateName**: Human-readable label
- **description**: Rationale for this decision
- **defaultOption**: Reference to the default `ASTRAOption`
- **hasOption**: References to all `ASTRAOption` entities
- **activeWhen**: Conditional activation (`"decision.option"` format)

Options are `["DefinedTerm", "ASTRAOption"]` with:
- **incompatibleWith**: `@id` refs to options that cannot coexist
- **requiresOption**: `@id` refs to options that must be co-selected
- **supportsInsight**: `@id` refs to insights supporting this choice
- **isExcluded** / **excludedReason**: Option considered but rejected

**Delegated decisions**: Sub-analyses can delegate to parent decisions via `delegatesTo` — they inherit the parent's selection without appearing in the universe.

### 4. Constraints

Options reference other options via `@id`:

```json
{
  "@id": "#decision/scaling/option/minmax",
  "@type": ["DefinedTerm", "ASTRAOption"],
  "incompatibleWith": [{"@id": "#decision/model/option/svm"}]
}
```

Constraints are validated when creating universes. Invalid combinations are rejected.

### 5. Recipes

Recipes use the Process Run Crate pattern — `CreateAction` entities:

```json
{
  "@id": "#output/accuracy/recipe",
  "@type": ["CreateAction", "ASTRARecipe"],
  "description": "python src/evaluate.py",
  "object": [{"@id": "#output/trained_model"}],
  "result": {"@id": "#output/accuracy"}
}
```

- `description`: The command to execute
- `object`: Input dependencies (other output entities)
- `result`: The output this recipe produces
- `containerImage`: Optional container image
- `hasResources`: Optional compute requirements

### 6. Insights and Evidence

Insights (`["Claim", "ASTRAInsight"]`) represent scientific knowledge:

- **Prior insights** (`hasPriorInsight`): Knowledge informing decisions
- **Findings** (`hasFinding`): Conclusions from analysis outputs

Each insight has `text` (the claim) and `hasEvidence` references to evidence entities.

Evidence entities (`ASTRAEvidence`) point to sources with W3C selectors:
- **Literature**: `identifier` (DOI) + quote/figure/table selectors
- **Artifact**: `isBasedOn` (output ref) + optional checksum/snapshot

Selectors follow W3C Web Annotation standards: `TextQuoteSelector`, `FigureSelector`, `TableSelector`, `FragmentSelector`.

### 7. Universes

Universes are flat entities in the root crate (Option A design):

```json
{
  "@id": "#universe/baseline",
  "@type": "ASTRAUniverse",
  "hasSelection": [
    {"@id": "#universe/baseline/sel/0"},
    {"@id": "#universe/baseline/sel/1"}
  ]
}
```

Each selection binds a decision to an option:
```json
{
  "@id": "#universe/baseline/sel/0",
  "@type": "ASTRAUniverseSelection",
  "selectsDecision": {"@id": "#decision/scaling"},
  "selectsOption": {"@id": "#decision/scaling/option/standard"}
}
```

Cross-crate selections use path prefixes:
```json
{
  "selectsDecision": {"@id": "feature_extraction/#decision/method"},
  "selectsOption": {"@id": "feature_extraction/#decision/method/option/pca"}
}
```

Delegated decisions are excluded from universes (they inherit from the parent).

### 8. Self-Similar Nesting

Sub-analyses are **subcrate directories** — each with its own `ro-crate-metadata.json`:

```
my-pipeline/
├── ro-crate-metadata.json          # Root decisions + universes
├── feature_extraction/
│   └── ro-crate-metadata.json      # Sub-analysis (standalone crate)
└── classification/
    └── ro-crate-metadata.json      # Sub-analysis (standalone crate)
```

Each subcrate is a valid ASTRA crate that can be extracted and used independently.

Sub-analysis inputs wire to parent inputs via `inputFrom: "parent_input_id"` or sibling outputs via `inputFrom: "sibling.output_id"`.

## Validation

### Semantic Validation

Checks performed by `validate_analysis()`:

| Check | Error Code |
|-------|------------|
| ID pattern (`^[a-z][a-z0-9_]*$`) | `INVALID_ID` |
| Duplicate input/output IDs | `DUPLICATE_INPUT`, `DUPLICATE_OUTPUT` |
| Default option exists in options | `INVALID_DEFAULT` |
| Default option not excluded | `EXCLUDED_DEFAULT` |
| Excluded option has reason | `EXCLUDED_NO_REASON` |
| Orphan excluded_reason | `ORPHAN_EXCLUDED_REASON` |
| Constraint refs valid | `INVALID_CONSTRAINT_REF` |
| Insight refs valid | `INVALID_INSIGHT_REF` |
| Output type valid | `INVALID_OUTPUT_TYPE` |
| Input type valid | `INVALID_INPUT_TYPE` |
| Recipe deps valid | `INVALID_RECIPE_INPUT` |
| No recipe cycles | `RECIPE_CYCLE` |
| Evidence has source | `EVIDENCE_SOURCE` |
| Literature evidence has selector | `MISSING_SELECTOR` |
| Insight has evidence | `MISSING_EVIDENCE` |
| Artifact refs valid | `INVALID_ARTIFACT_REF` |
| Criterion output valid | `INVALID_CRITERION_OUTPUT` |
| Condition requires output | `CONDITION_WITHOUT_OUTPUT` |
| Delegated decision exclusivity | `DELEGATED_WITH_LOCAL_FIELDS` |
| ActiveWhen format | `INVALID_WHEN_FORMAT` |

### Universe Validation

Checks performed by `validate_universe()`:

| Check | Error Code |
|-------|------------|
| All decisions have selections | `MISSING_DECISION` |
| Selected option exists | `INVALID_OPTION` |
| Excluded option not selected | `EXCLUDED_OPTION` |
| Incompatible options not co-selected | `INCOMPATIBLE_OPTIONS` |
| Required options co-selected | `MISSING_REQUIRED_OPTION` |

### Evidence Verification

Optional PDF-based verification:
1. Download paper by DOI (arXiv or Unpaywall)
2. Extract text from PDF
3. Fuzzy match quotes using RapidFuzz
4. Cache results by PDF hash

## Python SDK

### ASTRACrate

The primary API wraps `rocrate.ROCrate`:

```python
from astra import ASTRACrate

crate = ASTRACrate("Analysis Name", version="1.0")
crate.add_input(name, type, source=..., input_from=...)
crate.add_output(name, type, recipe_command=..., recipe_inputs=[...])
crate.add_decision(name, label, options={...}, default=..., rationale=...)
crate.add_delegated_decision(name, delegates_to=...)
crate.add_insight(name, claim, evidence_list=[...], is_finding=False)
crate.add_success_criterion(claim, output=..., condition=...)
crate.add_subcrate(name, analysis_name=...)
crate.add_universe(name, selections={...})
crate.generate_default_universe(name)
crate.write(path)

# Query
crate = ASTRACrate.load(path)
crate.get_inputs() / get_outputs() / get_decisions() / get_options(dec)
crate.get_universes() / get_universe_selections(name)
crate.get_prior_insights() / get_findings()
crate.get_subcrates() / get_subcrate(name)
crate.walk_local_decisions()  # yields (prefixed_id, entity) across tree
ASTRACrate.is_condition_met(when, universe_decisions)
```
