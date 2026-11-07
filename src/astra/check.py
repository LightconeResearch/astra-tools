"""check(): each planned result's record and bytes statuses, at each of its places, and the
statuses of the root's evidence (§20, design §4.7).

A checker reads records only through planned results (§20): the plan (`plan.plan`) gives each,
each after what it reads, with its places (§18), what each entry of its output's `inputs` reads
and the option each entry of its `decisions` selects. At each place:

- the record: none is there (`MISSING_RECORD`); it breaks a parse or schema rule, by the record
  schema its minor version picks (`INVALID_RECORD`, each code it breaks a reason); its `address`
  isn't the place's (`MISPLACED_RECORD`); its `inputs` aren't one item for each entry its output
  lists at the commit it names (`MISSING_RECORD_INPUTS`). Each leaves the result `missing`, and
  the last two are checked only on a record that breaks neither of the first two (Annex D
  case 9);
- the result is then `stale` where something `STALE_RESULT` compares has changed since the
  record's commit, the stack as it was there bound through a CommitReader, from the folder of
  the analysis the result belongs to; otherwise it is `unchanged`;
- its bytes are `present` where those at the default place hash to the record's, and `absent`
  otherwise (`ABSENT_RESULT`).

A result of an analysis from a commit is read through its record at the declared commit, in the
analysis it belongs to, and the hashes of the results it reads are taken from their records;
only one that a recipe reads gets a bytes status (§20 *Results of an analysis from a commit*).
Evidence gets the status of the records it cites (`STALE_EVIDENCE`, §20 *Evidence*). Each
record's environment gets what each registered scheme answered for it (design §4.10).

A check is made only of a valid stack: one that breaks a `MUST` gets no statuses (`api.check`).
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal

from astra import environments, hashing
from astra.contract import Contract
from astra.diagnostics import Catalogue, Level, Location
from astra.plan import Key, Read, RequestError, Result, plan, root_output, root_universe, selected
from astra.records import Record, read_record
from astra.rules.context import Context
from astra.sources import standins
from astra.sources.git import Repository
from astra.sources.reader import CommitReader, in_repository
from astra.sources.remote import Remotes
from astra.stack import Element, Member, Resolution, Stack, bind
from astra.universes import Place, Selection, along

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
    """An item of the root's evidence that cites an output, and the status it gets (§20
    *Evidence*)."""

    location: Location  # its `artifact`, in the root's astra.yaml
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

    @property
    def ok(self) -> bool:
        """True when every planned result, at each of its places, and every evidence is
        `unchanged`, absent bytes notwithstanding: `astra check`'s verdict."""
        # OPEN(O42): evidence that isn't unchanged fails the check, as STALE_EVIDENCE is a MUST.
        statuses = [status.record_status for c in self.results for status in c.statuses]
        statuses += [evidence.record_status for evidence in self.evidence]
        return all(status == "unchanged" for status in statuses)

    def to_json(self) -> dict[str, Any]:
        """The report as `astra-check-report/1` (design §4.11)."""
        # OPEN(O35): the exact JSON form.
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
        }


def check(
    stack: Stack,
    universes: Iterable[str] | None = None,
    outputs: Iterable[str] | None = None,
    remotes: Remotes | None = None,
) -> CheckReport:
    """The statuses of every planned result of `stack`, a valid stack, at each of its places,
    and of the root's evidence (§20), its records and bytes read where the stack is: in the
    working tree, or at the commit its root is read at.

    `universes`, ids of the root's universes, and `outputs`, addresses read in the root's file,
    only narrow the planned results reported to those built in those universes and of those
    outputs (design §4.7); the evidence is all the root's (§20 *Evidence*). Commits are got from
    remotes through `remotes`. Raises RequestError where a universe or an output asked for isn't
    there, or an output asked for has no planned result there."""
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
    # §20: only the results of an analysis from a commit that a recipe reads get a bytes status.
    read_by_recipes = {
        (entry.result.output, entry.result.universe)
        for user in results
        if not user.read_only
        for entry in user.inputs
        if entry.result is not None
    }
    statuses: dict[Key, tuple[Status, ...]] = {}
    for result in results:
        key = (result.output, result.universe)
        has_bytes = not result.read_only or key in read_by_recipes
        statuses[key] = tuple(
            checker.place(result, place, statuses, has_bytes) for place in result.places
        )
    evidence = tuple(
        checker.evidence(entry, statuses)
        for entry in stack.resolutions
        if entry.field == "artifact" and entry.file == stack.root
    )
    return CheckReport(
        stack.analyses[stack.root].file,
        stack.root.commit or "worktree",
        tuple(Checked(result, statuses[result.output, result.universe]) for result in kept),
        evidence,
    )


@dataclass(frozen=True)
class _Then:
    """A result as the commit its record names has it (§20 *When a result is unchanged*)."""

    context: Context  # the stack bound there, from the folder of the analysis it belongs to
    output: Element  # the output its name names there
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
        """`code` broken, at the level its rule's `MUST` or `SHOULD` gives (§3)."""
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
            if isinstance(then, str):
                reasons.append(self.reason("MISSING_RECORD_INPUTS", then, at))  # OPEN(O3)
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
        # OPEN(O39): what a scheme answers, and where the report shows it.
        if iri not in self._answers:
            self._answers[iri] = environments.answers(iri, self.schemes)
        return self._answers[iri]

    def _then(self, result: Result, place: Place, record: Record) -> _Then | str:
        """`result` as the commit `record` names has it: the stack bound there, from the folder
        of the analysis it belongs to, the output its name at `place` names there, and its
        universe's effective selection there; or why that can't be read, which leaves it
        `missing`."""
        # OPEN(O3): a commit that can't be read; OPEN(O34): one that holds no such output.
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
                "so what its output lists there can't be read"
            )
        selection = None
        if result.universe is not None:
            universe = Element(context.stack.root, "universe", result.universe.id)
            selection = context.selections.get(universe)
        return _Then(context, output, selection)

    def _bind(self, repo: Repository, commit: str, folder: str, url: str | None) -> Context | str:
        """The stack as it is at `commit` of `repo`, got from `url` where it is a remote's, from
        the analysis in `folder`; or why it can't be read there."""
        got = repo.has_commit(commit) if url is None else self.remotes.get(url, commit) is not None
        if not got:
            where = "the repository that holds its analysis" if url is None else f"`{url}`"
            return (
                f"the record names the commit `{commit}`, which {where} hasn't, so what its "
                "output lists there can't be read"
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
            "what its output lists there can't be read"
        )

    def _inputs(self, record: Record, then: _Then, at: Location) -> Iterable[Reason]:
        """`MISSING_RECORD_INPUTS`: one item of the record's `inputs` for each entry its output
        lists at the record's commit, matched by `entry`, and no other, in any order (§19)."""
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
        the output's declaration, the options its decisions select in its universe, the
        content of its inputs, and the results it reads (§20 *When a result is unchanged*)."""
        commit = record.commit[:12]
        now = self.stack.analysis(result.output.analysis).outputs[result.output.id]
        was = then.context.stack.analysis(then.output.analysis).outputs[then.output.id]
        changes = []
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
        for entry, read in zip(entries, result.inputs, strict=True):
            item = recorded.get(read.entry)
            if item is None:  # an entry its output didn't list at that commit: a change above
                continue
            if read.result is None:
                found = self._content(entry, read)
                if found is None:  # OPEN(O37)
                    changes.append(
                        f"the content of `{read.entry}` can't be read at {read.path}: only a "
                        "stand-in that gives no SHA-256 is there"
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

    def _content(self, entry: Resolution, read: Read) -> hashing.Digest | None:
        """The hash and size of an input's content: of its file or, where a stand-in is at its
        path, what the stand-in gives of it, never the stand-in's own (§20); None where neither
        is there, as where a stand-in beside its path gives no SHA-256."""
        assert entry.element is not None  # every address of a valid stack names an element
        reader = self.stack.analyses[entry.element.analysis].reader
        for standin in self.standins:
            if standin.place(read.path) == read.path and standin.recognises(reader, read.path):
                given = standin.gives(reader, read.path)  # OPEN(O37)
                return None if given is None else hashing.Digest(*given)
        return hashing.digest(reader, read.path)

    def _bytes(
        self, member: Member, place: Place, record: Record | None
    ) -> tuple[BytesStatus, tuple[Reason, ...]]:
        """The bytes' status at `place`, against `record`, the result's record there or None
        where it has none, and `ABSENT_RESULT` where they are absent (§18, §20)."""
        found = hashing.digest(member.reader, place.bytes)
        if record is not None and found is not None and found == record.digest:
            return "present", ()
        if record is None:  # OPEN(O38): no recorded bytes, so they are absent
            message = (
                f"the result has no valid record here, so nothing at {place.bytes} is recorded"
            )
        elif found is None:
            message = f"no file is at {place.bytes}, the result's default place"
        else:
            message = f"the bytes at {place.bytes} aren't the ones its record gives"
        return "absent", (self.reason("ABSENT_RESULT", message, _location(member, place.bytes)),)

    def _committed(self, member: Member, path: str) -> bool:
        """Whether git has the record at `path` as it is: one read at a commit has; one in the
        working tree where HEAD of the repository that holds its analysis holds the same bytes
        there."""
        # OPEN(O36): committed is HEAD's, byte for byte.
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
    ) -> EvidenceStatus:
        """The status of the root's evidence `entry` (§20 *Evidence*), from the results it cites,
        those `universes.building` reads for it that are planned: one where its `artifact` is
        pinned or names an output built once, and otherwise its output's in each of the root's
        universes where it is active and its analysis is built. Each gives the record at the
        place of its name along the artifact's declarations (`universes.along`), or, where they
        give none of its names, the worst of its records."""
        building, output = self.context.building, entry.element
        assert output is not None  # every address of a valid stack names an element
        read: list[Status] = []
        for found, at in building.reads:
            if found == entry and (output, at) in statuses:
                index = along(building.planned[output, at], entry.chain)
                each = statuses[output, at]
                read.extend(each if index is None else each[index : index + 1])
        status = _worst(s.record_status for s in read)
        location = self.stack.location(self.stack.root, entry.pointer)
        reasons: tuple[Reason, ...] = ()
        addresses = tuple(s.place.address for s in read)
        if status != "unchanged":
            what = (
                f"cites {', '.join(f'`{address}`' for address in addresses)}, whose record is "
                f"{status}"
                if read
                else "cites no result: its output is built in none of the root's universes"
            )
            reasons = (self.reason("STALE_EVIDENCE", f"`{entry.written}` {what}", location),)
        return EvidenceStatus(location, entry.written, addresses, status, reasons)


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
