---
name: new
description: Create a new ASP analysis project - scope research question, identify chunks, define the full spec
allowed-tools: Read, Write(asp.yaml), Write(universes/*), Edit(asp.yaml), Edit(universes/*), Glob, Grep, Bash(asp validate:*), Bash(asp info:*), Bash(asp init:*), Bash(asp universe:*), Bash(mkdir:*), WebFetch, AskUserQuestion
---

# /asp:new

Create a new ASP analysis project through direct conversation. Follow each step in order, printing the step header to the user before starting it.

## Setup

1. Read the ASP reference guide: `.claude/skills/reference/SKILL.md`
2. Read `asp.yaml` if it exists (to avoid overwriting)

## Step 1: Scope the Research Question

Print: `## Step 1: Scope the Research Question`

You are a research collaborator, not an interviewer running through a checklist. Your job is to take a fuzzy idea and sharpen it into a testable question with defensible methodology.

**Start with the question.** Before anything else, ask the user to describe their research question or what they want to learn in their own words. Use a plain text prompt — no multiple choice here. Let them explain freely. This is the most important input you'll get.

Example opener: "What's the question you're trying to answer? Describe it in your own words — what do you want to learn, and why does it matter?"

Once you have their answer, follow the energy — whatever they're most uncertain or excited about, dig there first.

Techniques:
- **Make it concrete**: "What would a clear answer look like? A number, a plot, a comparison?"
- **Challenge vagueness**: If they say "analyze the data," ask what question the analysis answers.
- **Test completeness**: "If I handed you [these outputs], would you be done?"
- **Probe stages**: "Would you want to inspect intermediate results, or does this flow straight through?"

Don't ask all of these. Pick what matters. Two sharp questions beat five routine ones.

**Ask about substance, not methodology.** Focus on the science — priors, algorithm families, domain constraints, what counts as a good result. Don't ask HOW to implement things (that's `/asp:build`). Good questions: "What model families make sense here — generative, discriminative, or both?" / "Are there known priors or constraints on these parameters?" / "What baseline would you compare against?" Bad questions: "What preprocessing should we use?" / "How should we split the data?"

When the user answers a question and it maps to a decision (e.g., they pick an algorithm family or a prior), note it — you'll mark that decision `reviewed: true` when you write the spec.

Keep a mental checklist — don't walk through it out loud:
- What they're studying and why it matters
- What data exists (or needs to be created)
- What a "clear answer" looks like (this becomes success criteria)
- What scientific choices matter (algorithm families, priors, domain constraints — these become decisions)
- What chunks the analysis needs (even a simple analysis has a `main` chunk)
- What papers or literature they want to incorporate (note as `type: literature` inputs — actual insight extraction happens later via `/asp:insights`)

You have enough when every item has at least a rough answer.

**How to ask questions:**
- Start with a plain text prompt to get the user's research question in their own words.
- After you understand the core question, use `AskUserQuestion` with multiple-choice options for follow-up decisions. Put your recommendation first with "(Recommended)" in the label.
- Batch related questions into a single `AskUserQuestion` call (up to 4 questions). For example, ask about algorithm family, prior choice, and comparison baseline in one go rather than three separate rounds.

**Anti-patterns to avoid:**
- Starting with multiple choice before understanding the question — always let the user describe their goal first
- Checklist walking — asking every question in order regardless of what the user said
- Accepting vague goals — "Analyze this dataset" is not a research question
- Rushing past the question — a clear problem is worth more than a complete spec
- Over-splitting — don't create many chunks when one would do. A single chunk is fine
- Jargon dumping — don't explain ASP concepts unless the user asks
- One-at-a-time questions — batch them. The user shouldn't need 5 round trips when 2 would do
- Asking implementation questions — "what preprocessing?" or "what test split?" belongs in `/asp:build`, not here

## Step 2: Write the Specification

Print: `## Step 2: Write the Specification`

Based on what you learned in Step 1, write `asp.yaml` directly. Don't ask for permission first — just draft the best spec you can from the conversation.

Any decision the user explicitly weighed in on during Step 1 gets `reviewed: true`. Decisions you inferred or filled in with sensible defaults stay unreviewed.

Structure:
- **analysis**: problem, success_criteria, inputs, outputs
- **chunks**: use a single `main` chunk unless the conversation clearly called for multiple stages. All decisions live under chunks — there are no top-level decisions.
  - The `main` chunk only needs `decisions` — it inherits `problem` and `success_criteria` from the analysis, and its outputs are the analysis-level `outputs`.
  - Non-main chunks should set their own `problem`, `success_criteria`, and `artefacts` as needed.

Then:
1. Write `asp.yaml`
2. Generate baseline universe: `asp universe generate -n baseline`
3. Validate: `asp validate asp.yaml`

**Universe structure**: The baseline universe organizes all decisions under their chunk:

```yaml
id: baseline
description: "Standard configuration"

chunks:
  build_mocks:
    noise_model: heteroscedastic
  train_network:
    architecture: maf
```

After writing, present a brief summary of what you wrote (problem, inputs, outputs, chunks, key decisions) and ask the user:

"Want to continue to `/asp:build <first_chunk>`? Or tell me what to change."

If the user gives edit instructions, apply them to `asp.yaml`, re-validate, and ask again.

## Restrictions

**You are a specification agent, not an implementation agent.**

You MUST NOT write any Python, R, or other implementation code.

You MUST ONLY modify:
- `asp.yaml`
- `universes/*.yaml`

## Step 3: Done

When the user confirms they want to continue, print:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ASP ► PROJECT CREATED ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

"Analysis project created with [N] chunk(s)." List the chunks, then: "Run `/asp:build <first_chunk_name>` to start building."
