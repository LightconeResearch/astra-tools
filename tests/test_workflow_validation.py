"""Tests for workflow validation logic."""

from pathlib import Path

import pytest

from asp.models.analysis import Analysis
from asp.workflow.parser import parse_cwl_inputs
from asp.workflow.validator import (
    get_decision_param_mapping,
    get_unmapped_cwl_params,
    validate_decision_coverage,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
WORKFLOWS_DIR = FIXTURES_DIR / "workflows"


class TestParseCWLInputs:
    """Tests for CWL input parsing."""

    def test_parse_simple_cwl(self):
        """Parse simple CWL with basic types."""
        params = parse_cwl_inputs(WORKFLOWS_DIR / "simple.cwl")
        names = {p.name for p in params}
        assert "model" in names
        assert "test_split" in names
        assert "seed" in names
        assert "preprocessing" in names

    def test_parse_required_vs_optional(self):
        """Distinguish required and optional parameters."""
        params = parse_cwl_inputs(WORKFLOWS_DIR / "simple.cwl")
        param_dict = {p.name: p for p in params}

        # Required params
        assert param_dict["model"].required is True
        assert param_dict["test_split"].required is True
        assert param_dict["seed"].required is True

        # Optional param (type: string?)
        assert param_dict["preprocessing"].required is False

    def test_parse_types(self):
        """Parse CWL type definitions."""
        params = parse_cwl_inputs(WORKFLOWS_DIR / "simple.cwl")
        param_dict = {p.name: p for p in params}

        assert param_dict["model"].type == "string"
        assert param_dict["test_split"].type == "float"
        assert param_dict["seed"].type == "int"
        assert param_dict["preprocessing"].type == "string"

    def test_file_not_found(self):
        """Raise error for non-existent file."""
        with pytest.raises(FileNotFoundError):
            parse_cwl_inputs(WORKFLOWS_DIR / "nonexistent.cwl")


class TestValidateDecisionCoverage:
    """Tests for decision coverage validation."""

    @pytest.fixture
    def full_analysis(self) -> Analysis:
        """Analysis matching the simple.cwl fixture."""
        return Analysis.model_validate(
            {
                "version": "1.0",
                "analysis": {
                    "name": "Test",
                    "problem": "Test problem",
                    "inputs": [{"id": "data", "type": "data"}],
                    "outputs": [{"id": "accuracy", "type": "metric", "dtype": "float"}],
                },
                "decisions": {
                    "model": {
                        "label": "Model",
                        "type": "method",
                        "default": "rf",
                        "options": {
                            "rf": {"label": "Random Forest"},
                            "svm": {"label": "SVM"},
                        },
                    },
                    "test_split": {
                        "label": "Test Split",
                        "type": "parameter",
                        "default": "split_20",
                        "options": {
                            "split_20": {"label": "20%", "value": 0.2},
                        },
                    },
                    "seed": {
                        "label": "Seed",
                        "type": "parameter",
                        "default": "seed_42",
                        "options": {
                            "seed_42": {"label": "42", "value": 42},
                        },
                    },
                    "preprocessing": {
                        "label": "Preprocessing",
                        "type": "method",
                        "default": "none",
                        "options": {
                            "none": {"label": "None"},
                            "standard": {"label": "Standard"},
                        },
                    },
                },
            }
        )

    def test_valid_mapping(self, full_analysis: Analysis):
        """All decisions map to CWL params."""
        errors = validate_decision_coverage(full_analysis, WORKFLOWS_DIR / "simple.cwl")
        assert errors == []

    def test_unmapped_decision_detected(self):
        """Detect when decision doesn't map to CWL param."""
        # Analysis with extra decision not in CWL
        analysis = Analysis.model_validate(
            {
                "version": "1.0",
                "analysis": {
                    "name": "Test",
                    "problem": "Test problem",
                    "inputs": [{"id": "data", "type": "data"}],
                    "outputs": [{"id": "result", "type": "metric", "dtype": "float"}],
                },
                "decisions": {
                    "model": {
                        "label": "Model",
                        "type": "method",
                        "default": "rf",
                        "options": {"rf": {"label": "RF"}},
                    },
                    "extra_decision": {
                        "label": "Extra",
                        "type": "parameter",
                        "default": "a",
                        "options": {"a": {"label": "A"}},
                    },
                },
            }
        )
        errors = validate_decision_coverage(analysis, WORKFLOWS_DIR / "simple.cwl")
        assert any(e.code == "UNMAPPED_DECISION" for e in errors)
        assert any("extra_decision" in str(e) for e in errors)

    def test_unused_parameter_detected(self):
        """Detect required CWL param not covered by ASP."""
        # Analysis missing some decisions that CWL requires
        analysis = Analysis.model_validate(
            {
                "version": "1.0",
                "analysis": {
                    "name": "Test",
                    "problem": "Test problem",
                    "inputs": [{"id": "data", "type": "data"}],
                    "outputs": [{"id": "result", "type": "metric", "dtype": "float"}],
                },
                "decisions": {
                    "model": {
                        "label": "Model",
                        "type": "method",
                        "default": "rf",
                        "options": {"rf": {"label": "RF"}},
                    },
                },
            }
        )
        errors = validate_decision_coverage(analysis, WORKFLOWS_DIR / "partial.cwl")
        # partial.cwl has extra_required which is not in ASP
        assert any(e.code == "UNUSED_PARAMETER" for e in errors)
        assert any("extra_required" in str(e) for e in errors)


class TestDictValueMapping:
    """Tests for dict value to CWL param mapping."""

    @pytest.fixture
    def analysis_with_dict_values(self) -> Analysis:
        """Analysis with dict value options."""
        return Analysis.model_validate(
            {
                "version": "1.0",
                "analysis": {
                    "name": "Test",
                    "problem": "Test problem",
                    "inputs": [{"id": "data", "type": "data"}],
                    "outputs": [{"id": "result", "type": "metric", "dtype": "float"}],
                },
                "decisions": {
                    "scaling": {
                        "label": "Scaling",
                        "type": "method",
                        "default": "standard",
                        "options": {
                            "standard": {
                                "label": "Standard",
                                "value": {"method": "standard", "with_mean": True},
                            },
                            "minmax": {
                                "label": "MinMax",
                                "value": {"method": "minmax", "with_mean": False},
                            },
                        },
                    },
                    "model": {
                        "label": "Model",
                        "type": "method",
                        "default": "rf",
                        "options": {"rf": {"label": "RF"}},
                    },
                    "test_size": {
                        "label": "Test Size",
                        "type": "parameter",
                        "default": "split_20",
                        "options": {
                            "split_20": {"label": "20%", "value": 0.2},
                        },
                    },
                },
            }
        )

    def test_dict_value_maps_to_cwl(self, analysis_with_dict_values: Analysis):
        """Dict values like {method: x} map to scaling_method CWL param."""
        errors = validate_decision_coverage(
            analysis_with_dict_values, WORKFLOWS_DIR / "with_dict_params.cwl"
        )
        assert errors == []

    def test_decision_param_mapping(self, analysis_with_dict_values: Analysis):
        """Get correct mapping for dict values."""
        mapping = get_decision_param_mapping(
            analysis_with_dict_values, WORKFLOWS_DIR / "with_dict_params.cwl"
        )
        assert "scaling_method" in mapping.get("scaling", [])
        assert "scaling_with_mean" in mapping.get("scaling", [])


class TestGetUnmappedCWLParams:
    """Tests for get_unmapped_cwl_params function."""

    def test_get_unmapped_params(self):
        """Get CWL params that don't map to ASP decisions."""
        analysis = Analysis.model_validate(
            {
                "version": "1.0",
                "analysis": {
                    "name": "Test",
                    "problem": "Test problem",
                    "inputs": [{"id": "data", "type": "data"}],
                    "outputs": [{"id": "result", "type": "metric", "dtype": "float"}],
                },
                "decisions": {
                    "model": {
                        "label": "Model",
                        "type": "method",
                        "default": "rf",
                        "options": {"rf": {"label": "RF"}},
                    },
                },
            }
        )
        unmapped = get_unmapped_cwl_params(analysis, WORKFLOWS_DIR / "partial.cwl")
        unmapped_names = {p.name for p in unmapped}
        assert "extra_required" in unmapped_names
