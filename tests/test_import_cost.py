"""What each public module is allowed to drag in when it is imported.

Import cost is part of the API. A downstream tool that imports
``astra.scaffold`` to write two template files, or ``astra.resolve`` to
walk a dict it already has, should not pay for the datamodel — reaching
``astra.datamodel`` loads ``linkml_runtime``, ~250 ms, an order of
magnitude more than the rest of ASTRA put together. Whoever calls the
function that needs a heavy dependency pays for it; whoever merely
imports a module that could does not.

The rule is one regrettable import away from being lost, and nothing
about the import itself looks wrong when it happens — which is what this
file is for. Subprocesses, because imports are process-global and pytest
has already loaded everything.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

#: Every dependency whose import cost is worth a decision, cheapest last.
WATCHED = (
    "linkml_runtime",
    "astra.datamodel",
    "pydantic",
    "httpx",
    "pypdf",
    "importlib.metadata",
    "yaml",
    "rich",
    "click",
    "rapidfuzz",
)

#: module → what importing it is allowed to pull in from `WATCHED`.
#: A module may import what it *is*; it defers what a subset of its
#: functions merely might need.
ALLOWED: dict[str, tuple[str, ...]] = {
    "astra.spec_version": (),
    "astra.scaffold": (),
    "astra.helpers": (),
    "astra.resolve": (),
    "astra.validation": (),
    "astra.validation.schema": (),
    "astra.validation.semantic": (),
    "astra.papers": (),
    "astra.spec_render": (),
    # Fuzzy matching is what `verification.pdf` does, so it pays for it up
    # front; `pypdf` and `httpx` are optional extras it may never touch.
    "astra.verification": ("rapidfuzz",),
    # The CLI cannot parse a command line or print without these.
    "astra.cli": ("rich", "click"),
}


@pytest.mark.parametrize("module", sorted(ALLOWED))
def test_import_pulls_in_nothing_it_does_not_need(module: str) -> None:
    code = (
        "import sys, importlib\n"
        f"importlib.import_module({module!r})\n"
        f"print(' '.join(n for n in {WATCHED!r} if n in sys.modules))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    pulled = set(proc.stdout.split())
    assert pulled <= set(ALLOWED[module]), (
        f"importing {module} pulled in {sorted(pulled - set(ALLOWED[module]))}; "
        "import it inside the function that needs it, or add it to ALLOWED "
        "with a note saying why the module is what it costs"
    )
