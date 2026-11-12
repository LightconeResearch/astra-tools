"""Remote repositories, each in a store of its own in the cache.

A store is a bare repository, one per URL, into which each commit asked for is fetched without
its blobs (`git fetch --filter=blob:none`) and kept by a ref of its own, so that a commit is
fetched once: a commit kept from an earlier fetch counts as got.
Authentication is git's, and git never waits for a password. Offline, nothing is
fetched.

A gitlink's commit that the submodule's checkout holds is read there before any fetch;
otherwise it is got from the URL its `.gitmodules` gives, a relative one resolved as git
resolves it.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from astra import cache
from astra.sources.git import Repository


@dataclass
class Remotes:
    """The stores one validation gets commits from, and what it has asked of them: each commit
    is asked for once."""

    offline: bool = False  # fetch nothing: read only the commits kept from earlier fetches
    _got: dict[tuple[str, str], Repository | None] = field(default_factory=dict, repr=False)

    def get(
        self, url: str | None, commit: str, local: Repository | None = None
    ) -> Repository | None:
        """The repository to read `commit` in: `local`, a local repository that may hold it,
        where it does; or else the store of `url`, holding it, kept or fetched now. None where
        the commit can't be got (astra-tools' `REMOTE_UNREACHABLE`)."""
        # A gitlink's commit the submodule's checkout holds counts as got, before any fetch.
        if local is not None and local.has_commit(commit):
            return local
        if url is None:
            return None
        if (url, commit) not in self._got:
            store = _store(url)
            got = store.has_commit(commit) or (not self.offline and store.fetch(commit))
            self._got[(url, commit)] = store if got else None
        return self._got[(url, commit)]

    @property
    def missed(self) -> bool:
        """Whether a commit asked for couldn't be got: what was read depends then on more than
        the commits that were."""
        return any(store is None for store in self._got.values())


def _store(url: str) -> Repository:
    """The store of `url` in the cache, made if need be: in a folder of its own, then moved
    into place, so that two processes never make one store together."""
    folder = cache.root() / "remotes"
    path = folder / hashlib.sha256(url.encode("utf-8")).hexdigest()
    if not path.is_dir():
        folder.mkdir(parents=True, exist_ok=True)
        made = Path(tempfile.mkdtemp(prefix=".tmp-", dir=folder))
        Repository.init_bare(made, url)
        try:
            made.rename(path)
        except OSError:  # another process made it first
            shutil.rmtree(made)
    return Repository(path)


def resolve(base: str, url: str) -> str:
    """`url`, a submodule's URL as `.gitmodules` gives it, resolved as git resolves it: one that
    starts `./` or `../` is relative to `base`, its superproject's remote, each `../` removing
    the last segment of `base`, and the last `:` of an scp-like `host:path` where it has no `/`
    left; any other is as written."""
    if not url.startswith(("./", "../")):
        return url
    base, colon = base.removesuffix("/"), False
    while url.startswith(("./", "../")):
        if url.startswith("./"):
            url = url[2:]
            continue
        url = url[3:]
        cut = base.rfind("/")
        if cut < 0 and ":" in base:
            cut, colon = base.rfind(":"), True
        base = base[:cut] if cut >= 0 else "."
    return f"{base}{':' if colon else '/'}{url}".removesuffix("/")
