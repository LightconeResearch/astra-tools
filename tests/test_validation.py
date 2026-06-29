"""Tests for validation modules."""

from pathlib import Path

from astra.helpers import load_yaml
from astra.validation.schema import (
    is_valid_analysis,
    is_valid_universe,
    validate_analysis_schema,
    validate_universe_schema,
)
from astra.validation.semantic import (
    SemanticError,
    validate_analysis,
    validate_analysis_file,
    validate_universe,
    validate_universe_file,
)


class TestSchemaValidation:
    """Tests for JSON schema validation."""

    def test_valid_minimal_analysis(self, minimal_analysis_path: Path):
        errors = validate_analysis_schema(minimal_analysis_path)
        assert errors == []
        assert is_valid_analysis(minimal_analysis_path)

    def test_valid_full_analysis(self, full_analysis_path: Path):
        errors = validate_analysis_schema(full_analysis_path)
        assert errors == []

    def test_valid_universe(self, baseline_universe_path: Path):
        errors = validate_universe_schema(baseline_universe_path)
        assert errors == []
        assert is_valid_universe(baseline_universe_path)

    def test_missing_version(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "missing_version.yaml")
        assert any(e.code == "MISSING_ROOT_FIELD" and "version" in e.message for e in errors)

    def test_invalid_input_type(self, invalid_dir: Path):
        errors = validate_analysis_schema(invalid_dir / "invalid_input_type.yaml")
        assert len(errors) > 0

    def test_invalid_output_type(self, invalid_dir: Path):
        errors = validate_analysis_schema(invalid_dir / "invalid_output_type.yaml")
        assert len(errors) > 0


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
    """Tests for universe validation."""

    def test_valid_universe(self, full_analysis_path: Path, baseline_universe_path: Path):
        errors = validate_universe_file(baseline_universe_path, full_analysis_path)
        assert errors == []

    def test_valid_svm_universe(self, full_analysis_path: Path, svm_universe_path: Path):
        # SVM requires standard preprocessing, which is set
        errors = validate_universe_file(svm_universe_path, full_analysis_path)
        assert errors == []

    def test_missing_decision(self, full_analysis_path: Path, invalid_dir: Path):
        errors = validate_universe_file(
            invalid_dir / "universe_missing_decision.yaml",
            full_analysis_path,
        )
        assert any(e.code == "MISSING_DECISION" for e in errors)

    def test_invalid_option(self, full_analysis_path: Path, invalid_dir: Path):
        errors = validate_universe_file(
            invalid_dir / "universe_invalid_option.yaml",
            full_analysis_path,
        )
        assert any(e.code == "UNKNOWN_OPTION" for e in errors)

    def test_incompatible_options(self, full_analysis_path: Path, invalid_dir: Path):
        errors = validate_universe_file(
            invalid_dir / "universe_incompatible.yaml",
            full_analysis_path,
        )
        assert any(e.code == "INCOMPATIBLE_OPTIONS" for e in errors)

    def test_missing_required_option(self, full_analysis_path: Path, invalid_dir: Path):
        errors = validate_universe_file(
            invalid_dir / "universe_missing_required.yaml",
            full_analysis_path,
        )
        assert any(e.code == "MISSING_REQUIRED_OPTION" for e in errors)


class TestNestedAnalysisValidation:
    """Tests for nested analysis semantic validation."""

    def test_valid_nested_analysis(self, valid_dir: Path):
        errors = validate_analysis_file(valid_dir / "nested.yaml")
        assert errors == []

    def test_valid_nested_universe(self, valid_dir: Path):
        analysis_data = load_yaml(valid_dir / "nested.yaml")
        universe_data = load_yaml(valid_dir / "nested_universe.yaml")
        errors = validate_universe(universe_data, analysis_data)
        assert errors == []

    def test_missing_analysis_decision_in_universe(self, valid_dir: Path, invalid_dir: Path):
        analysis_data = load_yaml(valid_dir / "nested.yaml")
        universe_data = load_yaml(invalid_dir / "universe_missing_analysis_decision.yaml")
        errors = validate_universe(universe_data, analysis_data)
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

    def test_cross_level_incompatible_universe(self, valid_dir: Path, invalid_dir: Path):
        """Universe violates cross-level incompatible_with constraint."""
        analysis_data = load_yaml(valid_dir / "nested.yaml")
        universe_data = load_yaml(invalid_dir / "universe_cross_level_incompatible.yaml")
        errors = validate_universe(universe_data, analysis_data)
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
                {"id": "cleaned", "type": "data", "recipe": {"command": "python clean.py"}},
                {
                    "id": "result",
                    "type": "metric",
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
                    "default": "a",
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
            "inputs": ["raw"],
            "decisions": ["m"],
            "recipe": {
                "command": "python run.py --in {inputs.raw} --m {decisions.m} --out {output}"
            },
        }
        decisions = {
            "m": {"label": "M", "default": "a", "options": {"a": {"label": "A"}}},
        }
        errors = validate_analysis(self._make(out, decisions))
        assert errors == []

    def test_undeclared_input_reference(self):
        out = {
            "id": "r",
            "type": "metric",
            "recipe": {"command": "python run.py {inputs.missing}"},
        }
        errors = validate_analysis(self._make(out))
        codes = [e.code for e in errors]
        assert "UNDECLARED_TEMPLATE_REF" in codes

    def test_undeclared_decision_reference(self):
        out = {
            "id": "r",
            "type": "metric",
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
            "decisions": ["m"],
            "recipe": {"command": "python run.py"},
        }
        decisions = {
            "m": {"label": "M", "default": "a", "options": {"a": {"label": "A"}}},
        }
        errors = validate_analysis(self._make(out, decisions))
        assert errors == []

    def test_inputs_glob_is_valid_template(self):
        out = {
            "id": "r",
            "type": "metric",
            "inputs": ["raw"],
            "recipe": {"command": "python run.py {inputs}"},
        }
        errors = validate_analysis(self._make(out))
        assert errors == []

    def test_literal_braces_are_allowed(self):
        out = {
            "id": "r",
            "type": "metric",
            "recipe": {"command": "echo '{{not a placeholder}}'"},
        }
        errors = validate_analysis(self._make(out))
        assert errors == []

    def test_unknown_placeholder_form(self):
        out = {
            "id": "r",
            "type": "metric",
            "recipe": {"command": "python run.py {bogus}"},
        }
        errors = validate_analysis(self._make(out))
        codes = [e.code for e in errors]
        assert "INVALID_COMMAND_TEMPLATE" in codes

    def test_unterminated_brace(self):
        out = {
            "id": "r",
            "type": "metric",
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

    def test_excluded_default(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "excluded_default.yaml")
        assert any(e.code == "EXCLUDED_DEFAULT" for e in errors)

    def test_orphan_excluded_reason(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "orphan_excluded_reason.yaml")
        assert any(e.code == "ORPHAN_EXCLUDED_REASON" for e in errors)


class TestUniverseNewFeaturesValidation:
    """Tests for universe validation with conditional decisions and excluded options."""

    def test_excluded_option_in_universe(self, invalid_dir: Path, valid_dir: Path):
        analysis_data = load_yaml(valid_dir / "full_v2.yaml")
        universe_data = load_yaml(invalid_dir / "universe_excluded_option.yaml")
        errors = validate_universe(universe_data, analysis_data)
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
                {"id": "base", "type": "data"},
                {
                    "id": "faint_only",
                    "type": "metric",
                    "when": "~sample.bright_only",
                },
            ],
            "decisions": {
                "sample": {
                    "label": "Sample",
                    "default": "combined",
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
                {"id": "base", "type": "data"},
                {
                    "id": "combined_report",
                    "type": "report",
                    "when": ["~sample.bright_only", "model.svm"],
                },
            ],
            "decisions": {
                "sample": {
                    "label": "Sample",
                    "default": "combined",
                    "options": {
                        "combined": {"label": "Combined"},
                        "bright_only": {"label": "Bright Only"},
                    },
                },
                "model": {
                    "label": "Model",
                    "default": "svm",
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
                    "default": "a",
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
            "outputs": [{"id": "result", "type": "metric"}],
            "decisions": {
                "mode": {
                    "label": "Mode",
                    "default": "full",
                    "options": {
                        "full": {"label": "Full"},
                        "lite": {"label": "Lite"},
                    },
                },
                "advanced_setting": {
                    "label": "Advanced",
                    "when": "~mode.lite",
                    "default": "on",
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
        analysis_data = load_yaml(valid_dir / "conditional_outputs.yaml")
        universe_data = load_yaml(valid_dir / "conditional_outputs_universe.yaml")
        errors = validate_universe(universe_data, analysis_data)
        assert errors == []

    def test_decision_list_when_active(self, valid_dir: Path):
        """Universe where list when condition IS met should include the decision."""
        analysis_data = load_yaml(valid_dir / "decision_list_when.yaml")
        universe_data = load_yaml(valid_dir / "decision_list_when_universe.yaml")
        errors = validate_universe(universe_data, analysis_data)
        assert errors == []

    def test_decision_list_when_inactive(self, valid_dir: Path):
        """Universe where list when condition is NOT met should skip the decision."""
        analysis_data = load_yaml(valid_dir / "decision_list_when.yaml")
        universe_data = load_yaml(valid_dir / "decision_list_when_universe_inactive.yaml")
        errors = validate_universe(universe_data, analysis_data)
        assert errors == []

    def test_decision_list_when_inactive_with_selection_is_error(self, valid_dir: Path):
        """Selecting an inactive decision (list when not met) should be an error."""
        analysis_data = load_yaml(valid_dir / "decision_list_when.yaml")
        universe_data = {
            "id": "bad",
            "decisions": {
                "mode": "basic",
                "backend": "cpu",
                "gpu_optimization": "tensor_cores",
            },
        }
        errors = validate_universe(universe_data, analysis_data)
        assert any(e.code == "INACTIVE_DECISION" for e in errors)


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


class TestDefaultUniverseConditional:
    """Tests for get_default_universe with conditional decisions."""

    def test_defaults_with_list_when(self, valid_dir: Path):
        """Conditional decision with list when should be included when conditions are met."""
        from astra.helpers import get_default_universe

        data = load_yaml(valid_dir / "decision_list_when.yaml")
        defaults = get_default_universe(data)
        decisions = defaults["decisions"]
        # mode=advanced, backend=gpu -> gpu_optimization should be included
        assert decisions["gpu_optimization"] == "tensor_cores"

    def test_defaults_skip_unmet_list_when(self):
        """Conditional decision with unmet list when should be skipped."""
        from astra.helpers import get_default_universe

        data = {
            "decisions": {
                "mode": {
                    "label": "Mode",
                    "default": "basic",
                    "options": {
                        "basic": {"label": "Basic"},
                        "advanced": {"label": "Advanced"},
                    },
                },
                "backend": {
                    "label": "Backend",
                    "default": "gpu",
                    "options": {
                        "cpu": {"label": "CPU"},
                        "gpu": {"label": "GPU"},
                    },
                },
                "gpu_opt": {
                    "label": "GPU Opt",
                    "when": ["mode.advanced", "backend.gpu"],
                    "default": "on",
                    "options": {"on": {"label": "On"}, "off": {"label": "Off"}},
                },
            }
        }
        defaults = get_default_universe(data)
        decisions = defaults["decisions"]
        # mode=basic -> condition not met, gpu_opt should NOT be included
        assert "gpu_opt" not in decisions
