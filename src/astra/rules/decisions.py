"""Decisions and options: every option named by an option reference, a universe's own
selection or a key of a switch's `cases` is one of its decision's options (`UNKNOWN_OPTION`).

Binding has resolved each address to its decision (`astra.stack`). Under an address that names
nothing, no option is checked; a key that loops still names its decision, and its option is
checked. A key of `cases` names an option of the decision its switch's `switch` names, and is
reported at the key (Elements *switch*); under a `switch` that names nothing, no key is checked.
"""

from __future__ import annotations

from collections.abc import Iterator

from astra.diagnostics import Diagnostic
from astra.rules.context import Context
from astra.universes import options

CODES = frozenset({"UNKNOWN_OPTION"})


def check(context: Context) -> Iterator[Diagnostic]:
    for resolution in context.stack.resolutions:
        option, owner = resolution.option, resolution.owner
        if option is None:
            continue
        decision, pointer, key = resolution, resolution.pointer, None
        if resolution.field == "case":  # the switch's decision's option, at the key
            assert owner is not None  # the switch whose `cases` holds it
            decision, pointer, key = context.stack.switches[owner].decision, pointer[:-1], option
        elif resolution.key is not None:  # a selection: its value, the option, is at its key
            pointer = (*pointer, resolution.key)
        if context.names_nothing(decision):
            continue
        assert decision.element is not None
        known = options(context.stack, decision.element)
        if option in known:
            continue
        listed = ", ".join(f"`{id_}`" for id_ in known)
        if resolution.field == "case":
            assert owner is not None
            message = (
                f"`{owner.id}` switches on `{decision.address}`, which has no option `{option}` "
                f"to key a case: its options are {listed}"
            )
        else:
            message = f"`{resolution.address}` has no option `{option}`: its options are {listed}"
        location = context.at(resolution.file, pointer, key)
        yield context.diagnostic("UNKNOWN_OPTION", message, location)
