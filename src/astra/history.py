"""History: what git holds of the records of the root's planned results, read on demand. A
feature beyond the specification, built on its records and their places: nothing is indexed,
and nothing kept in the cache.

A result is named by its address, the `address` of the record at its place. The record's
versions are its file at each commit along HEAD's history that changed it (`Repository.log`),
in the repository that holds the analysis the result belongs to, each read as a checker reads a
record (`records.read_record`), so a version that breaks a parse or schema rule says so. Four
queries:

- `timeline`: each version of a result's record, newest first;
- `lineage`: what a result was made from, as its record at HEAD gives it, each entry with its
  hash and, for a planned result, the version of that result's record whose hash and size are
  the ones recorded, committed no later than the record that lists them, and so on down; or,
  `used_by`, the planned results whose records list it;
- `find`: the versions whose `content_hash`, or whose environment, is the one asked for;
- `get`: the bytes a result had at a commit, checked against its record there.

Like the plan, history is read only of a valid stack (`api.history`).
"""

from __future__ import annotations

from dataclasses import dataclass

from astra.contract import Contract
from astra.diagnostics import Catalogue, Diagnostic
from astra.hashing import Digest, digest_bytes
from astra.plan import RequestError, Result, plan
from astra.records import Record, read_record
from astra.sources.git import Repository
from astra.sources.reader import CommitReader, in_repository
from astra.sources.remote import Remotes
from astra.stack import Identity, Stack
from astra.universes import Place


class NotInHistoryError(Exception):
    """What a query asks for isn't in git: no record of the result at that commit, or not the
    bytes it records."""


@dataclass(frozen=True)
class Version:
    """A result's record at one commit."""

    place: Place  # the result's place: its address and record's path
    commit: str  # the commit that changed the record's file there; for a result read through
    # its record, the commit its analysis is read at
    record: Record | tuple[Diagnostic, ...] | None  # what the file holds there: a record, the
    # parse or schema rules it breaks, or None where that commit removed it


@dataclass(frozen=True)
class Link:
    """An entry of a record's `inputs`, and what the recipe read through it."""

    entry: str  # as the record lists it
    digest: Digest  # the hash and size the record gives
    path: str | None  # for an input, its file, as the plan reads it: a leaf
    place: Place | None  # for a planned result, the place whose bytes the plan reads; neither
    # where today's plan has no such entry
    version: Version | None  # the newest version of that result's record that gives these
    # hash and size, committed no later than the record that lists them; None where none does
    inputs: tuple[Link, ...]  # what that version was made from


@dataclass(frozen=True)
class Use:
    """A planned result whose record lists another's: the other way of a lineage."""

    version: Version  # its record, as HEAD has it
    entry: str  # the entry of its `inputs` that reads the other
    digest: Digest  # the hash and size it gives for it
    read: Version | None  # the newest version of the other's record that gives them,
    # committed no later than this record; None where none does


@dataclass(frozen=True)
class Lineage:
    """A result's record as HEAD has it, and what it was made from or what uses it."""

    place: Place
    version: Version | None  # the newest version; None where its record was never committed
    inputs: tuple[Link, ...]  # without `used_by`: what that record says it was made from
    users: tuple[Use, ...]  # with `used_by`: each planned result whose record at HEAD lists it


class History:
    """The history of the records of a valid stack's planned results (`api.history`), each
    version read once."""

    def __init__(self, stack: Stack, remotes: Remotes | None = None) -> None:
        self.stack = stack
        self.remotes = remotes or Remotes()
        self.results = plan(stack).results
        self._contract = Contract.load(Catalogue.load())
        self._kept: dict[tuple[Identity, str], tuple[Version, ...]] = {}

    def timeline(self, address: str) -> tuple[Version, ...]:
        """Each version of the record of the result at `address`, newest first. Raises
        RequestError where no planned result has that address."""
        return self._versions(*self._named(address))

    def lineage(self, address: str, *, used_by: bool = False) -> Lineage:
        """What the result at `address` was made from, as its record at HEAD gives it, and so
        on down; or, with `used_by`, the planned results whose records at HEAD list it. Raises
        RequestError where no planned result has that address."""
        # HEAD's record, and each entry's version with its hash and size (`_made`).
        result, place = self._named(address)
        versions = self._versions(result, place)
        version = versions[0] if versions else None
        if version is None or not isinstance(version.record, Record):
            return Lineage(place, version, (), ())
        if used_by:
            return Lineage(place, version, (), self._users(result, place))
        return Lineage(place, version, self._inputs(result, version), ())

    def find(
        self, *, content_hash: str | None = None, environment: str | None = None
    ) -> tuple[Version, ...]:
        """The versions of the planned results' records whose `content_hash` is `content_hash`,
        or whose environment's IRI is `environment`, in the plan's order, each result's newest
        first. Raises ValueError unless exactly one of the two is given."""
        # Today's planned results' records, by their own hash or IRI, as written.
        if (content_hash is None) == (environment is None):
            raise ValueError("give exactly one of `content_hash` and `environment`")
        return tuple(
            version
            for result in self.results
            for place in result.places
            for version in self._versions(result, place)
            if isinstance(version.record, Record)
            and (
                version.record.content_hash == content_hash
                or version.record.environment == environment
            )
        )

    def get(self, address: str, revision: str) -> bytes:
        """The bytes the result at `address` had at the commit `revision` names in the
        repository that holds its analysis: those at its default place there, which are the
        ones its record at its place there gives. Raises RequestError where no planned result
        has that address or `revision` names no commit, and NotInHistoryError where that commit
        holds no record of the result, or not the bytes it gives."""
        result, place = self._named(address)
        repo, record_path = self._held(result, place.record)
        _, bytes_ = self._held(result, place.bytes)
        commit = repo.commit(revision)
        if commit is None:
            raise RequestError(f"`{revision}` names no commit of {repo.top}")
        reader = CommitReader(repo, commit, self.stack.analyses[result.owner].url, self.remotes)
        record = read_record(reader, record_path, self._contract)
        if not isinstance(record, Record) or record.address != place.address:
            what = "no record" if record is None else f"no valid record of `{place.address}`"
            raise NotInHistoryError(f"{commit} holds {what} at {place.record}")
        entry = reader.stat(bytes_)
        if entry is None or entry.kind != "file":  # bytes left out of git
            raise NotInHistoryError(
                f"{commit} holds no file at {place.bytes}: its bytes aren't in git there"
            )
        data = reader.read(bytes_)
        if digest_bytes(data) != record.digest:
            raise NotInHistoryError(
                f"the bytes at {place.bytes} in {commit} aren't the ones its record there gives"
            )
        return data

    def _named(self, address: str) -> tuple[Result, Place]:
        """The planned result whose place has the address `address`, and that place: the
        root's own result first, then the first in the plan's order. Raises RequestError where
        none has it."""
        # An address is resolved against today's plan.
        found = [
            (result, place)
            for result in self.results
            for place in result.places
            if place.address == address
        ]
        if not found:
            raise RequestError(
                f"`{address}` is the address of no planned result: `astra plan` lists them"
            )
        return min(found, key=lambda pair: pair[0].owner != self.stack.root)

    def _versions(self, result: Result, place: Place) -> tuple[Version, ...]:
        """Each version of the record at `place` of `result`, newest first: its file at each
        commit along HEAD's history that changed it, in the repository that holds the analysis
        it belongs to; for a result read through its record, the one at the commit its
        analysis is read at."""
        key = (result.owner, place.record)
        if key not in self._kept:
            if result.read_only:  # its one version, at the declared commit
                assert result.owner.commit is not None
                reader = self.stack.analyses[result.owner].reader
                found = read_record(reader, place.record, self._contract)
                self._kept[key] = (Version(place, result.owner.commit, found),)
            else:
                (repo, path), versions = self._held(result, place.record), []
                for commit in repo.log(path):
                    reader = CommitReader(repo, commit, None, self.remotes)
                    versions.append(
                        Version(place, commit, read_record(reader, path, self._contract))
                    )
                self._kept[key] = tuple(versions)
        return self._kept[key]

    def _inputs(self, result: Result, version: Version) -> tuple[Link, ...]:
        """What `version` of `result`'s record, one that holds a record, says the recipe read,
        each entry matched with today's plan of `result`: an input's file, or the place of the
        planned result it reads and the version of its record that gives the hash and size
        recorded (`_made`), and what that one read."""
        assert isinstance(version.record, Record)
        reads = {read.entry: read for read in result.inputs}
        links = []
        for item in version.record.inputs:
            read = reads.get(item.entry)  # today's plan
            if read is None or read.result is None or read.place is None:
                path = None if read is None else read.path
                links.append(Link(item.entry, item.digest, path, None, None, ()))
                continue
            made = self._made(read.result, read.place, item.digest, result, version)
            below = () if made is None else self._inputs(read.result, made)
            links.append(Link(item.entry, item.digest, None, read.place, made, below))
        return tuple(links)

    def _users(self, result: Result, place: Place) -> tuple[Use, ...]:
        """Each place of a planned result that reads `result` at `place` and whose record at
        HEAD lists it, with the hash and size it gives, and the version of `result`'s record
        that gives them."""
        uses = []
        for user in self.results:
            for read in user.inputs:
                done = read.result
                if done is None or read.place != place:
                    continue
                if (done.output, done.universe) == (result.output, result.universe):
                    uses.extend(self._uses(user, read.entry, result, place))
        return tuple(uses)

    def _uses(self, user: Result, entry: str, result: Result, place: Place) -> list[Use]:
        """Each place of `user` whose record at HEAD lists `entry`, which reads `result` at
        `place`."""
        uses = []
        for at in user.places:
            versions = self._versions(user, at)
            record = versions[0].record if versions else None
            for item in record.inputs if isinstance(record, Record) else ():
                if item.entry == entry:
                    made = self._made(result, place, item.digest, user, versions[0])
                    uses.append(Use(versions[0], item.entry, item.digest, made))
        return uses

    def _made(
        self, result: Result, place: Place, digest: Digest, by: Result, listed: Version
    ) -> Version | None:
        """The newest version of `result`'s record at `place` that gives `digest`, which
        `listed`, a version of `by`'s record, lists: where the two records are in one
        repository, one committed with `listed` or before it, since a recipe can't have read a
        later run."""
        # No later than the record that lists it, where one repository holds both.
        repo, _ = self._held(result, place.record)
        lister, _ = self._held(by, listed.place.record)
        bounded = not result.read_only and repo == lister
        return next(
            (
                version
                for version in self._versions(result, place)
                if isinstance(version.record, Record)
                and version.record.digest == digest
                and (not bounded or repo.is_ancestor(version.commit, listed.commit))
            ),
            None,
        )

    def _held(self, result: Result, path: str) -> tuple[Repository, str]:
        """The repository that holds the analysis `result` belongs to, and `path`, from the top
        of the tree that analysis is read in, as a path from that repository's top."""
        member = self.stack.analyses[result.owner]
        return in_repository(member.reader, result.owner.folder, path)
