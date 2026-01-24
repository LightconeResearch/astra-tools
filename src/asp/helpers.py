"""Dict-based helper utilities for ASP.

These utilities work with raw dict data structures loaded from YAML files,
avoiding the need for Pydantic model imports in the validation path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict.

    Args:
        path: Path to the YAML file.

    Returns:
        The parsed YAML content as a dictionary.
    """
    with open(path) as f:
        data: dict[str, Any] = yaml.safe_load(f)
        return data


def save_yaml(data: dict[str, Any], path: str | Path) -> None:
    """Save data to a YAML file.

    Args:
        data: The data to save.
        path: Path to write the YAML file.
    """
    with open(path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def get_input(data: dict[str, Any], input_id: str) -> dict[str, Any] | None:
    """Get an input by ID from analysis data.

    Args:
        data: Analysis data as a dict.
        input_id: The input ID to find.

    Returns:
        The input dict if found, None otherwise.
    """
    inputs = data.get("analysis", {}).get("inputs", [])
    for inp in inputs:
        if inp.get("id") == input_id:
            return inp
    return None


def get_output(data: dict[str, Any], output_id: str) -> dict[str, Any] | None:
    """Get an output by ID from analysis data.

    Args:
        data: Analysis data as a dict.
        output_id: The output ID to find.

    Returns:
        The output dict if found, None otherwise.
    """
    outputs = data.get("analysis", {}).get("outputs", [])
    for out in outputs:
        if out.get("id") == output_id:
            return out
    return None


def get_decision(data: dict[str, Any], decision_id: str) -> dict[str, Any] | None:
    """Get a decision by ID from analysis data.

    Args:
        data: Analysis data as a dict.
        decision_id: The decision ID to find.

    Returns:
        The decision dict if found, None otherwise.
    """
    decisions = data.get("decisions", {})
    return decisions.get(decision_id)


def get_insight(data: dict[str, Any], insight_id: str) -> dict[str, Any] | None:
    """Get an insight by ID from analysis data.

    Args:
        data: Analysis data as a dict.
        insight_id: The insight ID to find.

    Returns:
        The insight dict if found, None otherwise.
    """
    insights = data.get("insights", {})
    return insights.get(insight_id)


def get_default_universe(data: dict[str, Any]) -> dict[str, str]:
    """Get the default universe based on decision defaults.

    Args:
        data: Analysis data as a dict.

    Returns:
        Dict mapping decision_id to default option_id.
    """
    result: dict[str, str] = {}
    decisions = data.get("decisions", {})
    for decision_id, decision in decisions.items():
        default = decision.get("default")
        if default is not None:
            result[decision_id] = default
    return result


def create_universe_from_defaults(
    data: dict[str, Any],
    universe_id: str = "baseline",
    description: str | None = None,
) -> dict[str, Any]:
    """Create a universe dict from the default options in an analysis.

    Args:
        data: Analysis data as a dict.
        universe_id: ID for the new universe.
        description: Optional description for the universe.

    Returns:
        A universe dict with the default decisions selected.
    """
    decisions = get_default_universe(data)
    result: dict[str, Any] = {
        "id": universe_id,
        "decisions": decisions,
    }
    if description:
        result["description"] = description
    else:
        result["description"] = "Default configuration using standard practices"
    return result


def get_input_ids(data: dict[str, Any]) -> set[str]:
    """Get all input IDs from analysis data.

    Args:
        data: Analysis data as a dict.

    Returns:
        Set of input IDs.
    """
    inputs = data.get("analysis", {}).get("inputs", [])
    return {inp.get("id") for inp in inputs if inp.get("id")}


def get_output_ids(data: dict[str, Any]) -> set[str]:
    """Get all output IDs from analysis data.

    Args:
        data: Analysis data as a dict.

    Returns:
        Set of output IDs.
    """
    outputs = data.get("analysis", {}).get("outputs", [])
    return {out.get("id") for out in outputs if out.get("id")}


def get_decision_ids(data: dict[str, Any]) -> set[str]:
    """Get all decision IDs from analysis data.

    Args:
        data: Analysis data as a dict.

    Returns:
        Set of decision IDs.
    """
    return set(data.get("decisions", {}).keys())


def get_insight_ids(data: dict[str, Any]) -> set[str]:
    """Get all insight IDs from analysis data.

    Args:
        data: Analysis data as a dict.

    Returns:
        Set of insight IDs.
    """
    return set(data.get("insights", {}).keys())
