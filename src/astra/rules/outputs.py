"""§10 Outputs: an input and an output never share an id (`AMBIGUOUS_ID`), and no output
depends on itself, directly or through others (`OUTPUT_CYCLE`).

An output depends on each output an entry of its `inputs` resolves to, pinned or not, through
any declaration. Outputs are known by their analysis's identity (§17), so two spellings of one
output, and a declaration back through `..`, reach one output (§15). An address that names
nothing, or goes through an undetermined analysis, depends on nothing (Annex D cases 4, 5).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence

from astra.diagnostics import Diagnostic
from astra.rules.context import Context
from astra.stack import Element, Resolution

CODES = frozenset({"AMBIGUOUS_ID", "OUTPUT_CYCLE"})


def check(context: Context) -> Iterator[Diagnostic]:
    yield from _ambiguous(context)
    yield from _cycles(context)


def _ambiguous(context: Context) -> Iterator[Diagnostic]:
    for member, analysis in context.stack.determined():
        for id_ in analysis.outputs:
            if id_ in analysis.inputs:
                message = (
                    f"the input and the output `{id_}` share an id, and `Output.inputs` takes "
                    "both: rename one"
                )
                output = context.at(member.identity, ("outputs",), id_)
                input_ = context.at(member.identity, ("inputs",), id_)
                yield context.diagnostic("AMBIGUOUS_ID", message, output, [input_])


def _cycles(context: Context) -> Iterator[Diagnostic]:
    """`OUTPUT_CYCLE` at each entry of `inputs` that lies on a cycle: the output it names
    leads back to the output that lists it."""
    reads: dict[Element, list[tuple[Element, Resolution]]] = {}
    for resolution in context.stack.resolutions:
        if resolution.field != "inputs" or context.names_nothing(resolution):
            continue
        element = resolution.element
        assert element is not None
        if element.kind == "output":
            assert resolution.owner is not None  # the output whose `inputs` holds it
            reads.setdefault(resolution.owner, []).append((element, resolution))
    graph = {owner: [element for element, _ in entries] for owner, entries in reads.items()}
    for owner, entries in reads.items():
        for element, entry in entries:
            back = _path(graph, element, owner)
            if back is None:
                continue
            steps = " → ".join(context.named([output], entry.file) for output in (owner, *back))
            message = f"`{owner.id}` depends on itself through `{entry.written}`: {steps}"
            yield context.diagnostic("OUTPUT_CYCLE", message, context.at(entry.file, entry.pointer))


def _path(
    graph: Mapping[Element, Sequence[Element]], start: Element, end: Element
) -> list[Element] | None:
    """The shortest path of outputs from `start` to `end`, both included; None if there is
    none."""
    before: dict[Element, Element | None] = {start: None}
    todo = [start]
    while todo:
        current = todo.pop(0)
        if current == end:
            path = [current]
            while (previous := before[path[-1]]) is not None:
                path.append(previous)
            return path[::-1]
        for following in graph.get(current, ()):
            if following not in before:
                before[following] = current
                todo.append(following)
    return None
