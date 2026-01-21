"""Shared skill content for ASP - tool-agnostic."""

SKILL_QUICK_REFERENCE = """\
## Quick Reference

```bash
asp init <directory>              # Create new analysis project
asp validate asp.yaml             # Validate analysis specification
asp validate universes/foo.yaml   # Validate universe
asp info                          # Show analysis summary
asp universe generate -n baseline # Generate universe from defaults
asp viz                           # Visualize decision space
```

## Core Concepts

- **Analysis** (`asp.yaml`): Defines problem, inputs, outputs, and decisions
- **Decision**: A methodological choice with multiple options
- **Universe**: One complete set of decisions (one option per decision)
- **Insight**: Scientific knowledge from papers/analyses with precise evidence
"""

SKILL_CREATING_ANALYSIS = """\
## Creating a New Analysis

1. Run `asp init my-analysis` to scaffold the project
2. Edit `asp.yaml` to define inputs, outputs, and decisions
3. Add insights from relevant papers to support decisions
4. Validate with `asp validate asp.yaml`
"""

SKILL_EXTRACTING_INSIGHTS = """\
## Extracting Insights from Papers

When adding insights from a paper:

1. Get the DOI (format: `10.XXXX/...`)
2. For each relevant finding, create an insight:

```yaml
insights:
  finding_name:
    claim: "One sentence stating what we learned"
    source:
      doi: "10.1234/paper-doi"
    evidence:
      - figure: "Figure 3a"
        caption: "What it shows"
      # or: quote, table, equation, result
    scope: "When this applies (optional)"
```

3. Reference insights in decision options:

```yaml
decisions:
  method_choice:
    options:
      method_a:
        evidence:
          - insight: finding_name
```
"""

SKILL_WORKFLOW_EXECUTION = """\
## Workflow Execution

After design is complete, the experiment agent generates Snakemake workflows.

Execution commands:
```bash
snakemake -s workflow/Snakefile --dag | dot -Tpng > workflow/dag.png  # Generate DAG
snakemake -s workflow/Snakefile -n        # Dry run (verify)
snakemake -s workflow/Snakefile --cores 4 # Execute
```
"""

INIT_PROMPT_CONTENT = """\
You are helping create and run an ASP (Agentic Science Protocol) analysis.

## PHASE 1: Design (Interactive)

Have a conversation with the user to understand:
- What problem are they solving?
- What data do they have?
- What outputs do they need?
- What decisions (choices with multiple options) exist?

Write asp.yaml incrementally as you learn. Validate with `asp validate`.

Read the design agent instructions for detailed guidance on the design conversation.

When the spec is complete:
1. Create universes/baseline.yaml with sensible defaults
2. Tell the user: "Spec complete. Running the baseline analysis now..."

## PHASE 2-3: Execute (Autonomous)

Now work autonomously without asking the user questions:

1. Generate workflow/config.yaml from baseline universe
2. Write workflow/Snakefile with rules for each output
3. Write scripts/*.py for implementation
4. Generate DAG: snakemake -s workflow/Snakefile --dag | dot -Tpng > workflow/dag.png
5. Verify: snakemake -s workflow/Snakefile -n
6. Execute: snakemake -s workflow/Snakefile --cores 4
7. Report results to user (include the DAG visualization)

Read the experiment agent instructions for Snakemake patterns and execution details.

If something fails, fix it yourself if possible. Only ask the user
if you're truly stuck (e.g., missing data file, unclear requirement).

When done, summarize the results clearly.

---

Start by asking what problem the user is trying to solve.\
"""
