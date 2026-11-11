"""§6 Names: every address resolves, through the declarations, to an element of the kind its
field takes (`UNRESOLVED_ADDRESS`); and an `artifact` that names a switch names one each of whose
cases names an output other than a switch, or a switch like it (Rules `UNRESOLVED_ADDRESS`).

Binding has resolved every address of every valid file (`astra.stack`); an address through a
declaration whose analysis is undetermined isn't checked (design §4.13 case 4), and one that names
nothing names nothing for every other rule (design §4.13 case 5). An entry of `inputs`, or a
switch's case, whose id is both an input and an output names nothing too (case 5), but breaks
`AMBIGUOUS_ID`, not this rule. A switch is an output (Elements *switch*), so a message names the
kinds a field takes without it. An `artifact` naming a switch with a case, through nested
switches, that names nothing, or a switch on a cycle, isn't judged: that case's own cause is
reported (design §4.13 cases 5 and 13).
"""

from __future__ import annotations

from collections.abc import Iterator

from astra.diagnostics import Diagnostic
from astra.rules.context import Context
from astra.stack import TAKES, Element, Resolution

CODES = frozenset({"UNRESOLVED_ADDRESS"})


def check(context: Context) -> Iterator[Diagnostic]:
    for resolution in context.stack.resolutions:
        element = resolution.element
        if element is None and not resolution.undetermined:
            if not _ambiguous(context, resolution):
                yield _unresolved(context, resolution)
        elif resolution.field == "artifact" and element is not None and element.kind == "switch":
            case = _case_on_an_input(context, element)
            if case is not None:
                yield _cites_an_input(context, resolution, case)


def _ambiguous(context: Context, resolution: Resolution) -> bool:
    """Whether an entry of `inputs`, or a case, reaches, through all its declarations, an analysis
    where its id is both an input and an output (`AMBIGUOUS_ID`)."""
    if resolution.field not in ("inputs", "case"):
        return False
    if len(resolution.chain) < len(resolution.address.declarations):
        return False
    reached = resolution.chain[-1].reached if resolution.chain else resolution.file
    assert reached is not None  # every declaration of a full chain reached its analysis
    analysis, id_ = context.stack.analysis(reached), resolution.address.id
    return id_ in analysis.inputs and id_ in analysis.outputs


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
        kind = " or ".join(taken for taken in TAKES[resolution.field] if taken != "switch")
        where = f"`{through}`" if through else "this analysis"
        detail = f"{where} has no {kind} `{address.id}`"
        if resolution.field == "import":
            pointer = (*pointer, "universe")
    message = f"`{resolution.written}` names nothing: {detail}"
    location = context.at(resolution.file, pointer, resolution.key)
    return context.diagnostic("UNRESOLVED_ADDRESS", message, location)


def _case_on_an_input(context: Context, switch: Element) -> Resolution | None:
    """The first case, of `switch` or of a switch one of its cases names, directly or not, that
    names an input; None where none does, and where one names nothing or a switch on the way is
    on a cycle, as then the switch isn't judged as an `artifact` (design §4.13 cases 5 and 13)."""
    found: list[Resolution] = []
    path: list[Element] = []
    seen: set[Element] = set()

    def walk(at: Element) -> bool:  # False: a case names nothing, or a switch is on a cycle
        if at in path or context.on_cycle(at):
            return False
        if at in seen:
            return True
        path.append(at)
        for case in context.stack.switches[at].cases.values():
            target = case.element
            if target is None:
                return False
            if target.kind == "input":
                found.append(case)
            elif target.kind == "switch" and not walk(target):
                return False
        path.pop()
        seen.add(at)
        return True

    return found[0] if walk(switch) and found else None


def _cites_an_input(context: Context, resolution: Resolution, case: Resolution) -> Diagnostic:
    assert case.owner is not None and case.element is not None  # a switch's case on an input
    message = (
        f"`{resolution.written}` names a switch, and `{case.owner.id}`'s case for `{case.option}`, "
        f"`{case.written}`, names an input: evidence cites an output, or a switch each of whose "
        "cases names an output or a switch like it"
    )
    location = context.at(resolution.file, resolution.pointer)
    related = [context.at(case.file, case.pointer)]
    return context.diagnostic("UNRESOLVED_ADDRESS", message, location, related)


def _leads_to_its_file(resolution: Resolution) -> bool:
    """Whether an import's `analysis` leads back to the analysis whose file writes it."""
    reached = resolution.chain[-1].reached if resolution.chain else resolution.file
    return reached == resolution.file
