"""A file's SHA-256 and size, as a record gives them (§19), through the cache (design §4.7).

A file on disk is hashed once: its entry in the cache's `hashes`, keyed by its device and inode,
holds its size and modification time, and a hit needs both unchanged, so an unchanged file costs
a `stat`. A file modified less than two seconds before it is hashed isn't kept, since a write in
the same tick of the file system's clock would leave its modification time as it was. Bytes
read at a commit, through a Reader, are hashed as they are read.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from astra import cache
from astra.sources.reader import Reader, WorktreeReader

NAMESPACE = "hashes"
"""The cache's namespace of file hashes (`cache.NAMESPACES`)."""

_RECENT_NS = 2_000_000_000
_CHUNK = 1 << 20


@dataclass(frozen=True)
class Digest:
    """What a record gives of some bytes (§19): their hash, `sha256:` then the SHA-256 digest
    in lowercase hexadecimal, and their size in bytes."""

    content_hash: str
    size: int


def digest_bytes(data: bytes) -> Digest:
    """The digest of `data`."""
    return Digest(f"sha256:{hashlib.sha256(data).hexdigest()}", len(data))


def digest_file(path: Path) -> Digest:
    """The digest of the file at `path`, kept in the cache. Raises OSError where it can't be
    read."""
    before = os.stat(path)
    key = f"{before.st_dev}:{before.st_ino}"
    kept = cache.get(NAMESPACE, key)
    if kept is not None:
        entry = json.loads(kept)
        if (entry["size"], entry["mtime_ns"]) == (before.st_size, before.st_mtime_ns):
            return Digest(entry["content_hash"], entry["size"])
    started = time.time_ns()
    hasher, size = hashlib.sha256(), 0
    with open(path, "rb") as file:
        while chunk := file.read(_CHUNK):
            hasher.update(chunk)
            size += len(chunk)
    found = Digest(f"sha256:{hasher.hexdigest()}", size)
    if started - before.st_mtime_ns >= _RECENT_NS and size == before.st_size:
        entry = {"size": size, "mtime_ns": before.st_mtime_ns, "content_hash": found.content_hash}
        cache.put(NAMESPACE, key, json.dumps(entry).encode("ascii"))
    return found


def digest(reader: Reader, path: str) -> Digest | None:
    """The digest of the file at `path` in `reader`; None where no file is there, a symlink
    being none (Annex B). Raises OSError where it can't be read."""
    entry = reader.stat(path)
    if entry is None or entry.kind != "file":
        return None
    if isinstance(reader, WorktreeReader):
        return digest_file(reader.top / path)
    return digest_bytes(reader.read(path))
