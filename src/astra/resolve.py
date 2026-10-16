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

Across universes
----------------

Some outputs don't depend on a universe at all - one with no decisions and
no ``when`` whose inputs are all pinned (``artifact#universe``) or external.
``References`` works out which outputs are built per universe and which are
built once. ``plan`` lists every output to build across the declared
universes with where each result goes and what it reads.
"""

from __future__ import annotations

import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from astra.helpers import (
    Scope,
    ancestor_at,
    get_input,
    get_output_ids,
    is_condition_met,
    iter_analysis_nodes,
    parse_from_path,
)
from astra.universes import declared_universes, effective_universe

__all__ = [
    "PlannedOutput",
    "References",
    "ResolvedInput",
    "ResolvedOutput",
    "iter_analysis_nodes",
    "parse_from_path",
    "plan",
    "render_command",
    "resolve_outputs",
    "resolve_universe",
    "split_pin",
]

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
) -> dict[str, str]:
    """Resolve a universe into every decision it settles, by qualified id.

    Three things are applied that a universe does not state outright.
    A decision declared ``from: ../id`` takes the ancestor's chosen option,
    so an inherited decision has a value in the scope that uses it. A
    decision carrying ``when:`` is included only where its condition holds
    against the decisions already settled above it. And a sub-analysis's
    decisions come from the ``analyses.<id>.decisions`` block of the same
    universe, nested to whatever depth the tree has.

    A sub-analysis entry may also say ``universe: <id>`` instead of listing
    decisions, naming one of the universes that sub-analysis declares in
    its own ``universes`` list.

    Args:
        data: The analysis, with external sub-analyses already resolved.
        universe: The universe's effective selection (see
            ``astra.universes.effective_universe``).

    Returns:
        Qualified decision id → chosen option id. Root decisions are
        unqualified; a sub-analysis's are ``"<scope>.<decision_id>"``.
    """
    settled: dict[str, str] = {}
    _settle(data, universe, (), [], settled)
    return settled


def _selected_universe(
    node: Mapping[str, Any],
    universe_node: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Follow a ``universe:`` entry to the universe it names.

    The id names one of the universes the sub-analysis declares, and its
    effective selection stands in for the entry. An id that isn't declared
    leaves the entry as it is - ``UNKNOWN_SUB_UNIVERSE`` is the validator's
    to report.
    """
    name = universe_node.get("universe")
    if not name:
        return universe_node
    effective = effective_universe(node, str(name))
    return effective.selection if effective is not None else universe_node


def _settle(
    node: Mapping[str, Any],
    universe_node: Mapping[str, Any],
    scope: Scope,
    chain: list[dict[str, str]],
    settled: dict[str, str],
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
        sub_universe = _selected_universe(sub, sub_universe)
        _settle(sub, sub_universe, (*scope, str(sub_id)), [*chain, here], settled)


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
    #: The universe the entry is pinned to (``artifact#universe``) if any.
    pin: str | None = None


@dataclass(frozen=True)
class ResolvedOutput:
    """One output of one universe, with everything it needs resolved."""

    #: The qualified id: ``"classification.accuracy"``.
    id: str
    #: The analysis path it was declared in; empty at the root.
    scope: Scope
    #: The output as the spec declares it.
    definition: dict[str, Any]
    #: The declared serialization (``png``, ``csv``, ``parquet``, …), or
    #: ``None`` when the spec omits it. A re-export inherits the format of
    #: the output it stands for, so this is the terminal output's format,
    #: not the (necessarily absent) one on the alias.
    format: str | None
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
    #: Whether it's built once per universe - ``False`` for an output built once.
    per_universe: bool = True


def resolve_outputs(
    data: Mapping[str, Any],
    universe: Mapping[str, Any],
) -> list[ResolvedOutput]:
    """Resolve every output this universe produces, anywhere in the tree.

    Outputs whose ``when:`` condition does not hold in this universe are
    **left out** — that is what makes them conditional. Everything else is
    returned, re-exports included, so ``command`` is the test of what a
    runner has to execute.

    Args:
        data: The analysis, with external sub-analyses already resolved.
        universe: The universe's effective selection (see
            ``astra.universes.effective_universe``).

    Returns:
        Every active output, root scope first, in declaration order.
    """
    tree = _index(data, resolve_universe(data, universe))
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
    refs = References(data)
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
                _resolve_pinned_input(tree, scope, str(name))
                for name in declared.get("inputs") or []
            ),
            reexports=reexports.get(qualified),
            format=None,  # filled in by _follow, which knows the terminal output
            per_universe=refs.per_universe(qualified),
        )
        for qualified, scope, declared, local in declared_here
        if qualified in live
    ]

    definitions = {qualified: declared for qualified, _, declared, _ in declared_here}
    return [_follow(out, reexports, definitions) for out in resolved]


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


def _resolve_pinned_input(tree: _Index, scope: Scope, entry: str) -> ResolvedInput:
    """What an ``inputs`` entry reads, its pin set aside and kept on the result."""
    artifact, pin = split_pin(entry)
    found = _resolve_input(tree, scope, artifact)
    return ResolvedInput(id=entry, produced_by=found.produced_by, source=found.source, pin=pin)


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


def _follow(
    out: ResolvedOutput,
    reexports: Mapping[str, str],
    definitions: Mapping[str, Mapping[str, Any]],
) -> ResolvedOutput:
    """Point every ``produced_by`` past re-exports at what carries the recipe.

    Also settles ``format``: a re-export declares none of its own — the
    schema forbids it — so it takes the terminal output's.
    """
    terminal = _terminal(out.reexports, reexports)
    source = definitions.get(terminal, out.definition) if terminal else out.definition
    declared_format = source.get("format")
    inputs = tuple(
        ResolvedInput(
            id=i.id,
            produced_by=_terminal(i.produced_by, reexports),
            source=i.source,
            pin=i.pin,
        )
        for i in out.inputs
    )
    return ResolvedOutput(
        id=out.id,
        scope=out.scope,
        definition=out.definition,
        command=out.command,
        decisions=out.decisions,
        inputs=inputs,
        reexports=terminal,
        format=str(declared_format) if declared_format else None,
        per_universe=out.per_universe,
    )


def _terminal(qualified: str | None, reexports: Mapping[str, str]) -> str | None:
    """Chase a re-export chain to the output that actually produces bytes."""
    seen: set[str] = set()
    while qualified is not None and qualified in reexports and qualified not in seen:
        seen.add(qualified)
        qualified = reexports[qualified]
    return qualified


# =============================================================================
# References and scoping
# =============================================================================


def split_pin(entry: str) -> tuple[str, str | None]:
    """Splits ``artifact#universe`` into the artifact and its pin.

    The pin is ``None`` for an entry without one.
    """
    artifact, hash_, pin = entry.partition("#")
    return artifact, (pin if hash_ else None)


class References:
    """What the references in an analysis point at, and which of its outputs
    are built per universe.

    Both depend on the analysis's shape rather than on any one universe, so
    they're worked out once for all of them. An output is built per universe
    if it declares ``decisions``, has a ``when`` or reads an unpinned entry
    that resolves to an output built per universe. A re-export is whatever it
    stands for (unless its own ``when`` makes it per universe). Pins and
    external inputs never make an output per universe. A dependency cycle -
    an error the validator reports - counts as built once rather than
    recursing forever.
    """

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._tree = _index(data, {})
        self._outputs: dict[str, tuple[Scope, dict[str, Any]]] = {}
        self._reexports: dict[str, str] = {}
        for scope, node in self._tree.nodes.items():
            for declared in node.get("outputs") or []:
                if not isinstance(declared, dict) or not declared.get("id"):
                    continue
                qualified = qualify(scope, str(declared["id"]))
                self._outputs[qualified] = (scope, declared)
                target = _reexport_target(scope, str(declared.get("from") or ""))
                if target:
                    self._reexports[qualified] = target
        self._per_universe: dict[str, bool] = {}

    def outputs(self) -> list[tuple[str, Scope, dict[str, Any]]]:
        """Every output in the tree as (qualified id, scope, definition)."""
        return [(q, scope, declared) for q, (scope, declared) in self._outputs.items()]

    def resolve(self, scope: Scope, entry: str) -> ResolvedInput:
        """What an ``inputs`` entry declared at *scope* reads.

        The pin is set aside (and kept on the result) and re-exports are
        followed to the output that carries the recipe.
        """
        artifact, pin = split_pin(entry)
        found = _resolve_input(self._tree, scope, artifact)
        return ResolvedInput(
            id=entry,
            produced_by=_terminal(found.produced_by, self._reexports),
            source=found.source,
            pin=pin,
        )

    def is_external(self, scope: Scope, entry: str) -> bool:
        """Whether an entry reads an input the analysis doesn't compute.

        That includes an input aliased with ``from:`` to an ancestor's
        external input, and one declared without a ``source``.
        """
        artifact, _ = split_pin(entry)
        if "." in artifact or self.resolve(scope, entry).produced_by is not None:
            return False
        return get_input(self._tree.nodes.get(scope) or {}, artifact) is not None

    def per_universe(self, qualified: str) -> bool:
        """Whether the output *qualified* is built once per universe."""
        if qualified not in self._per_universe:
            self._per_universe[qualified] = False
            self._per_universe[qualified] = self._depends_on_a_universe(qualified)
        return self._per_universe[qualified]

    def _depends_on_a_universe(self, qualified: str) -> bool:
        scope, declared = self._outputs.get(qualified, ((), {}))
        if declared.get("when"):
            return True
        if qualified in self._reexports:
            target = _terminal(qualified, self._reexports)
            return target is not None and target != qualified and self.per_universe(target)
        if declared.get("decisions"):
            return True
        for entry in declared.get("inputs") or []:
            if split_pin(str(entry))[1] is not None:
                continue
            produced_by = self.resolve(scope, str(entry)).produced_by
            if produced_by is not None and self.per_universe(produced_by):
                return True
        return False


# =============================================================================
# Plan
# =============================================================================


@dataclass(frozen=True)
class PlannedOutput:
    """One output to build - in one universe or once for all of them.

    ``analysis`` is the id of the analysis being planned (``None`` if it
    declares none) and ``universe`` the universe the output is built in -
    ``None`` for an output built once. ``path`` is where its result goes and
    ``reads`` maps each of its ``inputs`` entries, as written, to the path it
    reads: a result path for an output and the declared ``source`` for an
    external input. ``output`` is the output resolved in that universe, whose
    ``command`` and ``decisions`` a runner passes to ``render_command``.
    """

    analysis: str | None
    universe: str | None
    path: str
    reads: dict[str, str]
    output: ResolvedOutput


def plan(data: Mapping[str, Any]) -> list[PlannedOutput]:
    """Every output to build, with where it goes and what it reads.

    An output built per universe is planned once for each universe the
    analysis declares where it's active. An output built once is planned once
    with no universe. Re-exports are left out as they make no file of their
    own.

    Results go in ``results/{universe}/{id}.{format}`` and outputs built once
    in ``results/{id}.{format}`` where ``id`` is the qualified id (e.g.
    ``classification.accuracy``). The layout is provisional - the layout RFC
    decides it.

    Args:
        data: The analysis, with external sub-analyses already resolved.

    Returns:
        The outputs built once first and then each universe's in the order
        the universes are declared.
    """
    refs = References(data)
    formats = {qualified: declared.get("format") for qualified, _, declared in refs.outputs()}
    analysis = str(data["id"]) if data.get("id") else None

    def result_path(qualified: str, universe: str | None) -> str:
        fmt = formats.get(qualified)
        name = f"{qualified}.{fmt}" if fmt else qualified
        return f"results/{universe}/{name}" if universe else f"results/{name}"

    def planned(out: ResolvedOutput, universe: str | None) -> PlannedOutput:
        reads: dict[str, str] = {}
        for i in out.inputs:
            if i.produced_by is not None:
                built_in = (i.pin or universe) if refs.per_universe(i.produced_by) else None
                reads[i.id] = result_path(i.produced_by, built_in)
            elif i.source is not None:
                reads[i.id] = i.source
        return PlannedOutput(
            analysis=analysis,
            universe=universe,
            path=result_path(out.id, universe),
            reads=reads,
            output=out,
        )

    entries = [
        planned(out, None)
        for out in resolve_outputs(data, {})
        if not out.reexports and not out.per_universe
    ]
    for universe_id in declared_universes(data):
        effective = effective_universe(data, universe_id)
        if effective is None:
            continue
        entries.extend(
            planned(out, universe_id)
            for out in resolve_outputs(data, effective.selection)
            if not out.reexports and out.per_universe
        )
    return entries


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
