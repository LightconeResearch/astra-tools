"""The cache: one folder of plain files, outside every repository.

It is `$ASTRA_CACHE_DIR`, which must be absolute, or else the platform's user cache folder:
`$XDG_CACHE_HOME/astra` or `~/.cache/astra`, `~/Library/Caches/astra` on macOS, and
`%LOCALAPPDATA%\\astra\\cache` on Windows. An entry is one file, `<namespace>/<sha256 of its
key>` with the suffix its kind of file takes, if any (`.pdf` for a paper), written atomically, so
processes that share the cache see the old value or the new one, never a mix. Everything in it is
safe to delete, and `clear` deletes what astra-tools keeps there (`NAMESPACES`).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

NAMESPACES = ("remotes", "validity", "hashes", "worktrees", "papers")
"""The folders astra-tools keeps in the cache: the remote stores (`sources.remote`), the
validity of analyses from a commit (`rules.commits`), the hashes of files (`hashing`), the
checkouts made for runs (`Repository.worktree`) and the papers cited by DOI
(`evidence.papers`)."""


class CacheError(Exception):
    """The cache can't be used where the environment puts it."""


def root() -> Path:
    """The cache's folder. Raises CacheError for a relative `ASTRA_CACHE_DIR`, which would put
    the cache in whatever repository astra runs in."""
    configured = os.environ.get("ASTRA_CACHE_DIR")
    if configured:
        folder = Path(configured).expanduser()
        if not folder.is_absolute():
            raise CacheError(
                f"ASTRA_CACHE_DIR is the relative path {configured!r}, which would put the cache "
                "inside whatever repository astra runs in: give it an absolute path"
            )
        return folder
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "astra"
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        return (Path(local) if local else Path.home() / "AppData" / "Local") / "astra" / "cache"
    xdg = os.environ.get("XDG_CACHE_HOME")
    return (Path(xdg) if xdg and Path(xdg).is_absolute() else Path.home() / ".cache") / "astra"


def get(namespace: str, key: str, suffix: str = "") -> bytes | None:
    """The value last put under `key` in `namespace`, with `suffix`, or None."""
    try:
        return _entry(namespace, key, suffix).read_bytes()
    except FileNotFoundError:
        return None


def path(namespace: str, key: str, suffix: str = "") -> Path | None:
    """The file that holds the value under `key` in `namespace`, with `suffix`, or None where
    there is none: for a tool that reads the file itself."""
    entry = _entry(namespace, key, suffix)
    return entry if entry.is_file() else None


def values(namespace: str, suffix: str) -> Iterator[bytes]:
    """Every value in `namespace` whose file has `suffix`, in no particular order."""
    folder = root() / namespace
    if not folder.is_dir():
        return
    for entry in folder.iterdir():
        if entry.name.endswith(suffix) and not entry.name.startswith(".tmp-"):
            with contextlib.suppress(FileNotFoundError):  # removed meanwhile
                yield entry.read_bytes()


def put(namespace: str, key: str, value: bytes, suffix: str = "") -> None:
    """Keep `value` under `key` in `namespace`, with `suffix`, in place of any value before it:
    written to a temporary file in the same folder, then moved into place by `os.replace`."""
    path = _entry(namespace, key, suffix)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write(value)
            os.replace(temporary, path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary)
    except OSError as error:
        raise CacheError(
            f"can't write the cache in {path.parent}: {error.strerror}; set ASTRA_CACHE_DIR to "
            "a folder astra can write"
        ) from error


def clear() -> Path:
    """Remove everything astra-tools keeps in the cache, each of `NAMESPACES` moved aside and
    then deleted, so that no process reads half of one; anything else in the folder is left
    alone. Gives the cache's folder. Raises CacheError where it can't be cleared."""
    folder = root()
    for namespace in NAMESPACES:  # only what astra-tools keeps there
        kept = folder / namespace
        if not kept.is_dir():
            continue
        try:
            aside = Path(tempfile.mkdtemp(prefix=".tmp-", dir=folder))
            try:
                kept.rename(aside / namespace)
            finally:
                shutil.rmtree(aside)
        except OSError as error:
            raise CacheError(
                f"can't clear {kept}: {error.strerror}; remove it by hand, it is safe to delete"
            ) from error
    return folder


def _entry(namespace: str, key: str, suffix: str = "") -> Path:
    return root() / namespace / (hashlib.sha256(key.encode("utf-8")).hexdigest() + suffix)
