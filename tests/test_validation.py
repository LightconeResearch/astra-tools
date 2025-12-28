"""Tests for validation modules."""

from pathlib import Path

from asp.models.analysis import Analysis
from asp.validation.schema import (
    is_valid_analysis,
    is_valid_universe,
    validate_analysis_schema,
    validate_universe_schema,
)
from asp.validation.semantic import (
    SemanticError,
    validate_analysis,
    validate_analysis_file,
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
        errors = validate_analysis_schema(invalid_dir / "missing_version.yaml")
        assert len(errors) > 0
        assert any("version" in e.lower() for e in errors)

    def test_missing_problem(self, invalid_dir: Path):
        errors = validate_analysis_schema(invalid_dir / "missing_problem.yaml")
        assert len(errors) > 0
        assert any("problem" in e.lower() for e in errors)

    def test_invalid_input_type(self, invalid_dir: Path):
        errors = validate_analysis_schema(invalid_dir / "invalid_input_type.yaml")
        assert len(errors) > 0

    def test_invalid_output_type(self, invalid_dir: Path):
        errors = validate_analysis_schema(invalid_dir / "invalid_output_type.yaml")
        assert len(errors) > 0

    def test_invalid_decision_type(self, invalid_dir: Path):
        errors = validate_analysis_schema(invalid_dir / "invalid_decision_type.yaml")
        assert len(errors) > 0


class TestSemanticValidation:
    """Tests for semantic validation."""

    def test_valid_analysis(self, full_analysis_path: Path):
        analysis = Analysis.from_yaml(full_analysis_path)
        errors = validate_analysis(analysis)
        assert errors == []

    def test_valid_analysis_file(self, full_analysis_path: Path):
        errors = validate_analysis_file(full_analysis_path)
        assert errors == []

    def test_duplicate_input_ids(self, invalid_dir: Path):
        # This will fail at Pydantic level or we need to check semantically
        # The schema allows it but semantic validation should catch it
        errors = validate_analysis_file(invalid_dir / "duplicate_input_ids.yaml")
        assert any(e.code == "DUPLICATE_INPUT" for e in errors)

    def test_duplicate_output_ids(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "duplicate_output_ids.yaml")
        assert any(e.code == "DUPLICATE_OUTPUT" for e in errors)

    def test_invalid_evidence_ref(self, invalid_dir: Path):
        errors = validate_analysis_file(invalid_dir / "invalid_evidence_ref.yaml")
        assert any(e.code == "INVALID_EVIDENCE_REF" for e in errors)

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
