"""ASP Analysis skill template for Claude Code."""

SKILL_CONTENT = """\
---
name: asp-analysis
description: >-
  Work with ASP (Agentic Science Protocol) analyses. Use when creating new analyses,
  extracting insights from papers, validating specifications, or managing universes.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(asp:*), Bash(python:*)
---

# ASP Analysis Skill

Help users work with the Agentic Science Protocol (ASP) - a declarative specification
format for scientific analyses.

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

See `SCHEMA_REFERENCE.md` for detailed field documentation.

## Creating a New Analysis

1. Run `asp init my-analysis` to scaffold the project
2. Edit `asp.yaml` to define inputs, outputs, and decisions
3. Add insights from relevant papers to support decisions
4. Validate with `asp validate asp.yaml`

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

## File Structure

```
my-analysis/
├── asp.yaml              # Analysis specification
├── universes/            # Decision selections
│   └── baseline.yaml
├── scripts/              # Implementation scripts
├── results/              # Outputs (gitignored)
└── .claude/
    ├── skills/asp-analysis/
    └── agents/
        ├── design.md     # Design agent
        └── experiment.md # Experiment agent
```

## Available Agents

- **design** - Interactive analysis design partner. Use when creating `asp.yaml`.
- **experiment** - Execution engine. Use when running an analysis.

Invoke with: `/agents/design` or `/agents/experiment`
"""
