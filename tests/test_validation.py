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

    def test_invalid_constraint_ref(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "invalid_constraint_ref.yaml")
        assert any(e.code == "INVALID_CONSTRAINT_REF" for e in errors)


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

    def test_invalid_decision_from_ref(self, invalid_dir: Path):
        """Decision with from: referencing non-existent parent decision."""
        errors = validate_analysis_file(invalid_dir / "invalid_parent_decision.yaml")
        assert any(e.code == "INVALID_DECISION_FROM_REF" for e in errors)

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


class TestRecipeValidation:
    """Tests for output-to-output recipe validation."""

    def test_recipe_inputs_must_reference_declared_outputs(self):
        """Recipe inputs must reference outputs declared in the same analysis."""
        data = {
            "version": "1.0",
            "name": "test",
            "inputs": [],
            "outputs": [
                {
                    "id": "result",
                    "type": "metric",
                    "recipe": {
                        "command": "python run.py",
                        "inputs": ["nonexistent"],
                    },
                },
            ],
        }
        errors = validate_analysis(data)
        codes = [e.code for e in errors]
        assert "INVALID_RECIPE_INPUT" in codes

    def test_recipe_output_dependency_cycle(self):
        """Cycle in output dependencies should be caught."""
        data = {
            "version": "1.0",
            "name": "test",
            "inputs": [],
            "outputs": [
                {"id": "a", "type": "data", "recipe": {"command": "run_a", "inputs": ["b"]}},
                {"id": "b", "type": "data", "recipe": {"command": "run_b", "inputs": ["a"]}},
            ],
        }
        errors = validate_analysis(data)
        codes = [e.code for e in errors]
        assert "RECIPE_CYCLE" in codes

    def test_valid_recipe_on_output(self):
        """Valid inline recipe should pass validation."""
        data = {
            "version": "1.0",
            "name": "test",
            "inputs": [],
            "outputs": [
                {"id": "cleaned", "type": "data", "recipe": {"command": "python clean.py"}},
                {
                    "id": "result",
                    "type": "metric",
                    "recipe": {
                        "command": "python analyze.py",
                        "inputs": ["cleaned"],
                    },
                },
            ],
        }
        errors = validate_analysis(data)
        assert len(errors) == 0

    def test_valid_recipe_no_inputs(self):
        """Recipe with no inputs should pass validation."""
        data = {
            "version": "1.0",
            "name": "test",
            "inputs": [],
            "outputs": [
                {
                    "id": "result",
                    "type": "metric",
                    "recipe": {
                        "command": "python run.py",
                    },
                },
            ],
        }
        errors = validate_analysis(data)
        assert len(errors) == 0

    def test_self_referencing_recipe_input(self):
        """Recipe input referencing its own output should create a cycle."""
        data = {
            "version": "1.0",
            "name": "test",
            "inputs": [],
            "outputs": [
                {"id": "a", "type": "data", "recipe": {"command": "run_a", "inputs": ["a"]}},
            ],
        }
        errors = validate_analysis(data)
        codes = [e.code for e in errors]
        assert "RECIPE_CYCLE" in codes


class TestRecipeHelpers:
    """Tests for recipe helper functions."""

    def test_get_output_dependencies(self):
        """get_output_dependencies should return output-to-output DAG."""
        from astra.helpers import get_output_dependencies

        data = {
            "outputs": [
                {"id": "clean", "type": "data", "recipe": {"command": "clean.py"}},
                {
                    "id": "train",
                    "type": "data",
                    "recipe": {
                        "command": "train.py",
                        "inputs": ["clean"],
                    },
                },
                {
                    "id": "eval",
                    "type": "metric",
                    "recipe": {
                        "command": "eval.py",
                        "inputs": ["train"],
                    },
                },
                {"id": "external", "type": "data"},  # no recipe
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


class TestSuccessCriteriaValidation:
    """Tests for structured success criteria."""

    def test_valid_success_criteria(self, valid_dir: Path):
        """Structured criteria with valid output refs should pass."""
        errors = validate_analysis_file(valid_dir / "success_criteria.yaml")
        assert errors == []

    def test_valid_success_criteria_schema(self, valid_dir: Path):
        """Structured success criteria should pass schema validation."""
        errors = validate_analysis_schema(valid_dir / "success_criteria.yaml")
        assert errors == []

    def test_condition_without_output(self, invalid_dir: Path):
        """Condition set without output should fail semantic validation."""
        errors = validate_analysis_file(invalid_dir / "success_criteria_condition_no_output.yaml")
        assert any(e.code == "CRITERION_CONDITION_NO_OUTPUT" for e in errors)

    def test_bad_output_reference(self, invalid_dir: Path):
        """Criterion referencing non-existent output should fail semantic validation."""
        errors = validate_analysis_file(invalid_dir / "success_criteria_bad_output.yaml")
        assert any(e.code == "INVALID_CRITERION_OUTPUT" for e in errors)


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


class TestConditionalOutputsUniverse:
    """Tests for universe validation with conditional outputs."""

    def test_valid_universe_with_conditional_outputs(self, valid_dir: Path):
        """Universe should validate against analysis with conditional outputs."""
        analysis_data = load_yaml(valid_dir / "conditional_outputs.yaml")
        universe_data = load_yaml(valid_dir / "conditional_outputs_universe.yaml")
        errors = validate_universe(universe_data, analysis_data)
        assert errors == []
