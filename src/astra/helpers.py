"""Dict-based helper utilities for ASTRA.

These utilities work with raw dict data structures loaded from YAML files,
avoiding the need for Pydantic model imports in the validation path.

Everything here but ``load_yaml`` and ``save_yaml`` operates on dicts that
are already in hand, so PyYAML — ~18 ms, more than the rest of this module
put together — is imported by those two functions rather than by everyone
who imports this one.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

#: The id grammar the schema enforces. It is what makes ``.`` an
#: unambiguous separator in a ``from:`` reference or a qualified id.
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

#: An analysis path: the sub-analysis ids descended through to reach a
#: node, empty at the root. Joined with ``.`` it qualifies any id declared
#: there, e.g. ``classification.accuracy``.
Scope = tuple[str, ...]

_T = TypeVar("_T")


# A unified path expression that any `from:` slot can take:
#
#   ../id              -- escape one scope upward, then `id`
#   ../../id           -- escape two scopes upward, then `id`
#   ../scope.id        -- escape upward, then descend into a named child
#   scope.id           -- descend from current scope into a named child
#   scope.sub.id       -- descend through nested children
#
# Direction restrictions are per-slot and belong to the validator, not here.
def parse_from_path(ref: str) -> tuple[int, list[str]] | None:
    """Parse a ``from:`` reference into ``(up_levels, descent_segments)``.

    Args:
        ref: The reference as written, e.g. ``"../feature_extraction.features"``.

    Returns:
        The number of ``../`` steps and the remaining dotted segments, or
        ``None`` if the reference is malformed (empty or invalid segments).

    Examples:
        ``"../id"`` → ``(1, ["id"])``; ``"../scope.id"`` → ``(1, ["scope",
        "id"])``; ``"scope.sub.id"`` → ``(0, ["scope", "sub", "id"])``.
    """
    up = 0
    rest = ref
    while rest.startswith("../"):
        up += 1
        rest = rest[3:]
    if not rest or rest.startswith(".") or rest.endswith("."):
        return None
    segments = rest.split(".")
    if not all(ID_PATTERN.match(seg) for seg in segments):
        return None
    return (up, segments)


def parse_option_ref(ref: str) -> tuple[str, str] | None:
    """Parse a ``decision_id.option_id`` reference.

    The grammar behind ``when:``, ``requires:`` and ``incompatible_with:``:
    one decision, one of its options. Negation (``~``) belongs to the
    condition rather than the reference, so callers strip it first.

    Args:
        ref: The reference as written, e.g. ``"scaling.standard"``.

    Returns:
        ``(decision_id, option_id)``, or ``None`` if the reference is not
        exactly two dot-separated parts. Malformed is the validator's to
        report — ``INVALID_WHEN_REF``, ``INVALID_CONSTRAINT_FORMAT`` —
        which it cannot do if parsing raises first.
    """
    decision_id, dot, option_id = ref.partition(".")
    if not dot or "." in option_id:
        return None
    return (decision_id, option_id)


def is_condition_met(
    when: str | list[str] | None,
    universe_decisions: dict[str, str],
) -> bool:
    """Check if a when condition is met given universe decisions.

    Args:
        when: A string, list of strings, or None. Each string is
            ``decision_id.option_id`` or ``~decision_id.option_id`` (negation).
            Multiple items are AND'd together.
        universe_decisions: Dict mapping decision_id to selected option_id.

    Returns:
        True if the condition is met (or when is None), False otherwise.
        A malformed reference is a condition nothing can satisfy, negated
        or not — reporting it belongs to the validator, and raising here
        took `astra universe check` down on a typo.
    """
    if when is None:
        return True
    conditions = [when] if isinstance(when, str) else when
    for cond in conditions:
        negate = cond.startswith("~")
        parsed = parse_option_ref(cond.lstrip("~"))
        if parsed is None:
            return False
        decision_id, option_id = parsed
        match = universe_decisions.get(decision_id) == option_id
        if negate:
            match = not match
        if not match:
            return False  # AND logic: all must be true
    return True


def _collect_node_decisions(node: dict[str, Any]) -> dict[str, Any]:
    """Collect locally-defined decisions from a node.

    Decisions with a ``from`` field are references to parent decisions
    and are excluded from the result since they are not locally defined.
    """
    decisions: dict[str, Any] = {}
    for decision_id, decision in (node.get("decisions") or {}).items():
        if isinstance(decision, dict) and decision.get("from"):
            continue  # Skip parent-decision references
        decisions[decision_id] = decision
    return decisions


def external_spec_path(base_path: Path, sub_path: str) -> Path:
    """The astra.yaml file a sub-analysis ``path:`` reference points at."""
    return (base_path / sub_path).resolve() / "astra.yaml"


def iter_analysis_nodes(data: Mapping[str, Any]) -> Iterator[tuple[Scope, dict[str, Any]]]:
    """Yield every node in the analysis tree with the scope it sits at.

    The root comes first, with an empty scope, then each sub-analysis
    depth-first. The scope path is what lets anything declared inside a
    sub-analysis be named unambiguously; where it does not matter,
    ``iter_sub_analyses`` is the same walk without it.

    An external (``path:``) sub-analysis is descended into like any other:
    before ``resolve_analysis_tree`` runs it has no content to descend
    into, and after it runs that content is the sub-analysis.

    Args:
        data: The analysis, external sub-analyses resolved or not.

    Yields:
        ``(scope, node)`` pairs, root first.
    """
    yield ((), dict(data))
    yield from _descend_nodes(data, ())


def _descend_nodes(node: Mapping[str, Any], scope: Scope) -> Iterator[tuple[Scope, dict[str, Any]]]:
    for sub_id, sub in (node.get("analyses") or {}).items():
        if not isinstance(sub, dict):
            continue
        here = (*scope, str(sub_id))
        yield (here, sub)
        yield from _descend_nodes(sub, here)


def iter_sub_analyses(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield every sub-analysis dict declared in ``node``'s ``analyses`` tree.

    Depth-first, parents before children; the node itself is not yielded.
    """
    for _, sub in _descend_nodes(node, ()):
        yield sub


def ancestor_at(chain: Sequence[_T], up: int) -> _T | None:
    """The entry ``up`` scopes above the current node in a root-first chain.

    What every ``../`` in a ``from:`` reference counts against, whether the
    chain holds ancestor nodes, ancestor universes, or what each ancestor
    settled: ``chain[-1]`` is the immediate parent, so ``up=1`` selects it.

    Args:
        chain: The ancestors of the current node, root first.
        up: The number of ``../`` steps taken.

    Returns:
        The entry that many scopes up, or ``None`` if the reference escapes
        past the root — which the validator reports and the resolver skips.
    """
    if up <= 0 or up > len(chain):
        return None
    return chain[len(chain) - up]


def resolve_analysis_tree(data: dict[str, Any], base_path: Path) -> dict[str, Any]:
    """Resolve external sub-analysis references in an analysis tree.

    Walks the ``analyses`` dict. For any sub-analysis with a ``path``
    field, loads ``<path>/astra.yaml`` as that sub-analysis's full
    content. Sub-analyses are either external (a ``path:``) or inline
    (content fields at the parent), never both — semantic validation
    enforces this via ``PATH_FIELD_CONFLICT``.

    Args:
        data: The analysis data as a dict.
        base_path: Base directory for resolving relative paths.

    Returns:
        A new dict with external sub-analyses resolved (deep copy of modified branches).
    """
    analyses = data.get("analyses")
    if not analyses:
        return data

    resolved_analyses: dict[str, Any] = {}
    changed = False

    for analysis_id, analysis_node in analyses.items():
        sub_path = analysis_node.get("path")
        if sub_path:
            sub_yaml_path = external_spec_path(base_path, sub_path)
            resolved_dir = sub_yaml_path.parent
            if sub_yaml_path.exists():
                sub_data = load_yaml(sub_yaml_path)
                # Keep the path field for reference
                sub_data["path"] = sub_path
                # Recursively resolve nested sub-analyses
                sub_data = resolve_analysis_tree(sub_data, resolved_dir)
                resolved_analyses[analysis_id] = sub_data
                changed = True
            else:
                logger.warning(
                    "Sub-analysis '%s' has path '%s' but %s does not exist",
                    analysis_id,
                    sub_path,
                    sub_yaml_path,
                )
                resolved_analyses[analysis_id] = analysis_node
        else:
            # Inline sub-analysis: recursively resolve its children
            resolved_sub = resolve_analysis_tree(analysis_node, base_path)
            resolved_analyses[analysis_id] = resolved_sub
            if resolved_sub is not analysis_node:
                changed = True

    if not changed:
        return data

    result = dict(data)
    result["analyses"] = resolved_analyses
    return result


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dict.

    Args:
        path: Path to the YAML file.

    Returns:
        The parsed YAML content as a dictionary.
    """
    import yaml

    with open(path) as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return data


def save_yaml(data: dict[str, Any], path: str | Path) -> None:
    """Save data to a YAML file.

    Args:
        data: The data to save.
        path: Path to write the YAML file.
    """
    import yaml

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


def get_prior_insight(data: dict[str, Any], insight_id: str) -> dict[str, Any] | None:
    """Get a prior insight by ID from analysis data.

    Args:
        data: Analysis data as a dict.
        insight_id: The prior insight ID to find.

    Returns:
        The prior insight dict if found, None otherwise.
    """
    prior_insights: dict[str, dict[str, Any]] = data.get("prior_insights", {})
    return prior_insights.get(insight_id)


def get_finding(data: dict[str, Any], finding_id: str) -> dict[str, Any] | None:
    """Get a finding by ID from analysis data.

    Args:
        data: Analysis data as a dict.
        finding_id: The finding ID to find.

    Returns:
        The finding dict if found, None otherwise.
    """
    findings: dict[str, dict[str, Any]] = data.get("findings", {})
    return findings.get(finding_id)


def get_default_universe(data: dict[str, Any]) -> dict[str, Any]:
    """Get the default universe based on decision defaults across entire tree.

    Args:
        data: Analysis data as a dict.

    Returns:
        Dict with 'decisions' and optional 'analyses' keys mirroring the tree.
    """
    return _get_node_defaults(data)


def _get_node_defaults(node: dict[str, Any]) -> dict[str, Any]:
    """Recursively get defaults from a node."""
    result: dict[str, Any] = {}
    decisions: dict[str, str] = {}
    all_decisions = _collect_node_decisions(node)

    for decision_id, decision in all_decisions.items():
        if decision.get("when"):
            continue  # Conditional decisions handled in second pass
        default = decision.get("default")
        if default is not None:
            decisions[decision_id] = default

    # Second pass: fixed-point loop for conditional decisions whose conditions are met.
    # Iterate until no new defaults are added, so that ordering in the YAML doesn't matter
    # (a conditional decision can depend on another conditional decision resolved earlier).
    changed = True
    while changed:
        changed = False
        for decision_id, decision in all_decisions.items():
            if decision_id in decisions:
                continue  # Already resolved
            when = decision.get("when")
            if not when:
                continue
            if is_condition_met(when, decisions):
                default = decision.get("default")
                if default is not None:
                    decisions[decision_id] = default
                    changed = True

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


def get_prior_insight_ids(data: dict[str, Any]) -> set[str]:
    """Get all prior insight IDs from analysis data.

    Args:
        data: Analysis data as a dict.

    Returns:
        Set of prior insight IDs.
    """
    return set(data.get("prior_insights", {}).keys())


def get_finding_ids(data: dict[str, Any]) -> set[str]:
    """Get all finding IDs from analysis data.

    Args:
        data: Analysis data as a dict.

    Returns:
        Set of finding IDs.
    """
    return set(data.get("findings", {}).keys())


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
    """Build the output-to-output dependency graph from output declarations.

    Args:
        data: Analysis data as a dict.

    Returns:
        Dict mapping output_id to list of input IDs (from Output.inputs).
        Outputs without declared inputs have an empty dependency list.
    """
    result: dict[str, list[str]] = {}
    for out in data.get("outputs") or []:
        out_id = out.get("id")
        if not out_id:
            continue
        result[out_id] = out.get("inputs") or []
    return result


def get_outputs_with_recipes(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Get outputs that have inline recipes.

    Args:
        data: Analysis data as a dict.

    Returns:
        List of output dicts that have a 'recipe' key.
    """
    return [out for out in (data.get("outputs") or []) if out.get("recipe")]
