"""The empty spec scaffold: an ``astra.yaml`` with nothing declared yet.

Its own module rather than part of :mod:`astra.cli`, so that scaffolding costs what writing
one template file should cost: this module imports the standard library only.

``astra init`` and downstream tools (e.g. lightcone-cli) both scaffold through
:func:`create_boilerplate`, so this is the one definition of what a fresh ASTRA project
contains.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path

SPEC_VERSION = "0.1.0"
"""The `spec_version` a new analysis is written at."""


def create_boilerplate(directory: Path) -> None:
    """Write the empty spec scaffold into ``directory``.

    Writes an empty ``astra.yaml``, making the folder if need be, and touches nothing else (no
    ``.gitignore``, no git init, no emptiness checks), so downstream tools can scaffold into
    existing directories under their own conventions. Universes are written in ``astra.yaml``
    since ASTRA 0.1, so there is no ``universes/`` folder. An existing file is overwritten;
    callers guard on ``astra.yaml`` presence.
    """
    directory.mkdir(parents=True, exist_ok=True)
    name = directory.resolve().name or "My Analysis"
    write_text(
        directory / "astra.yaml",
        "# ASTRA Analysis Specification\n\n"
        f'spec_version: "{SPEC_VERSION}"\n'
        f"label: {json.dumps(name, ensure_ascii=False)}\n",
    )


def write_text(file: Path, text: str) -> None:
    """Write ``text`` to ``file`` atomically; its folder is made if need be."""
    file.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{file.name}.", dir=file.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.chmod(temporary, 0o644)
        os.replace(temporary, file)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
