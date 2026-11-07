"""A file's SHA-256 and size, as a record gives them (§19), through the cache (design §4.7)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from astra import cache, hashing
from astra.sources.git import Repository
from astra.sources.reader import CommitReader, WorktreeReader
from astra.sources.remote import Remotes
from tests.conftest import git, repository

DATA = b"a,b\n1,2\n"
HASH = f"sha256:{hashlib.sha256(DATA).hexdigest()}"


def test_a_file_is_hashed_as_sha256_and_its_size(tmp_path: Path) -> None:
    """§19: `sha256:`, then the digest in lowercase hexadecimal, and the size in bytes."""
    (tmp_path / "data.csv").write_bytes(DATA)
    assert hashing.digest_file(tmp_path / "data.csv") == hashing.Digest(HASH, len(DATA))
    assert hashing.digest_bytes(DATA) == hashing.Digest(HASH, len(DATA))


def test_an_unchanged_file_costs_a_stat(tmp_path: Path) -> None:
    """design §4.7: kept by its device and inode with its size and modification time, so a file
    whose size and modification time are as they were isn't read again."""
    file = tmp_path / "data.csv"
    file.write_bytes(DATA)
    os.utime(file, ns=(10**18, 10**18))
    assert hashing.digest_file(file).content_hash == HASH
    with open(file, "r+b") as stream:  # other bytes, of the same size, at the same time
        stream.write(b"A")
    os.utime(file, ns=(10**18, 10**18))
    assert hashing.digest_file(file).content_hash == HASH
    os.utime(file, ns=(10**18, 10**18 + 1))
    assert hashing.digest_file(file).content_hash != HASH


def test_a_file_written_just_now_isnt_kept(tmp_path: Path) -> None:
    """A second write in the same tick of the file system's clock would leave its size and
    modification time as they were, so a file modified less than two seconds ago isn't kept."""
    file = tmp_path / "data.csv"
    file.write_bytes(DATA)
    assert hashing.digest_file(file).content_hash == HASH
    file.write_bytes(DATA.upper())
    assert hashing.digest_file(file) == hashing.digest_bytes(DATA.upper())


def test_cache_clear_deletes_the_hashes(tmp_path: Path) -> None:
    file = tmp_path / "data.csv"
    file.write_bytes(DATA)
    os.utime(file, ns=(10**18, 10**18))
    hashing.digest_file(file)
    assert (cache.root() / hashing.NAMESPACE).is_dir()
    cache.clear()
    assert not (cache.root() / hashing.NAMESPACE).exists()


def test_a_file_is_hashed_in_the_working_tree_or_at_a_commit(tmp_path: Path) -> None:
    """At a commit, the blob git stores, hashed as it is read; a symlink is no file (Annex B)."""
    top = repository(tmp_path, {"data.csv": DATA})
    commit = git(top, "rev-parse", "HEAD").strip()
    (top / "link.csv").symlink_to("data.csv")
    (top / "data.csv").write_bytes(DATA.upper())
    worktree = WorktreeReader(top, Repository(top))
    at = CommitReader(Repository(top), commit, None, Remotes())
    assert hashing.digest(worktree, "data.csv") == hashing.digest_bytes(DATA.upper())
    assert hashing.digest(at, "data.csv") == hashing.Digest(HASH, len(DATA))
    assert hashing.digest(worktree, "link.csv") is None
    assert hashing.digest(at, "nothere.csv") is None
