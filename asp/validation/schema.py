"""JSON Schema validation for ASP specifications.

Validates YAML files against the JSON schemas in spec/draft/.
The JSON schemas are the source of truth for validation, not the Pydantic models.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml


class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


def _get_spec_dir() -> Path:
    """Get the spec/draft directory path.

    Looks for spec/draft/ relative to the package installation,
    or in common locations for development.
    """
    # Try relative to this file (for installed package or development)
    pkg_dir = Path(__file__).parent.parent.parent
    spec_dir = pkg_dir / "spec" / "draft"
    if spec_dir.exists():
        return spec_dir

    # Try current working directory (for CLI usage)
    cwd_spec = Path.cwd() / "spec" / "draft"
    if cwd_spec.exists():
        return cwd_spec

    # Fall back to package directory even if doesn't exist
    # (will error when trying to load)
    return spec_dir


def load_schema_from_file(schema_name: str) -> dict[str, Any]:
    """Load a JSON schema from the spec/draft/ directory.

    Args:
        schema_name: Name of the schema (e.g., "analysis", "universe")

    Returns:
        The loaded JSON schema as a dict.

    Raises:
        FileNotFoundError: If the schema file doesn't exist.
    """
    spec_dir = _get_spec_dir()
    schema_path = spec_dir / f"{schema_name}.schema.json"

    if not schema_path.exists():
        raise FileNotFoundError(
            f"Schema file not found: {schema_path}\n"
            f"Run 'make schemas' to generate the schema files."
        )

    with open(schema_path) as f:
        schema: dict[str, Any] = json.load(f)
        return schema


def get_analysis_schema() -> dict[str, Any]:
    """Get the analysis JSON schema from spec/draft/."""
    return load_schema_from_file("analysis")


def get_universe_schema() -> dict[str, Any]:
    """Get the universe JSON schema from spec/draft/."""
    return load_schema_from_file("universe")


def get_insights_schema() -> dict[str, Any]:
    """Get the insights JSON schema from spec/draft/."""
    return load_schema_from_file("insights")


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file."""
    with open(path) as f:
        data: dict[str, Any] = yaml.safe_load(f)
        return data


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
