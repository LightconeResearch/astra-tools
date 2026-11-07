"""Stand-ins: what a large-file tool keeps in a file's place (§7, Annex B *Stand-ins*, design
§4.5).

Which stand-ins count is the validator's to say. astra-tools recognises three, and never
fetches what they stand for:

- Git LFS: a pointer file at the path (`version https://git-lfs.github.com/spec/v1`, then
  `oid sha256:…` and `size …`);
- git-annex: a symlink into `annex/objects/` at the path, or an unlocked pointer file there,
  whose one line is a path into `/annex/objects/`;
- DVC: a `<path>.dvc` file beside the path.

They are an extension point (design §4.10): another package adds one by registering an object
that has `StandIn`'s members in the entry-point group `astra.standins`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from astra.sources.reader import Reader

GROUP = "astra.standins"
"""The entry-point group other packages register their stand-ins in (design §4.10)."""


class StandIn(Protocol):
    """A kind of stand-in a tool keeps in a file's place."""

    @property
    def name(self) -> str:
        """The tool's name, as messages give it."""
        ...

    def place(self, path: str) -> str:
        """Where the tool keeps the stand-in for the file at `path`: what git tracks for it."""
        ...

    def recognises(self, reader: Reader, path: str) -> bool:
        """Whether what is at `place(path)` in `reader` stands in for the file at `path`."""
        ...


_LFS_VERSION = "version https://git-lfs.github.com/spec/v1"
_LFS_OID = re.compile(r"sha256:[0-9a-f]{64}")
_LFS_SIZE = re.compile(r"[0-9]+")


@dataclass(frozen=True)
class GitLfs:
    """A Git LFS pointer file, kept at the path itself."""

    name: str = "Git LFS"

    def place(self, path: str) -> str:
        return path

    def recognises(self, reader: Reader, path: str) -> bool:
        entry = reader.stat(path)
        if entry is None or entry.kind != "file":
            return False
        try:
            lines = reader.read(path).decode("utf-8").split("\n")
        except UnicodeDecodeError:
            return False
        if lines[0] != _LFS_VERSION or lines[-1] != "":
            return False
        fields = {key: value for key, _, value in (line.partition(" ") for line in lines[1:-1])}
        oid, size = fields.get("oid", ""), fields.get("size", "")
        return bool(_LFS_OID.fullmatch(oid) and _LFS_SIZE.fullmatch(size))


@dataclass(frozen=True)
class GitAnnex:
    """A git-annex link at the path itself: a symlink into `annex/objects/`, or an unlocked
    pointer file naming a path there."""

    name: str = "git-annex"

    def place(self, path: str) -> str:
        return path

    def recognises(self, reader: Reader, path: str) -> bool:
        entry = reader.stat(path)
        if entry is not None and entry.kind == "symlink" and entry.target is not None:
            return "/annex/objects/" in f"/{entry.target}"
        if entry is None or entry.kind != "file":
            return False
        line = reader.read(path).removesuffix(b"\n")
        return line.startswith(b"/annex/objects/") and b"\n" not in line


@dataclass(frozen=True)
class Dvc:
    """A DVC file, `<path>.dvc`, beside the path."""

    name: str = "DVC"

    def place(self, path: str) -> str:
        return f"{path}.dvc"

    def recognises(self, reader: Reader, path: str) -> bool:
        entry = reader.stat(self.place(path))
        return entry is not None and entry.kind == "file"


BUILT_IN: tuple[StandIn, ...] = (GitLfs(), GitAnnex(), Dvc())
"""The stand-ins astra-tools recognises itself (design §4.5)."""


def registered() -> tuple[StandIn, ...]:
    """The built-in stand-ins, then each one another package registers in `GROUP`."""
    from importlib.metadata import entry_points

    return (*BUILT_IN, *(point.load() for point in entry_points(group=GROUP)))
