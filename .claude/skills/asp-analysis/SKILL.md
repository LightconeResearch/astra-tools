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
├── universes/            # Decision selections
│   ├── baseline.yaml     # Default configuration
│   └── experiment1.yaml  # Alternative configuration
├── insights/             # Optional: separate insight files
│   └── scaling.yaml      # Insights on a specific topic
└── results/              # Execution outputs (gitignored)
```

## Tips

1. **Start with the problem**: Write a clear problem statement before defining decisions
2. **One insight per finding**: Don't combine multiple findings in one insight
3. **Precise evidence**: Include page numbers, figure labels, exact quotes
4. **Link insights to decisions**: Every decision option should ideally have supporting evidence
5. **Use scope**: Clarify when an insight applies (dataset, model type, conditions)

---

## Design Mode

When the user runs `asp init`, you enter **design mode**. Your job is to guide them through creating a complete analysis specification interactively.

### Design Conversation Flow

1. **Understand the Problem**
   - "What research question are you trying to answer?"
   - "What would success look like?"
   - "What's the scientific context?"

2. **Identify Inputs**
   - "What data do you have to work with?"
   - "Are there any papers or prior analyses that inform this work?"
   - "What format is the data in?"

3. **Define Outputs**
   - "What specific results do you need to produce?"
   - "What's the primary metric you'll use to answer your question?"
   - "Do you need figures, tables, or a written report?"

4. **Map Decisions**
   - "What methodological choices do you need to make?"
   - "For each choice, what are the reasonable options?"
   - "Are any options incompatible with others?"
   - "Why might you choose one option over another?"

5. **Finalize**
   - Write the complete `asp.yaml`
   - Validate with `asp validate asp.yaml`
   - Show summary with `asp info`
   - Create `universes/baseline.yaml` with default selections

### Progressive Writing

Don't wait until the end - write `asp.yaml` incrementally:
- After discussing the problem: write `analysis.problem`
- After identifying inputs: write `analysis.inputs`
- After defining outputs: write `analysis.outputs`
- After mapping decisions: write `decisions` section
- Validate frequently to catch issues early

### Example Design Session

```
User: I want to analyze the iris dataset

Claude: Great! Let me help you design this analysis. What specific question
are you trying to answer about the iris dataset? For example:
- Classification accuracy comparison?
- Feature importance analysis?
- Clustering evaluation?

User: I want to compare different classification methods

Claude: Perfect. Let me start building your spec...
[Writes initial asp.yaml with problem statement]

Now, what classification methods do you want to compare?

User: Random forest, SVM, and logistic regression

Claude: Good choices. Should I add any preprocessing decisions too,
like feature scaling? SVM typically needs scaled features...
[Continues building spec interactively]
```

---

## Execution Mode

When the user runs `asp run universes/<name>.yaml`, you enter **execution mode**. Your job is to implement and execute the analysis specification.

### Execution Flow

1. **Read Context**
   - Read `asp.yaml` completely - understand the problem, inputs, outputs
   - Read the specified universe file - get the selected decisions
   - Note the execution ID from the prompt

2. **Plan Implementation**
   - For each declared output, determine what code produces it
   - Identify which decisions affect which outputs
   - Plan the script structure in `scripts/`

3. **Clarify if Needed**
   - If the spec is ambiguous, ASK the user
   - Don't guess - the spec should be clear
   - Common questions: data format details, evaluation criteria, edge cases

4. **Implement**
   - Write scripts to `scripts/` directory
   - Follow the decisions from the universe exactly
   - Produce ALL declared outputs

5. **Execute**
   - Run the scripts
   - Save outputs to `results/<execution_id>/`
   - Capture all metrics

6. **Verify**
   - Check all declared outputs exist
   - Verify metrics are within declared ranges (if specified)
   - Verify artifact formats match spec (png, csv, etc.)

7. **Record**
   - Update `executions/<id>.yaml` with results
   - Set status to "completed" (or "failed" with error message)
   - Record all metric values and artifact paths

### Example Execution Session

```
# User ran: asp run universes/baseline.yaml
# Execution ID: baseline_20250120_143052

Claude: I'll execute this analysis. Let me read the spec first...
[Reads asp.yaml and universes/baseline.yaml]

The analysis specifies:
- Inputs: iris dataset from sklearn
- Outputs: accuracy (metric), confusion_matrix (figure), conclusion (report)
- Decisions: scaling=standard, model=random_forest, test_size=0.2, seed=42

I'll implement this now...
[Writes scripts/run_analysis.py]
[Executes the script]
[Saves outputs to results/baseline_20250120_143052/]
[Updates executions/baseline_20250120_143052.yaml with results]

Execution complete! Results:
- accuracy: 0.967
- confusion_matrix: results/baseline_20250120_143052/confusion_matrix.png
- conclusion: results/baseline_20250120_143052/conclusion.md
```

### Key Principles for Execution

1. **Follow the spec exactly** - The decisions in the universe are your instructions
2. **Ask don't guess** - If something is unclear, ask the user
3. **Produce all outputs** - Every declared output must be created
4. **Verify your work** - Check outputs match the spec before marking complete
5. **Record everything** - Update the execution record with all results
