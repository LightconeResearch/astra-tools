"""JSON Schema validation for ASTRA specifications.

This module validates ASTRA YAML files against bundled JSON schemas.
Schemas are loaded from the astra.spec package (populated from spec/draft/
at build time), or directly from spec/draft/ during development.
"""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

import jsonschema

from astra.helpers import load_yaml


class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


def _find_repo_root() -> Path | None:
    """Find the repository root by looking for spec/draft/."""
    # Start from this file's location and walk up
    current = Path(__file__).resolve().parent
    for _ in range(5):  # Don't go too far up
        if (current / "spec" / "draft").is_dir():
            return current
        current = current.parent
    return None


def _load_bundled_schema(name: str) -> dict[str, Any]:
    """Load a JSON schema from bundled package or spec/draft/ in development.

    Args:
        name: Schema filename (e.g., "analysis.schema.json").

    Returns:
        The loaded JSON schema as a dict.
    """
    # Try bundled schemas first (installed package)
    try:
        schema_text = files("astra.spec").joinpath(name).read_text()
        schema: dict[str, Any] = json.loads(schema_text)
        return schema
    except (FileNotFoundError, TypeError, ModuleNotFoundError):
        pass

    # Fall back to spec/draft/ for development
    repo_root = _find_repo_root()
    if repo_root:
        schema_path = repo_root / "spec" / "draft" / name
        if schema_path.exists():
            schema = json.loads(schema_path.read_text())
            return schema

    raise FileNotFoundError(
        f"Schema {name} not found. Run 'python tools/generate_schemas.py' to generate schemas."
    )


def get_analysis_schema() -> dict[str, Any]:
    """Get the JSON Schema for analysis specifications."""
    return _load_bundled_schema("analysis.schema.json")


def get_universe_schema() -> dict[str, Any]:
    """Get the JSON Schema for universe specifications."""
    return _load_bundled_schema("universe.schema.json")


def get_insights_schema() -> dict[str, Any]:
    """Get the JSON Schema for standalone insight collections."""
    return _load_bundled_schema("insights.schema.json")


def validate_against_schema(
    data: dict[str, Any],
    schema: dict[str, Any],
) -> list[str]:
    """Validate data against a JSON schema.

    Returns a list of error messages (empty if valid).
    """
    validator = jsonschema.Draft7Validator(schema)
    errors = []

    for error in sorted(validator.iter_errors(data), key=lambda e: e.path):
        path = ".".join(str(p) for p in error.path) if error.path else "(root)"
        errors.append(f"{path}: {error.message}")

    return errors


def validate_analysis_schema(path: str | Path) -> list[str]:
    """Validate an analysis YAML file against the schema.

    Args:
        path: Path to the analysis YAML file.

    Returns:
        List of validation errors (empty if valid).
    """
    data = load_yaml(path)
    schema = get_analysis_schema()
    return validate_against_schema(data, schema)


def validate_universe_schema(path: str | Path) -> list[str]:
    """Validate a universe YAML file against the schema.

    Args:
        path: Path to the universe YAML file.

    Returns:
        List of validation errors (empty if valid).
    """
    data = load_yaml(path)
    schema = get_universe_schema()
    return validate_against_schema(data, schema)


def is_valid_analysis(path: str | Path) -> bool:
    """Check if an analysis file is valid."""
    return not validate_analysis_schema(path)


def is_valid_universe(path: str | Path) -> bool:
    """Check if a universe file is valid."""
    return not validate_universe_schema(path)
