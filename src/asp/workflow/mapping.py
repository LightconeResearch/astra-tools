"""Core mapping logic for ASP decisions to CWL parameters.

Implements convention-based automatic mapping:
- Simple value (int/float/str): {decision_id} -> value
- Dict with keys: {decision_id}_{key} -> value[key] for each key
- No value field: {decision_id} -> option_id as string
"""

from __future__ import annotations

from typing import Any

from asp.models.analysis import Analysis
from asp.models.universe import Universe


def extract_decision_values(analysis: Analysis, universe: Universe) -> dict[str, Any]:
    """Extract the value from each selected option in a universe.

    For each decision in the universe, looks up the selected option and
    extracts its value. If the option has no value field, uses the option ID
    as the value.

    Args:
        analysis: The ASP analysis specification.
        universe: The universe with decision selections.

    Returns:
        Dict mapping decision_id to the selected option's value.
        If option has no value field, the value is the option_id string.
    """
    values: dict[str, Any] = {}

    for decision_id, option_id in universe.decisions.items():
        decision = analysis.decisions.get(decision_id)
        if decision is None:
            continue

        option = decision.options.get(option_id)
        if option is None:
            continue

        # Use value if present, otherwise use option_id as string
        if option.value is not None:
            values[decision_id] = option.value
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


def generate_cwl_params(analysis: Analysis, universe: Universe) -> dict[str, Any]:
    """Generate complete CWL parameter dict from a universe.

    Combines decision value extraction with naming convention application
    to produce a flat dict of CWL parameters.

    Args:
        analysis: The ASP analysis specification.
        universe: The universe with decision selections.

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

    return params
