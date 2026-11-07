"""The stable public functions of astra-tools (design §2): phase 1 has `validate`, `bind` and
`init`."""

from __future__ import annotations

import contextlib
import os
import posixpath
import tempfile
from pathlib import Path

from astra.sources.git import Repository
from astra.sources.reader import Reader, WorktreeReader
from astra.sources.remote import Remotes
from astra.stack import Bound
from astra.stack import bind as bind_reader
from astra.validate import ValidationReport
from astra.validate import validate as validate_reader

__all__ = ["Bound", "NoAnalysisError", "ValidationReport", "bind", "init", "validate"]


class NoAnalysisError(Exception):
    """No `astra.yaml` where an analysis is asked for: a usage error, not a broken rule."""


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
    made = Repository.discover(folder) is None  # OPEN(O24): none inside a working tree
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
        # OPEN(O9): outside a repository, a file's path is from the analysis's folder.
        reader, root = WorktreeReader(folder, None), ""
    else:
        reader = WorktreeReader(repo.top, repo)
        root = "/".join(folder.resolve().relative_to(repo.top).parts)
    entry = reader.stat(posixpath.join(root, "astra.yaml"))
    if entry is None or entry.kind != "file":  # OPEN(O11): a symlink isn't one
        raise NoAnalysisError(f"{folder} has no astra.yaml file: give the folder of an analysis")
    return reader, root
