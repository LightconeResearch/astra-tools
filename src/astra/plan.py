"""plan(): the root's planned results, in an order a runner can build them in, and
render_command (§11 *The command as a template*, §13, §16, §17, §18; design §4.6).

A thin layer over `universes.building`, which gives the planned results, their names and the
universe each entry reads in: each result here adds what a runner reads from it, its owner and
places (§18), what each entry of its output's `inputs` reads, the option each entry of its
`decisions` selects, its command, the folder it runs in and what its recipe asks for (§11), and
whether it is read through its record or run at a commit (§17). The plan also notes what an
author may want to tidy, though it breaks no rule (design §4.6): a pin that names another
analysis's universe only because its file has no entry of that id (§16), a result with two
names (§18), an output with no planned result (§18), results that are one computation in
several universes, and a command that names a path outside its analysis's folder, or inside an
analysis below it (`CODE_OUTSIDE_ANALYSIS`, §21).

`api.plan` plans only a valid stack: one that breaks a `MUST` has no plan. On such a stack,
`plan` gives the results whose planning is determined (design §4.13 case 12), for `check`.
Every path is a path from the top of the tree its analysis is read in (§17 *Identity*): the
root's working tree, or the repository a commit is read in.
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
    Selection,
    along,
    building,
    built,
    places,
    read_in,
)

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
    place: Place | None  # the place of the result's name whose bytes it reads; None for an input


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
    resources: Resources | None  # what its recipe asks for (§11)
    container: str | None  # its recipe's, or else its analysis's, as written (§11)


NoteKind = Literal["fallback_pin", "two_names", "unplanned", "same_computation", "outside_folder"]


@dataclass(frozen=True)
class Note:
    """Something an author may want to tidy, which breaks no rule (design §4.6)."""

    kind: NoteKind
    message: str
    location: Location | None  # the pin, the output or the command; None for the kinds of results
    results: tuple[Result, ...] = ()  # those it is about, for `two_names` and `same_computation`
    built: bool = True  # it concerns what the root builds: False only for a `fallback_pin` that no
    # planned result reads through, and an `unplanned` output or an `outside_folder` command of an
    # analysis the root doesn't build


@dataclass(frozen=True)
class Plan:
    """The planned results, each after every result it reads, and the notes on them."""

    root: str  # the root's astra.yaml, as a Location's `file` names it
    results: tuple[Result, ...]
    notes: tuple[Note, ...] = ()

    def to_json(self) -> dict[str, Any]:
        """The plan as `astra-plan/1` (design §4.11)."""
        # The exact JSON form.
        index = {(result.output, result.universe): at for at, result in enumerate(self.results)}

        def read(entry: Read) -> dict[str, Any]:
            result = entry.result
            at = None if result is None else index[result.output, result.universe]
            return {"entry": entry.entry, "path": entry.path, "commit": entry.commit, "result": at}

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
                    "container": result.container,
                }
                for result in self.results
            ],
            "notes": [note(found) for found in self.notes],
        }


def plan(
    stack: Stack, universes: Iterable[str] | None = None, outputs: Iterable[str] | None = None
) -> Plan:
    """The planned results of `stack` (§18), each after every result it reads. Where `stack`
    breaks a `MUST`, those whose planning is determined: a result is left out where an entry of
    its output's `inputs` names nothing (design §4.13 cases 4 and 5), gives an input's path above
    the top, names an output with no result planned there (`NOT_BUILT_IN_UNIVERSE`), or reads a
    result that is left out or that reads it back (`OUTPUT_CYCLE`), as `check` reads them
    (design §4.7).

    `universes`, ids of the root's universes, narrows them to the results built in those
    universes and what they read. `outputs`, addresses read in the root's file, names outputs
    to build, planned or not: each is planned as the root's own outputs are, once or in each of
    the root's universes where its analysis is built, and the plan holds its results (only
    those built once or in `universes`, where given) and what they read. Raises
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
        built = wanted is None or result.universe is None or result.universe in wanted
        return result.output in requested and built

    seeds = [result for result in found.planned.values() if chosen(result)]
    for output, address in zip(requested, addresses, strict=True):
        if not any(result.output == output for result in seeds):
            where = "the root's universes" if wanted is None else "the universes asked for"
            raise RequestError(
                f"`{address}` has no result in {where}: its analysis isn't built there"
            )
    made: dict[Key, Result] = {}
    left: set[Key] = set()  # left out, or being made: a result that reads it back is left out

    def visit(result: Planned) -> bool:
        """Make `result` after every result it reads, unless its planning isn't determined."""
        key = (result.output, result.universe)
        if key in made or key in left:
            return key in made
        left.add(key)
        reads = _reads(context, found.planned, result, bool(requested))
        if reads is None or not all(isinstance(read, str) or visit(read) for _, read in reads):
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

Reads = tuple[tuple[Resolution, Planned | str], ...]
"""Each entry of an output's `inputs`, and what it reads: a planned result, or an input's file,
as a path from the top."""


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


def _reads(
    context: Context, planned: Mapping[Key, Planned], result: Planned, requested: bool
) -> Reads | None:
    """What each entry of `result`'s output's `inputs` reads: an input's file, or a planned
    result (`read_in`). None where what one reads isn't determined, as only on a stack that
    breaks a `MUST`: it names nothing, gives a path above the top, or names an output with no
    result planned there. Where outputs are `requested`, that last raises RequestError
    instead: an output asked for can read what isn't built (§13, §16)."""
    reads: list[tuple[Resolution, Planned | str]] = []
    for entry in context.written[result.output]:
        if entry.field != "inputs":
            continue
        element = entry.element
        if element is None:
            return None
        if element.kind == "input":
            written = context.stack.analysis(element.analysis).inputs[element.id].path
            path = paths.join(element.analysis.folder, written)
            if path is None:
                return None
            reads.append((entry, path))
            continue
        at = read_in(entry, result.universe, context.pins, context.per_universe)
        read = planned.get((element, at))
        if read is None and requested:
            raise RequestError(
                f"`{result.output.id}` can't be built on request: `{entry.written}` reads a "
                "result that isn't built there"
            )
        if read is None:
            return None
        reads.append((entry, read))
    return tuple(reads)


def _result(context: Context, result: Planned, reads: Reads, made: Mapping[Key, Result]) -> Result:
    """`result` as a runner builds it, from the results it reads, already `made`."""
    stack, identity = context.stack, result.output.analysis
    inputs: list[Read] = []
    for entry, read in reads:
        assert entry.element is not None
        if isinstance(read, str):
            inputs.append(Read(entry.written, read, entry.element.analysis.commit, None, None))
            continue
        done = made[read.output, read.universe]
        # The name along the entry's declarations from the analysis `read` belongs
        # to, after `result`'s first chain where `result` belongs there too, or else the first.
        start = result.chains[0] if result.owner == read.owner else ()
        index = along(read, (*start, *entry.chain))
        place = done.places[0 if index is None else index]
        inputs.append(Read(entry.written, place.bytes, done.owner.commit, done, place))
    selection = None if result.universe is None else context.selections[result.universe]
    read_only = result.owner.commit != stack.root.commit
    analysis = stack.analysis(identity)
    recipe = analysis.outputs[result.output.id].recipe
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
        recipe.container if recipe.container is not None else analysis.container,
    )


def _notes(context: Context, found: Building, results: tuple[Result, ...]) -> tuple[Note, ...]:
    """What the plan notes (design §4.6), kind by kind. Those about files are about the files
    read where the root is, which an author can edit; those about results, about `results`.
    `fallback_pin`, `unplanned` and `outside_folder` notes say whether they concern what the root
    builds (`Note.built`): the root, and every analysis its universes drive (`built`)."""
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
        *_same_computations(stack.root, results),
        *_outside_folder(context, editable, builds),
    )


Editable = list[tuple[Member, Analysis]]
"""The analyses read where the root is, with their content."""


def _fallback_pins(context: Context, read: set[Resolution]) -> Iterator[Note]:
    """Each pin in a file read where the root is that names another analysis's universe only
    because the file's `universes` has no entry of its id, so that adding one would change what
    it names (§16 *Pins and imported universes*). It concerns what the root builds where the
    plan reads through it (`read`): an entry of a planned result's `inputs`, or of the root's
    evidence."""
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
    """Each of `results` with two names (§18 *Which analysis a result belongs to, and its name*)."""
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
    """Each output of an analysis read where the root is with no planned result (§18): an
    output of a declared analysis that no planned result reads and the root's evidence doesn't
    cite, or one of the root's built per universe, where the root has no universes. A check of
    the root never covers it. It concerns what the root builds where its analysis is one of
    `builds`; an analysis the root only reads from isn't its business."""
    stack = context.stack
    outputs = {key[0] for key in planned}
    for member, analysis in editable:
        for id_ in analysis.outputs:
            if Element(member.identity, "output", id_) in outputs:
                continue
            why = (
                "it is built per universe and the root has no universes"
                if member.identity == stack.root
                else "no planned result reads it and the root's evidence doesn't cite it"
            )
            message = (
                f"`{id_}` has no planned result: {why}, so a check of the root never covers it"
            )
            at = context.at(member.identity, ("outputs", id_))
            yield Note("unplanned", message, at, built=member.identity in builds)


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
    analysis's folder, where the recipe runs (§11), or one inside a folder below it that holds
    an `astra.yaml` of its own: the code a recipe runs is tracked in its analysis's folder,
    outside every analysis below it, or its output's inputs give it (`CODE_OUTSIDE_ANALYSIS`,
    §21). Whether a folder holds an `astra.yaml` is read through the analysis's Reader, once
    for each folder: every analysis read where the root is is read in one tree. It concerns
    what the root builds where its analysis is one of `builds`."""
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
                "its own, or that its output's inputs give it (`CODE_OUTSIDE_ANALYSIS`, §21)"
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
"""§11 *The command as a template*, read from the left: `{{`, `}}`, or a placeholder up to the
next `}`. A valid stack's commands hold nothing else (`UNDECLARED_TEMPLATE_REF`)."""


def render_command(
    result: Result,
    cwd: str | os.PathLike[str],
    *,
    absolute: bool = False,
    got: Mapping[str, str] | None = None,
) -> str:
    """`result`'s command with each placeholder, and each `{{` and `}}`, replaced as §11's table
    says, verbatim, with no shell quoting: `{inputs.<entry>}` by the path of what the entry
    reads, `{decisions.<entry>}` by the option selected, `{inputs}` by every entry's path in
    order, separated by spaces, and `{output}` by the default place of the result's bytes.

    `cwd` is the folder the recipe runs in: `result.workdir` in the checkout it runs in, whose
    top every path of the plan is measured from. Each path is relative to `cwd`, or absolute
    where `absolute`.

    An entry that reads at a commit (`Read.commit`) names no file in the checkout: its path is
    in the tree of that commit, and the runner gets the bytes (§17, §21). `got` gives, by entry,
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
