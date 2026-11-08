"""Records (§19): reading the record at a result's place, writing one; and a runner's building
blocks (§21, design §4.7, §4.8): making a result's records from its run, what stops a run in a
checkout, and landing what a run in a checkout of its own made in the main one.

A record is read as Annex A says (`load.load_json`) and checked by the record schema its minor
version picks (`contract.Contract.check_record`): 0.1's, the open one for a greater minor
version, which ignores the fields it doesn't know, and none below 0.1 (§19, Annex D). One is
written atomically, with sorted keys, two-space indentation and a final line break.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os
import posixpath
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astra.contract import Contract
from astra.diagnostics import Catalogue, Diagnostic, Location
from astra.hashing import Digest, digest, digest_file
from astra.load import ParseError, load_json
from astra.sources.git import Repository
from astra.sources.reader import CommitReader, Reader, WorktreeReader
from astra.universes import Place

if TYPE_CHECKING:
    from astra.plan import Result

SPEC_VERSION = "0.1.0"
"""The version of the records this astra-tools writes (§5 *Versions*)."""


@dataclass(frozen=True)
class RecordedInput:
    """What a recipe read through one entry of its output's `inputs` (§19)."""

    entry: str  # the entry, exactly as written
    content_hash: str
    size: int

    @property
    def digest(self) -> Digest:
        """The hash and size of what it read."""
        return Digest(self.content_hash, self.size)


@dataclass(frozen=True)
class Runner:
    """The runner that ran a recipe, and its version (§19)."""

    id: str
    version: str


@dataclass(frozen=True)
class Record:
    """A record (§19): a result's address, the hash and size of its bytes, and the run that made
    it: the commit the recipe ran from, what it read, the environment it ran in, the runner, and
    when it started and finished."""

    address: str
    content_hash: str
    size: int
    commit: str
    environment: str  # the environment's IRI
    runner: Runner
    inputs: tuple[RecordedInput, ...] = ()
    started: str | None = None  # a timestamp (Annex C)
    finished: str | None = None
    spec_version: str = SPEC_VERSION

    @property
    def digest(self) -> Digest:
        """The hash and size of the result's bytes."""
        return Digest(self.content_hash, self.size)

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> Record:
        """The record whose JSON value the contract accepted; a field of a greater minor version
        than 0.1 is left out (§19)."""
        run = value["generated_by"]
        return cls(
            value["address"],
            value["content_hash"],
            value["size"],
            run["commit"],
            run["environment"]["iri"],
            Runner(run["runner"]["id"], run["runner"]["version"]),
            tuple(
                RecordedInput(item["entry"], item["content_hash"], item["size"])
                for item in run.get("inputs", ())
            ),
            run.get("started"),
            run.get("finished"),
            value["spec_version"],
        )

    def to_json(self) -> dict[str, Any]:
        """The record's JSON value (§19): `inputs`, `started` and `finished` left out where it
        has none."""
        run: dict[str, Any] = {
            "commit": self.commit,
            "environment": {"iri": self.environment},
            "runner": asdict(self.runner),
        }
        if self.inputs:
            run["inputs"] = [asdict(item) for item in self.inputs]
        for name, moment in (("started", self.started), ("finished", self.finished)):
            if moment is not None:
                run[name] = moment
        return {
            "spec_version": self.spec_version,
            "address": self.address,
            "content_hash": self.content_hash,
            "size": self.size,
            "generated_by": run,
        }


def read_record(
    reader: Reader, path: str, contract: Contract
) -> Record | tuple[Diagnostic, ...] | None:
    """The record at `path` in `reader`; or, for one that breaks a parse or schema rule, the
    diagnostic of each, which leave its result `missing` (`INVALID_RECORD`, §20); None where no
    file is there, a symlink being none (Annex B). Raises OSError where it can't be read."""
    entry = reader.stat(path)
    if entry is None or entry.kind != "file":
        return None
    commit, url = (reader.commit, reader.url) if isinstance(reader, CommitReader) else (None, None)
    try:
        document = load_json(reader.read(path))
    except ParseError as error:
        location = Location(path, "", error.line, error.column, None, commit, url)
        return (contract.catalogue.diagnostic(error.code, error.message, location),)
    found = contract.check_record(document, path)
    if found:
        return tuple(
            replace(d, location=replace(d.location, commit=commit, url=url)) for d in found
        )
    return Record.from_json(document.value)


def write_record(path: Path, record: Record) -> None:
    """Write `record` at `path`, its folders made if need be: JSON with sorted keys, two-space
    indentation and a final line break, written to a temporary file in the same folder, then
    moved into place by `os.replace`. Raises OSError where it can't be written."""
    text = json.dumps(record.to_json(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def new_record(
    result: Result,
    *,
    checkout: Path,
    commit: str,
    environment: str,
    runner: Runner,
    started: datetime | None = None,
    finished: datetime | None = None,
    got: Mapping[str, str] | None = None,
) -> tuple[Record, ...]:
    """The records of `result`'s run (§19, design §4.8), one for each of its places, in their
    order, each with the result's address at that place's name. `checkout` is the top of the
    checkout the recipe ran in, which every path of the plan is measured from: the bytes it made
    are hashed at the first name's default place, where `{output}` put them, and what it read
    through each entry of its output's `inputs` at that entry's path or, for an entry that reads
    at a commit (`Read.commit`), where `got` says the runner put the bytes it got, as for
    `plan.render_command`. Raises ValueError where `got` doesn't give one. `commit` is the commit it
    ran from, as §19 defines it: a commit of the repository the record is committed in, the one
    that holds the analysis the result belongs to (`result.owner`), so a submodule's own commit
    for an analysis in a submodule, and the driver's for what a driver's universes build, never
    `result.run_at` (§21 `FALSE_RECORD`). `environment` is the IRI of the environment it ran in,
    and `started` and `finished` when it did. Raises OSError where a file to hash can't be
    read."""
    made = digest_file(checkout / result.places[0].bytes)  # `{output}`, the first name's
    inputs, got = [], got or {}
    for read in result.inputs:
        if read.commit is not None and read.entry not in got:
            message = f"`{read.entry}` reads at {read.commit}: `got` gives no place for its bytes"
            raise ValueError(message)
        found = digest_file(checkout / (read.path if read.commit is None else got[read.entry]))
        inputs.append(RecordedInput(read.entry, found.content_hash, found.size))
    return tuple(
        Record(
            place.address,
            made.content_hash,
            made.size,
            commit,
            environment,
            runner,
            tuple(inputs),
            None if started is None else timestamp(started),
            None if finished is None else timestamp(finished),
        )
        for place in result.places
    )


def uncommitted_changes(checkout: Path) -> tuple[str, ...]:
    """What stops a runner running a recipe in `checkout`, the top of a checkout of a commit
    (`UNCOMMITTED_CHANGES`, §21): each path, from its top, that `git status` reports changed in
    it or in its submodules (`Repository.changes`), but the records and results of any run,
    each result's bytes the recorded ones. Those are at the places §18 gives in the folder of an
    analysis, one holding an `astra.yaml` file: every change at a record's place,
    `.astra/records/{universe}/{name}.json` or `.astra/records/{name}.json`, and one at a
    default place, `results/{universe}/{name}.{format}` or `results/{name}.{format}`, where the
    bytes there are the ones the valid record at that name's place gives (`_run`). A change
    outside `checkout` doesn't stop a run. Raises GitError where git can't read `checkout`, and
    OSError where a file can't be read."""
    reader, contract = WorktreeReader(checkout, None), Contract.load(Catalogue.load())
    changes = Repository(checkout).changes()
    return tuple(path for path in changes if not _run(reader, path, contract))


def _run(reader: Reader, path: str, contract: Contract) -> bool:
    """Whether `path` is a record's place or, holding the recorded bytes, a result's default
    place, in an analysis's folder (§18 *Where records and bytes go*). A name is ids joined by
    `.`, which a format can hold too, so each split of a file name is tried."""
    parts = path.split("/")
    for size in (1, 2):  # {name}, or {universe}/{name}
        folder, universe, file = parts[:-size], parts[-size:-1], parts[-1]
        if folder[-2:] == [".astra", "records"] and file.endswith(".json"):
            if _analysis(reader, folder[:-2]):
                return True
        if folder[-1:] == ["results"] and _analysis(reader, folder[:-1]):
            for end in (index for index, char in enumerate(file) if char == "."):
                name, top = file[:end], folder[:-1]
                record = posixpath.join(*top, ".astra", "records", *universe, f"{name}.json")
                place = Place(name, "#".join((name, *universe)), record, path)
                if _recorded(reader, place, contract) is not None:
                    return True
    return False


def _analysis(reader: Reader, folder: list[str]) -> bool:
    """Whether `folder`, as path segments from the top, holds an `astra.yaml` file."""
    entry = reader.stat(posixpath.join(*folder, "astra.yaml"))
    return entry is not None and entry.kind == "file"


def land(run: Path, main: Path, results: Iterable[Result]) -> tuple[Place, ...]:
    """Move what a run in a checkout of its own made into the main checkout (design §4.8), and
    give the places moved: `run` is the top of the run's checkout (`Repository.worktree`), and
    `main` the top of the main one. Each place of `results`, the planned results (`plan.plan`)
    other than those read through a record (§17), is moved where its result is finished in
    `run`: its record there is valid and the result's, and the bytes at its default place are
    the recorded ones. The bytes, then the record, are moved by atomic rename, at the same paths
    in `main`, their folders made if need be, and no git command is run in `main`; where `run`
    is on another file system, each is copied beside its place and renamed into it (`_move`). A
    place whose record in `main` names a later commit than the run's record is left as it is.
    Raises GitError where git can't read `run`, and OSError where a file can't be read or
    moved."""
    # The places are the plan's: finished, and a later commit.
    made = WorktreeReader(run, Repository(run))
    there, contract = WorktreeReader(main, None), Contract.load(Catalogue.load())
    landed = []
    for result in results:
        for place in () if result.read_only else result.places:
            record = _recorded(made, place, contract)
            if record is None:
                continue
            kept = read_record(there, place.record, contract)
            if isinstance(kept, Record) and kept.commit != record.commit:
                repo, _ = made.holding(result.owner.folder)
                if repo.is_ancestor(record.commit, kept.commit):
                    continue
            for path in (place.bytes, place.record):
                _move(run / path, main / path)
            landed.append(place)
    return tuple(landed)


def _move(source: Path, target: Path) -> None:
    """Move the file `source` to `target`, its folders made if need be, by atomic rename; where
    the two are on different file systems, which a rename can't cross, by a copy into a
    temporary file in `target`'s folder, renamed into place, then `source` removed."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(source, target)
        return
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
    # Across file systems, a copy renamed into place
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(descriptor)
    try:
        shutil.copy(source, temporary)
        os.replace(temporary, target)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
    os.unlink(source)


def _recorded(reader: Reader, place: Place, contract: Contract) -> Record | None:
    """The record at `place` in `reader`, where it is valid and the result's, and the bytes at
    the place's default place are the ones it gives; otherwise None."""
    record = read_record(reader, place.record, contract)
    if not isinstance(record, Record) or record.address != place.address:
        return None
    if digest(reader, place.bytes) != record.digest:
        return None
    return record


def timestamp(moment: datetime) -> str:
    """`moment` as a record gives a time (Annex C): in UTC, to the millisecond, as
    `2026-10-26T14:00:00.000Z`. A naive `moment` is local time."""
    utc = moment.astimezone(UTC)
    return f"{utc:%Y-%m-%dT%H:%M:%S}.{utc.microsecond // 1000:03d}Z"
