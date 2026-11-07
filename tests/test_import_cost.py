"""What importing each module, and running the light commands, may pull in (design §4.12).

`astra --help`, completion and `validate --json` import neither rich nor the extras' packages,
and rich is imported only under `astra/cli/text/`. Each run is a fresh interpreter, since this
one has imported everything already.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import analysis, git_init

WATCHED = ("rich", "linkml_runtime", "pypdf", "rapidfuzz", "jsonschema", "ruamel.yaml")
"""The dependencies whose import costs enough to watch."""

EXTRAS_AND_RICH = {"rich", "linkml_runtime", "pypdf", "rapidfuzz"}

ALLOWED = {
    "astra.api": ("ruamel.yaml",),
    "astra.cache": (),
    "astra.check": ("ruamel.yaml",),
    "astra.cli": (),
    "astra.cli.cache": (),
    "astra.cli.check": (),
    "astra.cli.completion": (),
    "astra.cli.guide": (),
    "astra.cli.history": (),
    "astra.cli.info": (),
    "astra.cli.init": (),
    "astra.cli.paper": (),
    "astra.cli.plan": (),
    "astra.cli.rules": (),
    "astra.cli.schema": (),
    "astra.cli.spec": (),
    "astra.cli.text": ("rich",),
    "astra.cli.text.check": ("rich", "ruamel.yaml"),
    "astra.cli.text.history": ("rich", "ruamel.yaml"),
    "astra.cli.text.info": ("rich", "ruamel.yaml"),
    "astra.cli.text.paper": ("rich",),
    "astra.cli.text.plan": ("rich", "ruamel.yaml"),
    "astra.cli.text.rules": ("rich",),
    "astra.cli.text.spec": ("rich",),
    "astra.cli.text.universe": ("rich", "ruamel.yaml"),
    "astra.cli.text.validate": ("rich", "ruamel.yaml"),
    "astra.cli.text.view": ("rich", "ruamel.yaml"),
    "astra.cli.universe": (),
    "astra.cli.validate": (),
    "astra.cli.view": (),
    "astra.contract": (),
    "astra.diagnostics": (),
    "astra.environments": (),
    "astra.evidence": (),
    "astra.evidence.papers": ("pypdf",),
    "astra.evidence.quotes": ("pypdf", "rapidfuzz"),
    "astra.grammar": (),
    "astra.hashing": (),
    "astra.history": ("ruamel.yaml",),
    "astra.load": ("ruamel.yaml",),
    "astra.model": (),
    "astra.plan": ("ruamel.yaml",),
    "astra.records": ("ruamel.yaml",),
    "astra.reference": (),
    "astra.rules": ("ruamel.yaml",),
    "astra.rules.commits": ("ruamel.yaml",),
    "astra.rules.context": ("ruamel.yaml",),
    "astra.rules.decisions": ("ruamel.yaml",),
    "astra.rules.declarations": ("ruamel.yaml",),
    "astra.rules.driving": ("ruamel.yaml",),
    "astra.rules.inputs": ("ruamel.yaml",),
    "astra.rules.insights": ("ruamel.yaml",),
    "astra.rules.names": ("ruamel.yaml",),
    "astra.rules.outputs": ("ruamel.yaml",),
    "astra.rules.pins": ("ruamel.yaml",),
    "astra.rules.recipes": ("ruamel.yaml",),
    "astra.rules.universes": ("ruamel.yaml",),
    "astra.sources": (),
    "astra.sources.git": (),
    "astra.sources.paths": (),
    "astra.sources.reader": (),
    "astra.sources.remote": (),
    "astra.sources.standins": (),
    "astra.stack": ("ruamel.yaml",),
    "astra.universes": ("ruamel.yaml",),
    "astra.validate": ("ruamel.yaml",),
    "astra.view": ("ruamel.yaml",),
}
"""Each module, with what importing it may pull in of `WATCHED`. A new module is added here."""

SRC = Path(__file__).parents[1] / "src" / "astra"


def test_every_module_is_listed() -> None:
    modules = set()
    for path in SRC.rglob("*.py"):
        parts = path.relative_to(SRC.parent).with_suffix("").parts
        modules.add(".".join(parts[:-1] if parts[-1] == "__init__" else parts))
    assert modules == set(ALLOWED)


def imported(code: str, env: dict[str, str] | None = None) -> set[str]:
    """Which of `WATCHED` running `code` in a fresh interpreter imports."""
    probe = (
        f"{code}\nimport json, sys\nprint(json.dumps([n for n in {WATCHED!r} if n in sys.modules]))"
    )
    process = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, env=env, check=True
    )
    return set(json.loads(process.stdout.splitlines()[-1]))


@pytest.mark.parametrize("module", sorted(ALLOWED))
def test_importing_a_module_pulls_in_only_what_it_is(module: str) -> None:
    assert imported(f"import {module}") <= set(ALLOWED[module])


def run(*args: str) -> str:
    """Code that runs `astra <args>`, its output thrown away."""
    return (
        "import contextlib, io\n"
        "from astra.cli import main\n"
        "with contextlib.redirect_stdout(io.TextIOWrapper(io.BytesIO())):\n"
        "    try:\n"
        f"        main({list(args)!r}, prog_name='astra')\n"
        "    except SystemExit:\n"
        "        pass\n"
    )


def test_help_imports_neither_rich_nor_an_extra() -> None:
    assert imported(run("--help")) & EXTRAS_AND_RICH == set()


def test_completion_imports_neither_rich_nor_an_extra() -> None:
    assert imported(run("completion", "bash")) & EXTRAS_AND_RICH == set()
    env = {**os.environ, "_ASTRA_COMPLETE": "bash_complete", "COMP_WORDS": "astra va"}
    assert imported(run(), {**env, "COMP_CWORD": "1"}) & EXTRAS_AND_RICH == set()


def test_validate_json_imports_neither_rich_nor_an_extra(tmp_path: Path) -> None:
    folder = analysis(git_init(tmp_path))
    assert imported(run("validate", str(folder), "--json")) & EXTRAS_AND_RICH == set()


def importing(packages: set[str]) -> list[str]:
    """The modules of astra-tools whose source imports one of `packages`, or a module of one."""
    found = []
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_bytes())):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            if any(name.split(".")[0] in packages for name in names):
                found.append(path.relative_to(SRC).as_posix())
    return found


def test_rich_is_imported_only_under_cli_text() -> None:
    found = importing({"rich"})
    assert found and all(path.startswith("cli/text/") for path in found)


def test_the_evidence_extra_is_imported_only_under_evidence() -> None:
    found = importing({"pypdf", "rapidfuzz"})
    assert found and all(path.startswith("evidence/") for path in found)
