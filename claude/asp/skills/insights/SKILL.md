---
name: insights
description: Extract insights from scientific papers and add evidence to ASP analyses. Use when user provides a paper (PDF, DOI, arXiv link) or asks about adding literature support to decisions.
allowed-tools: Read, Edit(asp.yaml), Glob, Grep, Bash(asp validate:*), Bash(asp verify:*), WebFetch, WebSearch, AskUserQuestion
---

# /asp:insights

Extract insights from scientific papers and add evidence to ASP analysis decisions.

## Setup

1. Read `.claude/skills/reference/SKILL.md` for ASP concepts
2. Read `asp.yaml` to understand the analysis and decisions
3. Identify decisions that need literature support

## Finding Relevant Papers

Before extracting insights, identify papers relevant to your analysis decisions.

### Search Strategy

1. **Start with the decision**: What methodological choice needs evidence?
   - Example: "Which normalization method?" → search for normalization comparisons

2. **Search databases**:
   - **Google Scholar**: Broad coverage, good for citations
   - **Semantic Scholar**: AI-focused, good recommendations
   - **arXiv**: Preprints, ML/AI, physics, math (preferred for verification)
   - **PubMed**: Biomedical and life sciences

3. **Search terms**:
   - Include your data type: "normalization methods tabular data"
   - Include comparison keywords: "comparison", "benchmark", "evaluation"
   - Include your domain: "normalization genomics"

### Prioritization

Review papers in this order:
1. **Systematic reviews/meta-analyses**: Synthesize multiple studies
2. **Benchmark papers**: Direct comparisons on standard datasets
3. **Methodological papers**: Introduce and validate specific methods
4. **Application papers**: Use methods in similar contexts

### When to Stop

Stop searching when:
- You find a systematic review covering your decision
- Multiple independent sources agree
- You have evidence for all decision options
- Marginal papers aren't adding new information

### Handling Conflicts

When papers disagree:
- Note both findings as separate insights
- Document the scope/conditions where each applies
- Let the multiverse analysis explore both options

## Extracting Insights

### Step 1: Identify the Paper

Get the paper identifier:
- **arXiv**: ID with version (e.g., `1706.03762` version `7`)
- **DOI**: Format `10.XXXX/...` (e.g., `10.1038/s41586-023-06221-2`)

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
    id: insight_id  # Must match the key
    claim: "One sentence stating what we learned"
    created_at: "2024-01-15T10:30:00Z"  # ISO 8601 timestamp
    sources:
      - id: paper1
        type: arxiv
        arxiv_id: "1706.03762"
        version: 7
    evidence:
      # For quotes (preferred - verifiable):
      - id: ev1
        source_ref: paper1
        quote:
          exact: "Exact text from the paper (1-3 sentences)"
          prefix: "~20-100 chars before for disambiguation"  # optional
          suffix: "~20-100 chars after for disambiguation"   # optional
        location:
          page: 5  # 1-indexed page number
      # For figures:
      - id: ev2
        source_ref: paper1
        figure:
          label: "Figure 3a"
          caption: "Description of what it shows"  # optional
        location:
          page: 8
      # For tables:
      - id: ev3
        source_ref: paper1
        table:
          label: "Table 1"
          caption: "Table header text"  # optional
          region: "row 3, accuracy column"  # optional
        location:
          page: 12
    scope: "Context where this applies (optional)"
```

### Step 4: Link to Decisions

Reference insights in decision options:

```yaml
chunks:
  main:
    decisions:
      method_choice:
        options:
          method_a:
            label: "Method A"
            evidence:
              - insight: insight_id  # Reference the insight
```

### Step 5: Validate and Verify

```bash
asp validate asp.yaml   # Check structure
asp verify asp.yaml     # Verify quotes exist in PDFs
```

## Schema Reference

### Insight Sources

#### arXiv Papers (verifiable)

arXiv sources include version for reproducibility:

```yaml
sources:
  - id: attention_paper
    type: arxiv
    arxiv_id: "1706.03762"
    version: 7
    title: "Attention Is All You Need"  # optional
```

**Required fields:**
- `id`: Local identifier for evidence references
- `type`: Must be `arxiv`
- `arxiv_id`: Pattern `^\d{4}\.\d{4,5}$` (e.g., "1706.03762")
- `version`: Integer >= 1

#### DOI Papers

For published papers not on arXiv:

```yaml
sources:
  - id: nature_paper
    type: doi
    doi: "10.1038/s41586-023-06221-2"
    title: "Paper Title"  # optional
```

**Required fields:**
- `id`: Local identifier for evidence references
- `type`: Must be `doi`
- `doi`: Pattern `^10\.\d{4,}/.*$`

### Evidence Types

Each piece of evidence must have:
- `id`: Unique identifier within the insight
- `source_ref`: References a source's `id`
- At least one content selector: `quote`, `figure`, or `table`
- Optional `location` with page number

#### Quotes (Verifiable)

Best for verification — ASP can check that the exact text exists in the PDF:

```yaml
evidence:
  - id: scaling_quote
    source_ref: paper1
    quote:
      exact: "We found that layer normalization significantly improves training stability"
      prefix: "In our experiments, "  # optional, helps disambiguation
      suffix: " compared to batch normalization."  # optional
    location:
      page: 6
```

#### Figures

Reference figures by their label:

```yaml
evidence:
  - id: perf_figure
    source_ref: paper1
    figure:
      label: "Figure 2b"
      caption: "Comparison of model performance across datasets"  # optional
    location:
      page: 8
```

#### Tables

Reference tables with optional region specification:

```yaml
evidence:
  - id: results_table
    source_ref: paper1
    table:
      label: "Table 3"
      caption: "Performance comparison"  # optional
      region: "BLEU column, Transformer row"  # optional
    location:
      page: 10
```

## Verification

After adding insights, verify that evidence actually exists in source documents:

```bash
asp verify asp.yaml                    # Verify all insights
asp verify --insight scaling_paper     # Verify specific insight
asp verify --cache-dir ~/.asp/pdfs     # Use custom PDF cache
```

This downloads PDFs (arXiv sources only) and checks that quoted text exists.

### Verification Status

| Status | Meaning |
|--------|---------|
| `verified` | Evidence found at expected location |
| `wrong_page` | Evidence found but on different page |
| `not_found` | Evidence not found in document |
| `skipped` | Cannot verify (DOI source, figure/table) |
| `error` | Error during verification (download failed, etc.) |

### Fixing Issues

- **wrong_page**: Update `location.page` in your evidence to the correct page
- **not_found**:
  - Check quote for typos or OCR differences
  - Add `prefix`/`suffix` for disambiguation
  - Verify the arXiv version matches what you're quoting from
- **skipped**: Expected for DOI sources (no automated PDF access) and figure/table evidence

## Tips

1. **One insight per finding**: Don't combine multiple findings in one insight
2. **Prefer quotes over figures/tables**: Quotes are verifiable
3. **Include page numbers**: Helps verification and human review
4. **Use scope**: Clarify when an insight applies (dataset, model type, conditions)
5. **Link insights to decisions**: Every decision option should ideally have supporting evidence
6. **Match arXiv version**: Ensure the version matches the PDF you're quoting from
