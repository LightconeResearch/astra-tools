"""The stable public functions of astra-tools (design §2): phase 0 has `validate`."""

from __future__ import annotations

import os
import posixpath
from pathlib import Path

from astra.sources.git import Repository
from astra.sources.reader import WorktreeReader
from astra.validate import ValidationReport
from astra.validate import validate as validate_reader

__all__ = ["NoAnalysisError", "ValidationReport", "validate"]


class NoAnalysisError(Exception):
    """No `astra.yaml` where an analysis is asked for: a usage error, not a broken rule."""


def validate(path: str | os.PathLike[str] | None = None) -> ValidationReport:
    """The validator's report on the analysis whose folder is `path`, the current folder by
    default. Nothing is searched for: the folder holds the analysis's `astra.yaml`.

    It is read in the working tree of the git repository that holds it. Raises NoAnalysisError
    where there is no analysis, GitError where git can't be run, and OSError where the file
    can't be read.
    """
    folder = Path.cwd() if path is None else Path(path)
    if not folder.is_dir():
        raise NoAnalysisError(f"{folder} isn't a folder: give the folder of an analysis")
    repo = Repository.discover(folder)
    if repo is None:
        # OPEN(O9): outside a repository, a file's path is from the analysis's folder.
        reader, root = WorktreeReader(folder, None), ""
    else:
        reader = WorktreeReader(repo.top, repo)
        root = "/".join(folder.resolve().relative_to(repo.top).parts)
    entry = reader.stat(posixpath.join(root, "astra.yaml"))
    if entry is None or entry.kind != "file":  # OPEN(O11): a symlink isn't one
        raise NoAnalysisError(f"{folder} has no astra.yaml file: give the folder of an analysis")
    return validate_reader(reader, root)
