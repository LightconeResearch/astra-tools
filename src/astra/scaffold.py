"""The boilerplate spec scaffold: ``astra.yaml`` + ``universes/baseline.yaml``.

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
    """Write the boilerplate spec scaffold into ``directory``.

    Creates ``universes/`` and writes the boilerplate ``astra.yaml``
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
    """Create boilerplate astra.yaml with TODOs."""
    name = directory.name if directory != Path(".") else "My Analysis"
    spec_version = installed_spec_version() or "1.0"

    astra_yaml = f"""# ASTRA Analysis Specification

version: "{spec_version}"
name: "{name}"
container: python:3.12-slim
description: |
  TODO: One-paragraph overview of the analysis — its question,
  scope, and what the reader should take away. A richer write-up
  (figures, citations, multi-page structure) is authored separately
  as a report that references this analysis's elements; see the
  ASTRA documentation.

inputs:
  - id: primary_data
    type: data
    description: "TODO: Describe your primary data source"

outputs:
  - id: main_result
    type: metric
    format: json
    description: "TODO: Describe your primary output metric"
    decisions: [example_method]
    recipe:
      command: python src/main.py --method {{decisions.example_method}} --out {{output}}

  - id: conclusion
    type: report
    format: md
    description: "Summary of analysis findings"
    inputs: [main_result]
    recipe:
      command: python src/main.py --result {{inputs.main_result}} --out {{output}}

decisions:
  example_method:
    label: "Example Method Choice"
    rationale: "TODO: Explain why this decision matters"
    default: option_a
    options:
      option_a:
        label: "Option A"
        description: "TODO: Describe option A"
      option_b:
        label: "Option B"
        description: "TODO: Describe option B"
"""
    (directory / "astra.yaml").write_text(astra_yaml)

    # Create baseline universe
    baseline_universe = """# Baseline Universe
# Default configuration using standard practices

id: baseline
description: "Default configuration using standard practices"

decisions:
  example_method: option_a
"""
    (directory / "universes" / "baseline.yaml").write_text(baseline_universe)
