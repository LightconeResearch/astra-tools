---
name: build
description: Build and run an ASP analysis chunk. Usage: /asp:build [chunk] — build and run a specific chunk or all chunks.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Task, WebFetch, AskUserQuestion
---

# /asp:build

Build and run an analysis chunk. Decisions have already been reviewed during `/asp:new` — just build.

`/asp:new` defines WHAT we want. `/asp:build` figures out HOW to do it and executes.

**Usage:**
- `/asp:build` — build all chunks in order
- `/asp:build <chunk>` — build a specific chunk by name

## Setup

1. Read the ASP reference guide: `.claude/skills/reference/SKILL.md`
2. Read the workflow guide: `.claude/skills/reference/workflow-guide.md`
3. Read `asp.yaml` to understand the specification
4. If `<chunk>` was given, confirm it exists in `chunks`

## Process

### Determine scope

- No argument: if there are multiple chunks, use `AskUserQuestion` to ask which chunk to work on (list chunk names as options). Work on ONE chunk at a time.
- `<chunk>` argument: work on that specific chunk

### Build

1. Generate universes if missing (`asp universe generate -n baseline`)
2. Build CWL workflows mapping inputs, decisions, and outputs
3. Implement workflow steps in `steps/` (single chunk) or `steps/<chunk_name>/` (multiple chunks)
4. Validate (`asp workflow validate --cwl workflows/main.cwl`)
5. Run (`asp workflow run universes/baseline.yaml --cwl workflows/main.cwl -o results/baseline/`)

### Chunk builds

When building a specific chunk, scope all work to that chunk's decisions. Chunk decisions appear under `chunks.<name>.decisions` in the spec and `chunks.<name>` in universe files.

## Completion

- "Chunk `<name>` built and results ready." Use the actual chunk name.
- If there are remaining chunks, suggest: "Run `/asp:build <next_chunk>` to continue."
- If all chunks are done: "All chunks built. The analysis is complete."
