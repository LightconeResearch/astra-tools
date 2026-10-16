"""Tests for validation modules."""

from pathlib import Path

import pytest

from astra.helpers import load_yaml
from astra.validation.schema import (
    collect_recommendations,
    is_valid_analysis,
    validate_analysis_schema,
)
from astra.validation.semantic import (
    SemanticError,
    collect_semantic_warnings,
    validate_analysis,
    validate_analysis_file,
    validate_universe,
)


class TestSchemaValidation:
    """Tests for JSON schema validation."""

    def test_valid_minimal_analysis(self, minimal_analysis_path: Path):
        errors = validate_analysis_schema(minimal_analysis_path)
        assert errors == []
        assert is_valid_analysis(minimal_analysis_path)

    def test_valid_full_analysis(self, full_analysis_path: Path):
        """``full.yaml`` declares its universes, one derived from the other."""
        errors = validate_analysis_schema(full_analysis_path)
        assert errors == []

    def test_missing_version(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "missing_version.yaml")
        assert any(e.code == "MISSING_ROOT_FIELD" and "version" in e.message for e in errors)

    def test_invalid_input_type(self, invalid_dir: Path):
        errors = validate_analysis_schema(invalid_dir / "invalid_input_type.yaml")
        assert len(errors) > 0

    def test_invalid_output_type(self, invalid_dir: Path):
        errors = validate_analysis_schema(invalid_dir / "invalid_output_type.yaml")
        assert len(errors) > 0


class TestRecommendations:
    """`Output.format` is recommended, not required, until ASTRA 0.1.0.

    The point of these is the *severity*: an analysis without `format` must
    stay valid. Only the advisory channel is allowed to notice.
    """

    def _analysis(self, outputs: list[dict]) -> dict:
        return {"version": "1.0", "name": "Recommendations", "outputs": outputs}

    def test_an_output_without_a_format_is_reported(self):
        data = self._analysis([{"id": "result", "type": "metric"}])
        messages = collect_recommendations(data)
        assert len(messages) == 1
        assert "result" in messages[0] and "format" in messages[0]

    def test_an_output_with_a_format_is_not(self):
        data = self._analysis([{"id": "result", "type": "metric", "format": "json"}])
        assert collect_recommendations(data) == []

    def test_a_re_export_is_never_reported(self):
        """An alias inherits `format` and is forbidden from declaring one,
        so asking it for a format would be asking for a schema violation."""
        data = self._analysis([{"id": "result", "from": "child.result"}])
        assert collect_recommendations(data) == []

    def test_a_nested_output_is_named_by_its_qualified_id(self):
        data = self._analysis([])
        data["analyses"] = {
            "child": {"outputs": [{"id": "result", "type": "metric"}]},
        }
        messages = collect_recommendations(data)
        assert len(messages) == 1
        assert "child.result" in messages[0]

    def test_every_offender_is_named_in_one_message(self):
        data = self._analysis(
            [
                {"id": "a", "type": "metric"},
                {"id": "b", "type": "figure", "format": "png"},
                {"id": "c", "type": "table"},
            ]
        )
        messages = collect_recommendations(data)
        assert len(messages) == 1
        assert "a" in messages[0] and "c" in messages[0]
        assert "2 outputs" in messages[0]

    def test_the_deadline_is_read_off_the_installed_spec(self):
        """Not restated in this repo: astra-spec carries `required_in` on the
        generated model, so a spec that moves the date moves the warning."""
        from astra.datamodel.astra_pydantic import Output

        meta = Output.model_fields["format"].json_schema_extra["linkml_meta"]
        declared = meta["annotations"]["required_in"]["value"]
        messages = collect_recommendations(self._analysis([{"id": "result", "type": "metric"}]))
        assert declared in messages[0]

    def test_a_field_without_the_annotation_falls_back(self):
        """`description` carries no `required_in`, so the pinned constant stands
        in rather than the message going blank."""
        from astra.validation.schema import _RECOMMENDED_UNTIL, _required_in

        assert _required_in("description") == _RECOMMENDED_UNTIL

    def test_a_missing_format_does_not_make_the_analysis_invalid(self, tmp_path: Path):
        """The whole contract of `recommended`: advisory, never fatal."""
        from astra.validation.schema import validate_analysis_data

        data = self._analysis([{"id": "result", "type": "metric"}])
        assert validate_analysis_data(data) == []
        assert collect_recommendations(data)


class TestSemanticValidation:
    """Tests for semantic validation."""

    def test_valid_analysis(self, full_analysis_path: Path):
        data = load_yaml(full_analysis_path)
        errors = validate_analysis(data)
        assert errors == []

    def test_valid_analysis_file(self, full_analysis_path: Path):
        errors = validate_analysis_file(full_analysis_path)
        assert errors == []

    def test_duplicate_input_ids(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "duplicate_input_ids.yaml")
        assert any(e.code == "DUPLICATE_INPUT" for e in errors)

    def test_duplicate_output_ids(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "duplicate_output_ids.yaml")
        assert any(e.code == "DUPLICATE_OUTPUT" for e in errors)

    def test_invalid_insight_ref(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "invalid_insight_ref.yaml")
        assert any(e.code == "INVALID_INSIGHT_REF" for e in errors)

    def test_option_insights_resolve_in_local_and_ancestor_scope(self, valid_dir: Path):
        """`Option.insights` resolves bare ids against the node-local
        ``prior_insights`` map, and ``../id`` / ``../../id`` against the
        corresponding ancestor scope. Mirrors the ``../`` convention used
        by ``Input.from`` and ``Decision.from``.
        """
        errors = validate_analysis_file(valid_dir / "sub_scope_insight_ref.yaml")
        insight_errors = [e for e in errors if e.code == "INVALID_INSIGHT_REF"]
        assert insight_errors == [], (
            "Same-scope (bare id) and explicit `../`-form ancestor refs "
            f"should both resolve; got: {insight_errors}"
        )

    def test_insight_ref_bare_id_does_not_walk_ancestors(self, invalid_dir: Path):
        """A bare-id ``Option.insights`` ref in a sub-analysis must NOT
        silently resolve against the root's ``prior_insights``. Cross-scope
        refs require explicit ``../id``.
        """
        errors = validate_analysis_file(invalid_dir / "insight_ref_bare_id_crosses_scope.yaml")
        bad = [e for e in errors if e.code == "INVALID_INSIGHT_REF"]
        assert len(bad) == 1, f"expected 1 INVALID_INSIGHT_REF, got: {bad}"
        assert "root_insight" in bad[0].message

    def test_insight_ref_escapes_too_far(self, invalid_dir: Path):
        """A ``../id`` ref at root has no ancestor scope to resolve against."""
        errors = validate_analysis_file(invalid_dir / "insight_ref_escapes_too_far.yaml")
        bad = [e for e in errors if e.code == "INVALID_INSIGHT_REF"]
        assert len(bad) == 1, f"expected 1 INVALID_INSIGHT_REF, got: {bad}"
        assert "escapes" in bad[0].message

    def test_invalid_finding_output(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "invalid_finding_output.yaml")
        assert any(e.code == "INVALID_ARTIFACT_REF" for e in errors)

    def test_invalid_constraint_ref(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "invalid_constraint_ref.yaml")
        assert any(e.code == "INVALID_CONSTRAINT_REF" for e in errors)

    def test_path_field_conflict(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "path_field_conflict.yaml")
        conflicts = [e for e in errors if e.code == "PATH_FIELD_CONFLICT"]
        assert len(conflicts) == 1
        assert "preprocessing" in conflicts[0].message
        assert "name" in conflicts[0].message
        assert "description" in conflicts[0].message


class TestUniverseValidation:
    """Tests for validating the universes an analysis declares."""

    def test_valid_universes(self, full_analysis_path: Path):
        """``baseline`` in full, and ``svm-config`` derived from it - SVM
        requires standard preprocessing, which it inherits."""
        errors = validate_analysis_file(full_analysis_path)
        assert errors == []

    def test_missing_decision(
        self, full_analysis_path: Path, invalid_dir: Path, with_universe_entry
    ):
        data = with_universe_entry(
            full_analysis_path, invalid_dir / "universe_entry_missing_decision.yaml"
        )
        errors = validate_analysis(data)
        assert any(
            e.code == "MISSING_DECISION" and e.path == "universes.incomplete.decisions.model"
            for e in errors
        )

    def test_invalid_option(self, full_analysis_path: Path, invalid_dir: Path, with_universe_entry):
        data = with_universe_entry(
            full_analysis_path, invalid_dir / "universe_entry_invalid_option.yaml"
        )
        errors = validate_analysis(data)
        assert any(e.code == "UNKNOWN_OPTION" for e in errors)

    def test_incompatible_options(
        self, full_analysis_path: Path, invalid_dir: Path, with_universe_entry
    ):
        data = with_universe_entry(
            full_analysis_path, invalid_dir / "universe_entry_incompatible.yaml"
        )
        errors = validate_analysis(data)
        assert any(e.code == "INCOMPATIBLE_OPTIONS" for e in errors)

    def test_missing_required_option(
        self, full_analysis_path: Path, invalid_dir: Path, with_universe_entry
    ):
        data = with_universe_entry(
            full_analysis_path, invalid_dir / "universe_entry_missing_required.yaml"
        )
        errors = validate_analysis(data)
        assert any(e.code == "MISSING_REQUIRED_OPTION" for e in errors)


class TestNestedAnalysisValidation:
    """Tests for nested analysis semantic validation."""

    def test_valid_nested_analysis(self, valid_dir: Path):
        """Including its universe, which selects inside each sub-analysis."""
        errors = validate_analysis_file(valid_dir / "nested.yaml")
        assert errors == []

    def test_missing_analysis_decision_in_universe(
        self, valid_dir: Path, invalid_dir: Path, with_universe_entry
    ):
        data = with_universe_entry(
            valid_dir / "nested.yaml", invalid_dir / "universe_entry_missing_analysis_decision.yaml"
        )
        errors = validate_analysis(data)
        assert any(e.code == "MISSING_DECISION" for e in errors)


class TestSubAnalysisRequirements:
    """Tests for sub-analysis required fields and decision from: references."""

    def test_sub_missing_outputs(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "sub_missing_outputs.yaml")
        assert any(e.code == "MISSING_SUB_FIELD" and "outputs" in e.message for e in errors)

    def test_invalid_decision_from(self, invalid_dir: Path):
        """Decision with from: referencing non-existent parent decision."""
        errors = validate_analysis_file(invalid_dir / "invalid_parent_decision.yaml")
        assert any(e.code == "INVALID_DECISION_FROM" for e in errors)

    def test_cross_level_constraint_in_analysis(self, valid_dir: Path):
        """Decision from: allows constraints referencing parent decisions."""
        errors = validate_analysis_file(valid_dir / "nested.yaml")
        assert errors == []

    def test_cross_level_incompatible_universe(
        self, valid_dir: Path, invalid_dir: Path, with_universe_entry
    ):
        """Universe violates cross-level incompatible_with constraint."""
        data = with_universe_entry(
            valid_dir / "nested.yaml", invalid_dir / "universe_entry_cross_level_incompatible.yaml"
        )
        errors = validate_analysis(data)
        assert any(e.code == "INCOMPATIBLE_OPTIONS" for e in errors)


class TestFromPathGrammar:
    """Tests for the unified `from:` path grammar across Input/Output/Decision."""

    def test_valid_multilevel_from(self, valid_dir: Path):
        """Multi-level `../../id` and `child.sub.id` should resolve correctly."""
        errors = validate_analysis_file(valid_dir / "multilevel_from.yaml")
        assert errors == []

    def test_input_from_downward_rejected(self, invalid_dir: Path):
        """Input.from must escape upward — bare `child.out` form is rejected."""
        errors = validate_analysis_file(invalid_dir / "input_from_downward.yaml")
        # Pydantic rejects this at schema level; semantic just needs to not crash.
        # The schema-level error surfaces via the schema validator, not semantic.
        # We check semantic doesn't accept it — but since the YAML may not even
        # parse through pydantic, we instead check semantic flags it too.
        codes = [e.code for e in errors]
        assert "INVALID_FROM" in codes or "INVALID_OUTPUT_FROM" in codes

    def test_output_from_upward_rejected(self, invalid_dir: Path):
        """Output.from must descend; upward references rejected."""
        errors = validate_analysis_file(invalid_dir / "output_from_upward.yaml")
        codes = [e.code for e in errors]
        assert "INVALID_OUTPUT_FROM" in codes

    def test_output_from_unknown_child(self, invalid_dir: Path):
        """Output.from points at a sub-analysis that doesn't exist."""
        errors = validate_analysis_file(invalid_dir / "output_from_unknown_child.yaml")
        codes = [e.code for e in errors]
        assert "INVALID_OUTPUT_FROM" in codes


class TestOutputDependencyValidation:
    """Tests for Output.inputs/decisions and dependency-graph validation."""

    def test_output_input_must_reference_declared_id(self):
        """Output.inputs must reference an analysis input or sibling output."""
        data = {
            "version": "0.0.10",
            "name": "test",
            "inputs": [],
            "outputs": [
                {
                    "id": "result",
                    "type": "metric",
                    "inputs": ["nonexistent"],
                },
            ],
        }
        errors = validate_analysis(data)
        codes = [e.code for e in errors]
        assert "INVALID_OUTPUT_INPUT" in codes

    def test_output_dependency_cycle(self):
        """Cycle in output dependencies should be caught."""
        data = {
            "version": "0.0.10",
            "name": "test",
            "inputs": [],
            "outputs": [
                {"id": "a", "type": "data", "inputs": ["b"]},
                {"id": "b", "type": "data", "inputs": ["a"]},
            ],
        }
        errors = validate_analysis(data)
        codes = [e.code for e in errors]
        assert "OUTPUT_CYCLE" in codes

    def test_valid_output_chain(self):
        """Output that references a sibling output should pass validation."""
        data = {
            "version": "0.0.10",
            "name": "test",
            "inputs": [],
            "outputs": [
                {
                    "id": "cleaned",
                    "type": "data",
                    "format": "parquet",
                    "recipe": {"command": "python clean.py"},
                },
                {
                    "id": "result",
                    "type": "metric",
                    "format": "json",
                    "inputs": ["cleaned"],
                    "recipe": {"command": "python analyze.py {inputs.cleaned}"},
                },
            ],
        }
        errors = validate_analysis(data)
        assert errors == []

    def test_output_input_can_reference_analysis_input(self):
        """Output.inputs can resolve to an analysis-level Input."""
        data = {
            "version": "0.0.10",
            "name": "test",
            "inputs": [{"id": "raw", "type": "data", "source": "x.csv"}],
            "outputs": [
                {
                    "id": "cleaned",
                    "type": "data",
                    "format": "parquet",
                    "inputs": ["raw"],
                    "recipe": {"command": "python clean.py {inputs.raw}"},
                },
            ],
        }
        errors = validate_analysis(data)
        assert errors == []

    def test_valid_output_no_inputs(self):
        """Output with no inputs/decisions should pass validation."""
        data = {
            "version": "0.0.10",
            "name": "test",
            "inputs": [],
            "outputs": [
                {
                    "id": "result",
                    "type": "metric",
                    "format": "json",
                    "recipe": {"command": "python run.py"},
                },
            ],
        }
        errors = validate_analysis(data)
        assert errors == []

    def test_self_referencing_output_input(self):
        """Output input referencing its own ID should create a cycle."""
        data = {
            "version": "0.0.10",
            "name": "test",
            "inputs": [],
            "outputs": [
                {"id": "a", "type": "data", "inputs": ["a"]},
            ],
        }
        errors = validate_analysis(data)
        codes = [e.code for e in errors]
        assert "OUTPUT_CYCLE" in codes

    def test_output_decision_must_be_in_scope(self):
        """Output.decisions must reference a decision in scope."""
        data = {
            "version": "0.0.10",
            "name": "test",
            "inputs": [],
            "outputs": [
                {"id": "result", "type": "metric", "decisions": ["nonexistent"]},
            ],
            "decisions": {
                "real_decision": {
                    "label": "Real",
                    "options": {"a": {"label": "A"}},
                },
            },
        }
        errors = validate_analysis(data)
        codes = [e.code for e in errors]
        assert "INVALID_OUTPUT_DECISION" in codes


class TestCommandTemplateValidation:
    """Tests for the Recipe.command ``{...}`` placeholder grammar."""

    def _make(self, output: dict, decisions: dict | None = None) -> dict:
        return {
            "version": "0.0.10",
            "name": "test",
            "inputs": [{"id": "raw", "type": "data", "source": "x"}],
            "outputs": [output],
            "decisions": decisions or {},
        }

    def test_valid_template(self):
        out = {
            "id": "r",
            "type": "metric",
            "format": "json",
            "inputs": ["raw"],
            "decisions": ["m"],
            "recipe": {
                "command": "python run.py --in {inputs.raw} --m {decisions.m} --out {output}"
            },
        }
        decisions = {
            "m": {"label": "M", "options": {"a": {"label": "A"}}},
        }
        errors = validate_analysis(self._make(out, decisions))
        assert errors == []

    def test_undeclared_input_reference(self):
        out = {
            "id": "r",
            "type": "metric",
            "format": "json",
            "recipe": {"command": "python run.py {inputs.missing}"},
        }
        errors = validate_analysis(self._make(out))
        codes = [e.code for e in errors]
        assert "UNDECLARED_TEMPLATE_REF" in codes

    def test_undeclared_decision_reference(self):
        out = {
            "id": "r",
            "type": "metric",
            "format": "json",
            "recipe": {"command": "python run.py --m {decisions.missing}"},
        }
        errors = validate_analysis(self._make(out))
        codes = [e.code for e in errors]
        assert "UNDECLARED_TEMPLATE_REF" in codes

    def test_declared_but_unreferenced_input_is_fine(self):
        # The spec grants the runner free choice of delivery mechanism for
        # declared inputs ("via flags, env vars, or a sidecar"), so a recipe
        # whose command doesn't substitute every declared input is valid —
        # the runner may deliver them by sidecar instead of template.
        out = {
            "id": "r",
            "type": "metric",
            "format": "json",
            "inputs": ["raw"],
            "recipe": {"command": "python run.py"},
        }
        errors = validate_analysis(self._make(out))
        assert errors == []

    def test_declared_but_unreferenced_decision_is_fine(self):
        # Same as above for decisions.
        out = {
            "id": "r",
            "type": "metric",
            "format": "json",
            "decisions": ["m"],
            "recipe": {"command": "python run.py"},
        }
        decisions = {
            "m": {"label": "M", "options": {"a": {"label": "A"}}},
        }
        errors = validate_analysis(self._make(out, decisions))
        assert errors == []

    def test_inputs_glob_is_valid_template(self):
        out = {
            "id": "r",
            "type": "metric",
            "format": "json",
            "inputs": ["raw"],
            "recipe": {"command": "python run.py {inputs}"},
        }
        errors = validate_analysis(self._make(out))
        assert errors == []

    def test_literal_braces_are_allowed(self):
        out = {
            "id": "r",
            "type": "metric",
            "format": "json",
            "recipe": {"command": "echo '{{not a placeholder}}'"},
        }
        errors = validate_analysis(self._make(out))
        assert errors == []

    def test_unknown_placeholder_form(self):
        out = {
            "id": "r",
            "type": "metric",
            "format": "json",
            "recipe": {"command": "python run.py {bogus}"},
        }
        errors = validate_analysis(self._make(out))
        codes = [e.code for e in errors]
        assert "INVALID_COMMAND_TEMPLATE" in codes

    def test_unterminated_brace(self):
        out = {
            "id": "r",
            "type": "metric",
            "format": "json",
            "recipe": {"command": "python run.py {output"},
        }
        errors = validate_analysis(self._make(out))
        codes = [e.code for e in errors]
        assert "INVALID_COMMAND_TEMPLATE" in codes


class TestRecipeHelpers:
    """Tests for recipe helper functions."""

    def test_get_output_dependencies(self):
        """get_output_dependencies should mirror Output.inputs declarations."""
        from astra.helpers import get_output_dependencies

        data = {
            "outputs": [
                {"id": "clean", "type": "data", "recipe": {"command": "clean.py"}},
                {
                    "id": "train",
                    "type": "data",
                    "inputs": ["clean"],
                    "recipe": {"command": "train.py {inputs.clean}"},
                },
                {
                    "id": "eval",
                    "type": "metric",
                    "inputs": ["train"],
                    "recipe": {"command": "eval.py {inputs.train}"},
                },
                {"id": "external", "type": "data"},  # no inputs declared
            ],
        }
        deps = get_output_dependencies(data)
        assert deps == {"clean": [], "train": ["clean"], "eval": ["train"], "external": []}

    def test_get_outputs_with_recipes(self):
        """get_outputs_with_recipes should return only outputs that have recipes."""
        from astra.helpers import get_outputs_with_recipes

        data = {
            "outputs": [
                {"id": "a", "type": "data", "recipe": {"command": "run_a"}},
                {"id": "b", "type": "data"},
            ],
        }
        result = get_outputs_with_recipes(data)
        assert len(result) == 1
        assert result[0]["id"] == "a"


class TestDecisionTagsValidation:
    """Tests for decision tags."""

    def test_valid_decision_tags(self, valid_dir: Path):
        errors = validate_analysis_file(valid_dir / "full_v2.yaml")
        assert errors == []

    def test_decisions_with_tags(self, valid_dir: Path):
        data = load_yaml(valid_dir / "full_v2.yaml")
        assert data["decisions"]["preprocessing"]["tags"] == ["data_preparation"]


class TestExcludedOptionValidation:
    """Tests for excluded option validation."""

    def test_excluded_no_reason(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "excluded_no_reason.yaml")
        assert any(e.code == "MISSING_EXCLUDED_REASON" for e in errors)

    def test_orphan_excluded_reason(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "orphan_excluded_reason.yaml")
        assert any(e.code == "ORPHAN_EXCLUDED_REASON" for e in errors)


class TestUniverseNewFeaturesValidation:
    """Tests for universe validation with conditional decisions and excluded options."""

    def test_excluded_option_in_universe(
        self, invalid_dir: Path, valid_dir: Path, with_universe_entry
    ):
        data = with_universe_entry(
            valid_dir / "full_v2.yaml", invalid_dir / "universe_entry_excluded_option.yaml"
        )
        errors = validate_analysis(data)
        assert any(e.code == "EXCLUDED_OPTION_SELECTED" for e in errors)


class TestSemanticError:
    """Tests for SemanticError class."""

    def test_error_str_with_path(self):
        error = SemanticError("TEST_CODE", "Test message", "some.path")
        assert "[TEST_CODE]" in str(error)
        assert "some.path" in str(error)
        assert "Test message" in str(error)

    def test_error_str_without_path(self):
        error = SemanticError("TEST_CODE", "Test message")
        assert "[TEST_CODE]" in str(error)
        assert "Test message" in str(error)


class TestConditionalOutputs:
    """Tests for conditional outputs with when conditions."""

    def test_valid_output_with_when(self, valid_dir: Path):
        """Output with a valid when condition should pass validation."""
        errors = validate_analysis_file(valid_dir / "conditional_outputs.yaml")
        assert errors == []

    def test_output_when_negation(self):
        """Output with ~decision.option negation should pass validation."""
        data = {
            "version": "0.0.10",
            "name": "test",
            "inputs": [],
            "outputs": [
                {"id": "base", "type": "data", "format": "parquet"},
                {
                    "id": "faint_only",
                    "type": "metric",
                    "when": "~sample.bright_only",
                },
            ],
            "decisions": {
                "sample": {
                    "label": "Sample",
                    "options": {
                        "combined": {"label": "Combined"},
                        "bright_only": {"label": "Bright Only"},
                    },
                }
            },
        }
        errors = validate_analysis(data)
        assert errors == []

    def test_output_when_list(self):
        """Output with when as list (AND logic) should pass validation."""
        data = {
            "version": "0.0.10",
            "name": "test",
            "inputs": [],
            "outputs": [
                {"id": "base", "type": "data", "format": "parquet"},
                {
                    "id": "combined_report",
                    "type": "report",
                    "when": ["~sample.bright_only", "model.svm"],
                },
            ],
            "decisions": {
                "sample": {
                    "label": "Sample",
                    "options": {
                        "combined": {"label": "Combined"},
                        "bright_only": {"label": "Bright Only"},
                    },
                },
                "model": {
                    "label": "Model",
                    "options": {
                        "svm": {"label": "SVM"},
                        "rf": {"label": "RF"},
                    },
                },
            },
        }
        errors = validate_analysis(data)
        assert errors == []

    def test_invalid_output_when_ref(self, invalid_dir: Path):
        """Output when referencing non-existent decision should fail."""
        errors = validate_analysis_file(invalid_dir / "invalid_output_when_ref.yaml")
        assert any(e.code == "INVALID_WHEN_REF" for e in errors)

    def test_invalid_output_when_bad_option(self):
        """Output when referencing non-existent option should fail."""
        data = {
            "version": "0.0.10",
            "name": "test",
            "inputs": [],
            "outputs": [
                {
                    "id": "result",
                    "type": "metric",
                    "when": "model.nonexistent",
                },
            ],
            "decisions": {
                "model": {
                    "label": "Model",
                    "options": {"a": {"label": "A"}},
                }
            },
        }
        errors = validate_analysis(data)
        assert any(e.code == "INVALID_WHEN_REF" and "nonexistent" in e.message for e in errors)

    def test_decision_when_list(self, valid_dir: Path):
        """Decision with list-valued when should pass validation."""
        errors = validate_analysis_file(valid_dir / "decision_list_when.yaml")
        assert errors == []

    def test_decision_when_negation(self):
        """Decision with ~decision.option negation should pass validation."""
        data = {
            "version": "0.0.10",
            "name": "test",
            "inputs": [],
            "outputs": [{"id": "result", "type": "metric", "format": "json"}],
            "decisions": {
                "mode": {
                    "label": "Mode",
                    "options": {
                        "full": {"label": "Full"},
                        "lite": {"label": "Lite"},
                    },
                },
                "advanced_setting": {
                    "label": "Advanced",
                    "when": "~mode.lite",
                    "options": {
                        "on": {"label": "On"},
                        "off": {"label": "Off"},
                    },
                },
            },
        }
        errors = validate_analysis(data)
        assert errors == []


class TestConditionalOutputsUniverse:
    """Tests for universe validation with conditional outputs."""

    def test_valid_universe_with_conditional_outputs(self, valid_dir: Path):
        """Universe should validate against analysis with conditional outputs."""
        errors = validate_analysis_file(valid_dir / "conditional_outputs.yaml")
        assert errors == []

    def test_decision_list_when_active(self, valid_dir: Path):
        """Universe where list when condition IS met should include the decision."""
        errors = validate_analysis_file(valid_dir / "decision_list_when.yaml")
        assert not [e for e in errors if (e.path or "").startswith("universes.gpu_advanced")]

    def test_decision_list_when_inactive(self, valid_dir: Path):
        """Universe where list when condition is NOT met should skip the decision."""
        errors = validate_analysis_file(valid_dir / "decision_list_when.yaml")
        assert not [e for e in errors if (e.path or "").startswith("universes.cpu_basic")]

    def test_decision_list_when_inactive_with_selection_is_error(self, valid_dir: Path):
        """Selecting an inactive decision (list when not met) should be an error."""
        data = load_yaml(valid_dir / "decision_list_when.yaml")
        data["universes"].append(
            {
                "id": "bad",
                "decisions": {
                    "mode": "basic",
                    "backend": "cpu",
                    "gpu_optimization": "tensor_cores",
                },
            }
        )
        errors = validate_analysis(data)
        assert any(
            e.code == "INACTIVE_DECISION" and e.path == "universes.bad.decisions.gpu_optimization"
            for e in errors
        )

    def test_an_inherited_inactive_selection_is_dropped(self, valid_dir: Path):
        """Switching ``gpu_optimization`` off in a diff drops the selection it
        inherited - it isn't the diff's to report."""
        data = load_yaml(valid_dir / "decision_list_when.yaml")
        data["universes"].append(
            {
                "id": "cpu_from_gpu",
                "derived_from": "gpu_advanced",
                "decisions": {"mode": "basic", "backend": "cpu"},
            }
        )
        errors = validate_analysis(data)
        assert errors == []

    def test_a_when_on_a_from_alias_uses_the_alias_value(self):
        """``m`` is the parent's ``mode`` - the validator reads its value as
        the resolver does, so ``depth`` is active when ``mode`` is ``full``."""
        spec = {
            "version": "1.0",
            "name": "Alias condition",
            "inputs": [{"id": "raw", "type": "data", "source": "raw.csv"}],
            "outputs": [{"id": "out", "type": "data", "format": "parquet"}],
            "decisions": {"mode": {"label": "Mode", "options": {"fast": {}, "full": {}}}},
            "analyses": {
                "stage": {
                    "inputs": [{"id": "x", "from": "../raw"}],
                    "outputs": [{"id": "y", "type": "data", "decisions": ["depth"]}],
                    "decisions": {
                        "m": {"from": "../mode"},
                        "depth": {"label": "Depth", "when": ["m.full"], "options": {"a": {}}},
                    },
                }
            },
            "universes": [
                {
                    "id": "u",
                    "decisions": {"mode": "full"},
                    "analyses": {"stage": {"decisions": {"depth": "a"}}},
                }
            ],
        }
        assert validate_analysis(spec) == []


class TestDeclaredUniverses:
    """Tests for the rules on the universes an analysis declares."""

    FLAT = {
        "version": "1.0",
        "name": "Declared universes",
        "inputs": [{"id": "raw", "type": "data", "source": "raw.csv"}],
        "outputs": [{"id": "out", "type": "data", "decisions": ["method"]}],
        "decisions": {
            "method": {
                "label": "Method",
                "options": {"pca": {"label": "PCA"}, "mlp": {"label": "MLP"}},
            },
        },
    }

    NESTED = {
        "version": "1.0",
        "name": "Sub-analysis presets",
        "inputs": [{"id": "raw", "type": "data", "source": "raw.csv"}],
        "outputs": [{"id": "out", "type": "data", "format": "parquet"}],
        "analyses": {
            "stage": {
                "inputs": [{"id": "x", "from": "../raw"}],
                "outputs": [{"id": "y", "type": "data", "decisions": ["method"]}],
                "decisions": {
                    "method": {
                        "label": "Method",
                        "options": {"pca": {"label": "PCA"}, "mlp": {"label": "MLP"}},
                    },
                },
                "universes": [{"id": "fast", "decisions": {"method": "pca"}}],
            }
        },
    }

    @staticmethod
    def codes(spec: dict, *universes: dict) -> list[tuple[str, str | None]]:
        return [(e.code, e.path) for e in validate_analysis({**spec, "universes": list(universes)})]

    def test_duplicate_universe(self):
        found = self.codes(
            self.FLAT,
            {"id": "a", "decisions": {"method": "pca"}},
            {"id": "a", "decisions": {"method": "mlp"}},
        )
        assert ("DUPLICATE_UNIVERSE", "universes.a") in found

    def test_unknown_derived_from(self):
        found = self.codes(self.FLAT, {"id": "b", "derived_from": "nope", "decisions": {}})
        assert ("UNKNOWN_DERIVED_FROM", "universes.b.derived_from") in found

    def test_derived_from_cycle(self):
        found = self.codes(
            self.FLAT,
            {"id": "a", "derived_from": "b", "decisions": {}},
            {"id": "b", "derived_from": "a", "decisions": {}},
            {"id": "c", "derived_from": "a", "decisions": {}},
        )
        cycles = sorted(path or "" for code, path in found if code == "DERIVED_FROM_CYCLE")
        assert cycles == ["universes.a.derived_from", "universes.b.derived_from"]

    def test_a_diff_is_checked_on_its_effective_selection(self):
        found = self.codes(
            self.FLAT,
            {"id": "a", "decisions": {"method": "pca"}},
            {"id": "b", "derived_from": "a", "decisions": {}},
        )
        assert found == []

    def test_a_sub_analysis_universe_can_be_picked_by_id(self):
        found = self.codes(self.NESTED, {"id": "u", "analyses": {"stage": {"universe": "fast"}}})
        assert found == []

    def test_picking_a_universe_and_listing_decisions_is_a_conflict(self):
        found = self.codes(
            self.NESTED,
            {
                "id": "u",
                "analyses": {"stage": {"universe": "fast", "decisions": {"method": "mlp"}}},
            },
        )
        assert ("UNIVERSE_NODE_CONFLICT", "universes.u.analyses.stage") in found

    def test_unknown_sub_universe(self):
        found = self.codes(self.NESTED, {"id": "u", "analyses": {"stage": {"universe": "deep"}}})
        assert ("UNKNOWN_SUB_UNIVERSE", "universes.u.analyses.stage.universe") in found

    def test_a_sub_analysis_universes_get_structural_checks(self):
        stage = {**self.NESTED["analyses"]["stage"]}
        stage["universes"] = [{"id": "x", "derived_from": "nope"}]
        spec = {**self.NESTED, "analyses": {"stage": stage}}
        found = self.codes(spec)
        assert ("UNKNOWN_DERIVED_FROM", "analyses.stage.universes.x.derived_from") in found

    def test_a_sub_analysis_universe_is_judged_where_it_is_picked(self):
        stage = {**self.NESTED["analyses"]["stage"]}
        stage["universes"] = [{"id": "bad", "decisions": {"method": "nope"}}]
        spec = {**self.NESTED, "analyses": {"stage": stage}}
        assert self.codes(spec) == []
        found = self.codes(spec, {"id": "u", "analyses": {"stage": {"universe": "bad"}}})
        assert ("UNKNOWN_OPTION", "universes.u.analyses.stage.decisions.method") in found

    def test_a_universe_that_depends_on_its_parent_is_not_judged_on_its_own(self):
        """``depth`` only exists when the parent's ``mode`` is ``full`` and
        ``tol.lo`` requires it - on its own the stage can't tell."""
        stage = {
            "inputs": [{"id": "x", "from": "../raw"}],
            "outputs": [{"id": "y", "type": "data", "decisions": ["depth"]}],
            "decisions": {
                "m": {"from": "../mode"},
                "depth": {
                    "label": "Depth",
                    "when": ["m.full"],
                    "options": {"a": {"label": "A"}, "b": {"label": "B"}},
                },
                "tol": {
                    "label": "Tolerance",
                    "options": {
                        "lo": {"label": "Lo", "requires": ["m.full"]},
                        "hi": {"label": "Hi"},
                    },
                },
            },
            "universes": [
                {"id": "deep", "decisions": {"depth": "a", "tol": "lo"}},
                {"id": "deeper", "derived_from": "deep", "decisions": {"depth": "b"}},
            ],
        }
        spec = {
            **self.FLAT,
            "decisions": {"mode": {"label": "Mode", "options": {"fast": {}, "full": {}}}},
            "outputs": [{"id": "out", "type": "data", "format": "parquet"}],
            "analyses": {"stage": stage},
        }
        found = self.codes(
            spec,
            {
                "id": "u",
                "decisions": {"mode": "full"},
                "analyses": {"stage": {"universe": "deeper"}},
            },
        )
        assert found == []

    def test_a_diff_inherits_sub_analysis_selections(self):
        found = self.codes(
            self.NESTED,
            {"id": "a", "analyses": {"stage": {"decisions": {"method": "pca"}}}},
            {"id": "b", "derived_from": "a"},
            {"id": "c", "derived_from": "a", "analyses": {"stage": {"universe": "fast"}}},
        )
        assert found == []


class TestIsConditionMet:
    """Tests for the is_condition_met helper function."""

    def test_none_always_met(self):
        from astra.helpers import is_condition_met

        assert is_condition_met(None, {}) is True

    def test_simple_positive_match(self):
        from astra.helpers import is_condition_met

        assert is_condition_met("model.svm", {"model": "svm"}) is True

    def test_simple_positive_no_match(self):
        from astra.helpers import is_condition_met

        assert is_condition_met("model.svm", {"model": "rf"}) is False

    def test_negation_match(self):
        from astra.helpers import is_condition_met

        assert is_condition_met("~model.svm", {"model": "rf"}) is True

    def test_negation_no_match(self):
        from astra.helpers import is_condition_met

        assert is_condition_met("~model.svm", {"model": "svm"}) is False

    def test_list_and_all_met(self):
        from astra.helpers import is_condition_met

        decisions = {"model": "svm", "sample": "combined"}
        assert is_condition_met(["model.svm", "~sample.bright"], decisions) is True

    def test_list_and_one_not_met(self):
        from astra.helpers import is_condition_met

        decisions = {"model": "rf", "sample": "combined"}
        assert is_condition_met(["model.svm", "~sample.bright"], decisions) is False

    def test_missing_decision_is_no_match(self):
        from astra.helpers import is_condition_met

        assert is_condition_met("model.svm", {}) is False

    def test_missing_decision_negated_is_match(self):
        from astra.helpers import is_condition_met

        # ~model.svm with model not set: selected is None, match=(None==svm)=False, negated=True
        assert is_condition_met("~model.svm", {}) is True

    @pytest.mark.parametrize("ref", ["model", "model.svm.extra", "", "~model", "~model.svm.extra"])
    def test_a_malformed_reference_is_a_condition_nothing_satisfies(self, ref: str):
        """Not an exception. `is_condition_met` is reached from the
        validator as well as the resolver, so raising took `astra universe
        check` down on a typo the validator is perfectly able to report."""
        from astra.helpers import is_condition_met

        assert is_condition_met(ref, {"model": "svm"}) is False

    def test_a_malformed_reference_fails_the_whole_and(self):
        from astra.helpers import is_condition_met

        assert is_condition_met(["model.svm", "sample"], {"model": "svm"}) is False


class TestMalformedWhenIsReportedNotRaised:
    """A `when:` that does not parse is the validator's to report.

    Every command that reads a spec goes through `is_condition_met`, so a
    single typo used to surface as an uncaught `ValueError` traceback from
    `astra universe check` — while `astra validate`, on the same file,
    described the problem precisely.
    """

    SPEC = {
        "version": "1.0",
        "name": "Malformed",
        "inputs": [{"id": "seed", "type": "data", "source": "s3://raw"}],
        "outputs": [{"id": "out", "type": "data", "recipe": {"command": "run {output}"}}],
        "decisions": {
            "method": {"options": {"pca": {}, "mlp": {}}},
            "trees": {"when": ["method"], "options": {"fifty": {}}},
        },
    }

    def test_validate_universe_reports_instead_of_raising(self):
        errors = validate_universe({"decisions": {"method": "pca", "trees": "fifty"}}, self.SPEC)
        assert all(isinstance(e, SemanticError) for e in errors)

    def test_the_analysis_validator_still_names_the_typo(self):
        codes = {e.code for e in validate_analysis(self.SPEC)}
        assert "INVALID_WHEN_REF" in codes

    def test_an_output_when_is_reported_too(self):
        spec = {
            **self.SPEC,
            "decisions": {"method": {"options": {"pca": {}}}},
            "outputs": [
                {
                    "id": "out",
                    "type": "data",
                    "when": ["method.pca.extra"],
                    "recipe": {"command": "run {output}"},
                }
            ],
        }
        codes = {e.code for e in validate_analysis(spec)}
        assert "INVALID_WHEN_REF" in codes


PINS_SPEC = {
    "version": "1.0",
    "name": "Pins",
    "inputs": [{"id": "raw", "type": "data", "source": "raw.csv"}],
    "outputs": [
        {
            "id": "score",
            "type": "metric",
            "format": "json",
            "inputs": ["raw"],
            "decisions": ["model"],
        },
        {
            "id": "svm_margin",
            "type": "metric",
            "format": "json",
            "inputs": ["raw"],
            "decisions": ["model"],
            "when": ["model.svm"],
        },
        {"id": "summary", "type": "table", "format": "csv", "inputs": ["raw"]},
    ],
    "decisions": {
        "model": {"label": "Model", "options": {"rf": {"label": "RF"}, "svm": {"label": "SVM"}}},
    },
    "universes": [
        {"id": "rf", "decisions": {"model": "rf"}},
        {"id": "svm", "derived_from": "rf", "decisions": {"model": "svm"}},
    ],
}


def with_pins(*outputs: dict, **extra: object) -> dict:
    """``PINS_SPEC`` with *outputs* added, and any other top-level fields."""
    return {**PINS_SPEC, "outputs": [*PINS_SPEC["outputs"], *outputs], **extra}


def finding(artifact: str) -> dict:
    return {
        "f": {
            "claim": "A claim.",
            "created_at": "2026-10-16T00:00:00Z",
            "evidence": [{"id": "e", "artifact": artifact}],
        }
    }


class TestPins:
    """Pins (``artifact#universe``), and the ``format`` of outputs built once."""

    @staticmethod
    def found(data: dict) -> set[tuple[str, str | None]]:
        return {(e.code, e.path) for e in validate_analysis(data)}

    def test_a_comparison_of_two_universes_is_valid(self):
        comparison = {
            "id": "comparison",
            "type": "table",
            "format": "csv",
            "inputs": ["score#rf", "score#svm"],
            "recipe": {
                "command": "python c.py {inputs.score#rf} {inputs.score#svm} --out {output}"
            },
        }
        assert validate_analysis(with_pins(comparison)) == []

    def test_pinning_an_external_input(self):
        out = {"id": "bad", "type": "table", "format": "csv", "inputs": ["raw#rf"]}
        assert ("PIN_ON_EXTERNAL_INPUT", "outputs.bad.inputs") in self.found(with_pins(out))

    def test_pinning_an_undeclared_universe(self):
        out = {"id": "bad", "type": "table", "format": "csv", "inputs": ["score#nope"]}
        assert ("UNKNOWN_PIN_UNIVERSE", "outputs.bad.inputs") in self.found(with_pins(out))

    def test_pinning_a_universe_where_the_output_is_not_built(self):
        inactive = {"id": "bad", "type": "table", "format": "csv", "inputs": ["svm_margin#rf"]}
        active = {"id": "good", "type": "table", "format": "csv", "inputs": ["svm_margin#svm"]}
        found = self.found(with_pins(inactive, active))
        assert ("PIN_INACTIVE", "outputs.bad.inputs") in found
        assert ("PIN_INACTIVE", "outputs.good.inputs") not in found

    def test_an_output_built_once_must_declare_a_format(self):
        out = {"id": "bare", "type": "table", "inputs": ["score#rf"]}
        assert ("MISSING_FORMAT_ON_UNSCOPED_OUTPUT", "outputs.bare") in self.found(with_pins(out))

    def test_an_output_built_per_universe_needs_no_format_yet(self):
        """Through a decision, a ``when`` or an unpinned per-universe input."""
        outputs = (
            {"id": "a", "type": "table", "inputs": ["raw"], "decisions": ["model"]},
            {"id": "b", "type": "report", "when": ["model.svm"]},
            {"id": "c", "type": "table", "inputs": ["score"]},
        )
        assert validate_analysis(with_pins(*outputs)) == []

    def test_a_placeholder_names_the_entry_as_written(self):
        stage = {
            "inputs": [{"id": "x", "from": "../raw"}],
            "outputs": [{"id": "y", "type": "data", "format": "csv", "inputs": ["x"]}],
        }
        total = {
            "id": "total",
            "type": "metric",
            "format": "json",
            "inputs": ["stage.y", "score#rf"],
            "recipe": {"command": "run {inputs.stage.y} {inputs.score#rf} --out {output}"},
        }
        assert validate_analysis(with_pins(total, analyses={"stage": stage})) == []

    def test_a_placeholder_for_another_pin_is_undeclared(self):
        out = {
            "id": "bad",
            "type": "table",
            "format": "csv",
            "inputs": ["score#rf"],
            "recipe": {"command": "run {inputs.score#svm}"},
        }
        codes = {code for code, _ in self.found(with_pins(out))}
        assert "UNDECLARED_TEMPLATE_REF" in codes

    def test_evidence_may_pin_a_declared_universe(self):
        assert validate_analysis(with_pins(findings=finding("score#rf"))) == []

    def test_evidence_pinning_an_undeclared_universe(self):
        found = self.found(with_pins(findings=finding("score#nope")))
        assert ("UNKNOWN_PIN_UNIVERSE", "findings.f.evidence[0].artifact") in found

    def test_evidence_citing_an_unknown_artifact_is_still_reported(self):
        found = self.found(with_pins(findings=finding("nope#rf")))
        assert ("INVALID_ARTIFACT_REF", "findings.f.evidence[0].artifact") in found


class TestSemanticWarnings:
    """What is allowed but probably not meant - warnings."""

    @staticmethod
    def codes(data: dict) -> list[str]:
        return [w.code for w in collect_semantic_warnings(data)]

    def test_nothing_to_say(self):
        assert self.codes(PINS_SPEC) == []

    def test_a_pin_on_an_output_built_once(self):
        out = {"id": "again", "type": "table", "format": "csv", "inputs": ["summary#rf"]}
        assert self.codes(with_pins(out)) == ["REDUNDANT_PIN"]
        assert self.codes(with_pins(findings=finding("summary#rf"))) == ["REDUNDANT_PIN"]

    def test_evidence_without_a_pin_on_an_output_built_per_universe(self):
        assert self.codes(with_pins(findings=finding("score"))) == ["UNPINNED_EVIDENCE"]

    def test_decisions_but_no_universes(self):
        assert self.codes({**PINS_SPEC, "universes": []}) == ["NO_UNIVERSES"]
