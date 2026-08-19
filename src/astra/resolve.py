"""Resolve an analysis into what a universe actually produces.

The rest of ASTRA answers questions *about* a spec: is it valid, what ids
does it declare, what are the defaults. This module answers the question a
consumer asks when it is about to act on one — **given this analysis and
this universe, what outputs are produced, from what, under which
decisions?**

Every rule applied here is already specified and already enforced by
``astra.validation.semantic``; what was missing is the resolving half. A
consumer that needs the answer has otherwise had to re-derive scoping,
``from:`` references, conditional outputs and the recipe grammar from the
schema — which is how two implementations of one specification start
disagreeing.

Scope and naming
----------------

Sub-analyses nest arbitrarily, so every resolved thing is named by its
**qualified id**: the scope path and the local id joined with ``.``, e.g.
``classification.accuracy``. A root-level id is unqualified. Since ids
match ``^[a-z][a-z0-9_]*$``, the dot is unambiguous.

Validity is assumed
-------------------

These functions resolve a spec that passes ``astra validate``. They do not
re-report validation errors: an input that nothing supplies resolves to a
``ResolvedInput`` with neither ``produced_by`` nor ``source``, rather than
raising. Diagnosis belongs to the validator, and duplicating it here would
be the same duplication this module exists to remove.
"""

from __future__ import annotations

import logging
import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from astra.helpers import (
    Scope,
    ancestor_at,
    external_spec_path,
    get_input,
    get_output_ids,
    is_condition_met,
    iter_analysis_nodes,
    load_yaml,
    parse_from_path,
)

__all__ = [
    "ResolvedInput",
    "ResolvedOutput",
    "iter_analysis_nodes",
    "parse_from_path",
    "render_command",
    "resolve_outputs",
    "resolve_universe",
]

logger = logging.getLogger(__name__)

_FORMATTER = string.Formatter()


def qualify(scope: Scope, local_id: str) -> str:
    """Join a scope path and a local id into a qualified id.

    Args:
        scope: The analysis path the id was declared in; empty at the root.
        local_id: The id as declared.

    Returns:
        ``"a.b.id"`` inside sub-analyses, or ``"id"`` at the root.
    """
    return ".".join((*scope, local_id))


# =============================================================================
# Universes
# =============================================================================


def resolve_universe(
    data: Mapping[str, Any],
    universe: Mapping[str, Any],
    base_path: Path | None = None,
) -> dict[str, str]:
    """Resolve a universe into every decision it settles, by qualified id.

    Three things are applied that a universe file does not state outright.
    A decision declared ``from: ../id`` takes the ancestor's chosen option,
    so an inherited decision has a value in the scope that uses it. A
    decision carrying ``when:`` is included only where its condition holds
    against the decisions already settled above it. And a sub-analysis's
    decisions come from the ``analyses.<id>.decisions`` block of the same
    universe file, nested to whatever depth the tree has.

    A sub-analysis node may also say ``universe: <name>`` instead of
    listing decisions inline, naming one of the universes in that
    sub-analysis's own ``universes/`` directory. Loading it needs
    *base_path*; without one the reference is skipped, since there is
    nothing to resolve it against.

    Args:
        data: The analysis, with external sub-analyses already resolved.
        universe: The universe, as loaded from ``universes/<id>.yaml``.
        base_path: The directory the analysis was loaded from, needed only
            to follow a sub-analysis's ``universe:`` reference.

    Returns:
        Qualified decision id → chosen option id. Root decisions are
        unqualified; a sub-analysis's are ``"<scope>.<decision_id>"``.
    """
    settled: dict[str, str] = {}
    _settle(data, universe, (), [], settled, base_path)
    return settled


def _selected_universe(
    node: Mapping[str, Any],
    universe_node: Mapping[str, Any],
    base_path: Path | None,
    where: str,
) -> Mapping[str, Any]:
    """Follow a ``universe:`` reference to the file it names.

    Only an external (``path:``) sub-analysis has a ``universes/``
    directory of its own, so only one can be referred to this way.
    Anything unresolvable leaves the node as it stands — a missing file is
    the validator's to report, not this module's to raise on — but it is
    logged, because ``semantic.py`` validates nothing about ``universe:``
    and silence here would leave a whole subtree unsettled with no
    diagnostic from either layer.
    """
    name = universe_node.get("universe")
    if not name:
        return universe_node
    sub_path = node.get("path")
    if not sub_path:
        logger.warning(
            "universe '%s' selected for '%s', which is an inline sub-analysis "
            "and has no universes/ directory to name it in",
            name,
            where,
        )
        return universe_node
    if base_path is None:
        return universe_node
    path = external_spec_path(base_path, str(sub_path)).parent / "universes" / f"{name}.yaml"
    if not path.is_file():
        logger.warning("universe '%s' selected for '%s' but %s does not exist", name, where, path)
        return universe_node
    loaded = load_yaml(path)
    # An empty or comment-only file parses to `None`; that is the
    # validator's to report, and this module promises not to raise on it.
    return loaded if isinstance(loaded, Mapping) else universe_node


def _settle(
    node: Mapping[str, Any],
    universe_node: Mapping[str, Any],
    scope: Scope,
    chain: list[dict[str, str]],
    settled: dict[str, str],
    base_path: Path | None,
) -> None:
    """Settle one node's decisions, then recurse into its sub-analyses.

    *chain* is what each ancestor settled, by that ancestor's **local**
    ids, root first — the view ``from:`` reads, since ``../`` counts
    scopes rather than searching them. ``when:`` reads the whole chain
    flattened, which is what the validator compares against.
    """
    declared = node.get("decisions") or {}
    chosen = {str(k): str(v) for k, v in (universe_node.get("decisions") or {}).items()}
    ancestors: dict[str, str] = {}
    for level in chain:
        ancestors.update(level)
    here: dict[str, str] = {}

    # `from:` first: an inherited decision is settled wherever its ancestor
    # settled it, and a conditional decision below may depend on one.
    for decision_id, decision in declared.items():
        if not isinstance(decision, dict):
            continue
        parsed = parse_from_path(str(decision.get("from") or "")) if decision.get("from") else None
        if parsed is None:
            continue
        up, segments = parsed
        target = ancestor_at(chain, up) if len(segments) == 1 else None
        if target is not None and segments[0] in target:
            here[str(decision_id)] = target[segments[0]]

    # A condition reads everything this universe settles at or above this
    # node, not just what happens to be declared before it — which is what
    # `_validate_universe_node` compares against.
    in_scope = {**ancestors, **chosen}
    for decision_id, decision in declared.items():
        name = str(decision_id)
        if name in here or name not in chosen:
            continue
        when = decision.get("when") if isinstance(decision, dict) else None
        if when and not is_condition_met(when, {**in_scope, **here}):
            continue
        here[name] = chosen[name]

    for name, option in here.items():
        settled[qualify(scope, name)] = option

    for sub_id, sub in (node.get("analyses") or {}).items():
        if not isinstance(sub, dict):
            continue
        sub_universe = (universe_node.get("analyses") or {}).get(str(sub_id)) or {}
        sub_universe = _selected_universe(sub, sub_universe, base_path, qualify(scope, str(sub_id)))
        sub_base = base_path
        if base_path is not None and sub.get("path"):
            sub_base = external_spec_path(base_path, str(sub["path"])).parent
        _settle(sub, sub_universe, (*scope, str(sub_id)), [*chain, here], settled, sub_base)


# =============================================================================
# Outputs
# =============================================================================


@dataclass(frozen=True)
class ResolvedInput:
    """One of an output's declared inputs, resolved to what supplies it.

    Exactly one of ``produced_by`` and ``source`` is set for a spec that
    validates; both are ``None`` when nothing supplies the input, which is
    ``UNKNOWN_INPUT``'s business rather than this module's.
    """

    #: The id as the consuming output declares it.
    id: str
    #: The qualified id of the output that makes it, re-exports followed
    #: through to whatever carries the recipe.
    produced_by: str | None
    #: The external source, for an input the analysis does not compute.
    source: str | None


@dataclass(frozen=True)
class ResolvedOutput:
    """One output of one universe, with everything it needs resolved."""

    #: The qualified id: ``"classification.accuracy"``.
    id: str
    #: The analysis path it was declared in; empty at the root.
    scope: Scope
    #: The output as the spec declares it.
    definition: dict[str, Any]
    #: ``recipe.command``, or ``None`` for a re-export or a declared-only
    #: output. This is the test of whether the output is executable.
    command: str | None
    #: The declared decisions and the options this universe chose, by the
    #: **local** id a recipe writes as ``{decisions.<id>}``.
    decisions: dict[str, str]
    #: The declared inputs, in declaration order.
    inputs: tuple[ResolvedInput, ...]
    #: For a re-export, the qualified id it stands for; ``None`` otherwise.
    reexports: str | None


def resolve_outputs(
    data: Mapping[str, Any],
    universe: Mapping[str, Any],
    base_path: Path | None = None,
) -> list[ResolvedOutput]:
    """Resolve every output this universe produces, anywhere in the tree.

    Outputs whose ``when:`` condition does not hold in this universe are
    **left out** — that is what makes them conditional. Everything else is
    returned, re-exports included, so ``command`` is the test of what a
    runner has to execute.

    Args:
        data: The analysis, with external sub-analyses already resolved.
        universe: The universe, as loaded from ``universes/<id>.yaml``.
        base_path: The directory the analysis was loaded from, needed only
            to follow a sub-analysis's ``universe:`` reference.

    Returns:
        Every active output, root scope first, in declaration order.
    """
    tree = _index(data, resolve_universe(data, universe, base_path))
    declared_here: list[tuple[str, Scope, dict[str, Any], dict[str, str]]] = []
    reexports: dict[str, str] = {}

    for scope, node in tree.nodes.items():
        local = tree.decisions.get(scope) or {}
        for declared in node.get("outputs") or []:
            if not isinstance(declared, dict) or not declared.get("id"):
                continue
            if not is_condition_met(declared.get("when") or None, local):
                continue
            qualified = qualify(scope, str(declared["id"]))
            target = _reexport_target(scope, str(declared.get("from") or ""))
            if target:
                reexports[qualified] = target
            declared_here.append((qualified, scope, declared, local))

    live = _live_ids({entry[0] for entry in declared_here}, reexports)
    resolved = [
        ResolvedOutput(
            id=qualified,
            scope=scope,
            definition=declared,
            command=(declared.get("recipe") or {}).get("command") or None,
            decisions={
                name: local[name] for name in declared.get("decisions") or [] if name in local
            },
            inputs=tuple(
                _resolve_input(tree, scope, str(name)) for name in declared.get("inputs") or []
            ),
            reexports=reexports.get(qualified),
        )
        for qualified, scope, declared, local in declared_here
        if qualified in live
    ]

    return [_follow(out, reexports) for out in resolved]


def _live_ids(declared: set[str], reexports: Mapping[str, str]) -> set[str]:
    """Drop every re-export of an output this universe does not produce.

    A re-export carries no ``when:`` of its own — it is exactly as
    conditional as the output it stands for, and returning one whose target
    was conditioned away would hand a runner a target it cannot build.
    Dropping cascades, since a re-export may stand for another.
    """
    live = set(declared)
    dropping = True
    while dropping:
        dropping = False
        for qualified, target in reexports.items():
            if qualified in live and target not in live:
                live.discard(qualified)
                dropping = True
    return live


@dataclass(frozen=True)
class _Index:
    """The analysis tree and its universe, keyed by scope.

    Resolving asks the same questions over and over: what node sits at
    this scope, does it declare this output, what did this scope settle.
    Answering each by re-scanning made resolving cost more than everything
    else in this module put together, and grew with the size of the tree
    *times* the number of outputs in it.
    """

    #: The node at each scope.
    nodes: dict[Scope, dict[str, Any]]
    #: The output ids each scope declares.
    output_ids: dict[Scope, set[str]]
    #: What each scope settled, by the local decision id.
    decisions: dict[Scope, dict[str, str]]


def _index(data: Mapping[str, Any], settled: Mapping[str, str]) -> _Index:
    """Walk the tree once, and the settled universe once, up front."""
    nodes = dict(iter_analysis_nodes(data))
    decisions: dict[Scope, dict[str, str]] = {}
    for key, option in settled.items():
        *scope, name = key.split(".")
        decisions.setdefault(tuple(scope), {})[name] = option
    return _Index(
        nodes=nodes,
        output_ids={scope: get_output_ids(node) for scope, node in nodes.items()},
        decisions=decisions,
    )


def _descent_target(scope: Scope, segments: Sequence[str]) -> tuple[Scope, str]:
    """Split a downward path into the scope it lands in and the id there."""
    return ((*scope, *(str(seg) for seg in segments[:-1])), str(segments[-1]))


def _reexport_target(scope: Scope, ref: str) -> str | None:
    """The qualified id an ``Output.from`` re-export stands for."""
    parsed = parse_from_path(ref) if ref else None
    if parsed is None:
        return None
    up, segments = parsed
    if up or len(segments) < 2:
        return None
    return qualify(*_descent_target(scope, segments))


def _resolve_input(tree: _Index, scope: Scope, name: str) -> ResolvedInput:
    """What supplies *name* for an output declared at *scope*.

    An output may name one of its own scope's outputs, or a sub-analysis's
    output qualified as ``sub.out_id``. Otherwise the name is one of the
    scope's declared inputs, which either carries a ``source:`` or points
    elsewhere with ``from:`` — upward to an ancestor's input, which is
    resolved in turn, or across to a sub-analysis's output.
    """
    if "." in name:
        # Ids match `^[a-z][a-z0-9_]*$`, so a dot only ever separates the
        # sub-analyses descended through from the output at the end.
        target, output_id = _descent_target(scope, name.split("."))
        if output_id in tree.output_ids.get(target, ()):
            return ResolvedInput(id=name, produced_by=qualify(target, output_id), source=None)
        return ResolvedInput(id=name, produced_by=None, source=None)

    if name in tree.output_ids.get(scope, ()):
        return ResolvedInput(id=name, produced_by=qualify(scope, name), source=None)
    return _resolve_declared_input(tree, scope, name)


def _resolve_declared_input(tree: _Index, scope: Scope, name: str) -> ResolvedInput:
    """What supplies one of *scope*'s own declared inputs.

    Kept apart from `_resolve_input` because ``from: ../id`` names an
    *input* of the ancestor scope — which `_validate_input_from` checks it
    against — and a same-named output there must not stand in for it.
    """
    declared = get_input(tree.nodes.get(scope) or {}, name)
    if declared is None:
        return ResolvedInput(id=name, produced_by=None, source=None)

    if ref := declared.get("from"):
        parsed = parse_from_path(str(ref))
        if parsed is None or not 0 < parsed[0] <= len(scope):
            return ResolvedInput(id=name, produced_by=None, source=None)
        up, segments = parsed
        target = scope[: len(scope) - up]
        if len(segments) == 1:
            # An ancestor's input, which may itself be sourced or aliased.
            inherited = _resolve_declared_input(tree, target, segments[0])
            return ResolvedInput(
                id=name, produced_by=inherited.produced_by, source=inherited.source
            )
        return ResolvedInput(
            id=name, produced_by=qualify(*_descent_target(target, segments)), source=None
        )

    source = declared.get("source")
    return ResolvedInput(id=name, produced_by=None, source=str(source) if source else None)


def _follow(out: ResolvedOutput, reexports: Mapping[str, str]) -> ResolvedOutput:
    """Point every ``produced_by`` past re-exports at what carries the recipe."""
    if not reexports:
        return out
    inputs = tuple(
        ResolvedInput(id=i.id, produced_by=_terminal(i.produced_by, reexports), source=i.source)
        for i in out.inputs
    )
    return ResolvedOutput(
        id=out.id,
        scope=out.scope,
        definition=out.definition,
        command=out.command,
        decisions=out.decisions,
        inputs=inputs,
        reexports=_terminal(out.reexports, reexports),
    )


def _terminal(qualified: str | None, reexports: Mapping[str, str]) -> str | None:
    """Chase a re-export chain to the output that actually produces bytes."""
    seen: set[str] = set()
    while qualified is not None and qualified in reexports and qualified not in seen:
        seen.add(qualified)
        qualified = reexports[qualified]
    return qualified


# =============================================================================
# Recipes
# =============================================================================


def render_command(
    command: str,
    *,
    inputs: Mapping[str, str],
    decisions: Mapping[str, str],
    output: str,
) -> str:
    """Substitute a recipe command's placeholders.

    The grammar ``_validate_command_template`` checks: ``{output}`` is
    where the output is written, ``{inputs}`` is every input's value in
    declaration order, and ``{inputs.<id>}`` / ``{decisions.<id>}`` are one
    of each. ``{{`` and ``}}`` are literal braces.

    Args:
        command: The command template as the spec declares it.
        inputs: Declared input id → the value to substitute, in
            declaration order.
        decisions: Decision id → the option this universe chose, by the
            local id the recipe writes.
        output: Where the output is written.

    Returns:
        The command with every placeholder substituted.

    Raises:
        ValueError: On an unknown placeholder, a reference the output does
            not declare, or a format spec. Substituting nothing silently
            would produce a command that runs and means something else.
    """
    pieces: list[str] = []
    available = {"inputs": inputs, "decisions": decisions}
    for literal, name, spec, conversion in _FORMATTER.parse(command):
        pieces.append(literal)
        if name is None:
            continue
        if spec or conversion:
            raise ValueError(f"command placeholder '{{{name}}}' takes no format spec")
        if name == "output":
            pieces.append(output)
            continue
        if name == "inputs":
            pieces.append(" ".join(inputs.values()))
            continue
        head, dot, tail = name.partition(".")
        if not dot or head not in available:
            raise ValueError(
                f"unknown command placeholder '{{{name}}}' (use {{inputs}}, "
                "{inputs.<id>}, {decisions.<id>}, or {output})"
            )
        if tail not in available[head]:
            raise ValueError(
                f"command placeholder '{{{name}}}' references undeclared "
                f"{head[:-1]} '{tail}' (add it to Output.{head})"
            )
        pieces.append(available[head][tail])
    return "".join(pieces)
