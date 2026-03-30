"""YAML loading and validation for ASTRA analyses.

Loads `astra.yaml` files, validates against the LinkML-generated JSON Schema,
and returns either raw dicts or Pydantic model instances.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

_SCHEMA_CACHE: dict[str, Any] | None = None


def _get_schema() -> dict[str, Any]:
    """Load the generated JSON Schema (cached)."""
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        schema_path = Path(__file__).parent / "schema" / "generated" / "astra.schema.json"
        with open(schema_path) as f:
            _SCHEMA_CACHE = json.load(f)
    return _SCHEMA_CACHE


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load an astra.yaml file and return as a dict.

    Does NOT validate. Use validate_yaml() or load_analysis() for validation.
    """
    path = Path(path)
    if path.is_dir():
        path = path / "astra.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def validate_yaml(data: dict[str, Any]) -> list[str]:
    """Validate an analysis dict against the JSON Schema.

    Returns a list of error messages (empty if valid).
    """
    import jsonschema

    schema = _get_schema()
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'.'.join(str(p) for p in e.path)}: {e.message}" if e.path else e.message
        for e in validator.iter_errors(data)
    ]


def load_analysis(path: str | Path) -> Any:
    """Load an astra.yaml file into a Pydantic Analysis model.

    Validates against JSON Schema first, then loads into the model.
    Raises ValueError if validation fails.
    """
    from astra.schema.generated.astra_models import Analysis

    data = load_yaml(path)
    errors = validate_yaml(data)
    if errors:
        raise ValueError("Schema validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
    return Analysis(**data)


def find_analysis_dir(start: Path | None = None) -> tuple[Path, str]:
    """Find the nearest directory containing an analysis file.

    Returns (directory, format) where format is 'yaml' or 'rocrate'.
    Prefers astra.yaml over ro-crate-metadata.json.
    """
    current = start or Path.cwd()
    while True:
        if (current / "astra.yaml").exists():
            return current, "yaml"
        if (current / "ro-crate-metadata.json").exists():
            return current, "rocrate"
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise FileNotFoundError("No astra.yaml or ro-crate-metadata.json found")


def save_yaml(data: dict[str, Any], path: str | Path) -> None:
    """Save an analysis dict to a YAML file."""
    path = Path(path)
    if path.is_dir():
        path = path / "astra.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
