"""Git, through its own commands (design §4.3). Phase 0 asks it one thing: which repository
holds a folder."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(Exception):
    """git can't be run: a broken environment, not a broken analysis."""


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    """Run git, never waiting for a password (`GIT_TERMINAL_PROMPT=0`)."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        return subprocess.run(["git", *args], capture_output=True, env=env, check=False)
    except FileNotFoundError:
        raise GitError("astra needs git, and found no `git` on PATH: install git") from None


@dataclass(frozen=True)
class Repository:
    """A git repository with a working tree."""

    top: Path  # the top of its working tree

    @classmethod
    def discover(cls, folder: Path) -> Repository | None:
        """The repository whose working tree holds `folder`: the innermost, so a submodule's own
        (Annex B). None if there is none."""
        result = _git("-C", str(folder), "rev-parse", "--show-toplevel")
        if result.returncode != 0:
            return None
        return cls(Path(os.fsdecode(result.stdout.rstrip(b"\n"))))
