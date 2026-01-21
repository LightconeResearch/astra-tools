"""Templates for ASP project scaffolding."""

from asp.templates.agents import DESIGN_AGENT, EXPERIMENT_AGENT
from asp.templates.agents.claude_code import SKILL_CONTENT
from asp.templates.core import SCHEMA_REFERENCE as SCHEMA_REFERENCE_CONTENT

__all__ = ["DESIGN_AGENT", "EXPERIMENT_AGENT", "SCHEMA_REFERENCE_CONTENT", "SKILL_CONTENT"]
