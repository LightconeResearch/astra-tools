"""§12 Universes: a universe's `derived_from` names another of its analysis's universes
(`UNKNOWN_DERIVED_FROM`) and its chain doesn't loop (`DERIVED_FROM_CYCLE`); its own `decisions`
set only decisions it uses on some branch (`UNUSED_DECISION`), and should set only those it uses
(`INACTIVE_DECISION`); its effective selection keeps every constraint of the options it selects,
among the decisions in play (`MISSING_REQUIRED_OPTION`, `INCOMPATIBLE_OPTIONS`), and selects no
excluded one (`EXCLUDED_OPTION_SELECTED`).

Every universe of every analysis of the stack is checked (§16 *What a validator checks*), on its
effective selection (`universes.selections`), with its own analysis driving (Results *uses*,
`Context.runs`). A universe uses on some branch each decision listed or switched on by what its
analysis would reach there were every case of every switch followed, and each that a universe
inheriting its key for it, without setting it, uses on some branch.

The constraints hold among the decisions in play: those the universe uses and, in another
analysis's universe, those that something the root reaches through a pin uses there (Results);
a decision outside these selects nothing, so a `requires` naming it fails and an
`incompatible_with` naming it holds. Constraints never make a decision used.

None of the last four is checked for a universe that has no effective selection (design §4.13
case 7), for a selection that names nothing, nor against a constraint that names nothing (case
5). Where a decision's use is undetermined (case 6), neither `INACTIVE_DECISION` nor a
constraint on or naming its options is checked; where what an analysis uses on some branch is
(an address or a pin on the way names nothing), `UNUSED_DECISION` isn't checked on its
universes' keys. It is checked on a universe with no effective selection, as it doesn't turn on
the selection.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from astra import model
from astra.diagnostics import Diagnostic, Location
from astra.rules.context import Context
from astra.stack import Element, Resolution, Stack
from astra.universes import Selection, names_option, options, own_keys, own_universes

CODES = frozenset(
    {
        "UNKNOWN_DERIVED_FROM",
        "DERIVED_FROM_CYCLE",
        "UNUSED_DECISION",
        "INACTIVE_DECISION",
        "MISSING_REQUIRED_OPTION",
        "INCOMPATIBLE_OPTIONS",
        "EXCLUDED_OPTION_SELECTED",
    }
)

Constraints = Mapping[tuple[str, Element, str], tuple[Resolution, ...]]
"""Each option's `requires` and `incompatible_with`, by the field, the decision and the option."""


def check(context: Context) -> Iterator[Diagnostic]:
    for member, analysis in context.stack.determined():
        for id_, written in analysis.universes.items():
            if written.derived_from is not None:
                at = context.at(member.identity, ("universes", id_, "derived_from"))
                yield from _derived_from(context, analysis, id_, written.derived_from, at)
    yield from _unused(context)
    constraints = _constraints(context.stack)
    pinned = _pinned(context)
    for selection in context.selections.values():
        if selection is not None:
            universe = selection.universe
            play = context.used(universe) | pinned.get(universe, frozenset())
            maybe = context.maybe(universe)
            for entry in selection.entries:
                if names_option(context.stack, entry):
                    yield from _selected(context, constraints, selection, entry, play, maybe)


def _unused(context: Context) -> Iterator[Diagnostic]:
    """`UNUSED_DECISION` and `INACTIVE_DECISION` on each universe's own keys (Results *uses on
    some branch*, *uses*)."""
    stack = context.stack
    blind = frozenset().union(*(run.blind for run in context.runs.values()))
    for member, _ in stack.determined():
        run = context.runs[member.identity]
        universes = own_universes(stack, member.identity)
        for universe in universes:
            selection = context.selections[universe]
            for key in own_keys(stack, universe):
                decision = key.element
                if decision is None:
                    continue
                inheriting = [
                    other
                    for other in universes
                    if (found := context.selections[other]) is not None
                    and other != universe
                    and any(entry is key for entry in found.entries)
                ]
                on_branch = decision in run.branches.get(universe, frozenset()) or any(
                    decision in run.branches.get(other, frozenset()) for other in inheriting
                )
                location = context.at(key.file, key.pointer, key.key)
                if not on_branch:
                    if member.identity not in blind:
                        message = (
                            f"`{universe.id}` sets `{key.key}`, which no branch of this "
                            f"analysis uses in `{universe.id}`: nothing it can plan there, "
                            "whatever case each switch takes, lists or switches on it, nor in a "
                            "universe that inherits the key. Remove the key"
                        )
                        yield context.diagnostic("UNUSED_DECISION", message, location)
                    continue
                if selection is None or decision in context.used(universe):
                    continue
                if decision in context.maybe(universe):
                    continue
                message = (
                    f"`{universe.id}` sets `{key.key}`, which it doesn't use: it is used only "
                    "where a switch takes another case, or in a universe that inherits the key. "
                    "Set it only in the universes that use it"
                )
                yield context.diagnostic("INACTIVE_DECISION", message, location)


def _pinned(context: Context) -> Mapping[Element, frozenset[Element]]:
    """For each universe of another analysis than the root that a pin the root reaches names,
    the decisions that what is reached through such pins uses there (Results; `Run.pins`)."""
    root = context.stack.root
    found: dict[Element, frozenset[Element]] = {}
    for pin in context.runs[root].pins:
        found[pin.universe] = found.get(pin.universe, frozenset()) | pin.uses
    return found


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
    it isn't, though its chain may reach one: only a universe on the loop breaks
    DERIVED_FROM_CYCLE (§12)."""
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
    context: Context,
    constraints: Constraints,
    selection: Selection,
    entry: Resolution,
    play: frozenset[Element],
    maybe: frozenset[Element],
) -> Iterator[Diagnostic]:
    """The rules on one selection of an effective selection: its constraints only where its
    decision is in `play` and its use isn't undetermined (`maybe`)."""
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
    if decision not in play or decision in maybe:
        return
    for required in constraints.get(("requires", decision, option), ()):
        if not names_option(stack, required) or required.element in maybe:
            continue
        if not _selects(selection, required, play):
            message = f"{selects}, which requires `{required.written}`, and it isn't selected"
            if required.element not in play:
                message += f": `{universe}` doesn't use its decision, so selects no option of it"
            where = context.at(required.file, required.pointer)
            yield context.diagnostic("MISSING_REQUIRED_OPTION", message, at, [*related, where])
    for refused in constraints.get(("incompatible_with", decision, option), ()):
        if not names_option(stack, refused) or refused.element in maybe:
            continue
        if _selects(selection, refused, play):
            message = f"{selects}, which is incompatible with `{refused.written}`, selected too"
            where = context.at(refused.file, refused.pointer)
            yield context.diagnostic("INCOMPATIBLE_OPTIONS", message, at, [*related, where])


def _selects(selection: Selection, constraint: Resolution, play: frozenset[Element]) -> bool:
    """Whether `selection` selects the option `constraint` names: a decision out of `play`
    selects none."""
    decision = constraint.element
    assert decision is not None
    return decision in play and constraint.option in selection.options(decision)


def _at(
    context: Context, selection: Selection, entry: Resolution
) -> tuple[Location, list[Location]]:
    """Where a rule broken by a selection is reported, and the places related: at its key, where
    the universe sets it itself; or at the universe's `derived_from`, with the key where it is
    written beside it, where the universe inherits it (design §3)."""
    written = context.at(entry.file, entry.pointer, entry.key)
    if selection.own(entry):
        return written, []
    universe = selection.universe
    return context.at(universe.analysis, ("universes", universe.id, "derived_from")), [written]
