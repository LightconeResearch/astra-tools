"""Semantic validation for ASTRA specifications.

This module performs semantic validation (cross-references, constraints)
using dict-based data structures loaded from YAML files.
"""

from __future__ import annotations

import re
import string
from pathlib import Path
from typing import Any

from astra.helpers import (
    _collect_node_decisions,
    get_input_ids,
    get_output_ids,
    is_condition_met,
    load_yaml,
    resolve_analysis_tree,
)

_FORMATTER = string.Formatter()


class SemanticError:
    """A semantic validation error."""

    def __init__(self, code: str, message: str, path: str | None = None):
        self.code = code
        self.message = message
        self.path = path

    def __str__(self) -> str:
        if self.path:
            return f"[{self.code}] {self.path}: {self.message}"
        return f"[{self.code}] {self.message}"


# ---------------------------------------------------------------------------
# `from:` path grammar
# ---------------------------------------------------------------------------
#
# A unified path expression that any `from:` slot can take:
#
#   ../id              -- escape one scope upward, then `id`
#   ../../id           -- escape two scopes upward, then `id`
#   ../scope.id        -- escape upward, then descend into a named child
#   scope.id           -- descend from current scope into a named child
#   scope.sub.id       -- descend through nested children
#
# Direction restrictions are applied per-slot by the caller:
#   Input.from    : up, or up-then-into-sibling
#   Output.from   : down (re-export)
#   Decision.from : up only
#
# The Pydantic schema validator already enforces the regex grammar at load
# time; the helper here is for resolution against the actual analysis tree.

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def _parse_from_path(ref: str) -> tuple[int, list[str]] | None:
    """Parse a `from:` path into ``(up_levels, descent_segments)``.

    Returns ``None`` if the path is malformed (empty segments, invalid
    identifier characters, etc.). Examples:

        "../id"               -> (1, ["id"])
        "../../id"            -> (2, ["id"])
        "../scope.id"         -> (1, ["scope", "id"])
        "scope.id"            -> (0, ["scope", "id"])
        "scope.sub.id"        -> (0, ["scope", "sub", "id"])
    """
    up = 0
    rest = ref
    while rest.startswith("../"):
        up += 1
        rest = rest[3:]
    if not rest or rest.startswith(".") or rest.endswith("."):
        return None
    segments = rest.split(".")
    for seg in segments:
        if not _ID_PATTERN.match(seg):
            return None
    return (up, segments)


def _check_path_exclusivity(
    data: dict[str, Any], errors: list[SemanticError], path_prefix: str = ""
) -> None:
    """Enforce that any sub-analysis with ``path:`` has no other fields.

    A sub-analysis is either external (a ``path:`` pointing to its own
    ``astra.yaml``) or inline (content fields declared at the parent),
    never both. Mixing the two produces a silent override / silent drop
    failure mode that's confusing to debug.
    """
    sub_analyses = data.get("analyses") or {}
    for sub_id, sub_node in sub_analyses.items():
        if not isinstance(sub_node, dict):
            continue
        full_path = f"{path_prefix}.analyses.{sub_id}" if path_prefix else f"analyses.{sub_id}"
        if sub_node.get("path"):
            extra = sorted(k for k in sub_node if k != "path")
            if extra:
                errors.append(
                    SemanticError(
                        "PATH_FIELD_CONFLICT",
                        f"Sub-analysis '{sub_id}' has 'path:' alongside fields "
                        f"{extra}; content must come from the referenced file. "
                        f"Move these fields into the sub's astra.yaml.",
                        full_path,
                    )
                )
        else:
            _check_path_exclusivity(sub_node, errors, full_path)


def validate_analysis(data: dict[str, Any], base_path: Path | None = None) -> list[SemanticError]:
    """Validate an analysis specification semantically.

    Checks:
    - Input/output IDs are unique
    - Decisions: defaults exist, evidence refs valid, constraint refs valid
    - Sub-analysis validation (recursive)
    - `from` reference validation on sub-analysis inputs
    - `from` reference validation on sub-analysis decisions

    If ``base_path`` is provided, sub-analyses with ``path:`` will be loaded
    and merged before validation.

    Args:
        data: The analysis data as a dict.
        base_path: Base directory for resolving ``path:`` references on sub-analyses.

    Returns:
        List of semantic errors (empty if valid).
    """
    errors: list[SemanticError] = []

    # Run on the raw data before resolve_analysis_tree merges the
    # external file's content onto the parent reference.
    _check_path_exclusivity(data, errors)

    # Resolve external sub-analysis paths if base_path is provided
    if base_path is not None:
        data = resolve_analysis_tree(data, base_path)

    # Root analysis requires version, name, inputs, outputs
    for field in ("version", "name", "inputs", "outputs"):
        if field not in data or data[field] is None:
            errors.append(
                SemanticError(
                    "MISSING_ROOT_FIELD",
                    f"Root analysis is missing required field '{field}'",
                    field,
                )
            )

    inputs = data.get("inputs") or []
    outputs = data.get("outputs") or []
    prior_insights = data.get("prior_insights") or {}

    # Check for duplicate input IDs
    input_ids: set[str] = set()
    for inp in inputs:
        inp_id = inp.get("id")
        if inp_id in input_ids:
            errors.append(
                SemanticError(
                    "DUPLICATE_INPUT",
                    f"Duplicate input ID: {inp_id}",
                    f"inputs.{inp_id}",
                )
            )
        if inp_id:
            input_ids.add(inp_id)

    # Check for duplicate output IDs
    output_ids: set[str] = set()
    for out in outputs:
        out_id = out.get("id")
        if out_id in output_ids:
            errors.append(
                SemanticError(
                    "DUPLICATE_OUTPUT",
                    f"Duplicate output ID: {out_id}",
                    f"outputs.{out_id}",
                )
            )
        if out_id:
            output_ids.add(out_id)

    # Collect all decisions (only locally-defined ones at root)
    root_decisions = _collect_node_decisions(data)

    # Validate all decisions
    errors.extend(_validate_decisions(root_decisions, prior_insights, ""))

    # Validate evidence artifact references in prior_insights and findings
    errors.extend(
        _validate_insight_artifacts(
            data.get("prior_insights") or {}, output_ids, "", "prior_insights"
        )
    )
    errors.extend(
        _validate_insight_artifacts(data.get("findings") or {}, output_ids, "", "findings")
    )

    # Collect qualified sub-analysis output IDs so root recipes can
    # reference them (e.g. ``inputs: [hod_fitting.galaxy_mesh]``).
    sub_analyses = data.get("analyses") or {}
    sub_output_ids: set[str] = set()
    for analysis_id, analysis_node in sub_analyses.items():
        for out in analysis_node.get("outputs") or []:
            out_id = out.get("id")
            if out_id:
                sub_output_ids.add(f"{analysis_id}.{out_id}")

    # `from:` re-exports must be checked before output dependencies, which
    # rely on knowing which output ids are real.
    errors.extend(_validate_outputs_from(outputs, data, ""))

    errors.extend(
        _validate_output_dependencies(
            outputs,
            analysis_input_ids=input_ids,
            decisions_in_scope=root_decisions,
            path_prefix="",
            extra_valid_ids=sub_output_ids,
        )
    )

    # Validate output when conditions
    errors.extend(_validate_output_when(outputs, root_decisions, ""))
    for analysis_id, analysis_node in sub_analyses.items():
        errors.extend(
            _validate_analysis_node(
                analysis_id,
                analysis_node,
                prior_insights,
                ancestor_chain=[data],
                path_prefix="analyses",
            )
        )

    return errors


def _validate_analysis_node(
    node_id: str,
    node: dict[str, Any],
    prior_insights: dict[str, Any],
    ancestor_chain: list[dict[str, Any]],
    path_prefix: str,
) -> list[SemanticError]:
    """Validate a single analysis node's decisions, inputs, and sub-analyses.

    ``ancestor_chain`` is ordered root-first; ``ancestor_chain[-1]`` is the
    immediate parent of this node.
    """
    errors: list[SemanticError] = []
    node_path = f"{path_prefix}.{node_id}"

    # If this is a path-only sub-analysis stub (not yet resolved), skip deep validation
    if node.get("path") and not node.get("inputs") and not node.get("outputs"):
        return errors

    # Check required sub-analysis fields
    for field in ("inputs", "outputs"):
        if not node.get(field):
            errors.append(
                SemanticError(
                    "MISSING_SUB_FIELD",
                    f"Sub-analysis '{node_id}' is missing required field: {field}",
                    node_path,
                )
            )

    # Validate decision `from` references against ancestor decisions
    node_all_decisions = node.get("decisions") or {}
    for decision_id, decision in node_all_decisions.items():
        ref = decision.get("from")
        if ref:
            errors.extend(
                _validate_decision_from(
                    decision_id,
                    ref,
                    ancestor_chain,
                    f"{node_path}.decisions.{decision_id}",
                )
            )

    # Validate node inputs (check `from` references)
    node_inputs = node.get("inputs") or []
    node_input_ids: set[str] = set()
    for inp in node_inputs:
        inp_id = inp.get("id")
        if inp_id:
            node_input_ids.add(inp_id)
        ref = inp.get("from")
        if ref:
            errors.extend(
                _validate_input_from(
                    ref,
                    ancestor_chain,
                    node_id,
                    node_path,
                )
            )

    # Validate node output IDs are unique
    node_output_ids: set[str] = set()
    for out in node.get("outputs") or []:
        out_id = out.get("id")
        if out_id in node_output_ids:
            errors.append(
                SemanticError(
                    "DUPLICATE_OUTPUT",
                    f"Duplicate output ID in analysis node: {out_id}",
                    f"{node_path}.outputs.{out_id}",
                )
            )
        if out_id:
            node_output_ids.add(out_id)

    node_outputs = node.get("outputs") or []
    errors.extend(_validate_outputs_from(node_outputs, node, node_path))

    node_decisions = _collect_node_decisions(node)
    constraint_scope = dict(node_decisions)
    for decision_id, decision in node_all_decisions.items():
        ref = decision.get("from")
        if not ref:
            continue
        parsed = _parse_from_path(ref)
        if parsed is None:
            continue
        up, segments = parsed
        if up <= 0 or len(segments) != 1:
            continue
        target_scope = _resolve_ancestor_scope(ancestor_chain, up)
        if target_scope is None:
            continue
        target_decisions = target_scope.get("decisions") or {}
        if segments[0] in target_decisions:
            constraint_scope[decision_id] = target_decisions[segments[0]]
    errors.extend(_validate_decisions(node_decisions, prior_insights, node_path, constraint_scope))

    # Validate evidence artifact references in prior_insights and findings
    errors.extend(
        _validate_insight_artifacts(
            node.get("prior_insights") or {}, node_output_ids, node_path, "prior_insights"
        )
    )
    errors.extend(
        _validate_insight_artifacts(
            node.get("findings") or {}, node_output_ids, node_path, "findings"
        )
    )

    # Sub-analysis output IDs are exposed as qualified ids so this node's
    # outputs can declare them as inputs (e.g. ``inputs: [child.out]``).
    sub_analyses = node.get("analyses") or {}
    sub_output_ids: set[str] = set()
    for sub_id, sub_node in sub_analyses.items():
        for out in sub_node.get("outputs") or []:
            out_id = out.get("id")
            if out_id:
                sub_output_ids.add(f"{sub_id}.{out_id}")

    errors.extend(
        _validate_output_dependencies(
            node_outputs,
            analysis_input_ids=node_input_ids,
            decisions_in_scope=constraint_scope,
            path_prefix=node_path,
            extra_valid_ids=sub_output_ids,
        )
    )
    errors.extend(_validate_output_when(node_outputs, constraint_scope, node_path))

    for sub_id, sub_node in sub_analyses.items():
        errors.extend(
            _validate_analysis_node(
                sub_id,
                sub_node,
                prior_insights,
                ancestor_chain=ancestor_chain + [node],
                path_prefix=f"{node_path}.analyses",
            )
        )

    return errors


def _validate_outputs_from(
    outputs: list[dict[str, Any]],
    current_scope: dict[str, Any],
    path_prefix: str,
) -> list[SemanticError]:
    """Validate ``from:`` paths on a list of Outputs (re-exports)."""
    errors: list[SemanticError] = []
    outputs_prefix = f"{path_prefix}.outputs" if path_prefix else "outputs"
    for out in outputs:
        ref = out.get("from")
        out_id = out.get("id")
        if not ref or not out_id:
            continue
        errors.extend(
            _validate_output_from(
                ref,
                current_scope,
                f"{outputs_prefix}.{out_id}",
            )
        )
    return errors


def _validate_insight_artifacts(
    insights: dict[str, Any],
    output_ids: set[str],
    path_prefix: str,
    section: str,
) -> list[SemanticError]:
    """Validate that insight evidence artifacts reference valid output IDs.

    Each evidence item with an ``artifact`` field must reference a declared output ID.
    Applied to both ``prior_insights`` and ``findings``.
    """
    errors: list[SemanticError] = []
    if not insights:
        return errors

    insights_prefix = f"{path_prefix}.{section}" if path_prefix else section
    for insight_id, insight in insights.items():
        insight_path = f"{insights_prefix}.{insight_id}"
        for i, ev in enumerate(insight.get("evidence") or []):
            artifact_ref = ev.get("artifact")
            if artifact_ref is not None and artifact_ref not in output_ids:
                errors.append(
                    SemanticError(
                        "INVALID_ARTIFACT_REF",
                        f"Evidence artifact '{artifact_ref}' not found in declared outputs",
                        f"{insight_path}.evidence[{i}].artifact",
                    )
                )
    return errors


def _validate_decisions(
    decisions: dict[str, Any],
    prior_insights: dict[str, Any],
    path_prefix: str,
    constraint_scope: dict[str, Any] | None = None,
) -> list[SemanticError]:
    """Validate a set of decisions at a given node.

    Args:
        constraint_scope: Decisions available for constraint resolution. Defaults to
            decisions themselves, but may include parent decisions for sub-analyses.
    """
    errors: list[SemanticError] = []
    if constraint_scope is None:
        constraint_scope = decisions

    decisions_prefix = f"{path_prefix}.decisions" if path_prefix else "decisions"
    for decision_id, decision in decisions.items():
        decision_path = f"{decisions_prefix}.{decision_id}"
        options = decision.get("options", {})

        # Check default option exists
        default = decision.get("default")
        if default is not None and default not in options:
            errors.append(
                SemanticError(
                    "INVALID_DEFAULT",
                    f"Default option '{default}' not found in options",
                    decision_path,
                )
            )

        # Check `when` condition references a valid decision.option
        when = decision.get("when")
        if when:
            conditions = [when] if isinstance(when, str) else when
            for cond in conditions:
                ref = cond.lstrip("~")
                when_parts = ref.split(".")
                if len(when_parts) != 2:
                    errors.append(
                        SemanticError(
                            "INVALID_WHEN_REF",
                            f"Decision 'when' condition '{cond}' has invalid format",
                            decision_path,
                        )
                    )
                    continue
                when_decision_id, when_option_id = when_parts
                scope = constraint_scope or {}
                if when_decision_id not in decisions and when_decision_id not in scope:
                    errors.append(
                        SemanticError(
                            "INVALID_WHEN_REF",
                            f"'when' references non-existent decision '{when_decision_id}'",
                            decision_path,
                        )
                    )
                else:
                    ref_decision = decisions.get(when_decision_id) or (constraint_scope or {}).get(
                        when_decision_id
                    )
                    if ref_decision and when_option_id not in ref_decision.get("options", {}):
                        errors.append(
                            SemanticError(
                                "INVALID_WHEN_REF",
                                f"'when' references non-existent option '{when_option_id}' "
                                f"in decision '{when_decision_id}'",
                                decision_path,
                            )
                        )
                # Check no self-reference
                if when_decision_id == decision_id:
                    errors.append(
                        SemanticError(
                            "INVALID_WHEN_REF",
                            "'when' cannot reference own decision",
                            decision_path,
                        )
                    )

        # Validate options
        for option_id, option in options.items():
            option_path = f"{decision_path}.options.{option_id}"

            # Check insight references (options reference prior_insights)
            insight_refs = option.get("insights") or []
            for i, insight_ref in enumerate(insight_refs):
                if insight_ref not in prior_insights:
                    errors.append(
                        SemanticError(
                            "INVALID_INSIGHT_REF",
                            f"Option insight '{insight_ref}' not found in prior_insights",
                            f"{option_path}.insights[{i}]",
                        )
                    )

            # Check incompatible_with refs (scoped to constraint_scope)
            incompatible_with = option.get("incompatible_with") or []
            for ref in incompatible_with:
                errors.extend(_validate_constraint_ref(ref, constraint_scope, option_path))

            # Check requires refs (scoped to constraint_scope)
            requires = option.get("requires") or []
            for ref in requires:
                errors.extend(_validate_constraint_ref(ref, constraint_scope, option_path))

            # Check excluded option consistency
            is_excluded = option.get("excluded", False)
            excluded_reason = option.get("excluded_reason")
            if is_excluded and not excluded_reason:
                errors.append(
                    SemanticError(
                        "MISSING_EXCLUDED_REASON",
                        f"Excluded option '{option_id}' must have an 'excluded_reason'",
                        option_path,
                    )
                )
            if excluded_reason and not is_excluded:
                errors.append(
                    SemanticError(
                        "ORPHAN_EXCLUDED_REASON",
                        f"Option '{option_id}' has 'excluded_reason' but is not marked excluded",
                        option_path,
                    )
                )

        # Check default is not an excluded option
        if default is not None and default in options:
            default_option = options[default]
            if default_option.get("excluded", False):
                errors.append(
                    SemanticError(
                        "EXCLUDED_DEFAULT",
                        f"Default option '{default}' is marked as excluded",
                        decision_path,
                    )
                )

    return errors


def _validate_output_when(
    outputs: list[dict[str, Any]],
    decisions: dict[str, Any],
    path_prefix: str,
) -> list[SemanticError]:
    """Validate ``when`` conditions on outputs.

    Checks that each referenced decision.option exists in the available decisions.
    """
    errors: list[SemanticError] = []
    outputs_prefix = f"{path_prefix}.outputs" if path_prefix else "outputs"

    for out in outputs:
        out_id = out.get("id")
        if not out_id:
            continue
        when = out.get("when")
        if not when:
            continue

        conditions = [when] if isinstance(when, str) else when
        output_path = f"{outputs_prefix}.{out_id}"

        for cond in conditions:
            ref = cond.lstrip("~")
            parts = ref.split(".")
            if len(parts) != 2:
                errors.append(
                    SemanticError(
                        "INVALID_WHEN_REF",
                        f"Output 'when' condition '{cond}' has invalid format",
                        output_path,
                    )
                )
                continue
            decision_id, option_id = parts
            if decision_id not in decisions:
                errors.append(
                    SemanticError(
                        "INVALID_WHEN_REF",
                        f"Output 'when' references non-existent decision '{decision_id}'",
                        output_path,
                    )
                )
            else:
                ref_decision = decisions[decision_id]
                if option_id not in ref_decision.get("options", {}):
                    errors.append(
                        SemanticError(
                            "INVALID_WHEN_REF",
                            f"Output 'when' references non-existent option '{option_id}' "
                            f"in decision '{decision_id}'",
                            output_path,
                        )
                    )

    return errors


def _validate_output_dependencies(
    outputs: list[dict[str, Any]],
    analysis_input_ids: set[str],
    decisions_in_scope: dict[str, Any],
    path_prefix: str,
    extra_valid_ids: set[str] | None = None,
) -> list[SemanticError]:
    """Validate Output.inputs/decisions declarations and Recipe.command templates.

    Checks:
    - Each ``Output.inputs`` ID resolves to an analysis-level input,
      a sibling output, or a qualified sub-analysis output
      (``sub.output_id``, supplied via ``extra_valid_ids``).
    - Each ``Output.decisions`` ID resolves to a decision in scope.
    - Recipe.command template placeholders only reference items declared
      in ``Output.inputs`` / ``Output.decisions``.
    - No cycles in the output-to-output dependency graph.
    """
    errors: list[SemanticError] = []
    outputs_prefix = f"{path_prefix}.outputs" if path_prefix else "outputs"

    output_ids = {out.get("id") for out in outputs if out.get("id")}
    sibling_or_extra = output_ids | (extra_valid_ids or set())
    valid_input_ids = analysis_input_ids | sibling_or_extra

    dep_graph: dict[str, list[str]] = {}
    for out in outputs:
        out_id = out.get("id")
        if not out_id:
            continue
        out_path = f"{outputs_prefix}.{out_id}"

        # Aliased Outputs (re-exports) are pure pointers — they don't have
        # their own inputs/decisions/recipe to validate. The `from:` path
        # itself is checked by `_validate_outputs_from`.
        if out.get("from"):
            dep_graph[out_id] = []
            continue

        declared_inputs = out.get("inputs") or []
        # Cycle graph only edges to sibling outputs (analysis-level inputs
        # are leaves and can't participate in a cycle).
        dep_graph[out_id] = [i for i in declared_inputs if i in sibling_or_extra]

        for inp_id in declared_inputs:
            if inp_id not in valid_input_ids:
                errors.append(
                    SemanticError(
                        "INVALID_OUTPUT_INPUT",
                        f"Output input '{inp_id}' is not a declared analysis input "
                        f"or sibling output",
                        f"{out_path}.inputs",
                    )
                )

        declared_decisions = out.get("decisions") or []
        for dec_id in declared_decisions:
            if dec_id not in decisions_in_scope:
                errors.append(
                    SemanticError(
                        "INVALID_OUTPUT_DECISION",
                        f"Output decision '{dec_id}' is not a decision in scope",
                        f"{out_path}.decisions",
                    )
                )

        recipe = out.get("recipe")
        if recipe and recipe.get("command"):
            errors.extend(
                _validate_command_template(
                    recipe["command"],
                    set(declared_inputs),
                    set(declared_decisions),
                    f"{out_path}.recipe.command",
                )
            )

    cycle = _detect_output_cycle(dep_graph)
    if cycle:
        errors.append(
            SemanticError(
                "OUTPUT_CYCLE",
                f"Dependency cycle detected: {' -> '.join(cycle)}",
                outputs_prefix,
            )
        )

    return errors


def _validate_command_template(
    command: str,
    declared_inputs: set[str],
    declared_decisions: set[str],
    path: str,
) -> list[SemanticError]:
    """Validate ``{...}`` placeholders in a Recipe.command template.

    Recognized placeholders: ``{inputs}``, ``{inputs.<id>}``,
    ``{decisions.<id>}``, ``{output}``. ``{{`` and ``}}`` are literal braces.
    Each ``{inputs.<id>}`` / ``{decisions.<id>}`` must reference an item
    declared on the surrounding Output.

    We deliberately don't lint "declared but unreferenced" — the spec
    grants the runner free choice of delivery mechanism (flags, env vars,
    sidecar JSON), so a recipe with `python script.py` and decisions
    delivered by sidecar is just as valid as one using `{decisions.x}`.
    """
    try:
        parsed = list(_FORMATTER.parse(command))
    except ValueError as e:
        return [SemanticError("INVALID_COMMAND_TEMPLATE", str(e), path)]

    errors: list[SemanticError] = []
    declared = {"inputs": declared_inputs, "decisions": declared_decisions}
    for _literal, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if field_name == "" or format_spec or conversion:
            errors.append(
                SemanticError(
                    "INVALID_COMMAND_TEMPLATE",
                    f"Invalid command placeholder '{{{field_name}}}'",
                    path,
                )
            )
            continue
        if field_name in ("output", "inputs"):
            continue
        head, dot, tail = field_name.partition(".")
        if dot and "." not in tail and head in declared:
            if tail not in declared[head]:
                errors.append(
                    SemanticError(
                        "UNDECLARED_TEMPLATE_REF",
                        f"Command placeholder '{{{field_name}}}' references undeclared "
                        f"{head[:-1]} '{tail}' (add it to Output.{head})",
                        path,
                    )
                )
            continue
        errors.append(
            SemanticError(
                "INVALID_COMMAND_TEMPLATE",
                f"Unknown command placeholder '{{{field_name}}}' (use "
                "{inputs}, {inputs.<id>}, {decisions.<id>}, or {output})",
                path,
            )
        )
    return errors


def _detect_output_cycle(dep_graph: dict[str, list[str]]) -> list[str] | None:
    """Detect cycles in output dependency graph. Returns cycle path or None."""
    _white, _gray, _black = 0, 1, 2
    color: dict[str, int] = {oid: _white for oid in dep_graph}
    path: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = _gray
        path.append(node)
        for dep in dep_graph.get(node, []):
            if dep not in color:
                continue  # invalid ref, caught elsewhere
            if color[dep] == _gray:
                cycle_start = path.index(dep)
                return path[cycle_start:] + [dep]
            if color[dep] == _white:
                result = dfs(dep)
                if result:
                    return result
        path.pop()
        color[node] = _black
        return None

    for oid in dep_graph:
        if color[oid] == _white:
            result = dfs(oid)
            if result:
                return result
    return None


def _resolve_ancestor_scope(
    ancestor_chain: list[dict[str, Any]],
    up_levels: int,
) -> dict[str, Any] | None:
    """Walk ``up_levels`` scopes up from the current node.

    ``ancestor_chain`` is ordered root-first: ``ancestor_chain[-1]`` is the
    immediate parent. Returns the target scope, or ``None`` if the chain is
    not deep enough.
    """
    if up_levels <= 0 or up_levels > len(ancestor_chain):
        return None
    return ancestor_chain[len(ancestor_chain) - up_levels]


def _validate_decision_from(
    decision_id: str,
    ref: str,
    ancestor_chain: list[dict[str, Any]],
    decision_path: str,
) -> list[SemanticError]:
    """Validate a `from:` reference on a Decision.

    Decisions only flow downward through scopes — the only legal form is
    ``../id``, ``../../id``, etc. (an ancestor decision). Sibling-sub or
    child references are rejected.
    """

    def _error(message: str) -> list[SemanticError]:
        return [SemanticError("INVALID_DECISION_FROM", message, decision_path)]

    parsed = _parse_from_path(ref)
    if parsed is None:
        return _error(f"Decision.from '{ref}' has invalid path syntax")
    up, segments = parsed
    if up == 0:
        return _error(
            f"Decision.from '{ref}' must start with '../' to reference an ancestor decision"
        )
    if len(segments) != 1:
        return _error(
            f"Decision.from '{ref}' must reference a single decision id "
            "(no descent into sibling/child scopes allowed; "
            "lift the decision to a common ancestor instead)"
        )

    target_scope = _resolve_ancestor_scope(ancestor_chain, up)
    if target_scope is None:
        return _error(
            f"Decision.from '{ref}' escapes {up} level(s) but only "
            f"{len(ancestor_chain)} ancestor scope(s) available"
        )

    target_decisions = target_scope.get("decisions") or {}
    if segments[0] not in target_decisions:
        return _error(
            f"Decision.from '{ref}' points to non-existent ancestor decision '{segments[0]}'"
        )
    return []


def _validate_input_from(
    ref: str,
    ancestor_chain: list[dict[str, Any]],
    current_node_id: str,
    node_path: str,
) -> list[SemanticError]:
    """Validate a `from:` reference on an Input.

    Legal forms:

      ``../id``                       -- a parent (or further-ancestor) Input
      ``../scope.out_id``             -- a sibling sub-analysis's Output
      ``../../uncle.out_id``          -- a cousin sub's Output (further up)

    Reaching downward from an Input (``child.out_id``) is not allowed — those
    are consumed via Output re-export at the parent.
    """

    def _error(message: str) -> list[SemanticError]:
        return [SemanticError("INVALID_FROM", message, node_path)]

    parsed = _parse_from_path(ref)
    if parsed is None:
        return _error(f"Input.from '{ref}' has invalid path syntax")
    up, segments = parsed
    if up == 0:
        return _error(
            f"Input.from '{ref}' must start with '../' to escape upward "
            "(downward references aren't allowed on Inputs; "
            "consume sub outputs via Output re-export)"
        )

    target_scope = _resolve_ancestor_scope(ancestor_chain, up)
    if target_scope is None:
        return _error(
            f"Input.from '{ref}' escapes {up} level(s) but only "
            f"{len(ancestor_chain)} ancestor scope(s) available"
        )

    if len(segments) == 1:
        if segments[0] not in get_input_ids(target_scope):
            return _error(
                f"Input.from '{ref}' points to non-existent ancestor input '{segments[0]}'"
            )
        return []

    # len >= 2: descend through named sub-analyses to a final Output id.
    current = target_scope
    for i, seg in enumerate(segments[:-1]):
        sub_analyses = current.get("analyses") or {}
        if seg not in sub_analyses:
            return _error(
                f"Input.from '{ref}': sub-analysis '{seg}' not found at depth {i} in target scope"
            )
        # Block self-reference: `../<self>.out_id` would point at our own scope's outputs.
        if up == 1 and i == 0 and seg == current_node_id:
            return _error(f"Input.from '{ref}' cannot reference own outputs")
        current = sub_analyses[seg]

    if segments[-1] not in get_output_ids(current):
        return _error(
            f"Input.from '{ref}': output '{segments[-1]}' not found in target sub-analysis"
        )
    return []


def _validate_output_from(
    ref: str,
    current_scope: dict[str, Any],
    output_path: str,
) -> list[SemanticError]:
    """Validate a `from:` reference on an Output (re-export).

    Outputs only flow upward through re-export: a parent Output points down
    into a child sub-analysis's Output via ``child.out_id`` (or deeper,
    ``child.grandchild.out_id``). Upward references aren't allowed.
    """

    def _error(message: str) -> list[SemanticError]:
        return [SemanticError("INVALID_OUTPUT_FROM", message, output_path)]

    parsed = _parse_from_path(ref)
    if parsed is None:
        return _error(f"Output.from '{ref}' has invalid path syntax")
    up, segments = parsed
    if up != 0:
        return _error(
            f"Output.from '{ref}' must descend into a sub-analysis "
            "(upward references aren't allowed; outputs flow up via per-layer re-export)"
        )
    if len(segments) < 2:
        return _error(
            f"Output.from '{ref}' must take the form 'child.out_id' "
            "(at least one descent step into a named sub-analysis)"
        )

    current = current_scope
    for i, seg in enumerate(segments[:-1]):
        sub_analyses = current.get("analyses") or {}
        if seg not in sub_analyses:
            return _error(f"Output.from '{ref}': sub-analysis '{seg}' not found at depth {i}")
        current = sub_analyses[seg]

    if segments[-1] not in get_output_ids(current):
        return _error(
            f"Output.from '{ref}': output '{segments[-1]}' not found in target sub-analysis"
        )
    return []


def _validate_constraint_ref(
    ref: str,
    decisions: dict[str, Any],
    option_path: str,
) -> list[SemanticError]:
    """Validate a constraint reference (decision.option format)."""
    parts = ref.split(".")
    if len(parts) != 2:
        return [
            SemanticError(
                "INVALID_CONSTRAINT_FORMAT",
                f"Constraint '{ref}' should be in 'decision.option' format",
                option_path,
            ),
        ]

    decision_id, option_id = parts

    if decision_id not in decisions:
        return [
            SemanticError(
                "INVALID_CONSTRAINT_REF",
                f"Constraint ref '{ref}' points to non-existent decision '{decision_id}'",
                option_path,
            ),
        ]

    if option_id not in decisions[decision_id].get("options", {}):
        return [
            SemanticError(
                "INVALID_CONSTRAINT_REF",
                f"Constraint ref '{ref}' points to non-existent option '{option_id}'",
                option_path,
            ),
        ]

    return []


def validate_universe(
    universe_data: dict[str, Any],
    analysis_data: dict[str, Any],
) -> list[SemanticError]:
    """Validate a universe against an analysis specification.

    Universe mirrors the analysis tree: root-level decisions + recursive analyses.

    Checks:
    - All decisions in the analysis have a selection in the universe
    - All selections point to valid options
    - No constraint violations (requires, incompatible_with)

    Args:
        universe_data: The universe data as a dict.
        analysis_data: The analysis data as a dict.

    Returns:
        List of semantic errors (empty if valid).
    """
    return _validate_universe_node(
        universe_data,
        analysis_data,
        path_prefix="",
        ancestor_universe_chain=[],
    )


def _validate_universe_node(
    universe_node: dict[str, Any],
    analysis_node: dict[str, Any],
    path_prefix: str,
    ancestor_universe_chain: list[dict[str, str]],
) -> list[SemanticError]:
    """Recursively validate a universe node against an analysis node.

    Validates decisions at this level, checks for unknown/missing analyses,
    then recurses into sub-analyses. Decisions with ``from`` references are
    skipped (they inherit their value from the parent universe).
    """
    errors: list[SemanticError] = []

    # Validate decisions at this level
    analysis_decisions = _collect_node_decisions(analysis_node)
    # Also get all decisions including `from` references for detecting what the
    # universe should/shouldn't contain
    all_analysis_decisions = analysis_node.get("decisions") or {}
    universe_decisions = universe_node.get("decisions") or {}
    decisions_path = f"{path_prefix}.decisions" if path_prefix else "decisions"

    # Identify `from` reference decisions (resolved from parent, not set in universe)
    from_decision_ids = set()
    for decision_id, decision in all_analysis_decisions.items():
        if isinstance(decision, dict) and decision.get("from"):
            from_decision_ids.add(decision_id)

    # Check for unknown decisions in universe
    for decision_id, option_id in universe_decisions.items():
        if decision_id in from_decision_ids:
            errors.append(
                SemanticError(
                    "FROM_DECISION_IN_UNIVERSE",
                    f"Universe should not set decision '{decision_id}' "
                    f"(it uses 'from' to reference a parent decision)",
                    f"{decisions_path}.{decision_id}",
                )
            )
            continue

        if decision_id not in analysis_decisions:
            errors.append(
                SemanticError(
                    "UNKNOWN_DECISION",
                    f"Universe references unknown decision '{decision_id}'",
                    f"{decisions_path}.{decision_id}",
                )
            )
            continue

        options = analysis_decisions[decision_id].get("options", {})
        if option_id not in options:
            errors.append(
                SemanticError(
                    "UNKNOWN_OPTION",
                    f"Universe selects unknown option '{option_id}' for decision '{decision_id}'",
                    f"{decisions_path}.{decision_id}",
                )
            )

        # Check option is not excluded
        if option_id in options:
            selected_option = options[option_id]
            if selected_option.get("excluded", False):
                errors.append(
                    SemanticError(
                        "EXCLUDED_OPTION_SELECTED",
                        f"Universe selects excluded option '{option_id}' "
                        f"for decision '{decision_id}'",
                        f"{decisions_path}.{decision_id}",
                    )
                )

    # Merge current and ancestor universe decisions for condition evaluation
    all_universe_decisions: dict[str, str] = {}
    for ancestor_universe in ancestor_universe_chain:
        all_universe_decisions.update(ancestor_universe)
    all_universe_decisions.update(universe_decisions)

    # Check all locally-defined analysis decisions are covered
    # (skip `from` references -- they get their value from the parent universe)
    for decision_id in analysis_decisions:
        if decision_id in from_decision_ids:
            continue  # `from` decisions are inherited, not set locally

        decision = analysis_decisions[decision_id]
        when = decision.get("when")

        # If conditional, check if the condition is met
        if when:
            if not is_condition_met(when, all_universe_decisions):
                # Condition not met -- this decision should NOT be in the universe
                if decision_id in universe_decisions:
                    errors.append(
                        SemanticError(
                            "INACTIVE_DECISION",
                            f"Universe specifies decision '{decision_id}' but its condition "
                            f"'{when}' is not met",
                            f"{decisions_path}.{decision_id}",
                        )
                    )
                continue  # Skip the missing check

        if decision_id not in universe_decisions:
            errors.append(
                SemanticError(
                    "MISSING_DECISION",
                    f"Universe missing decision '{decision_id}'",
                    f"{decisions_path}.{decision_id}",
                )
            )

    # Check constraints
    # Build effective decisions: local selections + `from` resolved from
    # the appropriate ancestor in the chain (multi-level via `../../`).
    effective_decisions = dict(universe_decisions)
    for decision_id in from_decision_ids:
        ref = all_analysis_decisions[decision_id].get("from", "")
        parsed = _parse_from_path(ref)
        if parsed is None:
            continue
        up, segments = parsed
        if up <= 0 or len(segments) != 1:
            continue
        # The ancestor universe is `up` levels above us in the universe chain.
        if up > len(ancestor_universe_chain):
            continue
        target_universe = ancestor_universe_chain[len(ancestor_universe_chain) - up]
        target_decision_id = segments[0]
        if target_decision_id in target_universe:
            effective_decisions[decision_id] = target_universe[target_decision_id]

    # Build effective analysis decisions for constraint checking (include resolved `from`)
    effective_analysis_decisions = dict(analysis_decisions)

    errors.extend(
        _validate_node_universe_constraints(
            effective_decisions,
            effective_analysis_decisions,
            decisions_path,
        )
    )

    # Recurse into sub-analyses
    analysis_sub = analysis_node.get("analyses") or {}
    universe_sub = universe_node.get("analyses") or {}
    analyses_prefix = f"{path_prefix}.analyses" if path_prefix else "analyses"

    for analysis_id in universe_sub:
        if analysis_id not in analysis_sub:
            errors.append(
                SemanticError(
                    "UNKNOWN_ANALYSIS",
                    f"Universe references unknown analysis: {analysis_id}",
                    f"{analyses_prefix}.{analysis_id}",
                )
            )

    for analysis_id, sub_analysis_node in analysis_sub.items():
        sub_universe = universe_sub.get(analysis_id, {})

        # Handle universe: reference on universe nodes
        # (The actual loading of external universe files is done by the caller/resolver;
        # here we just validate the structure we have)

        errors.extend(
            _validate_universe_node(
                sub_universe,
                sub_analysis_node,
                path_prefix=f"{analyses_prefix}.{analysis_id}",
                ancestor_universe_chain=ancestor_universe_chain + [universe_decisions],
            )
        )

    return errors


def _parse_constraint_ref(ref: str) -> tuple[str, str] | None:
    """Parse a constraint reference into (decision_id, option_id)."""
    parts = ref.split(".")
    if len(parts) == 2:
        return parts[0], parts[1]
    return None


def _validate_node_universe_constraints(
    universe_decisions: dict[str, str],
    analysis_decisions: dict[str, Any],
    path_prefix: str,
) -> list[SemanticError]:
    """Validate that decision selections respect constraints at one node."""
    errors: list[SemanticError] = []

    for decision_id, option_id in universe_decisions.items():
        decision = analysis_decisions.get(decision_id)
        if not decision:
            continue

        option = decision.get("options", {}).get(option_id)
        if not option:
            continue

        path = f"{path_prefix}.{decision_id}"

        # Check incompatible_with
        for ref in option.get("incompatible_with") or []:
            parsed = _parse_constraint_ref(ref)
            if parsed and universe_decisions.get(parsed[0]) == parsed[1]:
                errors.append(
                    SemanticError(
                        "INCOMPATIBLE_OPTIONS",
                        f"Option '{decision_id}.{option_id}' is incompatible with '{ref}'",
                        path,
                    )
                )

        # Check requires
        for ref in option.get("requires") or []:
            parsed = _parse_constraint_ref(ref)
            if parsed and universe_decisions.get(parsed[0]) != parsed[1]:
                actual = universe_decisions.get(parsed[0], "(not set)")
                errors.append(
                    SemanticError(
                        "MISSING_REQUIRED_OPTION",
                        f"Option '{decision_id}.{option_id}' requires '{ref}' but got '{actual}'",
                        path,
                    )
                )

    return errors


def validate_analysis_file(path: str | Path) -> list[SemanticError]:
    """Load and validate an analysis file."""
    path = Path(path)
    data = load_yaml(path)
    return validate_analysis(data, base_path=path.parent)


def validate_universe_file(
    universe_path: str | Path,
    analysis_path: str | Path,
) -> list[SemanticError]:
    """Load and validate a universe file against an analysis."""
    analysis_data = load_yaml(analysis_path)
    universe_data = load_yaml(universe_path)
    return validate_universe(universe_data, analysis_data)
