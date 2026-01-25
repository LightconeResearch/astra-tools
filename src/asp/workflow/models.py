"""Data models for CWL workflow integration.

Uses dataclasses instead of Pydantic to avoid model dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParameterMapping:
    """Explicit mapping override from ASP decision to CWL parameter."""

    decision: str
    cwl_param: str
    transform: str | None = None


@dataclass
class WorkflowConfig:
    """Workflow configuration for an ASP analysis."""

    path: Path
    mappings: list[ParameterMapping] = field(default_factory=list)


@dataclass
class CWLParameter:
    """Parsed CWL input parameter."""

    name: str
    type: str
    required: bool = True
    default: Any | None = None


@dataclass
class WorkflowValidationError:
    """A workflow validation error."""

    code: str
    message: str
    decision_id: str | None = None
    cwl_param: str | None = None

    def __str__(self) -> str:
        parts = [f"[{self.code}]"]
        if self.decision_id:
            parts.append(f"decision={self.decision_id}")
        if self.cwl_param:
            parts.append(f"param={self.cwl_param}")
        parts.append(self.message)
        return " ".join(parts)
