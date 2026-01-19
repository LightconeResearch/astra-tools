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


def generate_params_string(
    analysis: Analysis,
    universe: Universe,
    *,
    include_inputs: bool = False,
    base_path: Path | None = None,
) -> str:
    """Generate CWL parameters as YAML string.

    Args:
        analysis: The ASP analysis specification.
        universe: The universe with decision selections.
        include_inputs: Whether to include ASP inputs as CWL File parameters.
        base_path: Base path for resolving relative file paths in inputs.

    Returns:
        YAML string with CWL parameters.
    """
    params = generate_cwl_params(
        analysis, universe, include_inputs=include_inputs, base_path=base_path
    )
    return _params_to_yaml(params)


def generate_params_file(
    analysis: Analysis,
    universe: Universe,
    output_path: Path,
    *,
    include_inputs: bool = False,
    base_path: Path | None = None,
) -> None:
    """Generate CWL parameters YAML from a universe.

    Creates a YAML file with CWL input parameters derived from the
    universe's decision selections.

    Args:
        analysis: The ASP analysis specification.
        universe: The universe with decision selections.
        output_path: Path to write the YAML file.
        include_inputs: Whether to include ASP inputs as CWL File parameters.
        base_path: Base path for resolving relative file paths in inputs.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    params_str = generate_params_string(
        analysis, universe, include_inputs=include_inputs, base_path=base_path
    )
    output_path.write_text(params_str)
