"""Core ASP templates - tool-agnostic instructions."""

from asp.templates.core.design import DESIGN_INSTRUCTIONS
from asp.templates.core.experiment import EXPERIMENT_INSTRUCTIONS
from asp.templates.core.schema_reference import SCHEMA_REFERENCE
from asp.templates.core.skill import (
    INIT_PROMPT_CONTENT,
    SKILL_CREATING_ANALYSIS,
    SKILL_EXTRACTING_INSIGHTS,
    SKILL_QUICK_REFERENCE,
    SKILL_WORKFLOW_EXECUTION,
)

__all__ = [
    "DESIGN_INSTRUCTIONS",
    "EXPERIMENT_INSTRUCTIONS",
    "INIT_PROMPT_CONTENT",
    "SCHEMA_REFERENCE",
    "SKILL_CREATING_ANALYSIS",
    "SKILL_EXTRACTING_INSIGHTS",
    "SKILL_QUICK_REFERENCE",
    "SKILL_WORKFLOW_EXECUTION",
]
