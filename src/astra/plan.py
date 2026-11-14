"""plan(): the root's planned results, in an order a runner can build them in, and
render_command, which fills in a command's placeholders.

A thin layer over `universes.building`, which gives the planned results, their names and the
universe each entry reads in: each result here adds what a runner reads from it, its owner and
places, what each entry of its output's `inputs` reads, the option each entry of its
`decisions` selects, its command, the folder it runs in and what its recipe asks for, and
whether it is read through its record or run at a commit. The plan also notes what an author
may want to tidy, though it breaks no rule: a pin that names another analysis's universe only
because its file has no entry of that id, a result with two names, an output with no planned
result, results that are one computation in several universes, an output, or a switch that
nothing reads, that a switch leaves unbuilt in a universe, as it has no case there for the option
its decision selects (Elements *switch*), and a command that names a path outside its analysis's
folder, or inside an analysis below it (`CODE_OUTSIDE_ANALYSIS`). Through a switch, an entry
reads what the case the switch takes names (Elements *takes*), which its read records.

`api.plan` plans only a valid stack: one that breaks a `MUST` has no plan. On such a stack,
`plan` gives the results whose planning is determined, for `check`. Every path is a path from
the top of the tree its analysis is read in: the root's working tree, or the repository a commit
is read in.
"""

from __future__ import annotations

import os
import posixpath
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any, Literal

from astra.diagnostics import Catalogue, Location
from astra.model import Analysis, Resources
from astra.rules.context import Context
from astra.sources import paths
from astra.stack import Element, Identity, Member, Resolution, Stack
from astra.universes import (
    Building,
    Place,
    Planned,
    Run,
    Selection,
    Through,
    along,
    building,
    built,
    own_universes,
    places,
    run,
)

SHAPE = "astra-plan/1"


class RequestError(ValueError):
    """What `plan` or `view` is asked for isn't in the stack, or can't be built there: a usage
    error."""


@dataclass(frozen=True)
class Read:
    """One entry of an output's `inputs`, as written, and what it reads: an input's file, or a
    planned result's bytes, through the case each switch on the way takes (Elements *takes*)."""

    entry: str
    path: str  # the input's file, or the default place of the result's bytes
    commit: str | None  # the commit `path` is read at; None for the working tree
    result: Result | None  # the planned result it reads; None for an input
    place: Place | None  # the place of the result's name whose bytes it reads; None for an input
    via: tuple[str, ...] = ()  # each case taken on the way, as written, in order; () where the
    # entry names no switch


@dataclass(frozen=True)
class Result:
    """A planned result, as a runner builds it."""

    names: tuple[str, ...]
    owner: Identity  # the analysis it belongs to
    output: Element
    universe: Element | None  # the universe it is built in; None for an output built once
    places: tuple[Place, ...]  # one for each name
    inputs: tuple[Read, ...]  # one for each entry of its output's `inputs`, in their order
    decisions: Mapping[str, str | None]  # each entry of its output's `decisions`, and its option
    command: str  # its recipe's `command`, a template
    workdir: str  # the folder its recipe runs in: its output's analysis's
    read_only: bool  # it belongs to an analysis read at another commit than the root's, one
    # from a commit or reached from it: read through its record
    run_at: str | None  # for a driven analysis from a commit, the commit its recipe runs on, on
    # that analysis's files; never the commit its record names, which is the driver's
    resources: Resources | None  # what its recipe asks for


NoteKind = Literal[
    "fallback_pin", "two_names", "unplanned", "not_built", "same_computation", "outside_folder"
]


@dataclass(frozen=True)
class Note:
    """Something an author may want to tidy, which breaks no rule."""

    kind: NoteKind
    message: str
    location: Location | None  # the pin, the output or the command; None for the kinds of results
    results: tuple[Result, ...] = ()  # those it is about, for `two_names` and `same_computation`
    built: bool = True  # it concerns what the root builds: False only for a `fallback_pin` that no
    # planned result reads through, as the root builds every analysis of a stack it can plan
    universes: tuple[Element, ...] = ()  # for `not_built`, the universes the output isn't built in
    switch: Element | None = None  # for `not_built`, the switch with no case there
    option: str | None = None  # for `not_built`, the option its decision selects there


@dataclass(frozen=True)
class Plan:
    """The planned results, each after every result it reads, and the notes on them."""

    root: str  # the root's astra.yaml, as a Location's `file` names it
    results: tuple[Result, ...]
    notes: tuple[Note, ...] = ()

    def to_json(self) -> dict[str, Any]:
        """The plan as `astra-plan/1`."""
        # The exact JSON form.
        index = {(result.output, result.universe): at for at, result in enumerate(self.results)}

        def read(entry: Read) -> dict[str, Any]:
            result = entry.result
            at = None if result is None else index[result.output, result.universe]
            return {
                "entry": entry.entry,
                "path": entry.path,
                "commit": entry.commit,
                "result": at,
                "via": list(entry.via),
            }

        def resources(asked: Resources | None) -> dict[str, Any] | None:
            if asked is None:
                return None
            return {key: value for key, value in asdict(asked).items() if value is not None}

        def note(found: Note) -> dict[str, Any]:
            return {
                "kind": found.kind,
                "message": found.message,
                "location": None if found.location is None else asdict(found.location),
                "results": [index[result.output, result.universe] for result in found.results],
                "built": found.built,
                "universes": [
                    {"analysis": asdict(universe.analysis), "id": universe.id}
                    for universe in found.universes
                ],
                "switch": None
                if found.switch is None
                else {"analysis": asdict(found.switch.analysis), "id": found.switch.id},
                "option": found.option,
            }

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
                    "resources": resources(result.resources),
                }
                for result in self.results
            ],
            "notes": [note(found) for found in self.notes],
        }


def plan(
    stack: Stack, universes: Iterable[str] | None = None, outputs: Iterable[str] | None = None
) -> Plan:
    """The planned results of `stack`, each after every result it reads. Where `stack` breaks a
    `MUST`, those whose planning is determined: a result is left out where an entry of its
    output's `inputs` names nothing, gives an input's path above the top, names an output with
    no result planned there (`NOT_BUILT_IN_UNIVERSE`), or reads a result that is left out or
    that reads it back (`OUTPUT_CYCLE`), as `check` reads them.

    `universes`, ids of the root's universes, narrows them to the results built in those
    universes and what they read. `outputs`, addresses read in the root's file, names outputs
    to build, planned or not: each is planned as the root's own outputs are, once or in each of
    the root's universes where its analysis is built, and the plan holds its results (only
    those built once or in `universes`, where given) and what they read. Raises
    RequestError where a universe or an output asked for isn't there, or is a switch, or an
    output asked for has no result there, reads a result that isn't built, or uses, or reads
    what uses, a decision that a universe it is built in doesn't set."""
    context = Context(stack, Catalogue.load())
    wanted = None if universes is None else {root_universe(stack, id_) for id_ in universes}
    addresses = tuple(outputs or ())
    requested = tuple(root_output(stack, address) for address in addresses)
    reached = _run(context, requested)
    found = building(stack, reached, context.driven)

    def chosen(result: Planned) -> bool:
        if not requested:
            return wanted is None or result.universe in wanted
        built = wanted is None or result.universe is None or result.universe in wanted
        return result.output in requested and built

    seeds = [result for result in found.planned.values() if chosen(result)]
    for output, address in zip(requested, addresses, strict=True):
        if not any(result.output == output for result in seeds):
            where = "the root's universes" if wanted is None else "the universes asked for"
            raise RequestError(
                f"`{address}` has no result in {where}: its analysis isn't built there, or it is "
                "built nowhere there"
            )
    if requested:
        _settled(context, reached, wanted, requested, addresses)
    made: dict[Key, Result] = {}
    left: set[Key] = set()  # left out, or being made: a result that reads it back is left out

    def visit(result: Planned) -> bool:
        """Make `result` after every result it reads, unless its planning isn't determined."""
        key = (result.output, result.universe)
        if key in made or key in left:
            return key in made
        left.add(key)
        reads = _reads(context, found.planned, result, bool(requested))
        if reads is None or not all(isinstance(read, str) or visit(read) for _, _, read in reads):
            return False
        left.remove(key)
        made[key] = _result(context, result, reads, made)
        return True

    for seed in seeds:
        visit(seed)
    results = tuple(made.values())
    notes = _notes(context, found, results)
    return Plan(stack.analyses[stack.root].file, results, notes)


Key = tuple[Element, Element | None]
"""A planned result's output and universe, which `building` keys it by."""

Reads = tuple[tuple[Resolution, Through, Planned | str], ...]
"""Each entry of an output's `inputs`, what it reads through the case each switch on the way
takes, and that: a planned result, or an input's file, as a path from the top."""


def _run(context: Context, requested: tuple[Element, ...]) -> Run:
    """The root's run (Results *plans*, *reaches*, *uses*), with the outputs `requested` as its
    own."""
    return run(
        context.stack, context.meaning, context.written, context.selections, context.pins,
        context.per_universe, context.cycles, context.stack.root, requested,
    )  # fmt: skip


def _settled(
    context: Context,
    reached: Run,
    wanted: set[Element] | None,
    requested: tuple[Element, ...],
    addresses: tuple[str, ...],
) -> None:
    """Raise RequestError where the plan's run, with the outputs `requested` as the root's own,
    uses in a universe it covers a decision that universe doesn't set (Results *uses*). A valid
    stack never plans such a result unasked (`MISSING_DECISION`), but an output asked for can
    reach an analysis driven only because nothing planned uses its decisions (Elements)."""
    unset = _unset(context, reached, wanted)
    if unset is None:
        return
    address = addresses[0]
    if len(requested) > 1:  # the first output asked for whose own run leaves one unset
        for output, written in zip(requested, addresses, strict=True):
            alone = _unset(context, _run(context, (output,)), wanted)
            if alone is not None:
                unset, address = alone, written
                break
    universe, decision = unset
    named = context.named([universe], context.stack.root)
    raise RequestError(
        f"`{address}` can't be built on request in {named}: it, or what it reads, uses "
        f"{_spelled(context, decision, universe)}, which {named} doesn't set"
    )


def _unset(
    context: Context, reached: Run, wanted: set[Element] | None
) -> tuple[Element, Element] | None:
    """The first universe `reached` uses a decision in that it doesn't set, and that decision,
    where the root's run doesn't already use it there (`Context.runs`): among the root's
    universes in `wanted`, or all of them, and every other analysis's universe. None where there
    is none."""
    stack = context.stack
    before = context.runs[stack.root].used
    for universe, decisions in reached.used.items():
        if universe.analysis == stack.root and wanted is not None and universe not in wanted:
            continue
        selection = context.selections.get(universe)
        if selection is None:  # the universe has no effective selection
            continue
        known = before.get(universe, frozenset())
        for decision in sorted(decisions - known, key=_order):
            if not selection.options(decision):
                return universe, decision
    return None


def _order(element: Element) -> tuple[str, str, str]:
    return element.analysis.folder, element.analysis.commit or "", element.id


def _spelled(context: Context, decision: Element, universe: Element) -> str:
    """`decision`, in backticks, as a key of `universe`'s `decisions` would set it: through the
    first chain its analysis's universes drive that reaches the decision's analysis."""
    reaching = built(context.driven[universe.analysis], universe.analysis).get(decision.analysis)
    if not reaching:
        return f"`{decision.id}` of `{decision.analysis}`"
    return "`" + ".".join((*(declaration.id for declaration in reaching[0]), decision.id)) + "`"


def root_universe(stack: Stack, id_: str) -> Element:
    """The root's universe `id_`. Raises RequestError where the root has none, or `id_` is an
    import, which selects nothing."""
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
    none, or names a switch, which has no result (Elements *switch*)."""
    output = stack.element(address, "output")
    if output is None and stack.element(address, "switch") is not None:
        raise RequestError(
            f"`{address}` is a switch, which has no result of its own: ask for the output a case "
            "names"
        )
    if output is None:
        raise RequestError(f"`{address}` names no output, read in the root's file")
    return output


def _reads(
    context: Context, planned: Mapping[Key, Planned], result: Planned, requested: bool
) -> Reads | None:
    """What each entry of `result`'s output's `inputs` reads, through the case each switch on
    the way takes (`Meaning.through`): an input's file, in the folder of the input's analysis,
    or a planned result. None where what one reads isn't determined, as only on a stack that
    breaks a `MUST`: it names nothing, gives a path above the top, reads through a switch that
    is undetermined or takes nothing, or names an output with no result planned there. Where
    outputs are `requested`, those last two raise RequestError instead: an output asked for can
    read what isn't built."""
    reads: list[tuple[Resolution, Through, Planned | str]] = []
    for entry in context.written[result.output]:
        if entry.field != "inputs":
            continue
        if entry.element is None:
            return None
        through = context.meaning.through(entry, result.universe)
        read: Planned | str | None = None
        if through is not None and through.target.kind == "input":
            target = through.target
            written = context.stack.analysis(target.analysis).inputs[target.id].path
            read = paths.join(target.analysis.folder, written)
            if read is None:
                return None
        elif through is not None:
            read = planned.get((through.target, through.universe))
        if read is None and requested:
            raise RequestError(
                f"`{result.output.id}` can't be built on request: `{entry.written}` reads a "
                "result that isn't built there"
            )
        if through is None or read is None:
            return None
        reads.append((entry, through, read))
    return tuple(reads)


def _result(context: Context, result: Planned, reads: Reads, made: Mapping[Key, Result]) -> Result:
    """`result` as a runner builds it, from the results it reads, already `made`."""
    stack, identity = context.stack, result.output.analysis
    inputs: list[Read] = []
    for entry, through, read in reads:
        via = tuple(step.case.written for step in through.steps)
        if isinstance(read, str):
            commit = through.target.analysis.commit
            inputs.append(Read(entry.written, read, commit, None, None, via))
            continue
        done = made[read.output, read.universe]
        # The name along the entry's declarations, then each case's, from the analysis `read`
        # belongs to, after `result`'s first chain where `result` belongs there too, or else the
        # first.
        start = result.chains[0] if result.owner == read.owner else ()
        index = along(read, (*start, *through.chain))
        place = done.places[0 if index is None else index]
        inputs.append(Read(entry.written, place.bytes, done.owner.commit, done, place, via))
    selection = None if result.universe is None else context.selections[result.universe]
    read_only = result.owner.commit != stack.root.commit
    analysis = stack.analysis(identity)
    recipe = analysis.outputs[result.output.id].recipe
    assert recipe is not None  # a result's output isn't a switch
    return Result(
        result.names,
        result.owner,
        result.output,
        result.universe,
        places(stack, result),
        tuple(inputs),
        MappingProxyType(selected(context.written[result.output], selection)),
        recipe.command,
        identity.folder,
        read_only,
        None if read_only or identity.commit == stack.root.commit else identity.commit,
        recipe.resources,
    )


def _notes(context: Context, found: Building, results: tuple[Result, ...]) -> tuple[Note, ...]:
    """What the plan notes, kind by kind. Those about files are about the files read where the root
    is, which an author can edit; those about results, about `results`. `fallback_pin`, `unplanned`
    and `outside_folder` notes say whether they concern what the root builds (`Note.built`): the
    root, and every analysis its universes drive (`built`). In a stack the plan accepts, that is
    every analysis: one whose decisions a universe of the root uses is built there
    (`NOT_BUILT_IN_UNIVERSE`), and one with none it uses has nothing to set, so is driven without a
    key (Elements). Only a `fallback_pin` that no planned result reads through concerns something
    else."""
    stack = context.stack
    editable = [
        (member, analysis)
        for member, analysis in stack.determined()
        if member.identity.commit == stack.root.commit
    ]
    builds = frozenset(built(context.driven[stack.root], stack.root))
    return (
        *_fallback_pins(context, {entry for entry, _ in found.reads}),
        *_two_names(stack.root, results),
        *_unplanned(context, found.planned, editable, builds),
        *_not_built(context, found.run),
        *_same_computations(stack.root, results),
        *_outside_folder(context, editable, builds),
    )


Editable = list[tuple[Member, Analysis]]
"""The analyses read where the root is, with their content."""


def _fallback_pins(context: Context, read: set[Resolution]) -> Iterator[Note]:
    """Each pin in a file read where the root is that names another analysis's universe only
    because the file's `universes` has no entry of its id, so that adding one would change what
    it names. It concerns what the root builds where the plan reads through it (`read`): an
    entry of a planned result's `inputs`, or of the root's evidence."""
    stack = context.stack
    for entry, universe in context.pins.items():
        file = entry.file
        if universe is None or file.commit != stack.root.commit:
            continue
        assert entry.pin is not None  # `pins` holds only pinned references
        if entry.pin in stack.analysis(file).universes:
            continue
        message = (
            f"`{entry.written}` names `{entry.pin}` of `{universe.analysis}` only because this "
            f"file has no universe `{entry.pin}`: adding one, or an import of that id, would "
            "change what it names"
        )
        at = context.at(file, entry.pointer)
        yield Note("fallback_pin", message, at, built=entry in read)


def _two_names(root: Identity, results: Iterable[Result]) -> Iterator[Note]:
    """Each of `results` with two names."""
    for result in results:
        if len(result.names) > 1:
            addresses = ", ".join(f"`{place.address}`" for place in result.places)
            message = (
                f"one result {_of(root, result)}has the names {addresses}: it is made once and "
                "placed under each, as its analysis is driven through two chains of declarations"
            )
            yield Note("two_names", message, None, (result,))


def _unplanned(
    context: Context,
    planned: Mapping[Key, Planned],
    editable: Editable,
    builds: frozenset[Identity],
) -> Iterator[Note]:
    """Each output other than a switch of an analysis read where the root is with no planned
    result: an output of a declared analysis that no planned result reads and the root's
    evidence doesn't cite; one of the root's that only a case of its own switches names, so that
    it is planned only where something planned reads it (Results *plans*); or another of the
    root's, built in none of its universes, as where it is built per universe and the root has
    none. A check of the root never covers it. It concerns what the root builds where its
    analysis is one of `builds`; an analysis the root only reads from isn't its business."""
    stack = context.stack
    outputs = {key[0] for key in planned}
    cased: dict[Element, Element] = {}  # each of the root's outputs a case of its own names
    for entry in stack.resolutions:
        if entry.field == "case" and entry.file == stack.root and entry.element is not None:
            assert entry.owner is not None  # the switch whose case it is
            cased.setdefault(entry.element, entry.owner)
    for member, analysis in editable:
        for id_, output in analysis.outputs.items():
            element = Element(member.identity, "output", id_)
            if output.is_switch or element in outputs:
                continue
            switch = cased.get(element)
            if member.identity != stack.root:
                why = "no planned result reads it and the root's evidence doesn't cite it"
            elif switch is not None:
                why = (
                    f"only a case of `{switch.id}` names it, so it is planned only where "
                    "something planned reads it, and nothing does"
                )
            elif not own_universes(stack, stack.root):
                why = "it is built per universe and the root has no universes"
            else:
                why = "it is built in none of the root's universes"
            message = (
                f"`{id_}` has no planned result: {why}, so a check of the root never covers it"
            )
            at = context.at(member.identity, ("outputs", id_))
            yield Note("unplanned", message, at, built=member.identity in builds)


def _not_built(context: Context, reached: Run) -> Iterator[Note]:
    """Each output other than a switch that the plan's run reaches in a universe where it isn't
    built, and each switch it reaches there that nothing it reaches reads there, as one it plans
    from does (Results *plans*), as a switch on the way, maybe that one, has no case there for
    the option its decision selects (Elements *switch*; Results *built*): one note for each
    output or switch, switch and option, at the entry of `outputs`, with the universes. A switch
    that something reached reads there is left to the note on its reader. A missing case breaks
    no rule: this is the plan's own report of it."""
    read = {(entry.element, at) for entry, at in reached.reads if entry.field in ("inputs", "case")}
    found: dict[tuple[Element, Element, str], list[Element]] = {}
    for element, universe in reached.reached:
        if universe is None or (element.kind == "switch" and (element, universe) in read):
            continue
        cause = context.meaning.cause(element, universe)
        if cause is not None:
            found.setdefault((element, cause.switch, cause.option), []).append(universe)
    for (output, switch, option), universes in found.items():
        whose = "" if switch.analysis == output.analysis else f" of `{switch.analysis}`"
        which = "it" if switch == output else f"`{switch.id}`{whose}"
        message = (
            f"`{output.id}` isn't built in {context.named(universes, output.analysis)}: "
            f"{which} has no case there for `{option}`, the option its decision selects"
        )
        at = context.at(output.analysis, ("outputs", output.id))
        yield Note(
            "not_built", message, at, universes=tuple(universes), switch=switch, option=option
        )


def _same_computations(root: Identity, results: Iterable[Result]) -> Iterator[Note]:
    """Each set of `results` that are one computation in several universes: of one output, so
    one command, reading the same files and the same computations, with the same options
    selected. A runner can build one and place its bytes at each. `results` come each after
    what it reads, so what a result reads already has its computation."""
    computations: dict[Key, object] = {}
    sets: dict[object, list[Result]] = {}
    for result in results:
        key = (result.output, result.universe)
        if result.universe is None or result.read_only:
            computations[key] = key  # one result, or one read through its record
            continue
        reads = tuple(
            (read.path, read.commit)
            if read.result is None
            else computations[read.result.output, read.result.universe]
            for read in result.inputs
        )
        computation = (result.output, reads, tuple(result.decisions.items()))
        computations[key] = computation
        sets.setdefault(computation, []).append(result)
    for same in sets.values():
        if len(same) > 1:
            addresses = ", ".join(f"`{r.places[0].address}` {_of(root, r)}".strip() for r in same)
            message = (
                f"{addresses} are one computation, with the same command, inputs and selected "
                "options: a runner can build one and place its bytes at each"
            )
            yield Note("same_computation", message, None, tuple(same))


def _of(root: Identity, result: Result) -> str:
    """Whose `result` is, before a message gives its address, which is in its owner's terms:
    nothing for the root's."""
    return "" if result.owner == root else f"of `{result.owner}` "


def _outside_folder(
    context: Context, editable: Editable, builds: frozenset[Identity]
) -> Iterator[Note]:
    """Each command of an analysis read where the root is that names a path climbing out of the
    analysis's folder, where the recipe runs, or one inside a folder below it that holds an
    `astra.yaml` of its own: the code a recipe runs is tracked in its analysis's folder, outside
    every analysis below it, or its output's inputs give it (`CODE_OUTSIDE_ANALYSIS`). Whether
    a folder holds an `astra.yaml` is read through the analysis's Reader, once for each folder:
    every analysis read where the root is is read in one tree. It concerns what the root builds
    where its analysis is one of `builds`."""
    holds: dict[str, bool] = {}

    def below(member: Member, path: str) -> str | None:
        """The folder below `member`'s, on the way to `path` there, that holds an `astra.yaml`
        of its own, the outermost; None where there is none."""
        folder = member.identity.folder
        inside = paths.join(folder, path)
        assert inside is not None  # a path that climbs out of `folder` isn't read here
        parts = (inside[len(folder) + 1 :] if folder else inside).split("/")[:-1]
        for count in range(1, len(parts) + 1):
            inner = posixpath.join(folder, *parts[:count])
            if inner not in holds:
                entry = member.reader.stat(posixpath.join(inner, "astra.yaml"))
                holds[inner] = entry is not None and entry.kind == "file"
            if holds[inner]:
                return inner
        return None

    for member, analysis in editable:
        for id_, output in analysis.outputs.items():
            if output.recipe is None:  # a switch runs nothing
                continue
            named: list[str] = []
            for path in _paths(output.recipe.command):
                if _climbs(path):
                    named.append(f"`{path}`, outside its analysis's folder")
                elif (inner := below(member, path)) is not None:
                    named.append(f"`{path}`, inside `{inner}`, which holds an analysis of its own")
            if not named:
                continue
            message = (
                f"the command names {'; '.join(named)}: a recipe should run only code tracked in "
                "its analysis's folder, outside every folder below it that holds an analysis of "
                "its own, or that its output's inputs give it (`CODE_OUTSIDE_ANALYSIS`)"
            )
            pointer = ("outputs", id_, "recipe", "command")
            at = context.at(member.identity, pointer)
            yield Note("outside_folder", message, at, built=member.identity in builds)


_WORD = re.compile(r"[^\s=:;&|<>()'\"`,]+")
"""A run of characters that can make up a path in a shell command: what lies between blanks,
quotes, `=` and `:` (as in `--flag=path` and `PYTHONPATH=a:b`), and the shell's operators."""


def _paths(command: str) -> list[str]:
    """Each path `command` names outside its placeholders, once, read from the left. A path
    from a placeholder starts elsewhere, and an absolute path names no folder of the analysis,
    so neither is read."""
    marked = _TEMPLATE.sub(lambda match: "\0" if match[1] is not None else match[0][0], command)
    found: list[str] = []
    for word in _WORD.findall(marked):
        if "\0" not in word and not word.startswith("/") and word not in found:
            found.append(word)
    return found


def _climbs(path: str) -> bool:
    """Whether `path` climbs out of the folder it is read from: its `..` outnumber the folders
    before them, read from the left."""
    depth = 0
    for part in path.split("/"):
        depth += -1 if part == ".." else int(part not in ("", "."))
        if depth < 0:
            return True
    return False


def outside(command: str) -> tuple[str, ...]:
    """Each path `command` names, outside its placeholders, that climbs out of the folder it
    runs in (`_paths`, `_climbs`)."""
    return tuple(path for path in _paths(command) if _climbs(path))


def selected(entries: Iterable[Resolution], selection: Selection | None) -> dict[str, str | None]:
    """Each entry of an output's `decisions`, among the addresses it writes (`entries`), as
    written, and the option `selection`, the effective selection of the universe its result is
    built in, selects for it; None where there is no selection, the entry names nothing or no
    option is selected (never, on a valid stack: `MISSING_DECISION`)."""
    return {
        entry.written: None
        if selection is None or entry.element is None
        else min(selection.options(entry.element), default=None)
        for entry in entries
        if entry.field == "decisions"
    }


_TEMPLATE = re.compile(r"\{\{|\}\}|\{([^}]*)\}")
"""What a command holds, read from the left: `{{`, `}}`, or a placeholder up to the next `}`.
A valid stack's commands hold nothing else (`UNDECLARED_TEMPLATE_REF`)."""


def render_command(
    result: Result,
    cwd: str | os.PathLike[str],
    *,
    absolute: bool = False,
    got: Mapping[str, str] | None = None,
) -> str:
    """`result`'s command with each `{{` and `}}` replaced by one brace, and each placeholder
    replaced verbatim, with no shell quoting: `{inputs.<entry>}` by the path of what the entry
    reads, `{decisions.<entry>}` by the option selected, `{inputs}` by every entry's path in
    order, separated by spaces, and `{output}` by the default place of the result's bytes.

    `cwd` is the folder the recipe runs in: `result.workdir` in the checkout it runs in, whose
    top every path of the plan is measured from. Each path is relative to `cwd`, or absolute
    where `absolute`.

    An entry that reads at a commit (`Read.commit`) names no file in the checkout: its path is
    in the tree of that commit, and the runner gets the bytes. `got` gives, by entry,
    where it put them: a path from the checkout's top, or an absolute one. An entry it doesn't
    give is written `<commit>:<path>`, git's name for the file at that commit, as `astra plan`
    shows it."""
    depth = len(result.workdir.split("/")) if result.workdir else 0
    top = os.path.join(cwd, *[os.pardir] * depth)  # one checkout for every path
    got = got or {}

    def path(place: str) -> str:
        full = os.path.normpath(os.path.join(top, place))  # an absolute `place` stays itself
        return os.path.abspath(full) if absolute else os.path.relpath(full, cwd)

    def where(read: Read) -> str:
        if read.commit is None:
            return path(read.path)
        return path(got[read.entry]) if read.entry in got else f"{read.commit}:{read.path}"

    reads = {read.entry: where(read) for read in result.inputs}

    def fill(match: re.Match[str]) -> str:
        text, placeholder = match[0], match[1]
        if text in ("{{", "}}"):
            return text[0]
        if placeholder == "output":
            return path(result.places[0].bytes)  # the first name's
        if placeholder == "inputs":
            return " ".join(reads[read.entry] for read in result.inputs)
        field, _, entry = placeholder.partition(".")
        if field == "inputs":
            return reads[entry]
        return result.decisions[entry] or ""  # None only on a stack that breaks MUST

    return _TEMPLATE.sub(fill, result.command)
