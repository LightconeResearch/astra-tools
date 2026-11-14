"""Binding: the analysis stack, read once each, with every address resolved.

`bind` reads the root's `astra.yaml` and follows every declaration, reading each analysis once
by its identity: its folder, from the top of the root's working tree or of the repository it
is read in, and the commit it is read at, or None for the working tree. A
declaration by `path` alone is read as the declaring analysis is; one with a `commit` at that
commit, through a `CommitReader`, in the repository that holds the declaring file or, in a file
read from a remote, from that remote; one with a `url` at the top of that repository, from its
store in the cache (`sources.remote`). Each file is loaded (`load`) and checked by the contract
(`contract`); one that breaks a parse or schema rule, or `UNSUPPORTED_SPEC_VERSION`, isn't a
valid document, its declarations aren't followed and its analysis is undetermined. Inside an
analysis read at a commit, each diagnostic's location carries the commit, and the URL it was
got from.

Each declaration keeps what it reached, or why it reached nothing. Every address of every valid
file is then resolved through its chain of declarations to an element, an analysis's
identity, a kind and an id, or to nothing. A switch is an element of its own kind, and its
addresses, its `switch` and its cases by option, are also kept by switch (`Stack.switches`;
Elements *switch*). Binding reports nothing about addresses or declarations: the rules do
(`astra.rules`).
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Literal

from astra import model
from astra.contract import Contract
from astra.diagnostics import Catalogue, Diagnostic, Location, json_pointer
from astra.grammar import (
    Address,
    parse_address,
    parse_option_reference,
    parse_reference,
)
from astra.load import Document, ParseError, load_yaml
from astra.sources import paths
from astra.sources.reader import CommitReader, Reader, UnreachableError
from astra.sources.remote import Remotes

Pointer = tuple[str | int, ...]


@dataclass(frozen=True)
class Identity:
    """What an analysis is known by (Elements *identity*): its folder, as a path from the top of the
    repository it is read in or, read in the working tree, from the top of the root's working
    tree ("" for the top), and the commit it is read at, None for the working tree."""

    folder: str
    commit: str | None = None

    def __str__(self) -> str:
        folder = self.folder or "."
        return folder if self.commit is None else f"{folder} at {self.commit}"


Outcome = Literal["reached", "invalid", "outside", "missing", "absent", "unreachable"]
"""What a declaration reached:

- `reached`: an analysis whose `astra.yaml` is a valid document;
- `invalid`: an analysis whose file isn't one, so undetermined;
- `outside`: nothing, since its `path` goes above the top (`DECLARATION_OUTSIDE_REPOSITORY`);
- `missing`: nothing, since its folder holds no `astra.yaml` file, reached through no symlink
  (`MISSING_DECLARED_ANALYSIS`);
- `absent`: nothing, since the repository that holds the declaring file hasn't its `commit`
  (`COMMIT_NOT_FOUND`);
- `unreachable`: nothing, since a commit its analysis is read from can't be got from its
  remote (`REMOTE_UNREACHABLE`).

Every outcome but `reached` leaves the declared analysis undetermined.
"""


@dataclass(frozen=True)
class Declaration:
    """An entry of an analysis's `analyses`, and what it reached."""

    owner: Identity  # the analysis whose file declares it
    id: str
    declared: model.AnalysisDeclaration
    outcome: Outcome
    folder: str | None = None  # the folder its `path` names, tidied; None above the top
    reached: Identity | None = None  # set where the outcome is `reached` or `invalid`
    unreachable: tuple[str | None, str] | None = None  # the URL and commit that can't be got


@dataclass(frozen=True)
class Member:
    """One analysis of the stack, as read."""

    identity: Identity
    reader: Reader  # what it is read through, its folder a path from the reader's top
    file: str  # its astra.yaml, as a Location's `file` names it
    document: Document | None  # None where the file breaks a parse rule
    analysis: model.Analysis | None  # None where the file isn't a valid document
    declarations: Mapping[str, Declaration]  # by id; none where `analysis` is None
    url: str | None = None  # the remote its commit was got from, if any


Kind = Literal["input", "output", "switch", "decision", "universe"]
"""An element's kind. A switch is an entry of `outputs` (Elements *switch*), but never of kind
`output`, as an import is never of kind `universe`: what wants a result, a record or a place
meets no switch, and each field that takes an output takes a switch too (`TAKES`)."""


@dataclass(frozen=True)
class Element:
    """An element an address resolves to: an analysis, known by its identity, a kind and an id.
    Two addresses that resolve to one Element are two spellings of it."""

    analysis: Identity
    kind: Kind
    id: str


Field = Literal[
    "inputs",
    "decisions",
    "switch",
    "case",
    "requires",
    "incompatible_with",
    "selection",
    "artifact",
    "import",
]
"""Where an address is written: `Output.inputs`; `Output.decisions`; `switch`,
a switch's `switch`; `case`, a value of a switch's `cases`; `Option.requires` and
`Option.incompatible_with`; a key of `Universe.decisions` (`selection`); `Evidence.artifact`;
and an import's `analysis` then `.` and its `universe`."""

TAKES: Mapping[Field, tuple[Kind, ...]] = MappingProxyType(
    {
        "inputs": ("input", "output", "switch"),  # an id two kinds share names nothing
        "decisions": ("decision",),
        "switch": ("decision",),
        "case": ("input", "output", "switch"),
        "requires": ("decision",),
        "incompatible_with": ("decision",),
        "selection": ("decision",),
        "artifact": ("output", "switch"),
        "import": ("universe",),
    }
)
"""The kinds of element each field's address resolves to (Rules `UNRESOLVED_ADDRESS`). An
address whose id is an element of more than one of them, as an input and an output or a switch
sharing an id (`AMBIGUOUS_ID`), names nothing."""


@dataclass(frozen=True)
class Resolution:
    """One address as written, and what it resolves to."""

    file: Identity  # the analysis whose astra.yaml writes it, where it is read
    owner: Element | None  # the output, switch, decision or entry of `universes` it is written
    # in; None for evidence
    field: Field
    pointer: Pointer  # where it is written; for a key of Universe.decisions, the map
    key: str | None  # the key of Universe.decisions; otherwise None
    written: str  # the value as written; for an import, `analysis.universe`
    address: Address  # without a pin or an option
    pin: str | None  # a reference's pin
    option: str | None  # the option a constraint or a selection names or, for a case, the option
    # it is keyed by
    chain: tuple[Declaration, ...]  # the declarations it goes through, as far as they resolve
    element: Element | None  # None where it names nothing
    undetermined: bool  # it goes through a declaration whose analysis is undetermined


@dataclass(frozen=True)
class Switch:
    """A switch's addresses as resolved (Elements *switch*): its `switch`, and its `cases` by
    option."""

    decision: Resolution  # field "switch"
    cases: Mapping[str, Resolution]  # field "case", by the option id each is keyed by


@dataclass(frozen=True)
class Stack:
    """The root and every analysis it declares, directly or through others (Rules *stack*)."""

    root: Identity
    analyses: Mapping[Identity, Member]  # in the order they were reached, the root first
    resolutions: tuple[Resolution, ...]  # every address of every valid file
    switches: Mapping[Element, Switch]  # every switch of every valid file, as `resolutions`
    # orders them

    def analysis(self, identity: Identity) -> model.Analysis:
        """The content of `identity`'s file, which is a valid document: every analysis an
        address resolves into, or a key drives, is one."""
        analysis = self.analyses[identity].analysis
        assert analysis is not None
        return analysis

    def element(self, address: str, kind: Kind) -> Element | None:
        """The element of kind `kind` that `address` names, read in the root's file; None
        where it names none."""
        return _resolve(self.analyses, self.root, parse_address(address), (kind,))[1]

    def determined(self) -> Iterator[tuple[Member, model.Analysis]]:
        """Each analysis whose file is a valid document, with its content: those the validator
        layer checks."""
        for member in self.analyses.values():
            if member.analysis is not None:
                yield member, member.analysis

    def location(self, identity: Identity, pointer: Pointer, key: str | None = None) -> Location:
        """Where `pointer`, and its key `key`, are in `identity`'s astra.yaml."""
        member = self.analyses[identity]
        found = None if member.document is None else member.document.position(pointer, key)
        line, column = found or (None, None)
        commit, url = member.identity.commit, member.url
        return Location(member.file, json_pointer(pointer), line, column, key, commit, url)


@dataclass(frozen=True)
class Bound:
    """What binding gives: the stack, and the parse and schema diagnostics of its files. The
    stack is None where the root's file isn't a valid document, and where the root is in no
    repository, whose declarations aren't followed."""

    stack: Stack | None
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True)
class _Place:
    """Where an analysis is read: its identity, its reader, and the remote its commit was got
    from, if any."""

    identity: Identity
    reader: Reader
    url: str | None


def bind(
    reader: Reader, root: str, catalogue: Catalogue | None = None, remotes: Remotes | None = None
) -> Bound:
    """The stack whose root is the analysis in the folder `root` of `reader` ("" for its top).
    Commits are got from remotes through `remotes`. Raises OSError where a file that is there
    can't be read."""
    catalogue = catalogue or Catalogue.load()
    contract = Contract.load(catalogue)
    remotes = remotes or Remotes()
    diagnostics: list[Diagnostic] = []
    members: dict[Identity, Member] = {}

    def read(place: _Place) -> model.Analysis | None:
        identity = place.identity
        file = posixpath.join(identity.folder, "astra.yaml")
        document, found = _check(place.reader.read(file), file, contract, catalogue)
        diagnostics.extend(
            replace(d, location=replace(d.location, commit=identity.commit, url=place.url))
            for d in found
        )
        analysis = None if found or document is None else model.Analysis.from_json(document.value)
        members[identity] = Member(
            identity, place.reader, file, document, analysis, MappingProxyType({}), place.url
        )
        return analysis

    at = (reader.commit, reader.url) if isinstance(reader, CommitReader) else (None, None)
    top = _Place(Identity(root, at[0]), reader, at[1])
    if read(top) is None or reader.repo is None:
        return Bound(None, tuple(diagnostics))
    todo = [top]
    while todo:
        owner = todo.pop(0)
        analysis = members[owner.identity].analysis
        assert analysis is not None
        declarations: dict[str, Declaration] = {}
        for id_, declared in analysis.analyses.items():
            declaration, place = _follow(remotes, owner, id_, declared)
            if place is not None and place.identity not in members:
                if read(place) is not None:
                    todo.append(place)
            if declaration.reached is not None and members[declaration.reached].analysis is None:
                declaration = replace(declaration, outcome="invalid")
            declarations[id_] = declaration
        member = members[owner.identity]
        members[owner.identity] = replace(member, declarations=MappingProxyType(declarations))
    resolutions = tuple(
        resolution
        for member in members.values()
        if member.analysis is not None
        for resolution in _resolutions(members, member.identity, member.analysis)
    )
    stack = Stack(top.identity, MappingProxyType(members), resolutions, _switches(resolutions))
    return Bound(stack, tuple(diagnostics))


def _check(
    data: bytes, file: str, contract: Contract, catalogue: Catalogue
) -> tuple[Document | None, tuple[Diagnostic, ...]]:
    """The document, and its parse and schema diagnostics: a file that can't be read is checked
    no further."""
    try:
        document = load_yaml(data)
    except ParseError as error:
        location = Location(file, "", error.line, error.column)
        return None, (catalogue.diagnostic(error.code, error.message, location),)
    return document, contract.check_analysis(document, file)


def _follow(
    remotes: Remotes, owner: _Place, id_: str, declared: model.AnalysisDeclaration
) -> tuple[Declaration, _Place | None]:
    """What a declaration of `owner`'s file reaches, and where that analysis is read: by `path`
    alone, as `owner` is read; with a `commit`, the `path` at that commit, in the repository that
    holds the declaring file or, in a file read from a remote, from that remote; with a `url`,
    the top of that repository at its commit. At a commit, a path that crosses a gitlink is read
    in the submodule's repository, at the commit the gitlink pins."""

    def stop(
        outcome: Outcome, folder: str | None, unreachable: tuple[str | None, str] | None = None
    ) -> tuple[Declaration, None]:
        return Declaration(owner.identity, id_, declared, outcome, folder, None, unreachable), None

    commit = declared.commit
    folder: str | None
    if declared.url is not None:
        assert commit is not None  # URL_WITHOUT_COMMIT is the schema's
        folder, repo = "", remotes.get(declared.url, commit)
        if repo is None:
            return stop("unreachable", folder, (declared.url, commit))
        reader: Reader = CommitReader(repo, commit, declared.url, remotes)
    elif commit is not None:
        assert declared.path is not None  # INVALID_DECLARATION_SOURCE is the schema's
        holder, base = owner.reader.holding(owner.identity.folder)
        folder = paths.join(base, declared.path)
        if owner.url is None:  # a file not read from a remote: its own repository's commit
            if not holder.has_commit(commit):
                return stop("absent", folder)
            reader = CommitReader(holder, commit, None, remotes)
        else:
            repo = remotes.get(owner.url, commit)
            if repo is None:
                return stop("unreachable", folder, (owner.url, commit))
            reader = CommitReader(repo, commit, owner.url, remotes)
    else:
        assert declared.path is not None
        folder, reader = paths.join(owner.identity.folder, declared.path), owner.reader
    if folder is None:
        return stop("outside", None)
    file = posixpath.join(folder, "astra.yaml")
    if isinstance(reader, CommitReader):
        try:
            found = reader.locate(file)
        except UnreachableError as error:
            return stop("unreachable", folder, (error.url, error.commit))
        if found is None:
            return stop("missing", folder)
        inner, path = found
        place = _Place(Identity(posixpath.dirname(path), inner.commit), inner, inner.url)
    else:
        entry = reader.stat(file)
        if entry is None or entry.kind != "file":
            return stop("missing", folder)
        place = _Place(Identity(folder), reader, None)
    return Declaration(owner.identity, id_, declared, "reached", folder, place.identity), place


def _resolutions(
    members: Mapping[Identity, Member], file: Identity, analysis: model.Analysis
) -> Iterator[Resolution]:
    """Every address `analysis`'s file writes, each resolved (`TAKES`)."""

    def resolve(
        owner: Element | None,
        field: Field,
        pointer: Pointer,
        written: str,
        address: Address,
        *,
        key: str | None = None,
        pin: str | None = None,
        option: str | None = None,
    ) -> Resolution:
        chain, element, undetermined = _resolve(members, file, address, TAKES[field])
        if field == "import" and element is not None and element.analysis == file:
            element = None  # an import names another analysis's universe
        return Resolution(
            file, owner, field, pointer, key, written, address, pin, option, chain, element,
            undetermined,
        )  # fmt: skip

    def constraints(
        owner: Element, field: Field, at: Pointer, written: Sequence[str]
    ) -> Iterator[Resolution]:
        for index, text in enumerate(written):
            reference = parse_option_reference(text)
            pointer = (*at, field, index)
            yield resolve(owner, field, pointer, text, reference.decision, option=reference.option)

    for id_, output in analysis.outputs.items():
        at: Pointer = ("outputs", id_)
        if output.switch is not None:  # its `switch`, then its cases in the file's order
            owner = Element(file, "switch", id_)
            pointer = (*at, "switch")
            yield resolve(owner, "switch", pointer, output.switch, parse_address(output.switch))
            for option_id, text in output.cases.items():
                reference = parse_reference(text)
                pointer = (*at, "cases", option_id)
                yield resolve(
                    owner, "case", pointer, text, reference.address, pin=reference.pin,
                    option=option_id,
                )  # fmt: skip
            continue
        owner = Element(file, "output", id_)
        for index, text in enumerate(output.inputs):
            reference = parse_reference(text)
            pointer = (*at, "inputs", index)
            yield resolve(owner, "inputs", pointer, text, reference.address, pin=reference.pin)
        for index, text in enumerate(output.decisions):
            pointer = (*at, "decisions", index)
            yield resolve(owner, "decisions", pointer, text, parse_address(text))
    for id_, decision in analysis.decisions.items():
        owner = Element(file, "decision", id_)
        for option_id, option in decision.options.items():
            at = ("decisions", id_, "options", option_id)
            yield from constraints(owner, "requires", at, option.requires)
            yield from constraints(owner, "incompatible_with", at, option.incompatible_with)
    for id_, universe in analysis.universes.items():
        owner = Element(file, "universe", id_)
        if universe.analysis is not None and universe.universe is not None:
            written = f"{universe.analysis}.{universe.universe}"
            yield resolve(owner, "import", ("universes", id_), written, parse_address(written))
        for text, option_id in universe.decisions.items():
            pointer = ("universes", id_, "decisions")
            address = parse_address(text)
            yield resolve(owner, "selection", pointer, text, address, key=text, option=option_id)
    insights = (("prior_insights", analysis.prior_insights), ("findings", analysis.findings))
    for group, entries in insights:
        for id_, insight in entries.items():
            for index, evidence in enumerate(insight.evidence):
                if evidence.artifact is not None:
                    reference = parse_reference(evidence.artifact)
                    pointer = (group, id_, "evidence", index, "artifact")
                    yield resolve(
                        None, "artifact", pointer, evidence.artifact, reference.address,
                        pin=reference.pin,
                    )  # fmt: skip


def _resolve(
    members: Mapping[Identity, Member], file: Identity, address: Address, kinds: Sequence[Kind]
) -> tuple[tuple[Declaration, ...], Element | None, bool]:
    """The chain of declarations `address` goes through from `file`, the element it resolves
    to, and whether it goes through an undetermined analysis. An id that is an element of more
    than one of `kinds` resolves to none."""
    chain: list[Declaration] = []
    current = file
    for id_ in address.declarations:
        declaration = members[current].declarations.get(id_)
        if declaration is None:
            return tuple(chain), None, False
        chain.append(declaration)
        if declaration.outcome != "reached" or declaration.reached is None:
            return tuple(chain), None, True
        current = declaration.reached
    analysis = members[current].analysis
    assert analysis is not None  # a declaration that reaches an invalid file is `invalid`
    found = [kind for kind in kinds if address.id in _elements(analysis, kind)]
    element = Element(current, found[0], address.id) if len(found) == 1 else None
    return tuple(chain), element, False


def _switches(resolutions: Sequence[Resolution]) -> Mapping[Element, Switch]:
    """Each switch, with its `switch` and its cases as resolved: a switch's `switch` comes before
    its cases in `resolutions` (`_resolutions`)."""
    decisions: dict[Element, Resolution] = {}
    cases: dict[Element, dict[str, Resolution]] = {}
    for resolution in resolutions:
        owner, option = resolution.owner, resolution.option
        if resolution.field == "switch":
            assert owner is not None  # the switch it is written in
            decisions[owner], cases[owner] = resolution, {}
        elif resolution.field == "case":
            assert owner is not None and option is not None  # a case is keyed by an option
            cases[owner][option] = resolution
    return MappingProxyType(
        {owner: Switch(found, MappingProxyType(cases[owner])) for owner, found in decisions.items()}
    )


def _elements(analysis: model.Analysis, kind: Kind) -> Mapping[str, object]:
    if kind == "input":
        return analysis.inputs
    if kind == "output":
        return {id_: o for id_, o in analysis.outputs.items() if not o.is_switch}
    if kind == "switch":
        return {id_: o for id_, o in analysis.outputs.items() if o.is_switch}
    if kind == "decision":
        return analysis.decisions
    return {id_: u for id_, u in analysis.universes.items() if not u.is_import}
