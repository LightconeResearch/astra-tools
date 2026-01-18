"""Pydantic models for CWL workflow integration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ParameterMapping(BaseModel):
    """Explicit mapping override from ASP decision to CWL parameter."""

    model_config = ConfigDict(extra="forbid")

    decision: str = Field(description="ASP decision reference")
    cwl_param: str = Field(description="CWL parameter name")
    transform: str | None = Field(default=None, description="Optional transform expression")


class WorkflowConfig(BaseModel):
    """Workflow configuration for an ASP analysis."""

    model_config = ConfigDict(extra="forbid")

    path: Path = Field(description="Path to CWL workflow file")
    mappings: list[ParameterMapping] = Field(default_factory=list)


class CWLParameter(BaseModel):
    """Parsed CWL input parameter."""

    model_config = ConfigDict(extra="forbid")

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
