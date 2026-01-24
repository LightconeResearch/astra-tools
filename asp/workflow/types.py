"""Simple types for workflow integration.

These are local to the asp package - no dependency on models/.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
