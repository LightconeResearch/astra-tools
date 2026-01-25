"""Core mapping logic for ASP decisions to CWL parameters.

Implements convention-based automatic mapping:
- Simple value (int/float/str): {decision_id} -> value
- Dict with keys: {decision_id}_{key} -> value[key] for each key
- No value field: {decision_id} -> option_id as string

Also handles ASP inputs -> CWL File inputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from asp.helpers import get_decisions, get_inputs, get_option


def extract_decision_values(analysis: dict[str, Any], universe: dict[str, Any]) -> dict[str, Any]:
    """Extract the value from each selected option in a universe.

    For each decision in the universe, looks up the selected option and
    extracts its value. If the option has no value field, uses the option ID
    as the value.

    Args:
        analysis: The ASP analysis specification as a dict.
        universe: The universe with decision selections as a dict.

    Returns:
        Dict mapping decision_id to the selected option's value.
        If option has no value field, the value is the option_id string.
    """
    values: dict[str, Any] = {}
    decisions = get_decisions(analysis)
    universe_decisions = universe.get("decisions", {})

    for decision_id, option_id in universe_decisions.items():
        decision = decisions.get(decision_id)
        if decision is None:
            continue

        option = get_option(decision, option_id)
        if option is None:
            continue

        # Use value if present, otherwise use option_id as string
        if option.get("value") is not None:
            values[decision_id] = option["value"]
        else:
            values[decision_id] = option_id

    return values


def apply_naming_convention(decision_id: str, value: Any) -> dict[str, Any]:
    """Apply naming convention to generate CWL parameter names.

    Convention rules:
    - Simple value (int/float/str/bool): {decision_id} -> value
    - Dict with single key: {decision_id}_{key} -> value
    - Dict with multiple keys: {decision_id}_{key} for each key
    - List: {decision_id} -> list (passed through)

    Args:
        decision_id: The ASP decision identifier.
        value: The value from the selected option.

    Returns:
        Dict mapping CWL parameter names to values.
    """
    result: dict[str, Any] = {}

    if isinstance(value, dict):
        # Flatten dict values with {decision_id}_{key} naming
        for key, val in value.items():
            param_name = f"{decision_id}_{key}"
            result[param_name] = val
    else:
        # Simple value or list - use decision_id directly
        result[decision_id] = value

    return result


def generate_cwl_params(
    analysis: dict[str, Any],
    universe: dict[str, Any],
    *,
    include_inputs: bool = False,
    base_path: Path | None = None,
) -> dict[str, Any]:
    """Generate complete CWL parameter dict from a universe.

    Combines decision value extraction with naming convention application
    to produce a flat dict of CWL parameters.

    Args:
        analysis: The ASP analysis specification as a dict.
        universe: The universe with decision selections as a dict.
        include_inputs: Whether to include ASP inputs as CWL File parameters.
        base_path: Base path for resolving relative file paths in inputs.

    Returns:
        Dict of CWL parameter names to values, ready to write as YAML.
    """
    params: dict[str, Any] = {}

    # Extract values from selected options
    decision_values = extract_decision_values(analysis, universe)

    # Apply naming convention to each decision value
    for decision_id, value in decision_values.items():
        param_dict = apply_naming_convention(decision_id, value)
        params.update(param_dict)

    # Optionally include inputs as CWL File references
    if include_inputs:
        input_params = resolve_inputs(analysis, base_path)
        params.update(input_params)

    return params


def resolve_input_source(inp: dict[str, Any], base_path: Path | None = None) -> dict[str, Any] | None:
    """Resolve an ASP input source to a CWL File reference.

    Args:
        inp: The ASP input definition as a dict.
        base_path: Base path for resolving relative file paths.

    Returns:
        CWL File object dict, or None if source cannot be resolved to a file.
    """
    source = inp.get("source")
    if source is None:
        return None

    # Handle string source (simple file path)
    if isinstance(source, str):
        path = source
        if base_path and not Path(path).is_absolute():
            path = str(base_path / path)
        return {"class": "File", "path": path}

    # Handle dict source
    if not isinstance(source, dict):
        return None

    source_type = source.get("type")

    if source_type == "file":
        path = source.get("path")
        if path is None:
            return None
        if base_path and not Path(path).is_absolute():
            path = str(base_path / path)
        return {"class": "File", "path": path}

    if source_type == "url":
        url = source.get("url")
        if url is None:
            return None
        return {"class": "File", "location": url}

    # S3, sklearn, asp sources require runtime resolution - return None for now
    return None


def resolve_inputs(
    analysis: dict[str, Any],
    base_path: Path | None = None,
) -> dict[str, Any]:
    """Resolve all ASP inputs to CWL File parameters.

    Only resolves inputs with type 'data' that have resolvable sources
    (local files or URLs). Other input types are skipped.

    Args:
        analysis: The ASP analysis specification as a dict.
        base_path: Base path for resolving relative file paths.

    Returns:
        Dict mapping input IDs to CWL File objects.
    """
    params: dict[str, Any] = {}

    for inp in get_inputs(analysis):
        # Only resolve data inputs with sources
        if inp.get("type") != "data":
            continue

        resolved = resolve_input_source(inp, base_path)
        if resolved is not None:
            params[inp["id"]] = resolved

    return params
