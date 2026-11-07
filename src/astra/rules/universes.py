"""§12 Universes: a universe's `derived_from` names another of its analysis's universes
(`UNKNOWN_DERIVED_FROM`) and its chain doesn't loop (`DERIVED_FROM_CYCLE`); its effective
selection keeps every constraint of the options it selects (`MISSING_REQUIRED_OPTION`,
`INCOMPATIBLE_OPTIONS`) and selects no excluded one (`EXCLUDED_OPTION_SELECTED`); and what it sets
itself is active there (`INACTIVE_DECISION`).

Every universe of every analysis of the stack is checked (§16 *What a validator checks*), on its
effective selection (`universes.selections`). None of the last four is checked for a universe
that has none (Annex D case 7), for a selection that names nothing, nor against a constraint
that names nothing (case 5), nor `INACTIVE_DECISION` for a decision whose activity is
undetermined (case 6).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from astra import model
from astra.diagnostics import Diagnostic, Location
from astra.rules.context import Context
from astra.stack import Element, Resolution, Stack
from astra.universes import Selection, names_option, options, when

CODES = frozenset(
    {
        "UNKNOWN_DERIVED_FROM",
        "DERIVED_FROM_CYCLE",
        "MISSING_REQUIRED_OPTION",
        "INCOMPATIBLE_OPTIONS",
        "EXCLUDED_OPTION_SELECTED",
        "INACTIVE_DECISION",
    }
)

Constraints = Mapping[tuple[str, Element, str], tuple[Resolution, ...]]
"""Each option's `requires` and `incompatible_with`, by the field, the decision and the option."""


def check(context: Context) -> Iterator[Diagnostic]:
    for member, analysis in context.stack.determined():
        for id_, universe in analysis.universes.items():
            if universe.derived_from is not None:
                at = context.at(member.identity, ("universes", id_, "derived_from"))
                yield from _derived_from(context, analysis, id_, universe.derived_from, at)
    constraints = _constraints(context.stack)
    for selection in context.selections.values():
        if selection is not None:
            for entry in selection.entries:
                if names_option(context.stack, entry):
                    yield from _selected(context, constraints, selection, entry)


def _derived_from(
    context: Context, analysis: model.Analysis, id_: str, named: str, at: Location
) -> Iterator[Diagnostic]:
    entry = analysis.universes.get(named)
    if entry is None:
        message = f"`{id_}` derives from `{named}`, which isn't a universe of this analysis"
        yield context.diagnostic("UNKNOWN_DERIVED_FROM", message, at)
    elif entry.is_import:
        message = (
            f"`{id_}` derives from `{named}`, an import: a universe derives only from another "
            "of its own analysis's universes, and an import selects nothing"
        )
        yield context.diagnostic("UNKNOWN_DERIVED_FROM", message, at)
    else:
        loop = _loop(analysis, id_)
        if loop is not None:
            message = (
                f"`{id_}`'s chain of `derived_from` loops ({' → '.join(loop)}): give one "
                "universe on the loop its whole selection, without `derived_from`"
            )
            yield context.diagnostic("DERIVED_FROM_CYCLE", message, at)


def _loop(analysis: model.Analysis, id_: str) -> tuple[str, ...] | None:
    """The chain of `derived_from` from `id_` back to it, where `id_` is on a loop; None where
    it isn't, though its chain may reach one. OPEN(O19): only a universe on the loop breaks
    DERIVED_FROM_CYCLE."""
    chain = [id_]
    while True:
        named = analysis.universes[chain[-1]].derived_from
        entry = None if named is None else analysis.universes.get(named)
        if named is None or entry is None or entry.is_import:
            return None
        if named == id_:
            return (*chain, named)
        if named in chain:
            return None
        chain.append(named)


def _constraints(stack: Stack) -> Constraints:
    found: dict[tuple[str, Element, str], list[Resolution]] = {}
    for resolution in stack.resolutions:
        if resolution.field in ("requires", "incompatible_with"):
            owner, option = resolution.owner, str(resolution.pointer[3])  # the option holding it
            assert owner is not None
            found.setdefault((resolution.field, owner, option), []).append(resolution)
    return {key: tuple(entries) for key, entries in found.items()}


def _selected(
    context: Context, constraints: Constraints, selection: Selection, entry: Resolution
) -> Iterator[Diagnostic]:
    """The rules on one selection of an effective selection."""
    decision, option = entry.element, entry.option
    assert decision is not None and option is not None
    stack, universe = context.stack, selection.universe.id
    selects = f"`{universe}` selects `{entry.key}: {option}`"
    if not selection.own(entry):
        assert entry.owner is not None  # the universe whose own `decisions` set it
        selects = f"`{universe}` inherits `{entry.key}: {option}` from `{entry.owner.id}`"
    at, related = _at(context, selection, entry)
    reason = options(stack, decision)[option].excluded
    if reason is not None:
        message = f"{selects}, which is excluded: {reason}"
        yield context.diagnostic("EXCLUDED_OPTION_SELECTED", message, at, related)
    for required in constraints.get(("requires", decision, option), ()):
        if names_option(stack, required) and not _selects(selection, required):
            message = f"{selects}, which requires `{required.written}`, and it isn't selected"
            where = context.at(required.file, required.pointer)
            yield context.diagnostic("MISSING_REQUIRED_OPTION", message, at, [*related, where])
    for refused in constraints.get(("incompatible_with", decision, option), ()):
        if names_option(stack, refused) and _selects(selection, refused):
            message = f"{selects}, which is incompatible with `{refused.written}`, selected too"
            where = context.at(refused.file, refused.pointer)
            yield context.diagnostic("INCOMPATIBLE_OPTIONS", message, at, [*related, where])
    if selection.own(entry) and context.activity(selection.universe, decision) is False:
        conditions = ", ".join(f"`{condition}`" for condition in when(stack, decision))
        message = (
            f"`{universe}` sets `{entry.key}` itself, though it isn't active there: its `when` "
            f"({conditions}) doesn't hold in `{universe}`'s effective selection"
        )
        yield context.diagnostic("INACTIVE_DECISION", message, at)


def _selects(selection: Selection, constraint: Resolution) -> bool:
    assert constraint.element is not None
    return constraint.option in selection.options(constraint.element)


def _at(
    context: Context, selection: Selection, entry: Resolution
) -> tuple[Location, list[Location]]:
    """Where a rule broken by a selection is reported, and the places related: at its key, where
    the universe sets it itself; or at the universe's `derived_from`, with the key where it is
    written beside it, where the universe inherits it. OPEN(O17)"""
    written = context.at(entry.file, entry.pointer, entry.key)
    if selection.own(entry):
        return written, []
    universe = selection.universe
    return context.at(universe.analysis, ("universes", universe.id, "derived_from")), [written]
