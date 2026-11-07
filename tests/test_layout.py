"""The package's layout: a namespace shared with astra-spec, and the core dependencies."""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

SRC = Path(__file__).parents[1] / "src" / "astra"


def test_the_namespace_has_no_init_and_no_schema() -> None:
    assert not (SRC / "__init__.py").exists()
    assert not (SRC / "schema").exists()


def test_the_core_dependencies() -> None:
    requires = importlib.metadata.requires("astra-tools") or []
    core = {
        re.sub(r"[-_.]+", "-", re.match(r"[A-Za-z0-9._-]+", r)[0]).lower()
        for r in requires
        if "extra ==" not in r
    }
    assert core == {"astra-spec", "click", "jsonschema", "rich", "ruamel-yaml"}
