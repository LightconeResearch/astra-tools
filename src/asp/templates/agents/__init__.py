"""Agent templates for ASP."""

import asp.templates.agents.claude_code  # noqa: F401  # Registers claude-code agent
from asp.templates.core import ASP_AGENT_INSTRUCTIONS as ASP_AGENT

__all__ = ["ASP_AGENT"]
