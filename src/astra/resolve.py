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

import string
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from astra.helpers import is_condition_met, parse_from_path

__all__ = [
    "ResolvedInput",
    "ResolvedOutput",
    "iter_analysis_nodes",
    "parse_from_path",
    "render_command",
    "resolve_outputs",
    "resolve_universe",
]

_FORMATTER = string.Formatter()

Scope = tuple[str, ...]


def qualify(scope: Scope, local_id: str) -> str:
    """Join a scope path and a local id into a qualified id.

    Args:
        scope: The analysis path the id was declared in; empty at the root.
        local_id: The id as declared.

    Returns:
        ``"a.b.id"`` inside sub-analyses, or ``"id"`` at the root.
    """
    return ".".join((*scope, local_id))


def iter_analysis_nodes(data: Mapping[str, Any]) -> Iterator[tuple[Scope, dict[str, Any]]]:
    """Yield every node in the analysis tree with the scope it sits at.

    The root comes first, with an empty scope, then each sub-analysis
    depth-first. Unlike ``iter_sub_analyses`` this yields the scope path —
    which is what lets anything declared inside a sub-analysis be named
    unambiguously — and it descends into external (``path:``)
    sub-analyses, whose content ``resolve_analysis_tree`` has already
    inlined by the time this runs.

    Args:
        data: The analysis, with external sub-analyses already resolved.

    Yields:
        ``(scope, node)`` pairs, root first.
    """
    yield ((), dict(data))
    yield from _descend(data, ())


def _descend(node: Mapping[str, Any], scope: Scope) -> Iterator[tuple[Scope, dict[str, Any]]]:
    for sub_id, sub in (node.get("analyses") or {}).items():
        if not isinstance(sub, dict):
            continue
        here = (*scope, str(sub_id))
        yield (here, sub)
        yield from _descend(sub, here)


# =============================================================================
# Universes
# =============================================================================


def resolve_universe(data: Mapping[str, Any], universe: Mapping[str, Any]) -> dict[str, str]:
    """Resolve a universe into every decision it settles, by qualified id.

    Three things are applied that a universe file does not state outright.
    A decision declared ``from: ../id`` takes the ancestor's chosen option,
    so an inherited decision has a value in the scope that uses it. A
    decision carrying ``when:`` is included only where its condition holds
    against the decisions already settled above it. And a sub-analysis's
    decisions come from the ``analyses.<id>.decisions`` block of the same
    universe file, nested to whatever depth the tree has.

    Args:
        data: The analysis, with external sub-analyses already resolved.
        universe: The universe, as loaded from ``universes/<id>.yaml``.

    Returns:
        Qualified decision id → chosen option id. Root decisions are
        unqualified; a sub-analysis's are ``"<scope>.<decision_id>"``.
    """
    settled: dict[str, str] = {}
    _settle(data, universe, (), [], settled)
    return settled


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
        if len(segments) != 1 or not 0 < up <= len(chain):
            continue
        target = chain[len(chain) - up]
        if segments[0] in target:
            here[str(decision_id)] = target[segments[0]]

    for decision_id, decision in declared.items():
        name = str(decision_id)
        if name in here or name not in chosen:
            continue
        when = decision.get("when") if isinstance(decision, dict) else None
        if when and not is_condition_met(when, {**ancestors, **here}):
            continue
        here[name] = chosen[name]

    for name, option in here.items():
        settled[qualify(scope, name)] = option

    for sub_id, sub in (node.get("analyses") or {}).items():
        if not isinstance(sub, dict):
            continue
        sub_universe = (universe_node.get("analyses") or {}).get(str(sub_id)) or {}
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


def resolve_outputs(data: Mapping[str, Any], universe: Mapping[str, Any]) -> list[ResolvedOutput]:
    """Resolve every output this universe produces, anywhere in the tree.

    Outputs whose ``when:`` condition does not hold in this universe are
    **left out** — that is what makes them conditional. Everything else is
    returned, re-exports included, so ``command`` is the test of what a
    runner has to execute.

    Args:
        data: The analysis, with external sub-analyses already resolved.
        universe: The universe, as loaded from ``universes/<id>.yaml``.

    Returns:
        Every active output, root scope first, in declaration order.
    """
    settled = resolve_universe(data, universe)
    nodes = dict(iter_analysis_nodes(data))
    resolved: list[ResolvedOutput] = []
    reexports: dict[str, str] = {}

    for scope, node in nodes.items():
        local = _scope_decisions(settled, scope)
        for declared in node.get("outputs") or []:
            if not isinstance(declared, dict) or not declared.get("id"):
                continue
            if not is_condition_met(declared.get("when") or None, local):
                continue
            output_id = str(declared["id"])
            target = _reexport_target(scope, str(declared.get("from") or ""))
            if target:
                reexports[qualify(scope, output_id)] = target
            resolved.append(
                ResolvedOutput(
                    id=qualify(scope, output_id),
                    scope=scope,
                    definition=declared,
                    command=(declared.get("recipe") or {}).get("command") or None,
                    decisions={
                        name: local[name]
                        for name in declared.get("decisions") or []
                        if name in local
                    },
                    inputs=tuple(
                        _resolve_input(nodes, scope, str(name))
                        for name in declared.get("inputs") or []
                    ),
                    reexports=target,
                )
            )

    return [_follow(out, reexports) for out in resolved]


def _scope_decisions(settled: Mapping[str, str], scope: Scope) -> dict[str, str]:
    """The decisions settled *in* one scope, by their local ids."""
    return {
        key.rsplit(".", 1)[-1]: value
        for key, value in settled.items()
        if tuple(key.split(".")[:-1]) == scope
    }


def _reexport_target(scope: Scope, ref: str) -> str | None:
    """The qualified id an ``Output.from`` re-export stands for."""
    parsed = parse_from_path(ref) if ref else None
    if parsed is None:
        return None
    up, segments = parsed
    if up or len(segments) < 2:
        return None
    return qualify((*scope, *segments[:-1]), segments[-1])


def _resolve_input(
    nodes: Mapping[Scope, Mapping[str, Any]], scope: Scope, name: str
) -> ResolvedInput:
    """What supplies *name* for an output declared at *scope*.

    An input naming an output of its own scope is that output. Otherwise
    it is one of the scope's declared inputs, which either carries a
    ``source:`` or points elsewhere with ``from:`` — upward to an
    ancestor's input, which is resolved in turn, or across to a
    sub-analysis's output.
    """
    node = nodes.get(scope) or {}
    if any(str(o.get("id")) == name for o in node.get("outputs") or [] if isinstance(o, dict)):
        return ResolvedInput(id=name, produced_by=qualify(scope, name), source=None)

    declared = next(
        (i for i in node.get("inputs") or [] if isinstance(i, dict) and str(i.get("id")) == name),
        None,
    )
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
            inherited = _resolve_input(nodes, target, segments[0])
            return ResolvedInput(
                id=name, produced_by=inherited.produced_by, source=inherited.source
            )
        return ResolvedInput(
            id=name,
            produced_by=qualify((*target, *segments[:-1]), segments[-1]),
            source=None,
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
