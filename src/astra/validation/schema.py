"""Schema validation for ASTRA specifications.

Validates ASTRA YAML files using the Pydantic models from astra-spec.
Dict keys are injected as ``id`` fields before validation, since ASTRA YAML
uses keyed dicts (e.g., ``decisions: {scaling: ...}``) while the Pydantic
models expect an explicit ``id`` on each object.

The models are imported inside the two functions that validate against
them. Reaching them costs ~200 ms — an order of magnitude more than the
rest of ASTRA put together, because ``astra.datamodel`` loads
``linkml_runtime`` — and the entry points here that every ``astra`` run
touches (``check_spec_version``, ``installed_spec_version``) need nothing
from them.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astra.helpers import iter_analysis_nodes, load_yaml

if TYPE_CHECKING:
    from pydantic import ValidationError as PydanticValidationError

# Re-exported: `installed_spec_version` moved to its own stdlib-only module
# so scaffolding can reach it without importing the datamodel, but it stays
# importable from here — including for tests that patch it by this name.
from astra.spec_version import installed_spec_version


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
    from astra.datamodel.astra_pydantic import Analysis
    from pydantic import ValidationError as PydanticValidationError

    preprocessed = copy.deepcopy(data)
    preprocessed.setdefault("id", "root")  # root analysis has no id in YAML
    _inject_ids_inplace(preprocessed)
    try:
        Analysis.model_validate(preprocessed)
        return []
    except PydanticValidationError as exc:
        return _format_pydantic_errors(exc)


# Fields the schema marks `recommended: true` rather than `required`. Omitting
# one is not an error — the document validates — but it will become one, so the
# validator says so while there is still time to act.
#
# `format` is forbidden on a re-exported Output (`from:`), which inherits it
# from its source, so aliases are skipped rather than flagged for a field they
# are not allowed to declare. astra-spec's schema is the source of truth; this
# check exists because the generated Pydantic models carry `recommended` only
# as prose in the field description.
_RECOMMENDED_UNTIL = "0.1.0"


def collect_recommendations(data: dict[str, Any]) -> list[str]:
    """Report recommended-but-absent fields anywhere in the analysis tree.

    Returns a list of human-readable messages (empty when nothing to say).
    These are warnings: they never make an analysis invalid.
    """
    missing_format: list[str] = []
    for scope, node in iter_analysis_nodes(data):
        for output in node.get("outputs") or []:
            if not isinstance(output, dict):
                continue
            if output.get("from") or output.get("format"):
                continue
            local_id = output.get("id")
            if not local_id:
                continue
            missing_format.append(".".join((*scope, str(local_id))))

    if not missing_format:
        return []
    subject = "output" if len(missing_format) == 1 else "outputs"
    return [
        f"{len(missing_format)} {subject} without a 'format': "
        f"{', '.join(missing_format)}. Optional today, required from ASTRA "
        f"{_RECOMMENDED_UNTIL} — add the artifact's file extension, e.g. 'format: png'."
    ]


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
    from astra.datamodel.astra_pydantic import Universe
    from pydantic import ValidationError as PydanticValidationError

    preprocessed = copy.deepcopy(data)
    _inject_universe_ids_inplace(preprocessed)
    try:
        Universe.model_validate(preprocessed)
        return []
    except PydanticValidationError as exc:
        return _format_pydantic_errors(exc)


def _normalize_version(v: str) -> tuple[int, ...] | None:
    parts = v.split(".")
    while len(parts) < 3:
        parts.append("0")
    try:
        return tuple(int(p) for p in parts[:3])
    except ValueError:
        return None


def check_spec_version(data: dict[str, Any]) -> str | None:
    """Compare an analysis's declared ASTRA spec version to the installed astra-spec.

    Returns a human-readable warning string when the declared ``version``
    differs from the installed ``astra-spec`` package version, else None.
    Returns None if either version is missing or unparseable — those cases
    are surfaced (or ignored) by other validation layers.
    """
    declared = data.get("version")
    if not isinstance(declared, str):
        return None
    installed = installed_spec_version()
    if installed is None:
        return None
    declared_t = _normalize_version(declared)
    installed_t = _normalize_version(installed)
    if declared_t is None or installed_t is None:
        return None
    if declared_t == installed_t:
        return None
    return (
        f"analysis declares ASTRA spec version {declared}, but astra-spec "
        f"{installed} is installed; validation reflects the installed version. "
        f"Pin astra-spec=={declared} to validate against the original spec, or "
        f"update the analysis's version field after confirming compatibility."
    )


def is_valid_analysis(path: str | Path) -> bool:
    """Check if an analysis file is valid."""
    return not validate_analysis_schema(path)


def is_valid_universe(path: str | Path) -> bool:
    """Check if a universe file is valid."""
    return not validate_universe_schema(path)
