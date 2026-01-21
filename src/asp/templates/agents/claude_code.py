"""Claude Code agent wrapper for ASP."""

from __future__ import annotations

from pathlib import Path

from asp.agents.registry import AgentConfig, register_agent
from asp.templates.core import (
    DESIGN_INSTRUCTIONS,
    EXPERIMENT_INSTRUCTIONS,
    INIT_PROMPT_CONTENT,
    SCHEMA_REFERENCE,
    SKILL_CREATING_ANALYSIS,
    SKILL_EXTRACTING_INSIGHTS,
    SKILL_QUICK_REFERENCE,
    SKILL_WORKFLOW_EXECUTION,
)

# Claude Code specific frontmatter
_SKILL_FRONTMATTER = """\
---
name: asp-analysis
description: >-
  Work with ASP (Agentic Science Protocol) analyses. Use when creating new analyses,
  extracting insights from papers, validating specifications, or managing universes.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(asp:*), Bash(python:*)
---
"""

# Claude Code specific file structure (includes .claude directory)
_CLAUDE_FILE_STRUCTURE = """\
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
"""

# Claude Code specific agent references
_CLAUDE_AGENTS_SECTION = """\
## Available Agents

- **design** - Interactive analysis design partner. Use when creating `asp.yaml`.
- **experiment** - Execution engine with Snakemake workflows. Use when running an analysis.

Invoke with: `/agents/design` or `/agents/experiment`
"""

# Compose the full skill content using shared + Claude-specific parts
SKILL_CONTENT = f"""{_SKILL_FRONTMATTER}
# ASP Analysis Skill

Help users work with the Agentic Science Protocol (ASP) - a declarative specification
format for scientific analyses.

{SKILL_QUICK_REFERENCE}
See `SCHEMA_REFERENCE.md` for detailed field documentation.

{SKILL_CREATING_ANALYSIS}
{SKILL_EXTRACTING_INSIGHTS}
{_CLAUDE_FILE_STRUCTURE}
{SKILL_WORKFLOW_EXECUTION}
{_CLAUDE_AGENTS_SECTION}"""


def _format_init_prompt() -> str:
    """Format the init prompt with Claude-specific file paths."""
    # Add Claude-specific file paths to the shared content
    prompt = INIT_PROMPT_CONTENT.replace(
        "Read the design agent instructions",
        "Read `.claude/agents/design.md`",
    ).replace(
        "Read the experiment agent instructions",
        "Read `.claude/agents/experiment.md`",
    )
    return prompt


# Initial prompt for Claude Code (shared content with Claude-specific paths)
CLAUDE_INIT_PROMPT = _format_init_prompt()


def create_claude_files(directory: Path) -> None:
    """Create Claude Code skill and agents in the project directory."""
    # Create skill directory
    skill_dir = directory / ".claude" / "skills" / "asp-analysis"
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Write skill files
    (skill_dir / "SKILL.md").write_text(SKILL_CONTENT)
    (skill_dir / "SCHEMA_REFERENCE.md").write_text(SCHEMA_REFERENCE)

    # Create agents directory
    agents_dir = directory / ".claude" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    # Write agent files using core instructions
    (agents_dir / "design.md").write_text(DESIGN_INSTRUCTIONS)
    (agents_dir / "experiment.md").write_text(EXPERIMENT_INSTRUCTIONS)


def get_claude_init_prompt() -> str:
    """Return the initial prompt for Claude Code."""
    return CLAUDE_INIT_PROMPT


# Register the Claude Code agent
register_agent(
    AgentConfig(
        name="claude-code",
        display_name="Claude Code",
        config_dir=".claude",
        launch_command=["claude"],
        create_files=create_claude_files,
        get_init_prompt=get_claude_init_prompt,
    )
)
