"""CWL file parsing utilities.

Parses CWL workflow and tool definitions to extract input parameters.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from asp.models.workflow import CWLParameter


def parse_cwl_inputs(cwl_path: Path) -> list[CWLParameter]:
    """Parse CWL workflow/tool and extract input parameters.

    Supports CWL v1.0, v1.1, and v1.2 input definitions.

    Args:
        cwl_path: Path to CWL file.

    Returns:
        List of CWLParameter objects describing each input.

    Raises:
        FileNotFoundError: If CWL file doesn't exist.
        ValueError: If CWL file is invalid or has no inputs.
    """
    if not cwl_path.exists():
        raise FileNotFoundError(f"CWL file not found: {cwl_path}")

    with open(cwl_path) as f:
        cwl_doc = yaml.safe_load(f)

    if not isinstance(cwl_doc, dict):
        raise ValueError(f"CWL file is not a valid document: {cwl_path}")

    inputs = cwl_doc.get("inputs") or {}
    parameters: list[CWLParameter] = []

    if isinstance(inputs, list):
        for inp in inputs:
            if isinstance(inp, dict) and (name := inp.get("id")):
                parameters.append(_make_param(name, inp))
    elif isinstance(inputs, dict):
        for name, inp_def in inputs.items():
            parameters.append(_make_param(name, inp_def))

    return parameters


def _make_param(name: str, inp_def: Any) -> CWLParameter:
    """Create a CWLParameter from an input definition."""
    if inp_def is None:
        return CWLParameter(name=name, type="Any", required=True)

    if isinstance(inp_def, str):
        cwl_type, required = _parse_type(inp_def)
        return CWLParameter(name=name, type=cwl_type, required=required)

    if not isinstance(inp_def, dict):
        return CWLParameter(name=name, type="Any", required=True)

    cwl_type, required = _parse_type(inp_def.get("type", "string"))
    return CWLParameter(
        name=name,
        type=cwl_type,
        required=required,
        default=inp_def.get("default"),
    )


def _parse_type(type_def: Any) -> tuple[str, bool]:
    """Parse a CWL type definition.

    Returns:
        Tuple of (base_type, is_required). Types ending with '?' are optional.
    """
    if type_def is None:
        return ("Any", True)

    if isinstance(type_def, str):
        if type_def.endswith("?"):
            return (type_def[:-1], False)
        return (type_def, True)

    if isinstance(type_def, list):
        is_optional = "null" in type_def
        types = [t for t in type_def if t != "null"]
        if len(types) == 1:
            base = types[0]
            type_name = _parse_complex_type(base) if isinstance(base, dict) else base
            return (type_name, not is_optional)
        return ("union", not is_optional)

    if isinstance(type_def, dict):
        return (_parse_complex_type(type_def), True)

    return ("Any", True)


def _parse_complex_type(type_def: dict[str, Any]) -> str:
    """Parse a complex CWL type definition (array, record, enum)."""
    type_class = type_def.get("type")

    if type_class == "array":
        items = type_def.get("items", "Any")
        return f"{items}[]" if isinstance(items, str) else "array"

    if type_class == "record":
        return "record"

    if type_class == "enum":
        return "enum"

    return str(type_class) if type_class else "Any"
