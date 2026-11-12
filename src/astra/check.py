"""check(): each planned result's record and bytes statuses, at each of its places, and the
statuses of the root's evidence and of a declared analysis's that cites a planned result (§20,
design §4.7).

A checker reads records only through planned results (§20): the plan (`plan.plan`) gives each,
each after what it reads, with its places (§18), what each entry of its output's `inputs` reads
and the option each entry of its `decisions` selects. At each place:

- the record: none is there (`MISSING_RECORD`); it breaks a parse or schema rule, by the record
  schema its minor version picks (`INVALID_RECORD`, each code it breaks a reason); its `address`
  isn't the place's (`MISPLACED_RECORD`); its `inputs` aren't one item for each entry its output
  lists at the commit it names (`MISSING_RECORD_INPUTS`). Each leaves the result `missing`, and
  the last two are checked only on a record that breaks neither of the first two (design §4.13
  case 9);
- the result is then `stale` where something `STALE_RESULT` compares has changed since the
  record's commit, the stack as it was there bound through a CommitReader, from the folder of
  the analysis the result belongs to, or where that commit can't be read or has no such output
  (§20); for each switch an entry reads through, that is the decision it switches on, the option
  selected for it where it is read and the case it takes, whatever bytes result (Results *made
  from*); otherwise it is `unchanged`;
- its bytes are `present` where those at the default place hash to the record's, and `absent`
  otherwise: `ABSENT_RESULT` where it has a valid record (§20, design §4.13 case 9).

A result of an analysis from a commit is read through its record at the declared commit, in the
analysis it belongs to, and the hashes of the results it reads are taken from their records;
only one that a planned result reads gets a bytes status (§20 *Results of an analysis from a
commit*).
Evidence gets the status of the records it cites (`STALE_EVIDENCE`, §20 *Evidence*), through
the case a switch it names takes in each of the root's universes (Results *Evidence*): the
root's, and each item of a declared analysis's evidence that cites a planned result (design
§4.7). Each record's environment gets what each registered scheme answered for it (design §4.10).

A stack that breaks a `MUST` is checked too (design §4.7): every result whose planning is
determined (design §4.13 case 12, `plan.plan`) gets its statuses, and so does the evidence citing
only such results, while the report holds the validation errors (`api.check`).
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal

from astra import environments, hashing
from astra.contract import Contract
from astra.diagnostics import Catalogue, Diagnostic, Level, Location
from astra.plan import Key, Read, RequestError, Result, plan, root_output, root_universe, selected
from astra.records import Record, read_record
from astra.rules.context import Context
from astra.sources import standins
from astra.sources.git import Repository
from astra.sources.reader import CommitReader, in_repository
from astra.sources.remote import Remotes
from astra.stack import Element, Identity, Member, Resolution, Stack, bind
from astra.universes import Place, Selection, Step, Through, along, read_in

SHAPE = "astra-check-report/1"

CODES = frozenset(
    {
        "MISSING_RECORD",
        "INVALID_RECORD",
        "MISPLACED_RECORD",
        "MISSING_RECORD_INPUTS",
        "STALE_RESULT",
        "ABSENT_RESULT",
        "STALE_EVIDENCE",
    }
)
"""The check layer's codes, which this module reports (§20)."""

RecordStatus = Literal["unchanged", "stale", "missing"]
BytesStatus = Literal["present", "absent"]

_WORST: tuple[RecordStatus, ...] = ("missing", "stale", "unchanged")
"""The record statuses, the worst first (§20 *Evidence*)."""


@dataclass(frozen=True)
class Reason:
    """A check rule broken at a place of a planned result, or by evidence (§20), and what
    breaks it."""

    code: str
    level: Level
    message: str
    location: Location  # the record, or the place in it of a parse or schema error; the bytes'
    # default place; or the evidence's `artifact`
    breaks: str | None = None  # for INVALID_RECORD, the parse or schema code the record breaks


@dataclass(frozen=True)
class Status:
    """A planned result's statuses at one of its places (§20)."""

    place: Place
    record_status: RecordStatus
    bytes_status: BytesStatus | None  # None for a result of an analysis from a commit that no
    # recipe reads
    committed: bool  # git has the record at the place as it is
    reasons: tuple[Reason, ...]
    record: Record | None  # the record there, where it is the result's: unchanged or stale
    environment: tuple[environments.Answer, ...]  # what each registered scheme answered for the
    # record's environment


@dataclass(frozen=True)
class Checked:
    """A planned result, and its statuses at each of its places, in their order."""

    result: Result
    statuses: tuple[Status, ...]


@dataclass(frozen=True)
class EvidenceStatus:
    """An item of evidence that cites an output, the root's or a declared analysis's, and the
    status it gets (§20 *Evidence*, design §4.7)."""

    location: Location  # its `artifact`, in the astra.yaml that holds it
    artifact: str  # as written
    cites: tuple[str, ...]  # the addresses of the records it is given the status of
    record_status: RecordStatus
    reasons: tuple[Reason, ...]  # STALE_EVIDENCE, where it isn't unchanged


@dataclass(frozen=True)
class CheckReport:
    """What checking an analysis found."""

    root: str  # the root's astra.yaml, as a Location's `file` names it
    at: str  # "worktree", or the commit the stack, its records and bytes are read at
    results: tuple[Checked, ...]  # in the plan's order
    evidence: tuple[EvidenceStatus, ...]
    errors: tuple[Diagnostic, ...] = ()  # the `MUST`s the analysis breaks, as `validate` finds

    @property
    def ok(self) -> bool:
        """True when the analysis is valid and every planned result, at each of its places, and
        every evidence is `unchanged`, absent bytes notwithstanding: `astra check`'s verdict."""
        # Evidence that isn't unchanged fails the check, as STALE_EVIDENCE is a MUST.
        statuses = [status.record_status for c in self.results for status in c.statuses]
        statuses += [evidence.record_status for evidence in self.evidence]
        return not self.errors and all(status == "unchanged" for status in statuses)

    def to_json(self) -> dict[str, Any]:
        """The report as `astra-check-report/1` (design §4.11)."""
        # The exact JSON form.
        return {
            "shape": SHAPE,
            "root": self.root,
            "at": self.at,
            "results": [
                {
                    "names": list(checked.result.names),
                    "owner": asdict(checked.result.owner),
                    "output": asdict(checked.result.output),
                    "universe": None
                    if checked.result.universe is None
                    else checked.result.universe.id,
                    "places": [
                        {
                            **asdict(status.place),
                            "record_status": status.record_status,
                            "bytes_status": status.bytes_status,
                            "committed": status.committed,
                            "reasons": [asdict(reason) for reason in status.reasons],
                            "environment": [asdict(answer) for answer in status.environment],
                        }
                        for status in checked.statuses
                    ],
                }
                for checked in self.results
            ],
            "evidence": [
                {
                    "location": asdict(evidence.location),
                    "artifact": evidence.artifact,
                    "cites": list(evidence.cites),
                    "record_status": evidence.record_status,
                    "reasons": [asdict(reason) for reason in evidence.reasons],
                }
                for evidence in self.evidence
            ],
            "errors": [diagnostic.to_json() for diagnostic in self.errors],
        }


def check(
    stack: Stack,
    universes: Iterable[str] | None = None,
    outputs: Iterable[str] | None = None,
    remotes: Remotes | None = None,
    errors: tuple[Diagnostic, ...] = (),
) -> CheckReport:
    """The statuses of every planned result of `stack` at each of its places, and of the root's
    evidence and each item of a declared analysis's evidence that cites a planned result (§20,
    design §4.7), its records and bytes read where the stack is: in the working tree, or at
    the commit its root is read at. Where `stack` breaks a `MUST`, whose `errors` the report
    holds, only the results whose planning is determined, and the evidence that cites only
    such results, get statuses (design §4.13 case 12).

    `universes`, ids of the root's universes, and `outputs`, addresses read in the root's file,
    only narrow the planned results reported to those built in those universes and of those
    outputs (design §4.7); the evidence is not narrowed (§20 *Evidence*). Commits are got from
    remotes through `remotes`. Raises RequestError where a universe or an output asked for isn't
    there, or is a switch, or an output asked for has no planned result there."""
    results = plan(stack).results
    narrowed = None if universes is None else {root_universe(stack, id_) for id_ in universes}
    named = {root_output(stack, address): address for address in outputs or ()}
    kept = [
        result
        for result in results
        if (narrowed is None or result.universe in narrowed)
        and (not named or result.output in named)
    ]
    for output, address in named.items():
        if not any(result.output == output for result in kept):
            where = "" if narrowed is None else " in the universes asked for"
            raise RequestError(
                f"`{address}` has no planned result{where}: a check covers only the planned "
                "results (§18), which `astra plan` lists"
            )
    catalogue = Catalogue.load()
    checker = _Checker(stack, catalogue, Contract.load(catalogue), remotes or Remotes())
    # §20 *Results of an analysis from a commit*: of the results of an analysis from a commit,
    # only those a planned result reads get a bytes status, and so ABSENT_RESULT.
    read = {
        (entry.result.output, entry.result.universe)
        for user in results
        for entry in user.inputs
        if entry.result is not None
    }
    statuses: dict[Key, tuple[Status, ...]] = {}
    for result in results:
        key = (result.output, result.universe)
        has_bytes = not result.read_only or key in read
        statuses[key] = tuple(
            checker.place(result, place, statuses, has_bytes) for place in result.places
        )
    evidence = (
        checker.evidence(entry, statuses)
        for entry in stack.resolutions
        if entry.field == "artifact"
    )
    return CheckReport(
        stack.analyses[stack.root].file,
        stack.root.commit or "worktree",
        tuple(Checked(result, statuses[result.output, result.universe]) for result in kept),
        tuple(status for status in evidence if status is not None),
        errors,
    )


@dataclass(frozen=True)
class _Then:
    """A result as the commit its record names has it (§20 *When a result is unchanged*)."""

    context: Context  # the stack bound there, from the folder of the analysis it belongs to
    output: Element  # the output its name names there
    universe: Element | None  # its universe there; None for a result built once
    selection: Selection | None  # its universe's effective selection there; None for a result
    # built once, and where that universe has none


class _Checker:
    """What one check reads, each once: the stacks bound at the records' commits, and HEAD of
    each repository that holds a record of the working tree."""

    def __init__(
        self, stack: Stack, catalogue: Catalogue, contract: Contract, remotes: Remotes
    ) -> None:
        self.stack = stack
        self.catalogue = catalogue
        self.contract = contract
        self.remotes = remotes
        self.context = Context(stack, catalogue)
        self.standins = standins.registered()
        self.schemes = environments.registered()
        self._answers: dict[str, tuple[environments.Answer, ...]] = {}
        self._bound: dict[tuple[Repository, str, str], Context | str] = {}
        self._heads: dict[Repository, CommitReader | None] = {}

    def reason(
        self, code: str, message: str, location: Location, breaks: str | None = None
    ) -> Reason:
        """`code` broken, at the level its rule's `MUST` or `SHOULD` gives (§4)."""
        return Reason(code, self.catalogue.level(code), message, location, breaks)

    def place(
        self,
        result: Result,
        place: Place,
        statuses: Mapping[Key, tuple[Status, ...]],
        has_bytes: bool,
    ) -> Status:
        """`result`'s statuses at `place`, from those of the results it reads (`statuses`)."""
        member = self.stack.analyses[result.owner]
        at = _location(member, place.record)
        found = read_record(member.reader, place.record, self.contract)
        reasons: list[Reason] = []
        status: RecordStatus = "missing"
        record = None
        if found is None:
            message = (
                f"no record is at {place.record}: build `{place.address}`, and record it there"
            )
            reasons.append(self.reason("MISSING_RECORD", message, at))
        elif isinstance(found, tuple):
            for broken in found:
                # A record below 0.1 breaks INVALID_RECORD itself, and no other code says why.
                breaks = None if broken.code == "INVALID_RECORD" else broken.code
                reasons.append(
                    self.reason("INVALID_RECORD", broken.message, broken.location, breaks)
                )
        else:
            if found.address != place.address:
                message = (
                    f"the record's address is `{found.address}`, where this place is "
                    f"`{place.address}`'s: a record is the record only of the result it names"
                )
                reasons.append(self.reason("MISPLACED_RECORD", message, at))
            then = self._then(result, place, found)
            if isinstance(then, str):  # stale, since what it is compared with is gone (§20)
                if not reasons:
                    reasons.append(self.reason("STALE_RESULT", then, at))
                    status, record = "stale", found
            else:
                reasons.extend(self._inputs(found, then, at))
                if not reasons:
                    changes = self._changes(result, found, then, statuses)
                    reasons.extend(self.reason("STALE_RESULT", change, at) for change in changes)
                    status, record = ("stale" if changes else "unchanged"), found
        bytes_status: BytesStatus | None = None
        if has_bytes:
            bytes_status, absent = self._bytes(member, place, record)
            reasons.extend(absent)
        committed = found is not None and self._committed(member, place.record)
        answers = () if record is None else self._environment(record.environment)
        return Status(place, status, bytes_status, committed, tuple(reasons), record, answers)

    def _environment(self, iri: str) -> tuple[environments.Answer, ...]:
        """What each registered scheme that recognises the environment `iri` answered for it
        (design §4.10)."""
        # What a scheme answers, and where the report shows it.
        if iri not in self._answers:
            self._answers[iri] = environments.answers(iri, self.schemes)
        return self._answers[iri]

    def _then(self, result: Result, place: Place, record: Record) -> _Then | str:
        """`result` as the commit `record` names has it: the stack bound there, from the folder
        of the analysis it belongs to, the output its name at `place` names there, and its
        universe's effective selection there; or why that can't be read, which leaves it
        `stale` (§20)."""
        commit = record.commit
        member = self.stack.analyses[result.owner]
        repo, folder = member.reader.holding(member.identity.folder)
        key = (repo, commit, folder)
        if key not in self._bound:
            self._bound[key] = self._bind(repo, commit, folder, member.url)
        context = self._bound[key]
        if isinstance(context, str):
            return context
        output = context.stack.element(place.name, "output")
        if output is None:
            return (
                f"at {commit[:12]}, the commit the record names, `{place.name}` names no output, "
                "so what the result was made from can't be compared"
            )
        universe, selection = None, None
        if result.universe is not None:
            universe = Element(context.stack.root, "universe", result.universe.id)
            selection = context.selections.get(universe)
        return _Then(context, output, universe, selection)

    def _bind(self, repo: Repository, commit: str, folder: str, url: str | None) -> Context | str:
        """The stack as it is at `commit` of `repo`, got from `url` where it is a remote's, from
        the analysis in `folder`; or why it can't be read there."""
        got = repo.has_commit(commit) if url is None else self.remotes.get(url, commit) is not None
        if not got:
            where = "the repository that holds its analysis" if url is None else f"`{url}`"
            return (
                f"the record names the commit `{commit}`, which {where} hasn't, so what the "
                "result was made from can't be compared"
            )
        reader = CommitReader(repo, commit, url, self.remotes)
        file = posixpath.join(folder, "astra.yaml")
        entry = reader.stat(file)
        if entry is not None and entry.kind == "file":
            bound = bind(reader, folder, self.catalogue, self.remotes)
            if bound.stack is not None:
                return Context(bound.stack, self.catalogue)
        return (
            f"at {commit[:12]}, the commit the record names, {file} isn't a valid astra.yaml, so "
            "what the result was made from can't be compared"
        )

    def _inputs(self, record: Record, then: _Then, at: Location) -> Iterable[Reason]:
        """`MISSING_RECORD_INPUTS`: one item of the record's `inputs` for each entry its output
        lists at the record's commit, matched by `entry`, and no other (§19), in any order
        (`MISSING_RECORD_INPUTS`, §20 *The rules*)."""
        listed = then.context.stack.analysis(then.output.analysis).outputs[then.output.id].inputs
        items = [item.entry for item in record.inputs]
        commit = record.commit[:12]
        for entry in listed:
            if entry not in items:
                message = (
                    f"the record has no item for `{entry}`, which its output lists at {commit}"
                )
                yield self.reason("MISSING_RECORD_INPUTS", message, at)
        for entry in dict.fromkeys(items):
            if entry not in listed:
                message = (
                    f"the record has an item for `{entry}`, which its output doesn't list at "
                    f"{commit}"
                )
                yield self.reason("MISSING_RECORD_INPUTS", message, at)
            elif items.count(entry) > 1:
                message = f"the record has {items.count(entry)} items for `{entry}`, not one"
                yield self.reason("MISSING_RECORD_INPUTS", message, at)

    def _changes(
        self,
        result: Result,
        record: Record,
        then: _Then,
        statuses: Mapping[Key, tuple[Status, ...]],
    ) -> list[str]:
        """What has changed, since the commit `record` names, of what `STALE_RESULT` compares:
        the output's declaration, the options its decisions select in its universe, for each
        switch an entry reads through the decision it switches on, the option selected for it
        and the case it takes, the content of its inputs, and the results it reads
        (`STALE_RESULT`, §20 *The rules*; §20 *When a result is unchanged*; Results *made
        from*)."""
        commit = record.commit[:12]
        now = self.stack.analysis(result.output.analysis).outputs[result.output.id]
        was = then.context.stack.analysis(then.output.analysis).outputs[then.output.id]
        changes = []
        assert now.recipe is not None and was.recipe is not None  # a result's output's
        if now.recipe.command != was.recipe.command:
            changes.append(f"its recipe's command isn't the one it had at {commit}")
        if now.inputs != was.inputs:
            changes.append(
                f"its inputs are {_listed(now.inputs)}, in that order, where they were "
                f"{_listed(was.inputs)} at {commit}"
            )
        if set(now.decisions) != set(was.decisions):
            changes.append(
                f"its decisions are {_listed(now.decisions)}, where they were "
                f"{_listed(was.decisions)} at {commit}"
            )
        if now.format != was.format:
            changes.append(f"its format is `{now.format}`, where it was `{was.format}` at {commit}")
        before = selected(then.context.written[then.output], then.selection)
        for written, option in result.decisions.items():
            if written in before and before[written] != option:
                assert result.universe is not None  # an output built once lists no decisions
                changes.append(
                    f"`{written}` selects {_option(option)} in `{result.universe.id}`, where it "
                    f"selected {_option(before[written])} at {commit}"
                )
        recorded = {item.entry: item for item in record.inputs}
        entries = [
            entry for entry in self.context.written[result.output] if entry.field == "inputs"
        ]
        listed = {  # the output's entries at that commit, by how each is written
            entry.written: entry
            for entry in then.context.written[then.output]
            if entry.field == "inputs"
        }
        for entry, read in zip(entries, result.inputs, strict=True):
            item = recorded.get(read.entry)
            if item is None:  # an entry its output didn't list at that commit: a change above
                continue
            through = self.context.meaning.through(entry, result.universe)
            assert through is not None  # what a planned result reads is determined
            earlier = listed.get(entry.written)
            read_then = (
                None if earlier is None else then.context.meaning.through(earlier, then.universe)
            )
            changes.extend(
                _switched(read.entry, through, read_then, self.context, then.context, commit)
            )
            if read.result is None:
                found = self._content(through.target.analysis, read)
                if found is None:  # stale, since it can't be compared (§20)
                    changes.append(
                        f"the content of `{read.entry}` can't be read at {read.path}: no file "
                        "is there, or only a stand-in that gives no SHA-256"
                    )
                elif found != item.digest:
                    changes.append(
                        f"the content of `{read.entry}`, {read.path}, isn't what the recipe read"
                    )
                continue
            status = _read(read, statuses)
            address = status.place.address
            what = f"`{address}`, which it reads" + (
                "" if read.entry == address else f" through `{read.entry}`"
            )
            if status.record_status != "unchanged":
                how = "has no valid record" if status.record_status == "missing" else "is stale"
                changes.append(f"{what}, {how}")
            elif status.record is not None and status.record.digest != item.digest:
                changes.append(f"{what}, was made again since, with other bytes than it read")
        return changes

    def _content(self, analysis: Identity, read: Read) -> hashing.Digest | None:
        """The hash and size of an input of `analysis`, which may be another than the switch's
        an entry reads it through: of its file or, where a stand-in is at its path, what the
        stand-in gives of it, never the stand-in's own (§20); None where neither is there, as
        where a stand-in beside its path gives no SHA-256."""
        reader = self.stack.analyses[analysis].reader
        for standin in self.standins:
            if standin.place(read.path) == read.path and standin.recognises(reader, read.path):
                given = standin.gives(reader, read.path)
                return None if given is None else hashing.Digest(*given)
        return hashing.digest(reader, read.path)

    def _bytes(
        self, member: Member, place: Place, record: Record | None
    ) -> tuple[BytesStatus, tuple[Reason, ...]]:
        """The bytes' status at `place`, against `record`, the result's record there or None
        where it has none, and `ABSENT_RESULT` where they are absent and it has one (§18, §20,
        design §4.13 case 9)."""
        if record is None:  # no recorded bytes, so absent, but no ABSENT_RESULT
            return "absent", ()
        found = hashing.digest(member.reader, place.bytes)
        if found is not None and found == record.digest:
            return "present", ()
        if found is None:
            message = f"no file is at {place.bytes}, the result's default place"
        else:
            message = f"the bytes at {place.bytes} aren't the ones its record gives"
        return "absent", (self.reason("ABSENT_RESULT", message, _location(member, place.bytes)),)

    def _committed(self, member: Member, path: str) -> bool:
        """Whether git has the record at `path` as it is: one read at a commit has; one in the
        working tree where HEAD of the repository that holds its analysis holds the same bytes
        there."""
        # Committed is HEAD's, byte for byte.
        reader = member.reader
        if isinstance(reader, CommitReader):
            return True
        repo, inner = in_repository(reader, member.identity.folder, path)
        if repo not in self._heads:
            head = repo.head()
            self._heads[repo] = (
                None if head is None else CommitReader(repo, head, None, self.remotes)
            )
        kept = self._heads[repo]
        if kept is None:
            return False
        entry = kept.stat(inner)
        return entry is not None and entry.kind == "file" and kept.read(inner) == reader.read(path)

    def evidence(
        self, entry: Resolution, statuses: Mapping[Key, tuple[Status, ...]]
    ) -> EvidenceStatus | None:
        """The status of the evidence `entry` (§20 *Evidence*), from the planned results it cites
        (`_cited`). Each gives the record at the place of its name along the artifact's
        declarations, then each case's, from the analysis it belongs to (`universes.along`), or,
        where they give none of its names, the worst of its records. None where its `artifact`
        names nothing, or what it cites is undetermined or a result whose planning isn't, as
        only on a stack that breaks a `MUST` (design §4.13 cases 4 to 7, 12 and 13); and for a
        declared analysis's evidence that cites no planned result, which a check doesn't cover."""
        element = entry.element
        if element is None:  # design §4.13 cases 4 and 5
            return None
        cited = self._cited(entry, element)
        if cited is None or (entry.file != self.stack.root and not cited):
            return None
        read: list[Status] = []
        for through in cited:
            key = (through.target, through.universe)
            if key not in statuses:
                return None
            index = along(self.context.building.planned[key], through.chain)
            each = statuses[key]
            read.extend(each if index is None else each[index : index + 1])
        status = _worst(s.record_status for s in read)
        location = self.stack.location(entry.file, entry.pointer)
        reasons: tuple[Reason, ...] = ()
        addresses = tuple(s.place.address for s in read)
        if status != "unchanged":
            none = (
                "cites no result: it takes a case with a planned result in none of the root's "
                "universes"
                if element.kind == "switch"
                else "cites no result: its output is built in none of the root's universes"
            )
            what = (
                f"cites {', '.join(f'`{address}`' for address in addresses)}, whose record is "
                f"{status}"
                if read
                else none
            )
            reasons = (self.reason("STALE_EVIDENCE", f"`{entry.written}` {what}", location),)
        return EvidenceStatus(location, entry.written, addresses, status, reasons)

    def _cited(self, entry: Resolution, element: Element) -> list[Through] | None:
        """What the evidence `entry`, the root's or a declared analysis's, reads for each planned
        result it cites (§20 *Evidence*; Results *Evidence*), each once: one where its `artifact`
        is pinned or names an output built once; and otherwise, where it names an output built
        per universe or a switch, in each of the root's universes, its output's result there, or
        the result of the case the switch takes there, where it is planned.

        None where, once or in one of those universes, what it cites is undetermined: its pin
        names no universe (design §4.13 case 5); a switch on the way is undetermined there
        (case 6), as one on a cycle is (case 13), or takes a case that names nothing (case 5);
        or what it reaches is planned by the root's run, but with its planning undetermined
        (cases 7, 12 and 13) or in a universe that doesn't build its analysis (case 12). Where a
        switch on the way takes no case, or what it reaches isn't built, it cites nothing
        there."""
        context, building = self.context, self.context.building
        if entry.pin is not None and context.pins[entry] is None:
            return None  # design §4.13 case 5
        universes: list[Element | None] = [None]
        if entry.pin is None and (element.kind == "switch" or element in context.per_universe):
            universes = [u for u in building.universes if u.analysis == self.stack.root]
        found: dict[Key, Through] = {}
        for universe in universes:
            through = context.meaning.through(entry, universe)
            if through is None:
                # a switch on the way takes no case (False), or is undetermined (None)
                at = read_in(entry, universe, context.pins, context.per_universe)
                if context.meaning.built(element, at) is not False:
                    return None
                continue
            key = (through.target, through.universe)
            if key in building.planned:
                found.setdefault(key, through)
            elif key in building.run.planned:  # planned, but not determined (design §4.13 case 12)
                return None
        return list(found.values())


def _switched(
    entry: str, now: Through, then: Through | None, here: Context, was: Context, commit: str
) -> list[str]:
    """What has changed, since `commit`, of the switches `entry` reads through, `now` and `then`
    as the stacks `here` and `was` have them: which switches it reads through, each one's
    decision, the option selected for it where it is read, and the case it takes (Results *made
    from*), whatever bytes result. Compared step by step, up to the first whose switch, decision
    or case differs, after which the steps follow other cases."""
    if then is None:
        if not now.steps:
            return []
        return [
            f"`{entry}` reads through {_switches(now.steps)}, where what it read at {commit} isn't "
            "determined there"
        ]
    other = (
        f"`{entry}` reads through {_switches(now.steps)}, where it read through "
        f"{_switches(then.steps)} at {commit}"
    )
    changes: list[str] = []
    for step, before in zip(now.steps, then.steps, strict=False):
        if _which(step) != _which(before):
            return [*changes, other]
        decision = here.stack.switches[step.switch].decision.written
        earlier = was.stack.switches[before.switch].decision.written
        if decision != earlier:
            return [
                *changes,
                f"`{step.switch.id}` switches on `{decision}`, where it switched on `{earlier}` at "
                f"{commit}",
            ]
        if step.option != before.option:
            changes.append(
                f"`{step.switch.id}` switches on `{decision}`, which selects `{step.option}` in "
                f"`{step.universe.id}`, where it selected `{before.option}` at {commit}"
            )
        elif step.case.written != before.case.written:
            changes.append(
                f"`{step.switch.id}`'s case for `{step.option}` is `{step.case.written}`, where it "
                f"was `{before.case.written}` at {commit}"
            )
        if step.case.written != before.case.written:
            return changes  # the steps after follow other cases
    if len(now.steps) != len(then.steps):
        changes.append(other)
    return changes


def _switches(steps: tuple[Step, ...]) -> str:
    """The switches of `steps`, in order, or that there are none."""
    return " then ".join(f"`{step.switch.id}`" for step in steps) or "no switch"


def _which(step: Step) -> tuple[str, str]:
    """A switch, by its analysis's folder and its id, as one stack and another bound at an
    earlier commit both know it."""
    return step.switch.analysis.folder, step.switch.id


def _worst(statuses: Iterable[RecordStatus]) -> RecordStatus:
    """The worst of `statuses`, `missing` then `stale`; `missing` where there are none (§20
    *Evidence*)."""
    found = set(statuses)
    return next((status for status in _WORST if status in found), "missing")


def _read(read: Read, statuses: Mapping[Key, tuple[Status, ...]]) -> Status:
    """The status of the place whose bytes `read` reads (`plan.Read.place`)."""
    done = read.result
    assert done is not None
    return next(s for s in statuses[done.output, done.universe] if s.place == read.place)


def _location(member: Member, path: str) -> Location:
    """The file at `path` in `member`'s tree, and the commit and remote it is read at."""
    return Location(path, "", None, None, None, member.identity.commit, member.url)


def _listed(items: Iterable[str]) -> str:
    """`[a, b]`, each in backticks; `none` for no item."""
    found = [f"`{item}`" for item in items]
    return f"[{', '.join(found)}]" if found else "none"


def _option(option: str | None) -> str:
    return "nothing" if option is None else f"`{option}`"
