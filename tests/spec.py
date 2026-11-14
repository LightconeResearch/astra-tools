"""astra-spec's source tree at the tag of the installed release: its conformance suite
(`conformance/`), its `examples/` and its test documents are the oracle. The published package
ships none of them, so the first run downloads them from that tag on GitHub and keeps them, one
folder per version, in the user's cache."""

from __future__ import annotations

import importlib.metadata
import io
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import pytest

TAG = f"v{importlib.metadata.version('astra-spec')}"
"""The tag of the astra-spec release installed."""

ARCHIVE = f"https://github.com/astra-project/astra-spec/archive/refs/tags/{TAG}.tar.gz"

KEPT = ("conformance/", "examples/", "tests/data/")
"""The folders of the source tree the tests read."""


def _source() -> Path:
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    root = cache / "astra-tools-tests" / f"astra-spec-{TAG}"
    if root.is_dir():
        return root
    try:
        with urllib.request.urlopen(ARCHIVE, timeout=60) as response:
            data = response.read()
    except OSError as error:
        pytest.fail(f"could not download astra-spec {TAG} from {ARCHIVE}: {error}", pytrace=False)
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=root.parent))
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            members = []
            for member in archive.getmembers():
                _, _, inside = member.name.partition("/")  # below the archive's top folder
                if inside.startswith(KEPT):
                    member.name = inside
                    members.append(member)
            archive.extractall(staging, members=members, filter="data")
        os.replace(staging, root)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return root


SPEC = _source()
"""astra-spec's source tree at the installed release's tag (the folders in `KEPT`)."""

DOCUMENTS = SPEC / "tests" / "data"
"""The conformance suite's documents: `valid/` and `invalid/`."""
