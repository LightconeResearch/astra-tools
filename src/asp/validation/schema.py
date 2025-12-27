"""JSON Schema validation for ASP specifications."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import jsonschema
import yaml

from asp.schemas import get_analysis_schema, get_universe_schema


class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


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
    return len(validate_analysis_schema(path)) == 0


def is_valid_universe(path: str | Path) -> bool:
    """Check if a universe file is valid."""
    return len(validate_universe_schema(path)) == 0
