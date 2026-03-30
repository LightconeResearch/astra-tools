"""Semantic validation for ASTRA RO-Crate specifications.

Validates cross-references, constraints, and logical consistency
of ASTRA crates.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from astra.crate import ASTRACrate

if TYPE_CHECKING:
    from rocrate.model.contextentity import ContextEntity

import re

from astra.vocabulary import (
    ID_PATTERN,
    INPUT_TYPES,
    OUTPUT_TYPES,
    PROP_ACTIVE_WHEN,
    PROP_CONDITION,
    PROP_DEFAULT_OPTION,
    PROP_DELEGATES_TO,
    PROP_EXCLUDED_REASON,
    PROP_HAS_EVIDENCE,
    PROP_HAS_OPTION,
    PROP_INCOMPATIBLE_WITH,
    PROP_INPUT_TYPE,
    PROP_IS_EXCLUDED,
    PROP_OUTPUT_TYPE,
    PROP_REQUIRES_OPTION,
    PROP_SUPPORTS_INSIGHT,
    SCHEMA_ALTERNATE_NAME,
    SCHEMA_IDENTIFIER,
    SCHEMA_IS_BASED_ON,
    SCHEMA_OBJECT,
    WHEN_PATTERN,
    as_list,
    id_of,
    parse_entity_name,
)


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

    def __repr__(self) -> str:
        return f"SemanticError({self.code!r}, {self.message!r}, path={self.path!r})"


def validate_analysis(crate: ASTRACrate, path: str = "") -> list[SemanticError]:
    """Validate an ASTRA crate semantically.

    Checks cross-references, constraints, uniqueness, and logical consistency.
    Recursively validates subcrates.
    """
    errors: list[SemanticError] = []
    prefix = f"{path}/" if path else ""

    # Fetch entities once so check functions don't re-resolve references
    inputs = crate.get_inputs()
    outputs = crate.get_outputs()
    decisions = crate.get_decisions()

    _check_unique_ids(inputs, outputs, errors, prefix)
    _check_decisions(crate, decisions, errors, prefix)
    _check_outputs(outputs, errors, prefix)
    _check_inputs(inputs, errors, prefix)
    _check_recipes(crate, outputs, errors, prefix)
    _check_insights(crate, outputs, errors, prefix)
    _check_success_criteria(crate, outputs, errors, prefix)

    # --- Recurse into subcrates ---
    for sub_name, sub_crate in crate.subcrates.items():
        sub_path = f"{prefix}{sub_name}"
        errors.extend(validate_analysis(sub_crate, sub_path))

    return errors


def validate_analysis_file(crate_dir: str | Path) -> list[SemanticError]:
    """Load a crate from a directory and validate it."""
    crate = ASTRACrate.load(crate_dir)
    return validate_analysis(crate)


def validate_universe(universe_name: str, crate: ASTRACrate) -> list[SemanticError]:
    """Validate a universe against the analysis crate.

    Checks:
    - Every non-delegated decision has a selection
    - All selections reference valid options
    - Constraint violations (incompatible_with, requires)
    - Excluded options not selected
    """
    errors: list[SemanticError] = []
    universe = crate.get_universe(universe_name)
    if not universe:
        errors.append(
            SemanticError(
                "UNIVERSE_NOT_FOUND",
                f"Universe '{universe_name}' not found",
            )
        )
        return errors

    selections = crate.get_universe_selections(universe_name)
    sel_map: dict[str, str] = dict(selections)

    # Collect all non-delegated decisions across the tree
    all_decisions = _collect_all_decisions(crate)

    # Check completeness: every non-delegated decision needs a selection
    for dec_id in all_decisions:
        if dec_id not in sel_map:
            errors.append(
                SemanticError(
                    "MISSING_DECISION",
                    f"Universe '{universe_name}' missing selection for decision '{dec_id}'",
                    path=f"universe/{universe_name}",
                )
            )

    # Check each selection
    for dec_id, opt_id in sel_map.items():
        # Validate option exists
        entity = crate.crate.dereference(opt_id)
        if not entity and "/" in opt_id:
            # Cross-crate reference — skip for now (would need subcrate loading)
            pass
        elif not entity:
            errors.append(
                SemanticError(
                    "INVALID_OPTION",
                    f"Universe '{universe_name}' selects non-existent option '{opt_id}'",
                    path=f"universe/{universe_name}",
                )
            )
            continue

        # Check excluded
        if entity and entity.get(PROP_IS_EXCLUDED):
            errors.append(
                SemanticError(
                    "EXCLUDED_OPTION",
                    f"Universe '{universe_name}' selects excluded option '{opt_id}'",
                    path=f"universe/{universe_name}",
                )
            )

    # Check constraints
    _check_universe_constraints(universe_name, sel_map, crate, errors)

    return errors


def validate_universe_file(universe_name: str, crate_dir: str | Path) -> list[SemanticError]:
    """Load a crate and validate a universe."""
    crate = ASTRACrate.load(crate_dir)
    return validate_universe(universe_name, crate)


# ---------------------------------------------------------------------------
# Internal validation helpers
# ---------------------------------------------------------------------------


_ID_RE = re.compile(ID_PATTERN)
_WHEN_RE = re.compile(WHEN_PATTERN)


def _check_unique_ids(
    inputs: list[ContextEntity],
    outputs: list[ContextEntity],
    errors: list[SemanticError],
    prefix: str,
) -> None:
    """Check that input and output IDs are unique and well-formed."""
    seen: set[str] = set()
    for inp in inputs:
        name = parse_entity_name(inp.id)
        if not _ID_RE.match(name):
            errors.append(
                SemanticError("INVALID_ID", f"Invalid input ID: '{name}'", path=f"{prefix}inputs")
            )
        if name in seen:
            errors.append(
                SemanticError(
                    "DUPLICATE_INPUT", f"Duplicate input ID: '{name}'", path=f"{prefix}inputs"
                )
            )
        seen.add(name)

    seen = set()
    for out in outputs:
        name = parse_entity_name(out.id)
        if not _ID_RE.match(name):
            errors.append(
                SemanticError("INVALID_ID", f"Invalid output ID: '{name}'", path=f"{prefix}outputs")
            )
        if name in seen:
            errors.append(
                SemanticError(
                    "DUPLICATE_OUTPUT", f"Duplicate output ID: '{name}'", path=f"{prefix}outputs"
                )
            )
        seen.add(name)


def _check_decisions(
    crate: ASTRACrate,
    decisions: list[ContextEntity],
    errors: list[SemanticError],
    prefix: str,
) -> None:
    """Validate decisions and their options."""
    for dec in decisions:
        dec_name = parse_entity_name(dec.id)
        dec_path = f"{prefix}decisions/{dec_name}"

        # Delegated decisions must not have label/options/default
        if dec.get(PROP_DELEGATES_TO):
            has_local = (
                dec.get(SCHEMA_ALTERNATE_NAME)
                or dec.get(PROP_HAS_OPTION)
                or dec.get(PROP_DEFAULT_OPTION)
            )
            if has_local:
                errors.append(
                    SemanticError(
                        "DELEGATED_WITH_LOCAL_FIELDS",
                        "Delegated decision must not have label, options, or default",
                        path=dec_path,
                    )
                )
            continue

        # Check activeWhen format
        when = dec.get(PROP_ACTIVE_WHEN)
        if when:
            for cond in as_list(when):
                if not _WHEN_RE.match(cond):
                    errors.append(
                        SemanticError(
                            "INVALID_WHEN_FORMAT",
                            f"Invalid activeWhen condition: '{cond}'",
                            path=dec_path,
                        )
                    )

        # Check default exists in options
        default_ref = dec.get(PROP_DEFAULT_OPTION)
        if default_ref:
            opt_refs = as_list(dec.get(PROP_HAS_OPTION))
            opt_ids = {id_of(r) for r in opt_refs}
            if id_of(default_ref) not in opt_ids:
                errors.append(
                    SemanticError(
                        "INVALID_DEFAULT",
                        f"Default option '{id_of(default_ref)}' not in options",
                        path=dec_path,
                    )
                )

            # Check default is not excluded
            default_entity = crate.crate.dereference(id_of(default_ref))
            if default_entity and default_entity.get(PROP_IS_EXCLUDED):
                errors.append(
                    SemanticError(
                        "EXCLUDED_DEFAULT",
                        "Default option is excluded",
                        path=dec_path,
                    )
                )

        for opt in crate.get_options(dec_name):
            opt_name = parse_entity_name(opt.id)
            opt_path = f"{dec_path}/options/{opt_name}"

            # Excluded requires reason
            if opt.get(PROP_IS_EXCLUDED) and not opt.get(PROP_EXCLUDED_REASON):
                errors.append(
                    SemanticError(
                        "EXCLUDED_NO_REASON",
                        "Excluded option missing excluded_reason",
                        path=opt_path,
                    )
                )

            # excluded_reason without excluded
            if opt.get(PROP_EXCLUDED_REASON) and not opt.get(PROP_IS_EXCLUDED):
                errors.append(
                    SemanticError(
                        "ORPHAN_EXCLUDED_REASON",
                        "excluded_reason set but isExcluded is not true",
                        path=opt_path,
                    )
                )

            # Validate constraint references
            for constraint_ref in as_list(opt.get(PROP_INCOMPATIBLE_WITH)):
                ref_id = id_of(constraint_ref)
                if not crate.crate.dereference(ref_id):
                    errors.append(
                        SemanticError(
                            "INVALID_CONSTRAINT_REF",
                            f"incompatibleWith references non-existent option '{ref_id}'",
                            path=opt_path,
                        )
                    )

            for constraint_ref in as_list(opt.get(PROP_REQUIRES_OPTION)):
                ref_id = id_of(constraint_ref)
                if not crate.crate.dereference(ref_id):
                    errors.append(
                        SemanticError(
                            "INVALID_CONSTRAINT_REF",
                            f"requiresOption references non-existent option '{ref_id}'",
                            path=opt_path,
                        )
                    )

            # Validate insight references
            for insight_ref in as_list(opt.get(PROP_SUPPORTS_INSIGHT)):
                ref_id = id_of(insight_ref)
                if not crate.crate.dereference(ref_id):
                    errors.append(
                        SemanticError(
                            "INVALID_INSIGHT_REF",
                            f"supportsInsight references non-existent insight '{ref_id}'",
                            path=opt_path,
                        )
                    )


def _check_outputs(
    outputs: list[ContextEntity],
    errors: list[SemanticError],
    prefix: str,
) -> None:
    """Validate output properties."""
    for out in outputs:
        out_name = parse_entity_name(out.id)
        out_path = f"{prefix}outputs/{out_name}"

        # Validate output type
        otype = out.get(PROP_OUTPUT_TYPE)
        if otype and otype not in OUTPUT_TYPES:
            errors.append(
                SemanticError(
                    "INVALID_OUTPUT_TYPE",
                    f"Invalid output type: '{otype}'",
                    path=out_path,
                )
            )


def _check_inputs(
    inputs: list[ContextEntity],
    errors: list[SemanticError],
    prefix: str,
) -> None:
    """Validate input properties."""
    for inp in inputs:
        inp_name = parse_entity_name(inp.id)
        inp_path = f"{prefix}inputs/{inp_name}"

        itype = inp.get(PROP_INPUT_TYPE)
        if itype and itype not in INPUT_TYPES:
            errors.append(
                SemanticError(
                    "INVALID_INPUT_TYPE",
                    f"Invalid input type: '{itype}'",
                    path=inp_path,
                )
            )


def _check_recipes(
    crate: ASTRACrate,
    outputs: list[ContextEntity],
    errors: list[SemanticError],
    prefix: str,
) -> None:
    """Validate recipe dependencies and check for cycles."""
    deps = crate.get_output_dependencies(outputs)
    output_names = {parse_entity_name(o.id) for o in outputs}

    for out_name, dep_names in deps.items():
        for dep in dep_names:
            if dep not in output_names:
                errors.append(
                    SemanticError(
                        "INVALID_RECIPE_INPUT",
                        f"Recipe for '{out_name}' references non-existent output '{dep}'",
                        path=f"{prefix}outputs/{out_name}/recipe",
                    )
                )

    # Cycle detection
    visited: set[str] = set()
    rec_stack: set[str] = set()

    def has_cycle(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)
        for neighbor in deps.get(node, []):
            if neighbor not in visited:
                if has_cycle(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True
        rec_stack.discard(node)
        return False

    for node in deps:
        if node not in visited:
            if has_cycle(node):
                errors.append(
                    SemanticError(
                        "RECIPE_CYCLE",
                        "Cycle detected in recipe dependency graph",
                        path=f"{prefix}recipes",
                    )
                )
                break


def _check_insights(
    crate: ASTRACrate,
    outputs: list[ContextEntity],
    errors: list[SemanticError],
    prefix: str,
) -> None:
    """Validate insight evidence references and constraints."""
    output_ids = {o.id for o in outputs}

    for insight in crate.get_prior_insights() + crate.get_findings():
        insight_name = parse_entity_name(insight.id)
        insight_path = f"{prefix}insights/{insight_name}"
        ev_refs = as_list(insight.get(PROP_HAS_EVIDENCE))

        # Insight must have at least one evidence item
        if not ev_refs:
            errors.append(
                SemanticError(
                    "MISSING_EVIDENCE",
                    "Insight must have at least one evidence",
                    path=insight_path,
                )
            )

        for ev_ref in ev_refs:
            ev = crate.crate.dereference(id_of(ev_ref))
            if not ev:
                continue

            has_doi = bool(ev.get(SCHEMA_IDENTIFIER))
            has_artifact = bool(ev.get(SCHEMA_IS_BASED_ON))
            ev_name = parse_entity_name(ev.id)
            ev_path = f"{insight_path}/evidence/{ev_name}"

            # Exactly one of doi or artifact
            if has_doi == has_artifact:
                errors.append(
                    SemanticError(
                        "EVIDENCE_SOURCE",
                        "Evidence must have exactly one of 'identifier' (DOI) "
                        "or 'isBasedOn' (artifact)",
                        path=ev_path,
                    )
                )

            # Literature evidence requires at least one content selector
            if has_doi and not (ev.get("quote") or ev.get("figure") or ev.get("table")):
                errors.append(
                    SemanticError(
                        "MISSING_SELECTOR",
                        "Literature evidence must have at least one content "
                        "selector (quote, figure, or table)",
                        path=ev_path,
                    )
                )

            # Artifact refs must point to valid outputs
            if has_artifact:
                ref_id = id_of(ev.get(SCHEMA_IS_BASED_ON))
                if ref_id not in output_ids:
                    errors.append(
                        SemanticError(
                            "INVALID_ARTIFACT_REF",
                            f"Evidence artifact references non-existent output '{ref_id}'",
                            path=ev_path,
                        )
                    )


def _check_success_criteria(
    crate: ASTRACrate,
    outputs: list[ContextEntity],
    errors: list[SemanticError],
    prefix: str,
) -> None:
    """Validate success criteria."""
    output_ids = {parse_entity_name(o.id) for o in outputs}

    for criterion in crate.get_success_criteria():
        c_path = f"{prefix}criteria/{criterion.id}"

        # condition requires output
        if criterion.get(PROP_CONDITION) and not criterion.get(SCHEMA_OBJECT):
            errors.append(
                SemanticError(
                    "CONDITION_WITHOUT_OUTPUT",
                    "Success criterion with 'condition' must also specify an 'output'",
                    path=c_path,
                )
            )

        # output must reference a valid output
        output_ref = criterion.get(SCHEMA_OBJECT)
        if output_ref:
            ref_name = parse_entity_name(id_of(output_ref))
            if ref_name not in output_ids:
                errors.append(
                    SemanticError(
                        "INVALID_CRITERION_OUTPUT",
                        f"Success criterion references non-existent output '{ref_name}'",
                        path=c_path,
                    )
                )


def _collect_all_decisions(crate: ASTRACrate) -> set[str]:
    """Collect all non-delegated decision @ids across the tree."""
    return {dec_id for dec_id, _dec in crate.walk_local_decisions()}


def _check_universe_constraints(
    universe_name: str,
    sel_map: dict[str, str],
    crate: ASTRACrate,
    errors: list[SemanticError],
) -> None:
    """Check incompatible_with and requires constraints in a universe."""
    selected_options: set[str] = set(sel_map.values())

    for dec_id, opt_id in sel_map.items():
        opt_entity = crate.crate.dereference(opt_id)
        if not opt_entity:
            continue

        # incompatible_with
        for incompat_ref in as_list(opt_entity.get(PROP_INCOMPATIBLE_WITH)):
            incompat_id = id_of(incompat_ref)
            if incompat_id in selected_options:
                errors.append(
                    SemanticError(
                        "INCOMPATIBLE_OPTIONS",
                        f"Option '{opt_id}' is incompatible with '{incompat_id}', "
                        f"but both selected in universe '{universe_name}'",
                        path=f"universe/{universe_name}",
                    )
                )

        # requires
        for req_ref in as_list(opt_entity.get(PROP_REQUIRES_OPTION)):
            req_id = id_of(req_ref)
            if req_id not in selected_options:
                errors.append(
                    SemanticError(
                        "MISSING_REQUIRED_OPTION",
                        f"Option '{opt_id}' requires '{req_id}', "
                        f"but it is not selected in universe '{universe_name}'",
                        path=f"universe/{universe_name}",
                    )
                )
