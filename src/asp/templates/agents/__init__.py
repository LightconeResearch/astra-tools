"""Agent templates for ASP."""

import asp.templates.agents.claude_code  # noqa: F401  # Registers claude-code agent
from asp.templates.core import DESIGN_INSTRUCTIONS as DESIGN_AGENT
from asp.templates.core import EXPERIMENT_INSTRUCTIONS as EXPERIMENT_AGENT

__all__ = ["DESIGN_AGENT", "EXPERIMENT_AGENT"]
