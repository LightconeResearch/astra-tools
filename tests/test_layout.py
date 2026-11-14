"""The package's layout: a namespace shared with astra-spec, and the core dependencies."""

from __future__ import annotations

import importlib
import importlib.metadata
import re
from pathlib import Path

SRC = Path(__file__).parents[1] / "src" / "astra"


def test_the_namespace_has_no_init_and_no_schema() -> None:
    assert not (SRC / "__init__.py").exists()
    assert not (SRC / "schema").exists()


def test_what_astra_spec_ships_in_the_namespace_is_its_own() -> None:
    """astra-tools has no file or folder of the namespace that astra-spec ships, so neither covers
    the other's, and astra-spec's datamodels load as they do with astra-spec alone."""
    theirs = {
        file.parts[1]
        for file in importlib.metadata.files("astra-spec") or ()
        if len(file.parts) > 1 and file.parts[0] == "astra"
    }
    ours = {path.name for path in SRC.iterdir() if path.name != "__pycache__"}
    assert {"schema", "datamodel"} <= theirs
    assert theirs & ours == set()
    assert importlib.import_module("astra.datamodel.astra_pydantic").Analysis.__name__ == "Analysis"


def test_the_core_dependencies() -> None:
    requires = importlib.metadata.requires("astra-tools") or []
    core = {
        re.sub(r"[-_.]+", "-", re.match(r"[A-Za-z0-9._-]+", r)[0]).lower()
        for r in requires
        if "extra ==" not in r
    }
    assert core == {"astra-spec", "click", "jsonschema", "rich", "ruamel-yaml"}
