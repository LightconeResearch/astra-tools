"""JSON Schema generation from Pydantic models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from asp.models.analysis import Analysis
from asp.models.universe import Universe


def get_analysis_schema() -> dict[str, Any]:
    """Get the JSON Schema for analysis specifications."""
    return Analysis.model_json_schema(mode="serialization")


def get_universe_schema() -> dict[str, Any]:
    """Get the JSON Schema for universe specifications."""
    return Universe.model_json_schema(mode="serialization")


def export_schemas(output_dir: str | Path) -> None:
    """Export JSON schemas to files.

    Args:
        output_dir: Directory to write schema files to.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Export analysis schema
    analysis_schema = get_analysis_schema()
    with open(output_dir / "analysis.schema.json", "w") as f:
        json.dump(analysis_schema, f, indent=2)

    # Export universe schema
    universe_schema = get_universe_schema()
    with open(output_dir / "universe.schema.json", "w") as f:
        json.dump(universe_schema, f, indent=2)
