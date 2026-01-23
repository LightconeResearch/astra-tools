"""Claude Code agent wrapper for ASP."""

from __future__ import annotations

from pathlib import Path

from asp.agents.registry import AgentConfig, register_agent
from asp.templates.core import (
    ASP_AGENT_INSTRUCTIONS,
    INIT_PROMPT_CONTENT,
    SCHEMA_REFERENCE,
    SKILL_CONTENT,
)


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

    # Write combined ASP agent
    (agents_dir / "asp.md").write_text(ASP_AGENT_INSTRUCTIONS)


def get_claude_init_prompt() -> str:
    """Return the initial prompt for Claude Code, with Claude-specific paths."""
    return INIT_PROMPT_CONTENT.replace(
        "the ASP agent instructions",
        "the ASP agent at `.claude/agents/asp.md`",
    ).strip()


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
