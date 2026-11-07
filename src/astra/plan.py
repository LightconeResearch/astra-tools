"""plan(): the root's planned results, in an order a runner can build them in, and
render_command (§11 *The command as a template*, §13, §16, §17, §18; design §4.6).

A thin layer over `universes.building`, which gives the planned results, their names and the
universe each entry reads in: each result here adds what a runner reads from it, its owner and
places (§18), what each entry of its output's `inputs` reads, the option each entry of its
`decisions` selects, its command and the folder it runs in (§11), and whether it is read
through its record or run at a commit (§17).

The plan is made only of a valid stack: one that breaks a `MUST` has no plan (`api.plan`).
Every path is a path from the top of the tree its analysis is read in (§17 *Identity*): the
root's working tree, or the repository a commit is read in.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any

from astra.diagnostics import Catalogue
from astra.rules.context import Context
from astra.sources import paths
from astra.stack import Element, Identity, Resolution, Stack
from astra.universes import Place, Planned, Selection, along, building, places, read_in

SHAPE = "astra-plan/1"


class RequestError(ValueError):
    """What `plan` or `view` is asked for isn't in the stack, or can't be built there: a usage
    error."""


@dataclass(frozen=True)
class Read:
    """One entry of an output's `inputs`, as written, and what it reads (§10): an input's file,
    or a planned result's bytes."""

    entry: str
    path: str  # the input's file, or the default place of the result's bytes
    commit: str | None  # the commit `path` is read at; None for the working tree
    result: Result | None  # the planned result it reads; None for an input


@dataclass(frozen=True)
class Result:
    """A planned result, as a runner builds it (design §4.6)."""

    names: tuple[str, ...]
    owner: Identity  # the analysis it belongs to (§18)
    output: Element
    universe: Element | None  # the universe it is built in; None for an output built once
    places: tuple[Place, ...]  # one for each name (§18)
    inputs: tuple[Read, ...]  # one for each entry of its output's `inputs`, in their order
    decisions: Mapping[str, str | None]  # each entry of its output's `decisions`, and its option
    command: str  # its recipe's `command`, a template (§11)
    workdir: str  # the folder its recipe runs in: its output's analysis's (§11)
    read_only: bool  # it belongs to an analysis read at another commit than the root's, one
    # from a commit or reached from it: read through its record (§17)
    run_at: str | None  # for a driven analysis from a commit, the commit its recipe runs on, on
    # that analysis's files; never the commit its record names, which is the driver's (§19)


@dataclass(frozen=True)
class Plan:
    """The planned results, each after every result it reads."""

    root: str  # the root's astra.yaml, as a Location's `file` names it
    results: tuple[Result, ...]

    def to_json(self) -> dict[str, Any]:
        """The plan as `astra-plan/1` (design §4.11)."""
        # OPEN(O28): the exact JSON form.
        index = {(result.output, result.universe): at for at, result in enumerate(self.results)}

        def read(entry: Read) -> dict[str, Any]:
            result = entry.result
            at = None if result is None else index[result.output, result.universe]
            return {"entry": entry.entry, "path": entry.path, "commit": entry.commit, "result": at}

        return {
            "shape": SHAPE,
            "root": self.root,
            "results": [
                {
                    "names": list(result.names),
                    "owner": asdict(result.owner),
                    "output": asdict(result.output),
                    "universe": None if result.universe is None else result.universe.id,
                    "places": [asdict(place) for place in result.places],
                    "inputs": [read(entry) for entry in result.inputs],
                    "decisions": dict(result.decisions),
                    "command": result.command,
                    "workdir": result.workdir,
                    "read_only": result.read_only,
                    "run_at": result.run_at,
                }
                for result in self.results
            ],
        }


def plan(
    stack: Stack, universes: Iterable[str] | None = None, outputs: Iterable[str] | None = None
) -> Plan:
    """The planned results of `stack`, a valid stack (§18), each after every result it reads.

    `universes`, ids of the root's universes, narrows them to the results built in those
    universes and what they read. `outputs`, addresses read in the root's file, names outputs
    to build, planned or not: each is planned as the root's own outputs are, once or in each of
    the root's universes where it is active and its analysis is built, and the plan holds its
    results (only those built once or in `universes`, where given) and what they read. Raises
    RequestError where a universe or an output asked for isn't there, or an output asked for
    has no result there or reads a result that isn't built."""
    context = Context(stack, Catalogue.load())
    wanted = None if universes is None else {root_universe(stack, id_) for id_ in universes}
    addresses = tuple(outputs or ())
    requested = tuple(root_output(stack, address) for address in addresses)
    found = building(
        stack, context.written, context.selections, context.driven, context.pins,
        context.per_universe, requested,
    )  # fmt: skip

    def chosen(result: Planned) -> bool:
        if not requested:
            return wanted is None or result.universe in wanted
        built = wanted is None or result.universe is None or result.universe in wanted  # OPEN(O33)
        return result.output in requested and built

    seeds = [result for result in found.planned.values() if chosen(result)]
    for output, address in zip(requested, addresses, strict=True):  # OPEN(O33)
        if not any(result.output == output for result in seeds):
            where = "the root's universes" if wanted is None else "the universes asked for"
            raise RequestError(
                f"`{address}` has no result in {where}: its analysis isn't built there, or it "
                "is active nowhere there"
            )
    made: dict[Key, Result] = {}

    def visit(result: Planned) -> None:
        if (result.output, result.universe) not in made:
            reads = _reads(context, found.planned, result)
            for _, read in reads:
                if read is not None:
                    visit(read)
            made[result.output, result.universe] = _result(context, result, reads, made)

    for seed in seeds:
        visit(seed)
    return Plan(stack.analyses[stack.root].file, tuple(made.values()))


Key = tuple[Element, Element | None]
"""A planned result's output and universe, which `building` keys it by."""

Reads = tuple[tuple[Resolution, Planned | None], ...]
"""Each entry of an output's `inputs`, and the planned result it reads; None for an input."""


def root_universe(stack: Stack, id_: str) -> Element:
    """The root's universe `id_`. Raises RequestError where the root has none, or `id_` is an
    import, which selects nothing (§12)."""
    entry = stack.analysis(stack.root).universes.get(id_)
    if entry is None or entry.is_import:
        own = [key for key, u in stack.analysis(stack.root).universes.items() if not u.is_import]
        what = (
            f"`{id_}` is an import, which selects nothing"
            if entry
            else f"the analysis has no universe `{id_}`"
        )
        listed = ", ".join(own) if own else "none"
        raise RequestError(f"{what}: its universes are {listed}")
    return Element(stack.root, "universe", id_)


def root_output(stack: Stack, address: str) -> Element:
    """The output `address` names in the root's file. Raises RequestError where it names
    none."""
    output = stack.element(address, "output")
    if output is None:
        raise RequestError(f"`{address}` names no output, read in the root's file")
    return output


def _reads(context: Context, planned: Mapping[Key, Planned], result: Planned) -> Reads:
    """What each entry of `result`'s output's `inputs` reads: an input, or a planned result
    (`read_in`). Raises RequestError where an output asked for reads what isn't built, which
    no planned result of a valid stack does (§13, §16)."""
    reads: list[tuple[Resolution, Planned | None]] = []
    for entry in context.written[result.output]:
        if entry.field != "inputs":
            continue
        assert entry.element is not None  # every address of a valid stack names an element
        read = None
        if entry.element.kind == "output":
            at = read_in(entry, result.universe, context.pins, context.per_universe)
            read = planned.get((entry.element, at))
            if read is None:  # OPEN(O33): only an output asked for can
                raise RequestError(
                    f"`{result.output.id}` can't be built on request: `{entry.written}` reads "
                    "a result that isn't built there"
                )
        reads.append((entry, read))
    return tuple(reads)


def _result(context: Context, result: Planned, reads: Reads, made: Mapping[Key, Result]) -> Result:
    """`result` as a runner builds it, from the results it reads, already `made`."""
    stack, identity = context.stack, result.output.analysis
    inputs: list[Read] = []
    for entry, read in reads:
        assert entry.element is not None
        if read is None:
            analysis = entry.element.analysis
            written = stack.analysis(analysis).inputs[entry.element.id].path
            path = paths.join(analysis.folder, written)
            assert path is not None  # inside its analysis's folder (INPUT_IN_ANOTHER_ANALYSIS)
            inputs.append(Read(entry.written, path, analysis.commit, None))
            continue
        done = made[read.output, read.universe]
        # OPEN(O32): the name along the entry's declarations from the analysis `read` belongs
        # to, after `result`'s first chain where `result` belongs there too, or else the first.
        start = result.chains[0] if result.owner == read.owner else ()
        index = along(read, (*start, *entry.chain))
        place = done.places[0 if index is None else index]
        inputs.append(Read(entry.written, place.bytes, done.owner.commit, done))
    selection = None if result.universe is None else context.selections[result.universe]
    read_only = result.owner.commit != stack.root.commit
    return Result(
        result.names,
        result.owner,
        result.output,
        result.universe,
        places(stack, result),
        tuple(inputs),
        MappingProxyType(selected(context.written[result.output], selection)),
        stack.analysis(identity).outputs[result.output.id].recipe.command,
        identity.folder,
        read_only,
        None if read_only or identity.commit == stack.root.commit else identity.commit,
    )


def selected(entries: Iterable[Resolution], selection: Selection | None) -> dict[str, str | None]:
    """Each entry of an output's `decisions`, among the addresses it writes (`entries`), as
    written, and the option `selection`, the effective selection of the universe its result is
    built in, selects for it; None where there is no selection, the entry names nothing or no
    option is selected."""
    # OPEN(O30): an inactive decision has no option selected.
    return {
        entry.written: None
        if selection is None or entry.element is None
        else min(selection.options(entry.element), default=None)
        for entry in entries
        if entry.field == "decisions"
    }


_TEMPLATE = re.compile(r"\{\{|\}\}|\{([^}]*)\}")
"""§11 *The command as a template*, read from the left: `{{`, `}}`, or a placeholder up to the
next `}`. A valid stack's commands hold nothing else (`UNDECLARED_TEMPLATE_REF`)."""


def render_command(result: Result, cwd: str | os.PathLike[str], *, absolute: bool = False) -> str:
    """`result`'s command with each placeholder, and each `{{` and `}}`, replaced as §11's table
    says, verbatim, with no shell quoting: `{inputs.<entry>}` by the path of what the entry
    reads, `{decisions.<entry>}` by the option selected, `{inputs}` by every entry's path in
    order, separated by spaces, and `{output}` by the default place of the result's bytes.

    `cwd` is the folder the recipe runs in: `result.workdir` in the checkout it runs in, whose
    top every path of the plan is measured from. Each path is relative to `cwd`, or absolute
    where `absolute`."""
    depth = len(result.workdir.split("/")) if result.workdir else 0
    top = os.path.join(cwd, *[os.pardir] * depth)  # OPEN(O31): one checkout for every path

    def path(place: str) -> str:
        full = os.path.normpath(os.path.join(top, *place.split("/")))
        return os.path.abspath(full) if absolute else os.path.relpath(full, cwd)

    reads = {read.entry: path(read.path) for read in result.inputs}

    def fill(match: re.Match[str]) -> str:
        text, placeholder = match[0], match[1]
        if text in ("{{", "}}"):
            return text[0]
        if placeholder == "output":
            return path(result.places[0].bytes)  # OPEN(O32): the first name's
        if placeholder == "inputs":
            return " ".join(reads[read.entry] for read in result.inputs)
        field, _, entry = placeholder.partition(".")
        if field == "inputs":
            return reads[entry]
        return result.decisions[entry] or ""  # OPEN(O30)

    return _TEMPLATE.sub(fill, result.command)
