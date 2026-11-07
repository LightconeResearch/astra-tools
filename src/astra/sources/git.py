"""Git, through its own commands (design §4.3): which repository holds a folder, what its
index tracks (§7), its commits and their objects (§17), the remote stores' fetches, and, for a
runner, what a checkout has changed and checkouts of its own (§21, design §4.8)."""

from __future__ import annotations

import os
import subprocess
import tempfile
import weakref
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

from astra import cache


class GitError(Exception):
    """git can't be run: a broken environment, not a broken analysis."""


_NOT_FOUND = "astra needs git, and found no `git` on PATH: install git"


def _environment(*, lazy: bool = False) -> dict[str, str]:
    """git's environment: it never waits for a password (`GIT_TERMINAL_PROMPT=0`) and, unless
    `lazy`, never fetches an object a partial clone lacks (`GIT_NO_LAZY_FETCH=1`)."""
    return {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        **({} if lazy else {"GIT_NO_LAZY_FETCH": "1"}),
    }


def _git(*args: str, input: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    """Run git in `_environment()`."""
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, env=_environment(), input=input, check=False
        )
    except FileNotFoundError:
        raise GitError(_NOT_FOUND) from None


@dataclass(frozen=True)
class Repository:
    """A git repository: one with a working tree, or a bare one (a remote store)."""

    top: Path  # the top of its working tree, or a bare repository's folder

    @classmethod
    def init(cls, folder: Path) -> Repository:
        """A new repository whose working tree is the folder `folder` (`astra init`)."""
        result = _git("init", "--quiet", str(folder))
        if result.returncode != 0:
            error = os.fsdecode(result.stderr).strip()
            raise GitError(f"git can't make a repository in {folder}: {error}")
        return cls(folder.resolve())

    @classmethod
    def init_bare(cls, folder: Path, url: str) -> Repository:
        """A new bare repository in the empty folder `folder`, whose remote `origin` is `url`."""
        commands = (
            ("init", "--quiet", "--bare", str(folder)),
            ("-C", str(folder), "config", "remote.origin.url", url),
        )
        for args in commands:
            result = _git(*args)
            if result.returncode != 0:
                error = os.fsdecode(result.stderr).strip()
                raise GitError(f"git can't make a repository in {folder}: {error}")
        return cls(folder)

    @classmethod
    def discover(cls, folder: Path) -> Repository | None:
        """The repository whose working tree holds `folder`: the innermost, so a submodule's own
        (Annex B). None if there is none."""
        result = _git("-C", str(folder), "rev-parse", "--show-toplevel")
        if result.returncode != 0:
            return None
        return cls(Path(os.fsdecode(result.stdout.rstrip(b"\n"))))

    def tracked(self, paths: Collection[str]) -> frozenset[str]:
        """Those of `paths`, each from the top of the working tree, that name a file or a
        symlink in the index (Annex B *Tracked*). A path inside a submodule names none, since
        the index holds the submodule as one gitlink, and a gitlink is no file."""
        wanted = sorted(set(paths))
        found: set[str] = set()
        for start in range(0, len(wanted), _PATHSPECS):
            pathspecs = [f":(literal){path}" for path in wanted[start : start + _PATHSPECS]]
            result = _git("-C", str(self.top), "ls-files", "--stage", "-z", "--", *pathspecs)
            if result.returncode != 0:
                error = os.fsdecode(result.stderr).strip()
                raise GitError(f"git can't read the index of {self.top}: {error}")
            for record in result.stdout.split(b"\0"):  # "<mode> <object> <stage>\t<path>"
                meta, _, name = record.partition(b"\t")
                if name and not meta.startswith(b"160000 "):
                    found.add(os.fsdecode(name))
        return frozenset(found.intersection(wanted))

    def has_commit(self, commit: str) -> bool:
        """Whether the repository has the commit `commit`, a full id. Nothing is fetched."""
        result = _git("-C", str(self.top), "cat-file", "-t", commit)
        return result.returncode == 0 and result.stdout == b"commit\n"

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        """Whether the commit `ancestor` is `descendant` or one of its ancestors."""
        result = _git("-C", str(self.top), "merge-base", "--is-ancestor", ancestor, descendant)
        return result.returncode == 0

    def head(self) -> str | None:
        """HEAD's commit, or None while it has none."""
        result = _git("-C", str(self.top), "rev-parse", "--quiet", "--verify", "HEAD^{commit}")
        if result.returncode != 0:
            return None
        return os.fsdecode(result.stdout).strip() or None

    def commit(self, revision: str) -> str | None:
        """The full id of the commit `revision` names, as git reads a revision (a branch, a tag,
        a shortened id, `HEAD~1`); None where it names none."""
        result = _git(
            "-C", str(self.top), "rev-parse", "--quiet", "--verify", "--end-of-options",
            f"{revision}^{{commit}}",
        )  # fmt: skip
        if result.returncode != 0:
            return None
        return os.fsdecode(result.stdout).strip() or None

    def remote_url(self) -> str | None:
        """The URL of the default remote, as git chooses it (the current branch's, or the one
        remote, or `origin`); None where there is none."""
        result = _git("-C", str(self.top), "ls-remote", "--get-url")
        if result.returncode != 0:
            return None
        return os.fsdecode(result.stdout).strip() or None

    def fetch(self, commit: str) -> bool:
        """Fetch `commit` from `origin`, without its blobs, which are read as they are asked for
        (`git fetch --filter=blob:none`), and keep it by a ref of its own, `refs/astra/<commit>`,
        so that it is fetched once. Whether the repository has it now."""
        _git(
            "-C", str(self.top), "fetch", "--quiet", "--no-tags", "--no-write-fetch-head",
            "--filter=blob:none", "origin", f"{commit}:refs/astra/{commit}",
        )  # fmt: skip
        return self.has_commit(commit)  # also where another process kept it first

    def changes(self) -> tuple[str, ...]:
        """Each path, from the top of the working tree, that `git status --porcelain=v2
        --untracked-files=all` reports: changed in the index or the working tree since HEAD, or
        untracked, renames as two paths; and, in each checked-out submodule that has changes of
        its own, each of those, after the submodule's path. A submodule is a change itself only
        where git reports more than its content changed: its commit, say."""
        # OPEN(O4): what git reports as a change, in the checkout and its submodules.
        result = _git(
            "-C", str(self.top), "status", "--porcelain=v2", "--untracked-files=all",
            "--no-renames", "--ignore-submodules=none", "-z",
        )  # fmt: skip
        if result.returncode != 0:
            error = os.fsdecode(result.stderr).strip()
            raise GitError(f"git can't read the status of {self.top}: {error}")
        found: list[str] = []
        for record in result.stdout.split(b"\0"):
            if record.startswith(b"? "):  # "? <path>"
                found.append(os.fsdecode(record[2:]))
            elif record.startswith((b"1 ", b"u ")):  # "1 <XY> <sub> <6 fields> <path>", "u ..."
                fields = record.split(b" ", 8 if record.startswith(b"1") else 10)
                xy, sub, path = fields[1], fields[2], os.fsdecode(fields[-1])
                if not sub.startswith(b"S"):  # "N...", not a submodule
                    found.append(path)
                    continue
                if sub[2:4] != b"..":  # "S<C><M><U>": tracked or untracked changes inside
                    found.extend(
                        f"{path}/{inner}" for inner in Repository(self.top / path).changes()
                    )
                if sub[1:2] == b"C" or xy != b".M":
                    found.append(path)
        return tuple(sorted(found))

    def worktree(self, commit: str) -> Repository:
        """A checkout of `commit` of its own, for a run (§21, design §4.8): a detached `git
        worktree add` in a new folder of the cache's `worktrees`, its submodules updated (`git
        submodule update --init --recursive`). Raises GitError where git can't make it, and
        CacheError where the cache can't be used."""
        folder = cache.root() / "worktrees"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = Path(tempfile.mkdtemp(prefix=f"{commit[:12]}-", dir=folder))
        except OSError as cant:
            raise cache.CacheError(
                f"can't make a folder in {folder}: {cant.strerror}; set ASTRA_CACHE_DIR to a "
                "folder astra can write"
            ) from cant
        commands = (
            ("-C", str(self.top), "worktree", "add", "--quiet", "--detach", str(path), commit),
            ("-C", str(path), "submodule", "update", "--quiet", "--init", "--recursive"),
        )
        for args in commands:
            result = _git(*args)
            if result.returncode != 0:
                error = os.fsdecode(result.stderr).strip()
                raise GitError(f"git can't make a checkout of {commit} in {path}: {error}")
        return Repository(path)


class Objects:
    """A repository's objects, as git stores them, through one long-lived `git cat-file
    --batch` (design §4.3). With `lazy`, an object a partial clone lacks is fetched from its
    remote when it is asked for; without, it reads as missing."""

    def __init__(self, repo: Repository, *, lazy: bool) -> None:
        try:
            self._process = subprocess.Popen(
                ["git", "-C", str(repo.top), "cat-file", "--batch"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=_environment(lazy=lazy),
            )
        except FileNotFoundError:
            raise GitError(_NOT_FOUND) from None
        weakref.finalize(self, _end, self._process)

    def read(self, oid: str) -> tuple[str, bytes] | None:
        """The type and content of the object `oid`, a full id; None where it is missing."""
        stdin, stdout = self._process.stdin, self._process.stdout
        assert stdin is not None and stdout is not None
        stdin.write(oid.encode("ascii") + b"\n")
        stdin.flush()
        header = stdout.readline().split()  # "<oid> <type> <size>", or "<oid> missing"
        if not header:
            raise GitError(f"git cat-file stopped reading {oid}")
        if len(header) != 3:
            return None
        content = stdout.read(int(header[2]))
        stdout.read(1)
        return header[1].decode("ascii"), content

    def tree(self, oid: str) -> Mapping[str, tuple[str, str]]:
        """The entries of the tree `oid` by name, each with its mode as git writes it
        (`100644`, `100755`, `120000`, `40000` or `160000`) and its object's id."""
        found = self.read(oid)
        if found is None or found[0] != "tree":
            raise GitError(f"git has no tree {oid}")
        data, size, entries, start = found[1], len(oid) // 2, {}, 0
        while start < len(data):  # "<mode> <name>\0<id, raw>", one after another
            space = data.index(b" ", start)
            nul = data.index(b"\0", space)
            name = os.fsdecode(data[space + 1 : nul])
            entries[name] = (
                data[start:space].decode("ascii"),
                data[nul + 1 : nul + 1 + size].hex(),
            )
            start = nul + 1 + size
        return entries


def _end(process: subprocess.Popen[bytes]) -> None:
    """End a batch process: closing its input ends it."""
    for stream in (process.stdin, process.stdout):
        if stream is not None:
            stream.close()
    process.wait()


def read_gitmodules(data: bytes) -> dict[str, str]:
    """Each submodule's URL, by its `path` as written, from the bytes of a `.gitmodules`, read
    by git's own reader of its config files."""
    result = _git("config", "--file", "-", "--null", "--list", input=data)
    if result.returncode != 0:
        return {}
    found: dict[str, dict[str, str]] = {}
    for record in result.stdout.split(b"\0"):  # "submodule.<name>.<key>\n<value>"
        key, _, value = os.fsdecode(record).partition("\n")
        section, _, rest = key.partition(".")
        name, _, variable = rest.rpartition(".")
        if section == "submodule" and variable in ("path", "url"):
            found.setdefault(name, {})[variable] = value
    return {
        entry["path"]: entry["url"] for entry in found.values() if entry.keys() == {"path", "url"}
    }


_PATHSPECS = 200
"""How many paths one `git ls-files` is given, so its command line stays short."""
