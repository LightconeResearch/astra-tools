"""Core ASP templates - loaded from markdown files."""

from pathlib import Path

_CORE_DIR = Path(__file__).parent

ASP_AGENT_INSTRUCTIONS = (_CORE_DIR / "ASP_AGENT.md").read_text()
INIT_PROMPT_CONTENT = (_CORE_DIR / "INIT_PROMPT.md").read_text()
SCHEMA_REFERENCE = (_CORE_DIR / "SCHEMA_REFERENCE.md").read_text()
SKILL_CONTENT = (_CORE_DIR / "SKILL.md").read_text()

__all__ = [
    "ASP_AGENT_INSTRUCTIONS",
    "INIT_PROMPT_CONTENT",
    "SCHEMA_REFERENCE",
    "SKILL_CONTENT",
]
