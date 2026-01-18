"""CWL parameter file generation from ASP universes."""

from __future__ import annotations

from pathlib import Path

import yaml

from asp.models.analysis import Analysis
from asp.models.universe import Universe
from asp.workflow.mapping import generate_cwl_params


def _params_to_yaml(params: dict[str, object]) -> str:
    """Convert parameters dict to YAML string."""
    return yaml.safe_dump(params, sort_keys=False, allow_unicode=True)


def generate_params_string(analysis: Analysis, universe: Universe) -> str:
    """Generate CWL parameters as YAML string.

    Useful for preview/dry-run without writing to file.
    """
    return _params_to_yaml(generate_cwl_params(analysis, universe))


def generate_params_file(analysis: Analysis, universe: Universe, output_path: Path) -> None:
    """Generate CWL parameters YAML from a universe.

    Creates a YAML file with CWL input parameters derived from the
    universe's decision selections.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(generate_params_string(analysis, universe))
