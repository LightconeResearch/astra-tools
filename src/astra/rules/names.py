"""§6 Names: every address resolves, through the declarations, to an element of the kind its
field takes (`UNRESOLVED_ADDRESS`).

Binding has resolved every address of every valid file (`astra.stack`); an address through a
declaration whose analysis is undetermined isn't checked (Annex D case 4), and one that names
nothing names nothing for every other rule (Annex D case 5).
"""

from __future__ import annotations

from collections.abc import Iterator

from astra.diagnostics import Diagnostic
from astra.rules.context import Context
from astra.stack import TAKES, Resolution

CODES = frozenset({"UNRESOLVED_ADDRESS"})


def check(context: Context) -> Iterator[Diagnostic]:
    for resolution in context.stack.resolutions:
        if resolution.element is None and not resolution.undetermined:
            yield _unresolved(context, resolution)


def _unresolved(context: Context, resolution: Resolution) -> Diagnostic:
    address, chain = resolution.address, resolution.chain
    through = ".".join(address.segments[: len(chain)])
    pointer = resolution.pointer
    if len(chain) < len(address.declarations):
        missing = address.declarations[len(chain)]
        where = f"`{through}` declares" if through else "this file declares"
        detail = f"{where} no analysis `{missing}`"
        if resolution.field == "import":
            pointer = (*pointer, "analysis")
    elif resolution.field == "import" and _leads_to_its_file(resolution):
        detail = (
            f"an import names a universe of another analysis, and `{through}` leads back to "
            "this one: a pin names this analysis's own universes without one"
        )
        pointer = (*pointer, "analysis")
    else:
        kind = " or ".join(TAKES[resolution.field])
        where = f"`{through}`" if through else "this analysis"
        detail = f"{where} has no {kind} `{address.id}`"
        if resolution.field == "import":
            pointer = (*pointer, "universe")
    message = f"`{resolution.written}` names nothing: {detail}"
    location = context.at(resolution.file, pointer, resolution.key)
    return context.diagnostic("UNRESOLVED_ADDRESS", message, location)


def _leads_to_its_file(resolution: Resolution) -> bool:
    """Whether an import's `analysis` leads back to the analysis whose file writes it."""
    reached = resolution.chain[-1].reached if resolution.chain else resolution.file
    return reached == resolution.file
