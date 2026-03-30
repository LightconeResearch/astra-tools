"""Dict-based query helpers for ASTRA analyses.

Provides functions for navigating and querying analysis data
loaded from astra.yaml files as plain dicts.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

# ---------------------------------------------------------------------------
# Entity accessors
# ---------------------------------------------------------------------------


def get_input(analysis: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Get an input by name."""
    for inp in analysis.get("inputs") or []:
        if inp.get("name") == name:
            return inp
    return None


def get_output(analysis: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Get an output by name."""
    for out in analysis.get("outputs") or []:
        if out.get("name") == name:
            return out
    return None


def get_decision(analysis: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Get a decision by name."""
    decisions = analysis.get("decisions") or {}
    return decisions.get(name)


def get_option(
    analysis: dict[str, Any], decision_name: str, option_name: str
) -> dict[str, Any] | None:
    """Get an option by decision and option name."""
    dec = get_decision(analysis, decision_name)
    if dec:
        options = dec.get("options") or {}
        return options.get(option_name)
    return None


def get_universe(analysis: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Get a universe by name."""
    universes = analysis.get("universes") or {}
    return universes.get(name)


def get_sub_analysis(analysis: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Get a sub-analysis by name."""
    analyses = analysis.get("analyses") or {}
    return analyses.get(name)


def get_insight(analysis: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Get a prior insight or finding by name."""
    for section in ("prior_insights", "findings"):
        items = analysis.get(section) or {}
        if name in items:
            return items[name]
    return None


# ---------------------------------------------------------------------------
# Collection accessors
# ---------------------------------------------------------------------------


def get_inputs(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Get all inputs."""
    return analysis.get("inputs") or []


def get_outputs(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    """Get all outputs."""
    return analysis.get("outputs") or []


def get_decisions(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Get all decisions."""
    return analysis.get("decisions") or {}


def get_local_decisions(analysis: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Get locally-defined decisions (excludes delegated)."""
    return {
        name: dec for name, dec in get_decisions(analysis).items() if not dec.get("delegates_to")
    }


# ---------------------------------------------------------------------------
# Tree walking
# ---------------------------------------------------------------------------


def walk_decisions(
    analysis: dict[str, Any], prefix: str = ""
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield (path, name, decision) for all local decisions across the tree.

    Path is the slash-separated path to the sub-analysis (empty for root).
    """
    for name, dec in get_local_decisions(analysis).items():
        yield prefix, name, dec

    for sub_name, sub in (analysis.get("analyses") or {}).items():
        sub_prefix = f"{prefix}{sub_name}/" if prefix else f"{sub_name}/"
        yield from walk_decisions(sub, sub_prefix)


# ---------------------------------------------------------------------------
# Universe helpers
# ---------------------------------------------------------------------------


def get_universe_selections(analysis: dict[str, Any], universe_name: str) -> dict[str, str]:
    """Get universe selections as a flat {decision_path: option} dict.

    Handles both list format [{decision: x, option: y}] and
    potential flat dict format {decision: option}.
    """
    universe = get_universe(analysis, universe_name)
    if not universe:
        return {}

    selections = universe.get("selections") or []
    if isinstance(selections, dict):
        return dict(selections)

    result = {}
    for sel in selections:
        dec = sel.get("decision", "")
        opt = sel.get("option", "")
        if dec and opt:
            result[dec] = opt
    return result


def generate_default_universe(
    analysis: dict[str, Any],
    universe_name: str = "baseline",
    description: str | None = None,
) -> dict[str, Any]:
    """Generate a universe dict from default options across the tree."""
    selections: list[dict[str, str]] = []

    for path, name, dec in walk_decisions(analysis):
        default = dec.get("default")
        if default:
            decision_path = f"{path}{name}" if path else name
            selections.append({"decision": decision_path, "option": default})

    universe: dict[str, Any] = {"name": universe_name, "selections": selections}
    if description:
        universe["description"] = description
    return universe


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


def is_condition_met(
    when: str | list[str] | None,
    universe_selections: dict[str, str],
) -> bool:
    """Evaluate whether a condition is satisfied.

    Args:
        when: Condition(s) in "decision.option" or "~decision.option" format.
            Lists are AND'd together.
        universe_selections: Dict mapping decision names to selected option names.
    """
    if when is None:
        return True

    conditions = [when] if isinstance(when, str) else when

    for cond in conditions:
        negated = cond.startswith("~")
        if negated:
            cond = cond[1:]
        parts = cond.split(".", 1)
        if len(parts) != 2:
            return False
        dec_name, opt_name = parts
        selected = universe_selections.get(dec_name)
        matches = selected == opt_name
        if negated:
            matches = not matches
        if not matches:
            return False
    return True


# ---------------------------------------------------------------------------
# Output dependencies
# ---------------------------------------------------------------------------


def get_output_dependencies(analysis: dict[str, Any]) -> dict[str, list[str]]:
    """Build output-to-output dependency graph from recipes."""
    deps: dict[str, list[str]] = {}
    for out in get_outputs(analysis):
        name = out.get("name", "")
        recipe = out.get("recipe")
        if recipe:
            deps[name] = recipe.get("depends_on") or []
        else:
            deps[name] = []
    return deps
