"""Pydantic models for ASP universe specifications."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from models.analysis import Analysis


class Universe(BaseModel):
    """A universe specification - a complete set of decisions."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "https://asp-spec.org/v1/universe.schema.json",
            "title": "ASP Universe Specification",
        },
    )

    schema_: str | None = Field(default=None, alias="$schema", description="JSON Schema reference")
    id: str = Field(
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Unique identifier for the universe",
    )
    description: str | None = Field(default=None, description="What this universe represents")
    decisions: dict[str, str] = Field(description="Map of decision_id to selected option_id")

    @classmethod
    def from_yaml(cls, path: str | Path) -> Universe:
        """Load a universe from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)

    def to_yaml(self, path: str | Path) -> None:
        """Save the universe to a YAML file."""
        data = self.model_dump(by_alias=True, exclude_none=True)
        with open(path, "w") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

    @classmethod
    def from_defaults(
        cls,
        analysis: Analysis,
        universe_id: str = "baseline",
        description: str | None = None,
    ) -> Universe:
        """Create a universe from the default options in an analysis."""
        from models.analysis import Analysis

        if not isinstance(analysis, Analysis):
            raise TypeError("analysis must be an Analysis instance")

        decisions = analysis.get_default_universe()
        return cls(
            id=universe_id,
            description=description or "Default configuration using standard practices",
            decisions=decisions,
        )
