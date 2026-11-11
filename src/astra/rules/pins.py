"""§13 Pins (Rules `PIN_NOT_BUILT`): every pinned output, or switch, is built in the universe it is
pinned to, in `inputs`, in `cases` and in `artifact`; and a universe of an analysis other than the
driving analysis, named by a pin the root reaches, sets every decision, of its analysis and of
those its universes drive, that something reached through that pin uses there and the universe
doesn't use itself.

The first is judged on every pin written, whether anything reaches it or not; not where the pin
names no universe (design §4.13 case 5) or one with no effective selection (case 7), nor where
the target is on a cycle (case 13) or undetermined in that universe (case 6): there the cause is
reported. The second is judged on the pins the root's run follows (`Run.pins`), with the
universe's own use from its own analysis's run, so that a decision it uses itself is left to
`MISSING_DECISION`, reported in its own file; not for a decision whose use there is
undetermined (case 6), nor for one of an analysis not built there, which
`NOT_BUILT_IN_UNIVERSE` judges.
"""

from __future__ import annotations

from collections.abc import Iterator

from astra.diagnostics import Diagnostic
from astra.rules.context import Context
from astra.universes import built

CODES = frozenset({"PIN_NOT_BUILT"})


def check(context: Context) -> Iterator[Diagnostic]:
    yield from _not_built(context)
    yield from _unset(context)


def _not_built(context: Context) -> Iterator[Diagnostic]:
    """Each pinned reference to an output or a switch that isn't built in the universe its pin
    names, with the switch that has no case there."""
    for entry in context.stack.resolutions:
        element = entry.element
        if entry.pin is None or entry.field not in ("inputs", "case", "artifact"):
            continue
        if element is None or element.kind == "input" or context.on_cycle(element):
            continue
        universe = context.pins[entry]
        if universe is None or context.selections.get(universe) is None:
            continue
        if context.built(element, universe) is not False:
            continue
        cause = context.meaning.cause(element, universe)
        assert cause is not None  # what isn't built has a switch with no case on its way
        named = context.named([universe], entry.file)
        where = context.named([cause.universe], cause.switch.analysis)
        message = (
            f"`{entry.written}` pins `{entry.address}` to {named}, where it isn't built: "
            f"`{cause.switch.id}` has no case in {where} for `{cause.option}`, the option its "
            "decision selects there. Pin a universe where it is built"
        )
        yield context.diagnostic("PIN_NOT_BUILT", message, context.at(entry.file, entry.pointer))


def _unset(context: Context) -> Iterator[Diagnostic]:
    """Each pin the root reaches into a universe of another analysis, where something reached
    through it uses decisions that the universe neither uses nor sets."""
    stack = context.stack
    for pin in context.runs[stack.root].pins:
        universe = pin.universe
        selection = context.selections.get(universe)
        if selection is None:
            continue
        analyses = built(context.driven[universe.analysis], universe.analysis)
        used, maybe = context.used(universe), context.maybe(universe)
        unset = [
            decision
            for decision in pin.uses
            if decision.analysis in analyses
            and decision not in used
            and decision not in maybe
            and not selection.options(decision)
        ]
        if not unset:
            continue
        spelled = sorted(
            ".".join((*(d.id for d in analyses[decision.analysis][0]), decision.id))
            for decision in unset
        )
        decisions = ", ".join(f"`{each}`" for each in spelled)
        named = context.named([universe], pin.entry.file)
        message = (
            f"`{pin.entry.written}` reads in {named} what uses {decisions}, which that universe "
            "neither sets nor uses itself: set them in its `decisions`, or pin a universe that "
            "sets them"
        )
        location = context.at(pin.entry.file, pin.entry.pointer)
        yield context.diagnostic("PIN_NOT_BUILT", message, location)
