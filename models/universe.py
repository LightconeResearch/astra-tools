"""Pydantic models for ASTRA universe specifications."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from models.analysis import Analysis


class UniverseNode(BaseModel):
    """A universe node mirroring the analysis tree structure.

    A universe node can either contain inline decisions or reference
    an external sub-analysis universe by name via ``universe``.
    When ``universe`` is set, it points to a universe file in the
    sub-analysis's ``universes/`` directory (e.g., ``universe: baseline``
    loads ``<sub_analysis_path>/universes/baseline.yaml``).
    """

    model_config = ConfigDict(extra="forbid")

    universe: str | None = Field(
        default=None,
        description="Name of a universe in the sub-analysis's universes/ directory. "
        "Alternative to inline decisions.",
    )
    decisions: dict[str, str] = Field(
        default_factory=dict,
        description="Map of decision ID to selected option ID",
    )
    analyses: dict[str, UniverseNode] | None = Field(
        default=None,
        description="Map of sub-analysis IDs to their universe selections",
    )


# Required for Pydantic self-referencing models
UniverseNode.model_rebuild()


class Universe(BaseModel):
    """A universe specification - a complete set of decisions across the analysis tree."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "https://astra-spec.org/v1/universe.schema.json",
            "title": "ASTRA Universe Specification",
        },
    )

    schema_: str | None = Field(default=None, alias="$schema", description="JSON Schema reference")
    id: str = Field(
        pattern=r"^[a-z][a-z0-9_-]*$",
        description="Unique identifier for the universe",
    )
    description: str | None = Field(default=None, description="What this universe represents")
    decisions: dict[str, str] = Field(
        default_factory=dict,
        description="Map of decision ID to selected option ID (root-level decisions)",
    )
    analyses: dict[str, UniverseNode] | None = Field(
        default=None,
        description="Map of sub-analysis IDs to their universe selections",
    )

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

        defaults = analysis.get_default_universe()

        return cls(
            id=universe_id,
            description=description or "Default configuration using standard practices",
            decisions=defaults.get("decisions", {}),
            analyses=cls._build_node_from_defaults(defaults.get("analyses")),
        )

    @classmethod
    def _build_node_from_defaults(
        cls, analyses_defaults: dict[str, Any] | None
    ) -> dict[str, UniverseNode] | None:
        """Recursively build UniverseNode tree from defaults dict."""
        if not analyses_defaults:
            return None
        result: dict[str, UniverseNode] = {}
        for node_id, node_defaults in analyses_defaults.items():
            result[node_id] = UniverseNode(
                decisions=node_defaults.get("decisions", {}),
                analyses=cls._build_node_from_defaults(node_defaults.get("analyses")),
            )
        return result
