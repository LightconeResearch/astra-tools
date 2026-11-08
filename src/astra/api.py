"""The stable public functions of astra-tools (design §2): `validate`, `bind`, `init`, `plan`,
`view`, `check` and `history`; and, with the extra `[evidence]`, `papers` and `quotes`."""

from __future__ import annotations

import contextlib
import os
import posixpath
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from astra.check import CheckReport
from astra.check import check as check_stack
from astra.history import History, NotInHistoryError
from astra.plan import Plan, RequestError
from astra.plan import plan as plan_stack
from astra.sources.git import Repository
from astra.sources.reader import CommitReader, Reader, WorktreeReader
from astra.sources.remote import Remotes
from astra.stack import Bound, Stack
from astra.stack import bind as bind_reader
from astra.validate import ValidationReport, validated
from astra.validate import validate as validate_reader
from astra.view import UniverseView
from astra.view import view as view_stack

if TYPE_CHECKING:
    from astra.diagnostics import Diagnostic
    from astra.evidence.papers import Cited

__all__ = [
    "Bound",
    "CheckReport",
    "History",
    "InvalidAnalysisError",
    "NoAnalysisError",
    "NotInHistoryError",
    "Plan",
    "RequestError",
    "UniverseView",
    "ValidationReport",
    "bind",
    "check",
    "history",
    "init",
    "papers",
    "plan",
    "quotes",
    "validate",
    "view",
]


class NoAnalysisError(Exception):
    """No `astra.yaml` where an analysis is asked for: a usage error, not a broken rule."""


class InvalidAnalysisError(Exception):
    """The analysis breaks a `MUST`, so it has no plan, no view, no history and no papers:
    `report` says where. `check` gives what statuses it can instead (design §4.7)."""

    def __init__(self, report: ValidationReport) -> None:
        super().__init__(f"{report.root} breaks a MUST: `astra validate` says where")
        self.report = report


def validate(
    path: str | os.PathLike[str] | None = None, *, offline: bool = False
) -> ValidationReport:
    """The validator's report on the analysis whose folder is `path`, the current folder by
    default. Nothing is searched for: the folder holds the analysis's `astra.yaml`.

    It is read in the working tree of the git repository that holds it. A commit is got from a
    remote into the cache, once (§17); `offline`, nothing is fetched, and only the commits kept
    from earlier fetches can be got. Raises NoAnalysisError where there is no analysis,
    GitError where git can't be run, CacheError where the cache can't be used, and OSError
    where a file can't be read.
    """
    reader, root = _root(path)
    return validate_reader(reader, root, Remotes(offline=offline))


def bind(path: str | os.PathLike[str] | None = None) -> Bound:
    """The stack whose root is the analysis whose folder is `path`, read as `validate` reads it,
    with the parse and schema diagnostics of its files (design §4.4). Its `stack` is None where
    the root's file isn't a valid document, or the root is in no repository. Raises as
    `validate` does."""
    reader, root = _root(path)
    return bind_reader(reader, root, remotes=Remotes())


def plan(
    path: str | os.PathLike[str] | None = None,
    *,
    universes: Iterable[str] | None = None,
    outputs: Iterable[str] | None = None,
) -> Plan:
    """The planned results of the analysis whose folder is `path`, read as `validate` reads
    it, in an order a runner can build them in (§18, design §4.6): all of them, or those
    `universes` and `outputs` ask for (`plan.plan`). Raises InvalidAnalysisError where the
    analysis breaks a `MUST`, RequestError where a universe or an output asked for isn't there,
    and otherwise as `validate` does."""
    return plan_stack(_valid(path), universes, outputs)


def view(universe: str, path: str | os.PathLike[str] | None = None) -> UniverseView:
    """The analysis whose folder is `path`, read as `validate` reads it, as it is in its
    universe `universe` (design §4.6). Raises InvalidAnalysisError where the analysis breaks a
    `MUST`, RequestError where it has no such universe, and otherwise as `validate` does."""
    return view_stack(_valid(path), universe)


def check(
    path: str | os.PathLike[str] | None = None,
    *,
    at: str | None = None,
    universes: Iterable[str] | None = None,
    outputs: Iterable[str] | None = None,
) -> CheckReport:
    """The checker's report on the analysis whose folder is `path`, read as `validate` reads it
    (§20, design §4.7): each planned result's record and bytes statuses at each of its places,
    and its evidence's, all of them or those `universes` and `outputs` narrow it to
    (`check.check`). With `at`, a revision of the repository that holds the analysis (a commit,
    a branch, a tag), the analysis is checked as it is at that commit, with its records and
    bytes read there. Where the analysis breaks a `MUST`, the report holds the errors, and only
    the results whose planning is determined (design §4.13 case 12) get statuses: none where the
    root's file isn't a valid document or it is in no repository. Raises RequestError where `at`
    names no commit or a universe or an output asked for isn't there, and otherwise as
    `validate` does."""
    remotes = Remotes()
    reader, report, stack = _read(path, at, remotes)
    errors = tuple(diagnostic for diagnostic in report.diagnostics if diagnostic.level == "error")
    if stack is None:  # no result's planning is determined (design §4.13 case 12)
        commit = reader.commit if isinstance(reader, CommitReader) else "worktree"
        return CheckReport(report.root, commit, (), (), errors)
    return check_stack(stack, universes, outputs, remotes, errors)


def history(path: str | os.PathLike[str] | None = None) -> History:
    """The history of the records of the planned results of the analysis whose folder is
    `path`, read as `validate` reads it, and read from git on demand (design §6 *Phase 4*):
    each query is one call of what this gives, `timeline`, `lineage`, `find` or `get`
    (`history.History`). Raises InvalidAnalysisError where the analysis breaks a `MUST`, and
    otherwise as `validate` does."""
    # The form of the public API.
    remotes = Remotes()
    return History(_valid(path, None, remotes), remotes)


def papers(path: str | os.PathLike[str] | None = None) -> tuple[Cited, ...]:
    """Each work the evidence of the analysis whose folder is `path` cites by DOI, read as
    `validate` reads it, at each version it cites, once, and whether the cache holds its paper
    (design §6 *Phase 5*). Raises ImportError where the extra `[evidence]` isn't installed,
    InvalidAnalysisError where the analysis breaks a `MUST`, and otherwise as `validate` does."""
    from astra.evidence.papers import cited  # the extra's API

    return cited(_valid(path))


def quotes(path: str | os.PathLike[str] | None = None) -> tuple[Diagnostic, ...]:
    """The `EVIDENCE_` warnings on the quotes that the evidence of the analysis whose folder is
    `path` takes from works it cites by DOI, read as `validate` reads it (`evidence.quotes`): a
    paper not in the cache, or a quote not found in it. Raises `evidence.papers.PaperError`
    where a paper the cache holds can't be read, and otherwise as `papers` does."""
    from astra.evidence.quotes import verify

    return verify(_valid(path))


def _valid(
    path: str | os.PathLike[str] | None, at: str | None = None, remotes: Remotes | None = None
) -> Stack:
    """The stack whose root is the analysis in `path`, read in the working tree or at the
    revision `at`, where it is valid (§3). Raises InvalidAnalysisError where it isn't, and
    RequestError where `at` names no commit."""
    _, report, stack = _read(path, at, remotes or Remotes())
    if not report.valid:  # no plan and no view of an invalid analysis
        raise InvalidAnalysisError(report)
    assert stack is not None  # a valid analysis has a stack
    return stack


def _read(
    path: str | os.PathLike[str] | None, at: str | None, remotes: Remotes
) -> tuple[Reader, ValidationReport, Stack | None]:
    """The reader of the analysis in `path`, in the working tree or at the revision `at`, its
    validation report, and the stack it judged (`validate.validated`). Raises RequestError
    where `at` names no commit."""
    reader, root = _root(path)
    if at is not None and reader.repo is not None:
        commit = reader.repo.commit(at)
        if commit is None:
            raise RequestError(f"`{at}` names no commit of {reader.repo.top}")
        reader = CommitReader(reader.repo, commit, None, remotes)
        entry = reader.stat(posixpath.join(root, "astra.yaml"))
        if entry is None or entry.kind != "file":
            raise NoAnalysisError(f"{root or '.'} has no astra.yaml file at {commit}")
    report, stack = validated(reader, root, remotes)
    return reader, report, stack


MINIMAL = """\
spec_version: "0.1.0"
outputs:
  result:
    type: metric
    format: json
    recipe:
      command: python src/result.py '{output}'
"""
"""What `init` writes: a `spec_version` and one output, all an analysis needs (§5)."""


def init(path: str | os.PathLike[str] | None = None) -> tuple[Path, bool]:
    """Make a minimal analysis in the folder `path`, the current folder by default, made if need
    be: its `astra.yaml` holds `MINIMAL`. Where no git repository holds the folder, it becomes a
    new one. Gives the file written, and whether a repository was made. Raises FileExistsError
    where the folder has an `astra.yaml` or is a file, GitError where git can't be run, and
    OSError where the folder can't be written."""
    folder = Path.cwd() if path is None else Path(path)
    file = folder / "astra.yaml"
    if os.path.lexists(folder) and not folder.is_dir():
        raise FileExistsError(f"{folder} isn't a folder: give a folder for the analysis")
    if os.path.lexists(file):
        raise FileExistsError(f"{folder} has an astra.yaml already: give a folder without one")
    folder.mkdir(parents=True, exist_ok=True)
    made = Repository.discover(folder) is None  # none inside a working tree
    if made:
        Repository.init(folder)
    descriptor, temporary = tempfile.mkstemp(prefix=".astra.yaml.", dir=folder)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(MINIMAL)
        os.chmod(temporary, 0o644)
        os.replace(temporary, file)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
    return file, made


def _root(path: str | os.PathLike[str] | None) -> tuple[Reader, str]:
    """The reader of the working tree that holds the folder `path`, and the folder's path in
    it. Raises NoAnalysisError where the folder holds no `astra.yaml` file."""
    folder = Path.cwd() if path is None else Path(path)
    if not folder.is_dir():
        raise NoAnalysisError(f"{folder} isn't a folder: give the folder of an analysis")
    repo = Repository.discover(folder)
    reader: Reader
    if repo is None:
        # Outside a repository, a file's path is from the analysis's folder.
        reader, root = WorktreeReader(folder, None), ""
    else:
        reader = WorktreeReader(repo.top, repo)
        root = "/".join(folder.resolve().relative_to(repo.top).parts)
    entry = reader.stat(posixpath.join(root, "astra.yaml"))
    if entry is None or entry.kind != "file":  # a symlink isn't one
        raise NoAnalysisError(f"{folder} has no astra.yaml file: give the folder of an analysis")
    return reader, root
