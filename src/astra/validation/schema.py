"""Schema validation for ASTRA specifications.

Validates ASTRA YAML files using the Pydantic models from astra-spec.
Dict keys are injected as ``id`` fields before validation, since ASTRA YAML
uses keyed dicts (e.g., ``decisions: {scaling: ...}``) while the Pydantic
models expect an explicit ``id`` on each object.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from astra.datamodel.astra_pydantic import Analysis, Universe
from pydantic import ValidationError as PydanticValidationError

from astra.helpers import load_yaml


def _inject_ids_inplace(data: dict[str, Any]) -> None:
    """Prepare a raw YAML dict for Pydantic validation.

    Injects dict keys as ``id`` fields (ASTRA YAML uses keyed dicts).
    """
    for field in ("decisions", "analyses", "prior_insights", "findings"):
        mapping = data.get(field)
        if not isinstance(mapping, dict):
            continue
        for key, value in mapping.items():
            if not isinstance(value, dict):
                continue
            value.setdefault("id", key)
            if field == "decisions":
                if isinstance(value.get("options"), dict):
                    for okey, ovalue in value["options"].items():
                        if isinstance(ovalue, dict):
                            ovalue.setdefault("id", okey)
            if field == "analyses":
                _inject_ids_inplace(value)


def _format_pydantic_errors(exc: PydanticValidationError) -> list[str]:
    """Convert Pydantic validation errors to simple error strings."""
    errors: list[str] = []
    for err in exc.errors():
        path = ".".join(str(p) for p in err["loc"]) if err["loc"] else "(root)"
        errors.append(f"{path}: {err['msg']}")
    return errors


def validate_analysis_schema(path: str | Path) -> list[str]:
    """Validate an analysis YAML file against the schema.

    Returns a list of error messages (empty if valid).
    """
    data = load_yaml(path)
    return validate_analysis_data(data)


def validate_analysis_data(data: dict[str, Any]) -> list[str]:
    """Validate analysis data dict against the schema.

    Returns a list of error messages (empty if valid).
    """
    preprocessed = copy.deepcopy(data)
    preprocessed.setdefault("id", "root")  # root analysis has no id in YAML
    _inject_ids_inplace(preprocessed)
    try:
        Analysis.model_validate(preprocessed)
        return []
    except PydanticValidationError as exc:
        return _format_pydantic_errors(exc)


def validate_universe_schema(path: str | Path) -> list[str]:
    """Validate a universe YAML file against the schema.

    Returns a list of error messages (empty if valid).
    """
    data = load_yaml(path)
    return validate_universe_data(data)


def _inject_universe_ids_inplace(node: dict[str, Any]) -> None:
    """Inject dict keys as ``id`` fields on universe sub-analysis nodes."""
    analyses = node.get("analyses")
    if not isinstance(analyses, dict):
        return
    for key, value in analyses.items():
        if isinstance(value, dict):
            value.setdefault("id", key)
            _inject_universe_ids_inplace(value)


def validate_universe_data(data: dict[str, Any]) -> list[str]:
    """Validate universe data dict against the schema.

    Returns a list of error messages (empty if valid).
    """
    preprocessed = copy.deepcopy(data)
    _inject_universe_ids_inplace(preprocessed)
    try:
        Universe.model_validate(preprocessed)
        return []
    except PydanticValidationError as exc:
        return _format_pydantic_errors(exc)


def is_valid_analysis(path: str | Path) -> bool:
    """Check if an analysis file is valid."""
    return not validate_analysis_schema(path)


def is_valid_universe(path: str | Path) -> bool:
    """Check if a universe file is valid."""
    return not validate_universe_schema(path)
