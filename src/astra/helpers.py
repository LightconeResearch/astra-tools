"""Dict-based helper utilities for ASTRA.

These utilities work with raw dict data structures loaded from YAML files,
avoiding the need for Pydantic model imports in the validation path.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _collect_node_decisions(node: dict[str, Any]) -> dict[str, Any]:
    """Collect decisions from a node."""
    decisions: dict[str, Any] = dict(node.get("decisions") or {})
    return decisions


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
    inputs: list[dict[str, Any]] = data.get("inputs") or []
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
    outputs: list[dict[str, Any]] = data.get("outputs") or []
    for out in outputs:
        if out.get("id") == output_id:
            return out
    return None


def get_decision(
    data: dict[str, Any], decision_id: str, path: str | None = None
) -> dict[str, Any] | None:
    """Get a decision by ID from analysis data.

    Searches root decisions, then recursively through sub-analyses.
    If path is given, searches only within that sub-analysis.

    Args:
        data: Analysis data as a dict.
        decision_id: The decision ID to find.
        path: Optional dot-separated path to a sub-analysis (e.g., 'build_mocks').

    Returns:
        The decision dict if found, None otherwise.
    """
    if path is not None:
        node = _resolve_node(data, path)
        if node is None:
            return None
        result: dict[str, Any] | None = _collect_node_decisions(node).get(decision_id)
        return result

    # Search root decisions first, then sub-analyses recursively
    root_decisions = _collect_node_decisions(data)
    if decision_id in root_decisions:
        found: dict[str, Any] = root_decisions[decision_id]
        return found
    return _search_node_decision(data, decision_id)


def _resolve_node(analysis_content: dict[str, Any], path: str) -> dict[str, Any] | None:
    """Resolve a dot-separated path to a sub-analysis node."""
    parts = path.split(".")
    node = analysis_content
    for part in parts:
        analyses = node.get("analyses") or {}
        if part not in analyses:
            return None
        node = analyses[part]
    return node


def _search_node_decision(node: dict[str, Any], decision_id: str) -> dict[str, Any] | None:
    """Recursively search a node's sub-analyses for a decision."""
    for sub_node in (node.get("analyses") or {}).values():
        decisions: dict[str, Any] = _collect_node_decisions(sub_node)
        if decision_id in decisions:
            match: dict[str, Any] = decisions[decision_id]
            return match
        nested = _search_node_decision(sub_node, decision_id)
        if nested is not None:
            return nested
    return None


def get_insight(data: dict[str, Any], insight_id: str) -> dict[str, Any] | None:
    """Get an insight by ID from analysis data.

    Args:
        data: Analysis data as a dict.
        insight_id: The insight ID to find.

    Returns:
        The insight dict if found, None otherwise.
    """
    insights: dict[str, dict[str, Any]] = data.get("insights", {})
    return insights.get(insight_id)


def get_default_universe(data: dict[str, Any]) -> dict[str, Any]:
    """Get the default universe based on decision defaults across entire tree.

    Args:
        data: Analysis data as a dict.

    Returns:
        Dict with 'decisions' and optional 'analyses' keys mirroring the tree.
    """
    return _get_node_defaults(data)


def _get_node_defaults(node: dict[str, Any]) -> dict[str, Any]:
    """Recursively get defaults from a node.

    Skips conditional decisions whose ``when`` condition is not met
    by the defaults being collected so far.
    """
    result: dict[str, Any] = {}
    decisions: dict[str, str] = {}
    all_decisions = _collect_node_decisions(node)

    # First pass: collect defaults for unconditional decisions
    for decision_id, decision in all_decisions.items():
        if decision.get("when"):
            continue  # handle in second pass
        default = decision.get("default")
        if default is not None:
            decisions[decision_id] = default

    # Second pass: collect defaults for conditional decisions whose condition is met
    for decision_id, decision in all_decisions.items():
        when = decision.get("when")
        if not when:
            continue
        when_parts = when.split(".")
        if len(when_parts) == 2:
            when_decision_id, when_option_id = when_parts
            if decisions.get(when_decision_id) == when_option_id:
                default = decision.get("default")
                if default is not None:
                    decisions[decision_id] = default

    if decisions:
        result["decisions"] = decisions
    sub_analyses = node.get("analyses") or {}
    if sub_analyses:
        analyses_defaults: dict[str, Any] = {}
        for sub_id, sub_node in sub_analyses.items():
            sub_defaults = _get_node_defaults(sub_node)
            if sub_defaults:
                analyses_defaults[sub_id] = sub_defaults
        if analyses_defaults:
            result["analyses"] = analyses_defaults
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
    defaults = get_default_universe(data)
    result: dict[str, Any] = {
        "id": universe_id,
        "description": description or "Default configuration using standard practices",
    }
    if "decisions" in defaults:
        result["decisions"] = defaults["decisions"]
    if "analyses" in defaults:
        result["analyses"] = defaults["analyses"]
    return result


def get_input_ids(data: dict[str, Any]) -> set[str]:
    """Get all input IDs from analysis data.

    Args:
        data: Analysis data as a dict.

    Returns:
        Set of input IDs.
    """
    return {inp.get("id") for inp in (data.get("inputs") or []) if inp.get("id")}


def get_output_ids(data: dict[str, Any]) -> set[str]:
    """Get all output IDs from analysis data.

    Args:
        data: Analysis data as a dict.

    Returns:
        Set of output IDs.
    """
    return {out.get("id") for out in (data.get("outputs") or []) if out.get("id")}


def get_decision_ids(data: dict[str, Any]) -> set[str]:
    """Get all decision IDs from analysis data (across entire tree).

    Args:
        data: Analysis data as a dict.

    Returns:
        Set of decision IDs.
    """
    result: set[str] = set()
    result.update(_collect_node_decisions(data).keys())
    _collect_node_decision_ids(data, result)
    return result


def _collect_node_decision_ids(node: dict[str, Any], result: set[str]) -> None:
    """Recursively collect decision IDs from sub-analyses."""
    for sub_node in (node.get("analyses") or {}).values():
        result.update(_collect_node_decisions(sub_node).keys())
        _collect_node_decision_ids(sub_node, result)


def get_insight_ids(data: dict[str, Any]) -> set[str]:
    """Get all insight IDs from analysis data.

    Args:
        data: Analysis data as a dict.

    Returns:
        Set of insight IDs.
    """
    return set(data.get("insights", {}).keys())


def get_inputs(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Get all inputs from analysis data.

    Args:
        data: Analysis data as a dict.

    Returns:
        List of input dicts.
    """
    inputs: list[dict[str, Any]] = data.get("inputs") or []
    return inputs


def get_outputs(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Get all outputs from analysis data.

    Args:
        data: Analysis data as a dict.

    Returns:
        List of output dicts.
    """
    outputs: list[dict[str, Any]] = data.get("outputs") or []
    return outputs


def get_decisions(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Get all decisions from analysis data (collected from entire tree).

    Warning: If different nodes define decisions with the same ID, later ones
    overwrite earlier ones. Use ``get_analysis_decisions()`` for tree-scoped lookup.

    Args:
        data: Analysis data as a dict.

    Returns:
        Dict mapping decision_id to decision dict.
    """
    result: dict[str, dict[str, Any]] = {}

    # Root decisions
    for decision_id, decision in _collect_node_decisions(data).items():
        result[decision_id] = decision

    # Collect from sub-analyses
    _collect_decisions_from_node(data, result)

    return result


def _collect_decisions_from_node(
    node: dict[str, Any],
    result: dict[str, dict[str, Any]],
) -> None:
    """Recursively collect decisions from sub-analyses."""
    for node_id, sub_node in (node.get("analyses") or {}).items():
        for decision_id, decision in _collect_node_decisions(sub_node).items():
            if decision_id in result:
                logger.warning(
                    "Decision ID '%s' in analysis '%s' overwrites a decision with the same ID. "
                    "Use get_analysis_decisions() for tree-scoped access.",
                    decision_id,
                    node_id,
                )
            result[decision_id] = decision
        _collect_decisions_from_node(sub_node, result)


def get_analysis_decisions(data: dict[str, Any]) -> dict[str, Any]:
    """Get all decisions organized by analysis tree structure.

    Returns a dict with:
    - 'decisions': root-level decisions dict
    - 'analyses': dict of sub-analysis ID to their recursive decision structure

    Args:
        data: Analysis data as a dict.

    Returns:
        Recursive dict of decisions organized by analysis tree.
    """
    return _get_node_decision_tree(data)


def _get_node_decision_tree(node: dict[str, Any]) -> dict[str, Any]:
    """Build recursive decision tree from a node."""
    result: dict[str, Any] = {}
    decisions = _collect_node_decisions(node)
    if decisions:
        result["decisions"] = decisions
    sub_analyses = node.get("analyses") or {}
    if sub_analyses:
        analyses_result: dict[str, Any] = {}
        for node_id, sub_node in sub_analyses.items():
            sub_tree = _get_node_decision_tree(sub_node)
            if sub_tree:
                analyses_result[node_id] = sub_tree
        if analyses_result:
            result["analyses"] = analyses_result
    return result


def get_option(decision: dict[str, Any], option_id: str) -> dict[str, Any] | None:
    """Get an option from a decision by ID.

    Args:
        decision: Decision dict.
        option_id: The option ID to find.

    Returns:
        The option dict if found, None otherwise.
    """
    result: dict[str, Any] | None = decision.get("options", {}).get(option_id)
    return result


def get_option_value(decision: dict[str, Any], option_id: str) -> str:
    """Get the value for an option (returns the option_id).

    Args:
        decision: Decision dict.
        option_id: The option ID.

    Returns:
        The option_id string.
    """
    return option_id


def get_output_dependencies(data: dict[str, Any]) -> dict[str, list[str]]:
    """Build the output-to-output dependency graph from inline recipes.

    Args:
        data: Analysis data as a dict.

    Returns:
        Dict mapping output_id to list of input output_ids (from recipe.inputs).
        Outputs without recipes have an empty dependency list.
    """
    result: dict[str, list[str]] = {}
    for out in data.get("outputs") or []:
        out_id = out.get("id")
        if not out_id:
            continue
        recipe = out.get("recipe")
        if recipe:
            result[out_id] = recipe.get("inputs") or []
        else:
            result[out_id] = []
    return result


def get_outputs_with_recipes(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Get outputs that have inline recipes.

    Args:
        data: Analysis data as a dict.

    Returns:
        List of output dicts that have a 'recipe' key.
    """
    return [out for out in (data.get("outputs") or []) if out.get("recipe")]
