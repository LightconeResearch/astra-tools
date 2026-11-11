"""§8 Decisions and options: every option named by an option reference or a universe's own
selection is one of its decision's options (`UNKNOWN_OPTION`).

Binding has resolved each address to its decision (`astra.stack`). Under an address that names
nothing, no option is checked (design §4.13 case 5); a key that loops still names its decision, and
its option is checked (design §4.13 case 10).
"""

from __future__ import annotations

from collections.abc import Iterator

from astra.diagnostics import Diagnostic
from astra.rules.context import Context
from astra.universes import options

CODES = frozenset({"UNKNOWN_OPTION"})


def check(context: Context) -> Iterator[Diagnostic]:
    for resolution in context.stack.resolutions:
        element, option = resolution.element, resolution.option
        if option is None or context.names_nothing(resolution):
            continue
        assert element is not None
        known = options(context.stack, element)
        if option in known:
            continue
        pointer = resolution.pointer
        if resolution.key is not None:  # a selection: its value, the option, is at its key
            pointer = (*pointer, resolution.key)
        listed = ", ".join(f"`{id_}`" for id_ in known)
        message = f"`{resolution.address}` has no option `{option}`: its options are {listed}"
        yield context.diagnostic("UNKNOWN_OPTION", message, context.at(resolution.file, pointer))
