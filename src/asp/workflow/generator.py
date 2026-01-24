"""CWL workflow and parameter file generation from ASP specifications."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from asp.workflow.mapping import generate_cwl_params


def _to_yaml(data: dict[str, object], *, default_flow_style: bool | None = None) -> str:
    """Convert dict to YAML string."""
    result: str = yaml.safe_dump(
        data, sort_keys=False, allow_unicode=True, default_flow_style=default_flow_style
    )
    return result


def _params_to_yaml(params: dict[str, object]) -> str:
    """Convert parameters dict to YAML string."""
    return _to_yaml(params)


def _infer_cwl_type_from_option(option: dict[str, Any]) -> str:
    """Infer CWL type from an option's value."""
    value = option.get("value") if isinstance(option, dict) else None
    if value is None:
        return "string"  # Option ID will be used as string

    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        # Try to infer array item type
        if value and isinstance(value[0], str):
            return "string[]"
        return "string[]"
    if isinstance(value, dict):
        return "record"  # Special marker - will be expanded
    return "string"


def _get_decision_cwl_inputs(
    decision_id: str, decision: dict[str, Any]
) -> list[dict[str, Any]]:
    """Generate CWL input definitions for a decision.

    Handles dict values by creating separate inputs for each key.
    """
    inputs: list[dict[str, Any]] = []

    # Look at first option to determine structure
    options = decision.get("options", {})
    first_option = next(iter(options.values()), None)
    if first_option is None:
        return inputs

    cwl_type = _infer_cwl_type_from_option(first_option)

    first_value = first_option.get("value") if isinstance(first_option, dict) else None
    if cwl_type == "record" and isinstance(first_value, dict):
        # Dict value - create separate input for each key
        for key, val in first_value.items():
            param_name = f"{decision_id}_{key}"
            if isinstance(val, bool):
                val_type = "boolean"
            elif isinstance(val, int):
                val_type = "int"
            elif isinstance(val, float):
                val_type = "float"
            else:
                val_type = "string"
            inputs.append(
                {
                    "name": param_name,
                    "type": val_type,
                    "doc": f"From decision '{decision_id}', key '{key}'",
                }
            )
    else:
        # Simple value
        label = decision.get("label") or f"Decision: {decision_id}"
        inputs.append(
            {
                "name": decision_id,
                "type": cwl_type,
                "doc": label,
            }
        )

    return inputs


def _get_input_cwl_type(inp: dict[str, Any]) -> str:
    """Map ASP input type to CWL type."""
    if inp.get("type") == "data":
        return "File"
    # analysis and literature types default to string
    return "string"


def generate_cwl_skeleton(analysis: dict[str, Any]) -> str:
    """Generate a CWL workflow skeleton from an ASP analysis specification.

    Creates a CommandLineTool with:
    - Inputs for each ASP input (data -> File)
    - Inputs for each ASP decision (using naming convention)
    - Outputs for each ASP output
    - Placeholder baseCommand

    Args:
        analysis: The ASP analysis specification dict.

    Returns:
        CWL workflow as YAML string.
    """
    cwl: dict[str, Any] = {
        "cwlVersion": "v1.2",
        "class": "CommandLineTool",
        "baseCommand": ["python", "scripts/main.py"],
        "requirements": {
            "InitialWorkDirRequirement": {"listing": [{"entry": "$(inputs)", "writable": True}]}
        },
    }

    # Build inputs section
    inputs: dict[str, Any] = {}

    analysis_content = analysis.get("analysis", {})

    # Add ASP inputs
    for inp in analysis_content.get("inputs", []):
        cwl_type = _get_input_cwl_type(inp)
        inp_id = inp.get("id")
        inputs[inp_id] = {
            "type": cwl_type,
            "doc": inp.get("description") or f"Input: {inp_id}",
            "inputBinding": {"prefix": f"--{inp_id.replace('_', '-')}"},
        }

    # Add ASP decisions
    for decision_id, decision in analysis.get("decisions", {}).items():
        decision_inputs = _get_decision_cwl_inputs(decision_id, decision)
        for dinp in decision_inputs:
            name = dinp.pop("name")
            dinp["inputBinding"] = {"prefix": f"--{name.replace('_', '-')}"}
            inputs[name] = dinp

    cwl["inputs"] = inputs

    # Build outputs section
    outputs: dict[str, Any] = {}
    for out in analysis_content.get("outputs", []):
        out_id = out.get("id")
        # Default to JSON file output - user should customize
        outputs[out_id] = {
            "type": "File",
            "doc": out.get("description") or f"Output: {out_id}",
            "outputBinding": {"glob": f"{out_id}.json"},
        }

    cwl["outputs"] = outputs

    # Generate YAML with comments
    yaml_str = _to_yaml(cwl)

    # Add header comment
    analysis_name = analysis_content.get("name", "Unknown")
    header = f"""# CWL workflow generated from ASP specification
# Analysis: {analysis_name}
#
# TODO: Customize this workflow:
# 1. Update baseCommand to point to your script
# 2. Adjust output glob patterns
# 3. Add any additional requirements
#
"""
    return header + yaml_str


def generate_cwl_file(analysis: dict[str, Any], output_path: Path) -> None:
    """Generate CWL workflow skeleton file from an ASP analysis.

    Args:
        analysis: The ASP analysis specification dict.
        output_path: Path to write the CWL file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cwl_str = generate_cwl_skeleton(analysis)
    output_path.write_text(cwl_str)


def generate_params_string(
    analysis: dict[str, Any],
    universe: dict[str, Any],
    *,
    include_inputs: bool = False,
    base_path: Path | None = None,
) -> str:
    """Generate CWL parameters as YAML string.

    Args:
        analysis: The ASP analysis specification dict.
        universe: The universe dict with 'decisions' key.
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
    analysis: dict[str, Any],
    universe: dict[str, Any],
    output_path: Path,
    *,
    include_inputs: bool = False,
    base_path: Path | None = None,
) -> None:
    """Generate CWL parameters YAML from a universe.

    Creates a YAML file with CWL input parameters derived from the
    universe's decision selections.

    Args:
        analysis: The ASP analysis specification dict.
        universe: The universe dict with 'decisions' key.
        output_path: Path to write the YAML file.
        include_inputs: Whether to include ASP inputs as CWL File parameters.
        base_path: Base path for resolving relative file paths in inputs.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    params_str = generate_params_string(
        analysis, universe, include_inputs=include_inputs, base_path=base_path
    )
    output_path.write_text(params_str)
