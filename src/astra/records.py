"""Records: reading the record at a result's place, writing one, and making a result's
records from its run.

A record is read as UTF-8 JSON text (`load.load_json`) and checked by the record schema its
minor version picks (`contract.Contract.check_record`): 0.1's, the open one for a greater minor
version, which ignores the fields it doesn't know, and none below 0.1. One is written
atomically, with sorted keys, two-space indentation and a final line break.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astra.contract import Contract
from astra.diagnostics import Diagnostic, Location
from astra.hashing import Digest, digest_file
from astra.load import ParseError, load_json
from astra.sources.reader import CommitReader, Reader

if TYPE_CHECKING:
    from astra.plan import Result

SPEC_VERSION = "0.1.0"
"""The version of the records this astra-tools writes."""


@dataclass(frozen=True)
class RecordedInput:
    """What a recipe read through one entry of its output's `inputs`."""

    entry: str  # the entry, exactly as written
    content_hash: str
    size: int

    @property
    def digest(self) -> Digest:
        """The hash and size of what it read."""
        return Digest(self.content_hash, self.size)


@dataclass(frozen=True)
class Runner:
    """The runner that ran a recipe, and its version."""

    id: str
    version: str


@dataclass(frozen=True)
class Record:
    """A record: a result's address, the hash and size of its bytes, and the run that made
    it: the commit the recipe ran from, what it read, the environment it ran in, the runner, and
    when it started and finished."""

    address: str
    content_hash: str
    size: int
    commit: str
    environment: str  # the environment's IRI
    runner: Runner
    inputs: tuple[RecordedInput, ...] = ()
    started: str | None = None  # a timestamp
    finished: str | None = None
    spec_version: str = SPEC_VERSION

    @property
    def digest(self) -> Digest:
        """The hash and size of the result's bytes."""
        return Digest(self.content_hash, self.size)

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> Record:
        """The record whose JSON value the contract accepted; a field of a greater minor version
        than 0.1 is left out."""
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
        """The record's JSON value: `inputs`, `started` and `finished` left out where it has
        none."""
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
    diagnostic of each, which leave its result `missing` (`INVALID_RECORD`); None where no file
    is there, a symlink being none. Raises OSError where it can't be read."""
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
    """The records of `result`'s run, one for each of its places, in their order, each with the
    result's address at that place's name. `checkout` is the top of the checkout the recipe ran in,
    which every path of the plan is measured from: the bytes it made are hashed at the first name's
    default place, where `{output}` put them, and what it read through each entry of its output's
    `inputs` at that entry's path or, for an entry that reads at a commit (`Read.commit`), where
    `got` says the runner put the bytes it got, as for `plan.render_command`. Raises ValueError
    where `got` doesn't give one. `commit` is the commit it ran from: a commit of the repository the
    record is committed in, the one that holds the analysis the result belongs to (`result.owner`),
    so a submodule's own commit for an analysis in a submodule, and the driver's for what a driver's
    universes build, never `result.run_at` (`FALSE_RECORD`). `environment` is the IRI of the
    environment it ran in, and `started` and `finished` when it did. Raises OSError where a file to
    hash can't be read."""
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


def timestamp(moment: datetime) -> str:
    """`moment` as a record gives a time: in UTC, to the millisecond, as `2026-10-26T14:00:00.000Z`.
    A naive `moment` is local time."""
    utc = moment.astimezone(UTC)
    return f"{utc:%Y-%m-%dT%H:%M:%S}.{utc.microsecond // 1000:03d}Z"
