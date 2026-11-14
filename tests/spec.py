"""astra-spec's source tree at the tag of the installed release: its conformance suite
(`conformance/`), its `examples/` and its test documents are the oracle. The published package
ships none of them, so `ASTRA_SPEC_SOURCE` names a checkout of that tag. A test module that imports
this one fails to collect without it."""

from __future__ import annotations

import importlib.metadata
import os
import subprocess
from pathlib import Path

import pytest

TAG = f"v{importlib.metadata.version('astra-spec')}"
"""The tag of the astra-spec release installed."""


def _source() -> Path:
    where = os.environ.get("ASTRA_SPEC_SOURCE")
    if not where:
        pytest.fail(
            f"set ASTRA_SPEC_SOURCE to a checkout of astra-spec at {TAG}, the release installed",
            pytrace=False,
        )
    tags = subprocess.run(
        ["git", "-C", where, "tag", "--points-at", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    if TAG not in tags:
        pytest.fail(
            f"ASTRA_SPEC_SOURCE ({where}) is no checkout of {TAG}, the astra-spec installed",
            pytrace=False,
        )
    return Path(where)


SPEC = _source()
"""astra-spec's source tree at the installed release's tag."""

DOCUMENTS = SPEC / "tests" / "data"
"""The conformance suite's documents: `valid/` and `invalid/`."""
