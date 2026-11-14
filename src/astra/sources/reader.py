"""Readers: where an analysis's bytes come from.

A path is tidied (`sources.paths`) and relative to the reader's top, with `/` between folders,
and "" for the top. It names the entry at exactly that path: each of its names is
found in its folder's listing, so `data/A.csv` never names `data/a.csv`, even where the file
system ignores case. A symlink is an entry, and is never followed: at a path it is neither a
file nor a folder, and a path through a symlinked folder names nothing.

In the working tree, a folder that holds a `.git` of its own, a checked-out submodule, is a
gitlink, whose entries are read on disk. At a commit, a path that crosses a gitlink goes on
into the submodule, at the commit the gitlink pins.
"""

from __future__ import annotations

import errno
import os
import posixpath
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Protocol

from astra.sources.git import Objects, Repository, read_gitmodules
from astra.sources.paths import join, lies_inside
from astra.sources.remote import Remotes, resolve

Kind = Literal["file", "folder", "symlink", "gitlink"]


@dataclass(frozen=True)
class Entry:
    """What is at a path."""

    kind: Kind
    target: str | None = None  # a symlink's target, as it is written; never followed


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
        """What is at `path`; None if nothing is."""
        ...

    def tracked(self, folder: str, paths: Collection[str]) -> frozenset[str]:
        """Those of `paths` that are tracked in the repository that holds the analysis in
        `folder`: read in the working tree, in its index; read at a commit, in that commit's
        tree; either way reached through no gitlink."""
        ...

    def holding(self, folder: str) -> tuple[Repository, str]:
        """The repository that holds the analysis in `folder`, the innermost, and the folder as
        a path from its top."""
        ...


def in_repository(reader: Reader, folder: str, path: str) -> tuple[Repository, str]:
    """The repository that holds the analysis in `folder` (`Reader.holding`), and `path`, a
    file of that analysis from the top of the tree `reader` reads, as a path from that
    repository's top."""
    repo, inner = reader.holding(folder)
    return repo, posixpath.join(inner, posixpath.relpath(path, folder or "."))


@dataclass(frozen=True)
class WorktreeReader:
    """The working tree, on disk: the root, and analyses reached by `path` alone."""

    top: Path  # the top of the repository's working tree, or the analysis's folder without one
    repo: Repository | None

    def read(self, path: str) -> bytes:
        return (self.top / path).read_bytes()

    def stat(self, path: str) -> Entry | None:
        if path == "":
            return Entry("folder")
        folder, _, name = path.rpartition("/")
        entries = self._entries(folder)
        kind = None if entries is None else entries.get(name)
        if kind == "symlink":
            return Entry(kind, os.readlink(self.top / path))
        return None if kind is None else Entry(kind)

    def tracked(self, folder: str, paths: Collection[str]) -> frozenset[str]:
        if self.repo is None:
            return frozenset()
        top = self._holding(folder)
        if top == "":
            return self.repo.tracked(paths)
        own = {path[len(top) + 1 :]: path for path in paths if lies_inside(path, top)}
        return frozenset(own[path] for path in Repository(self.top / top).tracked(own))

    def holding(self, folder: str) -> tuple[Repository, str]:
        if self.repo is None:
            raise ValueError(f"{self.top} is in no repository")
        top = self._holding(folder)
        if top == "":
            return self.repo, folder
        return Repository(self.top / top), folder[len(top) + 1 :]

    def _holding(self, folder: str) -> str:
        """The top of the repository that holds the analysis in `folder`, the innermost: the
        deepest checked-out submodule on the way to it, or "" for the root's."""
        segments = folder.split("/") if folder else []
        for count in range(len(segments), 0, -1):
            prefix = "/".join(segments[:count])
            entry = self.stat(prefix)
            if entry is not None and entry.kind == "gitlink":
                return prefix
        return ""

    def _entries(self, folder: str) -> dict[str, Kind] | None:
        """The kind of each entry of `folder`, by name; None where `folder` names no folder or
        gitlink, or goes through a symlink."""
        found = self.stat(folder) if folder else Entry("folder")
        if found is None or found.kind not in ("folder", "gitlink"):
            return None
        entries: dict[str, Kind] = {}
        with os.scandir(self.top / folder) as scan:
            for entry in scan:
                if entry.is_symlink():
                    entries[entry.name] = "symlink"
                elif entry.is_dir(follow_symlinks=False):
                    gitlink = os.path.lexists(os.path.join(entry.path, ".git"))
                    entries[entry.name] = "gitlink" if gitlink else "folder"
                elif entry.is_file(follow_symlinks=False):
                    entries[entry.name] = "file"
        return entries


_TREE, _GITLINK, _SYMLINK = "40000", "160000", "120000"
"""The modes of a tree's entries that aren't files (`100644` and `100755` are)."""

_KINDS: Mapping[str, Kind] = MappingProxyType(
    {_TREE: "folder", _GITLINK: "gitlink", _SYMLINK: "symlink"}
)


class UnreachableError(Exception):
    """A commit that can't be got from its remote."""

    def __init__(self, url: str | None, commit: str) -> None:
        super().__init__(f"{commit} can't be got from {url or 'a submodule with no URL'}")
        self.url = url  # None where the `.gitmodules` gives a gitlink none
        self.commit = commit


@dataclass(frozen=True)
class _Found:
    """An entry, and the reader of the commit whose tree holds it."""

    reader: CommitReader
    path: str  # from the top of that commit's tree
    mode: str
    oid: str


class CommitReader:
    """A commit, read through one long-lived `git cat-file --batch`, and never checked out:
    analyses from a commit, local or from a remote. Each file is the blob git stores.

    A path that crosses a gitlink goes on into the submodule, at the commit the gitlink pins:
    read in the submodule's own repository where it is checked out in this repository's working
    tree and holds that commit, and otherwise got from the URL that this
    commit's `.gitmodules` gives it, a relative one resolved against the remote this commit was
    got from or, for a local one, its repository's default remote, or else its folder, as git
    resolves it."""

    def __init__(self, repo: Repository, commit: str, url: str | None, remotes: Remotes) -> None:
        self.repo = repo  # the local repository, or the store of `url`
        self.commit = commit
        self.url = url  # the remote the commit was got from; None for a local one
        self.remotes = remotes
        self._objects = Objects(repo, lazy=not remotes.offline)
        self._top: _Found | None = None
        self._trees: dict[str, Mapping[str, tuple[str, str]]] = {}
        self._submodules: dict[str, CommitReader | UnreachableError] = {}
        self._gitmodules: dict[str, str] | None = None

    def read(self, path: str) -> bytes:
        found = self._found(path)
        if found is None or not found.mode.startswith("100"):
            raise FileNotFoundError(errno.ENOENT, f"no file at {path} in {self.commit}", path)
        return found.reader._blob(found.oid, path)

    def stat(self, path: str) -> Entry | None:
        found = self._found(path)
        if found is None:
            return None
        kind = _KINDS.get(found.mode, "file")
        if kind == "symlink":
            return Entry(kind, os.fsdecode(found.reader._blob(found.oid, path)))
        return Entry(kind)

    def tracked(self, folder: str, paths: Collection[str]) -> frozenset[str]:
        # The analysis's folder crosses no gitlink: binding reads it in the submodule's commit.
        def kept(path: str) -> bool:
            found = self._walk(path, cross=False)
            return found is not None and found.mode[:3] in ("100", "120")

        return frozenset(path for path in paths if kept(path))

    def holding(self, folder: str) -> tuple[Repository, str]:
        return self.repo, folder

    def locate(self, path: str) -> tuple[CommitReader, str] | None:
        """The reader of the commit whose tree holds the file at `path`, through any gitlink on
        the way, and its path there; None where no file is there. Raises UnreachableError where
        a gitlink's commit can't be got."""
        found = self._walk(path, cross=True)
        if found is None or not found.mode.startswith("100"):
            return None
        return found.reader, found.path

    def _found(self, path: str) -> _Found | None:
        """What is at `path`; None where nothing is, or a gitlink's commit on the way can't be
        got."""
        try:
            return self._walk(path, cross=True)
        except UnreachableError:  # no file is got there, so none is named
            return None

    def _walk(self, path: str, *, cross: bool) -> _Found | None:
        """The entry at `path`, going on through each gitlink on the way if `cross`; None where
        nothing is there."""
        found = self._root()
        for segment in path.split("/") if path else ():
            if found.mode == _GITLINK and cross:
                found = found.reader._inside(found)
            if found.mode != _TREE:
                return None
            entry = found.reader._tree(found.oid).get(segment)
            if entry is None:
                return None
            found = _Found(found.reader, f"{found.path}/{segment}".lstrip("/"), *entry)
        return found

    def _root(self) -> _Found:
        """The top of the commit's tree."""
        if self._top is None:
            found = self._objects.read(self.commit)
            if found is None or found[0] != "commit":
                message = f"{self.repo.top} has no commit {self.commit}"
                raise FileNotFoundError(errno.ENOENT, message)
            tree = found[1].split(b"\n", 1)[0].removeprefix(b"tree ").decode("ascii")
            self._top = _Found(self, "", _TREE, tree)
        return self._top

    def _tree(self, oid: str) -> Mapping[str, tuple[str, str]]:
        if oid not in self._trees:
            self._trees[oid] = self._objects.tree(oid)
        return self._trees[oid]

    def _blob(self, oid: str, path: str) -> bytes:
        found = self._objects.read(oid)
        if found is None:
            message = (
                f"{path} at {self.commit} isn't kept in the cache: validate without --offline "
                "to fetch it"
            )
            raise FileNotFoundError(errno.ENOENT, message, path)
        return found[1]

    def _inside(self, gitlink: _Found) -> _Found:
        """The top of the submodule whose gitlink, in this commit's tree, is `gitlink`, at the
        commit it pins. Raises UnreachableError where that commit can't be got."""
        if gitlink.path not in self._submodules:
            url = self._urls().get(gitlink.path)
            local = self._checkout(gitlink.path)
            repo = self.remotes.get(url, gitlink.oid, local)
            self._submodules[gitlink.path] = (
                UnreachableError(url, gitlink.oid)
                if repo is None
                else CommitReader(repo, gitlink.oid, None if repo is local else url, self.remotes)
            )
        found = self._submodules[gitlink.path]
        if isinstance(found, UnreachableError):
            raise UnreachableError(found.url, found.commit)
        return found._root()

    def _checkout(self, path: str) -> Repository | None:
        """The submodule's own repository, where the gitlink at `path` is checked out in the
        working tree of this commit's repository; None where it isn't, as in a remote's store,
        which has no working tree."""
        folder = self.repo.top / path
        return Repository(folder) if (folder / ".git").exists() else None

    def _urls(self) -> dict[str, str]:
        """Each submodule's URL, resolved, by its path, as this commit's `.gitmodules` gives."""
        if self._gitmodules is None:
            found = self._walk(".gitmodules", cross=False)
            data = b"" if found is None else self._blob(found.oid, ".gitmodules")
            base = self.url or self.repo.remote_url() or str(self.repo.top)
            self._gitmodules = {
                tidied: resolve(base, url)
                for path, url in read_gitmodules(data).items()
                if (tidied := join("", path)) is not None
            }
        return self._gitmodules
