"""Workflow validation against ASP specifications.

Validates that ASP decisions properly map to CWL workflow parameters,
detecting unmapped decisions and unused parameters. Optionally validates
CWL syntax using cwltool.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from asp.models.workflow import CWLParameter, WorkflowValidationError
from asp.workflow.mapping import apply_naming_convention
from asp.workflow.parser import parse_cwl_inputs

if TYPE_CHECKING:
    from asp.models.analysis import Analysis, Decision


def validate_cwl_syntax(cwl_path: Path) -> list[WorkflowValidationError]:
    """Validate CWL file syntax using cwltool.

    Args:
        cwl_path: Path to CWL workflow file.

    Returns:
        List of validation errors. Empty list means valid CWL.
    """
    import re
    import subprocess

    if not cwl_path.exists():
        return [WorkflowValidationError("CWL_FILE_NOT_FOUND", f"File not found: {cwl_path}")]

    result = subprocess.run(
        ["cwltool", "--validate", str(cwl_path)],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        return []

    # Strip ANSI escape codes and extract error (cwltool writes to stdout)
    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    output = ansi_escape.sub("", result.stdout + result.stderr)

    # Find error lines (after ERROR marker)
    lines = output.split("\n")
    error_msg = "CWL validation failed"
    for i, line in enumerate(lines):
        if "ERROR" in line:
            # Collect all lines from ERROR onwards
            error_lines = [ln.strip() for ln in lines[i:] if ln.strip()]
            error_msg = " ".join(error_lines).replace("ERROR ", "")
            break

    return [WorkflowValidationError(code="CWL_SYNTAX_ERROR", message=error_msg)]


def _get_possible_params(decision_id: str, decision: Decision) -> set[str]:
    """Get all possible CWL parameter names a decision could produce."""
    possible: set[str] = set()
    for option in decision.options.values():
        if option.value is not None:
            possible.update(apply_naming_convention(decision_id, option.value).keys())
        else:
            possible.add(decision_id)
    return possible


def get_decision_param_mapping(
    analysis: Analysis,
    cwl_path: Path,
) -> dict[str, list[str]]:
    """Get mapping of ASP decisions to CWL parameters.

    Args:
        analysis: The ASP analysis specification.
        cwl_path: Path to CWL workflow file.

    Returns:
        Dict mapping decision_id to list of CWL parameter names it maps to.
    """
    try:
        cwl_params = parse_cwl_inputs(cwl_path)
    except (FileNotFoundError, ValueError):
        return {}

    cwl_param_names = {p.name for p in cwl_params}
    mapping: dict[str, list[str]] = {}

    for decision_id, decision in analysis.decisions.items():
        matched = sorted(_get_possible_params(decision_id, decision) & cwl_param_names)
        if matched:
            mapping[decision_id] = matched

    return mapping


def validate_decision_coverage(
    analysis: Analysis,
    cwl_path: Path,
) -> list[WorkflowValidationError]:
    """Validate all ASP decisions map to CWL parameters.

    Checks that:
    1. Every ASP decision can produce at least one CWL parameter
    2. Every required CWL parameter has a corresponding ASP decision

    Args:
        analysis: The ASP analysis specification.
        cwl_path: Path to CWL workflow file.

    Returns:
        List of validation errors. Empty list means valid.
    """
    try:
        cwl_params = parse_cwl_inputs(cwl_path)
    except FileNotFoundError as e:
        return [WorkflowValidationError("CWL_FILE_NOT_FOUND", str(e))]
    except ValueError as e:
        return [WorkflowValidationError("CWL_PARSE_ERROR", str(e))]

    cwl_param_names = {p.name for p in cwl_params}
    cwl_required = {p.name for p in cwl_params if p.required}

    errors: list[WorkflowValidationError] = []
    covered_params: set[str] = set()

    for decision_id, decision in analysis.decisions.items():
        possible = _get_possible_params(decision_id, decision)
        matched = possible & cwl_param_names

        if matched:
            covered_params.update(matched)
        else:
            errors.append(
                WorkflowValidationError(
                    code="UNMAPPED_DECISION",
                    message=f"Decision '{decision_id}' has no corresponding CWL parameter. "
                    f"Expected one of: {sorted(possible)}",
                    decision_id=decision_id,
                )
            )

    for param_name in sorted(cwl_required - covered_params):
        errors.append(
            WorkflowValidationError(
                code="UNUSED_PARAMETER",
                message=f"Required CWL parameter '{param_name}' has no corresponding ASP decision",
                cwl_param=param_name,
            )
        )

    return errors


def get_unmapped_cwl_params(
    analysis: Analysis,
    cwl_path: Path,
) -> list[CWLParameter]:
    """Get CWL parameters that don't map to any ASP decision.

    Args:
        analysis: The ASP analysis specification.
        cwl_path: Path to CWL workflow file.

    Returns:
        List of CWL parameters with no corresponding ASP decision.
    """
    try:
        cwl_params = parse_cwl_inputs(cwl_path)
    except (FileNotFoundError, ValueError):
        return []

    mapping = get_decision_param_mapping(analysis, cwl_path)
    covered = {param for params in mapping.values() for param in params}
    return [p for p in cwl_params if p.name not in covered]
