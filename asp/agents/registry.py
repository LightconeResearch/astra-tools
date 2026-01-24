"""Agent registry for AI coding tools."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AgentConfig:
    """Configuration for an AI coding tool."""

    name: str  # e.g., "claude-code"
    display_name: str  # e.g., "Claude Code"
    config_dir: str  # e.g., ".claude"
    launch_command: list[str] | None  # e.g., ["claude"]
    create_files: Callable[[Path], None]  # Function to create tool-specific files
    get_init_prompt: Callable[[], str]  # Function to generate initial prompt


AGENT_REGISTRY: dict[str, AgentConfig] = {}


def register_agent(config: AgentConfig) -> None:
    """Register an agent configuration."""
    AGENT_REGISTRY[config.name] = config


def get_agent(name: str) -> AgentConfig | None:
    """Get an agent configuration by name."""
    return AGENT_REGISTRY.get(name)


def list_agents() -> list[str]:
    """List all registered agent names."""
    return list(AGENT_REGISTRY.keys())
