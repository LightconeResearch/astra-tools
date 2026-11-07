"""Readers: where an analysis's bytes come from (design §4.3).

A path is relative to the reader's top, with `/` between folders. A symlink is an entry, never
followed (Annex B).
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from astra.sources.git import Repository


@dataclass(frozen=True)
class Entry:
    """What is at a path."""

    kind: Literal["file", "folder", "symlink", "gitlink"]


class Reader(Protocol):
    """Where an analysis is read from."""

    @property
    def repo(self) -> Repository | None:
        """The repository read, if any."""
        ...

    def read(self, path: str) -> bytes:
        """The bytes of the file at `path`; raises OSError where there is none."""
        ...

    def stat(self, path: str) -> Entry | None:
        """What is at `path`, a symlink not followed; None if nothing is."""
        ...


@dataclass(frozen=True)
class WorktreeReader:
    """The working tree, on disk: the root, and analyses reached by `path` alone."""

    top: Path  # the top of the repository's working tree, or the analysis's folder without one
    repo: Repository | None

    def read(self, path: str) -> bytes:
        return (self.top / path).read_bytes()

    def stat(self, path: str) -> Entry | None:
        try:
            mode = os.lstat(self.top / path).st_mode
        except (FileNotFoundError, NotADirectoryError):
            return None
        if stat.S_ISLNK(mode):
            return Entry("symlink")
        if stat.S_ISDIR(mode):
            return Entry("folder")
        return Entry("file") if stat.S_ISREG(mode) else None
