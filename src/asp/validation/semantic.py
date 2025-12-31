"""Semantic validation for ASP specifications."""

from __future__ import annotations

from pathlib import Path

from asp.models.analysis import Analysis
from asp.models.universe import Universe


class SemanticError:
    """A semantic validation error."""

    def __init__(self, code: str, message: str, path: str | None = None):
        self.code = code
        self.message = message
        self.path = path

    def __str__(self) -> str:
        if self.path:
            return f"[{self.code}] {self.path}: {self.message}"
        return f"[{self.code}] {self.message}"


def validate_analysis(analysis: Analysis) -> list[SemanticError]:
    """Validate an analysis specification semantically.

    Checks:
    - Default options exist in their decision's options
    - Evidence refs point to valid inputs
    - Constraint refs (requires, incompatible_with) point to valid decision.option pairs
    - Input/output IDs are unique

    Args:
        analysis: The analysis to validate.

    Returns:
        List of semantic errors (empty if valid).
    """
    errors: list[SemanticError] = []

    # Check for duplicate input IDs
    input_ids: set[str] = set()
    for inp in analysis.analysis.inputs:
        if inp.id in input_ids:
            errors.append(
                SemanticError(
                    "DUPLICATE_INPUT", f"Duplicate input ID: {inp.id}", f"inputs.{inp.id}"
                )
            )
        input_ids.add(inp.id)

    # Check for duplicate output IDs
    output_ids: set[str] = set()
    for out in analysis.analysis.outputs:
        if out.id in output_ids:
            errors.append(
                SemanticError(
                    "DUPLICATE_OUTPUT", f"Duplicate output ID: {out.id}", f"outputs.{out.id}"
                )
            )
        output_ids.add(out.id)

    # Validate decisions
    for decision_id, decision in analysis.decisions.items():
        decision_path = f"decisions.{decision_id}"

        # Check default option exists
        if decision.default is not None and decision.default not in decision.options:
            errors.append(
                SemanticError(
                    "INVALID_DEFAULT",
                    f"Default option '{decision.default}' not found in options",
                    decision_path,
                )
            )

        # Validate options
        for option_id, option in decision.options.items():
            option_path = f"{decision_path}.options.{option_id}"

            # Check evidence refs
            if option.evidence:
                for i, evidence in enumerate(option.evidence):
                    # Check insight reference
                    if evidence.insight:
                        if evidence.insight not in analysis.insights:
                            errors.append(
                                SemanticError(
                                    "INVALID_INSIGHT_REF",
                                    f"Evidence insight '{evidence.insight}' not found in insights",
                                    f"{option_path}.evidence[{i}]",
                                )
                            )
                    # Check legacy input reference
                    elif evidence.ref:
                        ref = evidence.ref
                        if ref.startswith("inputs."):
                            input_id = ref[7:]  # Remove "inputs." prefix
                            if input_id not in input_ids:
                                errors.append(
                                    SemanticError(
                                        "INVALID_EVIDENCE_REF",
                                        f"Evidence ref '{ref}' points to non-existent input",
                                        f"{option_path}.evidence[{i}]",
                                    )
                                )

            # Check incompatible_with refs
            if option.incompatible_with:
                for ref in option.incompatible_with:
                    errors.extend(_validate_constraint_ref(ref, analysis, option_path))

            # Check requires refs
            if option.requires:
                for ref in option.requires:
                    errors.extend(_validate_constraint_ref(ref, analysis, option_path))

    return errors


def _validate_constraint_ref(ref: str, analysis: Analysis, option_path: str) -> list[SemanticError]:
    """Validate a constraint reference (decision.option format)."""
    errors: list[SemanticError] = []

    parts = ref.split(".")
    if len(parts) != 2:
        errors.append(
            SemanticError(
                "INVALID_CONSTRAINT_FORMAT",
                f"Constraint '{ref}' should be in 'decision.option' format",
                option_path,
            )
        )
        return errors

    decision_id, option_id = parts

    if decision_id not in analysis.decisions:
        errors.append(
            SemanticError(
                "INVALID_CONSTRAINT_REF",
                f"Constraint ref '{ref}' points to non-existent decision '{decision_id}'",
                option_path,
            )
        )
    elif option_id not in analysis.decisions[decision_id].options:
        errors.append(
            SemanticError(
                "INVALID_CONSTRAINT_REF",
                f"Constraint ref '{ref}' points to non-existent option '{option_id}'",
                option_path,
            )
        )

    return errors


def validate_universe(universe: Universe, analysis: Analysis) -> list[SemanticError]:
    """Validate a universe against an analysis specification.

    Checks:
    - All decisions in the analysis have a selection in the universe
    - All selections point to valid options
    - No constraint violations (requires, incompatible_with)

    Args:
        universe: The universe to validate.
        analysis: The analysis specification.

    Returns:
        List of semantic errors (empty if valid).
    """
    errors: list[SemanticError] = []

    # Check all decisions are covered
    for decision_id in analysis.decisions:
        if decision_id not in universe.decisions:
            errors.append(
                SemanticError(
                    "MISSING_DECISION",
                    f"Universe missing decision: {decision_id}",
                    f"decisions.{decision_id}",
                )
            )

    # Check all selections are valid
    for decision_id, option_id in universe.decisions.items():
        if decision_id not in analysis.decisions:
            errors.append(
                SemanticError(
                    "UNKNOWN_DECISION",
                    f"Universe references unknown decision: {decision_id}",
                    f"decisions.{decision_id}",
                )
            )
            continue

        decision = analysis.decisions[decision_id]
        if option_id not in decision.options:
            errors.append(
                SemanticError(
                    "UNKNOWN_OPTION",
                    f"Universe selects unknown option '{option_id}' for decision '{decision_id}'",
                    f"decisions.{decision_id}",
                )
            )

    # Check constraints
    errors.extend(_validate_universe_constraints(universe, analysis))

    return errors


def _validate_universe_constraints(universe: Universe, analysis: Analysis) -> list[SemanticError]:
    """Validate that the universe respects all constraints."""
    errors: list[SemanticError] = []

    for decision_id, option_id in universe.decisions.items():
        if decision_id not in analysis.decisions:
            continue

        decision = analysis.decisions[decision_id]
        if option_id not in decision.options:
            continue

        option = decision.options[option_id]

        # Check incompatible_with
        if option.incompatible_with:
            for ref in option.incompatible_with:
                parts = ref.split(".")
                if len(parts) == 2:
                    other_decision_id, other_option_id = parts
                    if universe.decisions.get(other_decision_id) == other_option_id:
                        errors.append(
                            SemanticError(
                                "INCOMPATIBLE_OPTIONS",
                                f"Option '{decision_id}.{option_id}' is incompatible with "
                                f"'{other_decision_id}.{other_option_id}'",
                                f"decisions.{decision_id}",
                            )
                        )

        # Check requires
        if option.requires:
            for ref in option.requires:
                parts = ref.split(".")
                if len(parts) == 2:
                    other_decision_id, other_option_id = parts
                    if universe.decisions.get(other_decision_id) != other_option_id:
                        actual = universe.decisions.get(other_decision_id, "(not set)")
                        errors.append(
                            SemanticError(
                                "MISSING_REQUIRED_OPTION",
                                f"Option '{decision_id}.{option_id}' requires "
                                f"'{other_decision_id}.{other_option_id}' but got '{actual}'",
                                f"decisions.{decision_id}",
                            )
                        )

    return errors


def validate_analysis_file(path: str | Path) -> list[SemanticError]:
    """Load and validate an analysis file."""
    analysis = Analysis.from_yaml(path)
    return validate_analysis(analysis)


def validate_universe_file(
    universe_path: str | Path,
    analysis_path: str | Path,
) -> list[SemanticError]:
    """Load and validate a universe file against an analysis."""
    analysis = Analysis.from_yaml(analysis_path)
    universe = Universe.from_yaml(universe_path)
    return validate_universe(universe, analysis)
