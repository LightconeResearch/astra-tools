"""§13 Pins, and outputs built per universe or once: every pinned output is active in the
universe it is pinned to (`PIN_INACTIVE`), and every output read without a pin by the output of
a result planned in the universe being built is active there (`INPUT_NOT_BUILT`).

`PIN_INACTIVE` holds of every pin on an output, in every file of the stack. `INPUT_NOT_BUILT`
holds only in the universes built, for the results planned there (§16 *What a validator
checks*, `universes.building`). Neither is checked for an output whose activity is
undetermined, nor in a universe with no effective selection (design §4.13 cases 6 and 7), nor for a
reference that names nothing or a pin that names no universe (case 5), nor for one that names an
output on a cycle (case 13).
"""

from __future__ import annotations

from collections.abc import Iterator

from astra.diagnostics import Diagnostic
from astra.rules.context import Context
from astra.stack import Element, Resolution
from astra.universes import when

CODES = frozenset({"PIN_INACTIVE", "INPUT_NOT_BUILT"})


def check(context: Context) -> Iterator[Diagnostic]:
    yield from _pinned(context)
    yield from _read(context)


def _pinned(context: Context) -> Iterator[Diagnostic]:
    for entry in context.stack.resolutions:
        output, universe = entry.element, context.pins.get(entry)
        if output is None or output.kind != "output" or universe is None:
            continue
        if context.on_cycle(output):  # design §4.13 case 13
            continue
        if context.activity(universe, output) is False:
            message = (
                f"`{entry.written}` pins `{entry.address}` to "
                f"{context.named([universe], entry.file)}, where it isn't active "
                f"({_when(context, output)} doesn't hold there), so it has no result there: pin "
                "a universe where it is active"
            )
            yield context.diagnostic("PIN_INACTIVE", message, context.at(entry.file, entry.pointer))


def _read(context: Context) -> Iterator[Diagnostic]:
    """Each entry of a planned result's output that reads, without a pin, an output inactive in
    the universe the result is built in, with every such universe."""
    inactive: dict[Resolution, list[Element]] = {}
    for entry, universe in context.building.reads:
        if entry.field == "inputs" and entry.pin is None and universe is not None:
            assert entry.element is not None
            if context.on_cycle(entry.element):  # design §4.13 case 13
                continue
            if context.activity(universe, entry.element) is False:
                inactive.setdefault(entry, []).append(universe)
    for entry, universes in inactive.items():
        read, owner = entry.element, entry.owner
        assert read is not None and owner is not None
        reader = owner.id
        message = (
            f"`{reader}` reads `{entry.written}` without a pin in "
            f"{context.named(universes, entry.file)}, where it isn't active "
            f"({_when(context, read)} doesn't hold there), so it isn't built there: pin a "
            f"universe where it is active, or give `{reader}` a `when` that holds only where "
            f"`{entry.written}` is active"
        )
        location = context.at(entry.file, entry.pointer)
        yield context.diagnostic("INPUT_NOT_BUILT", message, location)


def _when(context: Context, output: Element) -> str:
    """An output's `when`, as a message names it."""
    conditions = when(context.stack, output)
    return "its `when`, " + ", ".join(f"`{condition}`" for condition in conditions) + ","
