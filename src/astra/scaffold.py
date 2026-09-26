"""The empty spec scaffold: ``astra.yaml`` + ``universes/baseline.yaml``.

Its own module rather than part of :mod:`astra.cli`, so that scaffolding
costs what writing two template files should cost. Importing ``astra.cli``
pulls in Click, Rich and the validation stack — and through the datamodel,
``linkml_runtime`` — about half a second, none of which writing a template
needs. This module imports stdlib only.

``astra init`` and downstream tools (e.g. lightcone-cli) both scaffold
through :func:`create_boilerplate`, so this is the one definition of what
a fresh ASTRA project contains.
"""

from __future__ import annotations

from pathlib import Path

from astra.spec_version import installed_spec_version


def create_boilerplate(directory: Path) -> None:
    """Write the empty spec scaffold into ``directory``.

    Creates ``universes/`` and writes an empty ``astra.yaml``
    and ``universes/baseline.yaml``. Touches nothing
    else — no ``.gitignore``, no git init, no emptiness checks — so
    downstream tools (e.g. lightcone-cli) can scaffold into existing
    directories under their own conventions. Existing files are
    overwritten; callers guard on ``astra.yaml`` presence.
    """
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "universes").mkdir(parents=True, exist_ok=True)
    _create_boilerplate_astra_yaml(directory)


def _create_boilerplate_astra_yaml(directory: Path) -> None:
    """Create an empty astra.yaml and a baseline universe that selects nothing."""
    name = directory.name if directory != Path(".") else "My Analysis"
    spec_version = installed_spec_version() or "1.0"

    # The root collections are required fields, so an empty analysis
    # spells them out as empty rather than omitting them.
    astra_yaml = f"""# ASTRA Analysis Specification

version: "{spec_version}"
name: "{name}"
description: ""

inputs: []

outputs: []

decisions: {{}}
"""
    (directory / "astra.yaml").write_text(astra_yaml)

    # An analysis runs under at least one universe, even with no decisions.
    baseline_universe = """# Baseline Universe

id: baseline
description: "Default configuration"

decisions: {}
"""
    (directory / "universes" / "baseline.yaml").write_text(baseline_universe)
