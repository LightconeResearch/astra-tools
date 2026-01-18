"""Tests for workflow mapping logic."""

from pathlib import Path

import pytest

from asp.models.analysis import Analysis
from asp.models.universe import Universe
from asp.workflow.mapping import (
    apply_naming_convention,
    extract_decision_values,
    generate_cwl_params,
)


class TestApplyNamingConvention:
    """Tests for apply_naming_convention function."""

    def test_simple_int_value(self):
        """Simple int value maps to decision_id."""
        result = apply_naming_convention("seed", 42)
        assert result == {"seed": 42}

    def test_simple_float_value(self):
        """Simple float value maps to decision_id."""
        result = apply_naming_convention("test_size", 0.2)
        assert result == {"test_size": 0.2}

    def test_simple_string_value(self):
        """Simple string value maps to decision_id."""
        result = apply_naming_convention("model", "random_forest")
        assert result == {"model": "random_forest"}

    def test_simple_bool_value(self):
        """Simple bool value maps to decision_id."""
        result = apply_naming_convention("use_cache", True)
        assert result == {"use_cache": True}

    def test_dict_single_key(self):
        """Dict with single key maps to decision_id_key."""
        result = apply_naming_convention("scaling", {"method": "standard"})
        assert result == {"scaling_method": "standard"}

    def test_dict_multiple_keys(self):
        """Dict with multiple keys maps to decision_id_key for each."""
        result = apply_naming_convention(
            "scaling", {"method": "standard", "with_mean": True}
        )
        assert result == {"scaling_method": "standard", "scaling_with_mean": True}

    def test_list_value(self):
        """List value passes through with decision_id."""
        result = apply_naming_convention("features", ["a", "b", "c"])
        assert result == {"features": ["a", "b", "c"]}


class TestExtractDecisionValues:
    """Tests for extract_decision_values function."""

    @pytest.fixture
    def analysis_with_values(self) -> Analysis:
        """Analysis with options that have value fields."""
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
                    "test_size": {
                        "label": "Test Size",
                        "type": "parameter",
                        "default": "split_20",
                        "options": {
                            "split_20": {"label": "20%", "value": 0.2},
                            "split_30": {"label": "30%", "value": 0.3},
                        },
                    },
                    "model": {
                        "label": "Model",
                        "type": "method",
                        "default": "rf",
                        "options": {
                            "rf": {"label": "Random Forest"},  # No value field
                            "svm": {"label": "SVM"},
                        },
                    },
                },
            }
        )

    def test_extract_with_value_field(self, analysis_with_values: Analysis):
        """Options with value field return the value."""
        universe = Universe.model_validate(
            {
                "id": "test",
                "decisions": {"test_size": "split_20", "model": "rf"},
            }
        )
        values = extract_decision_values(analysis_with_values, universe)
        assert values["test_size"] == 0.2

    def test_extract_without_value_field(self, analysis_with_values: Analysis):
        """Options without value field return option_id as string."""
        universe = Universe.model_validate(
            {
                "id": "test",
                "decisions": {"test_size": "split_20", "model": "rf"},
            }
        )
        values = extract_decision_values(analysis_with_values, universe)
        assert values["model"] == "rf"

    def test_extract_ignores_unknown_decisions(self, analysis_with_values: Analysis):
        """Unknown decisions in universe are ignored."""
        universe = Universe.model_validate(
            {
                "id": "test",
                "decisions": {
                    "test_size": "split_20",
                    "model": "rf",
                    "unknown": "option",
                },
            }
        )
        values = extract_decision_values(analysis_with_values, universe)
        assert "unknown" not in values


class TestGenerateCWLParams:
    """Tests for generate_cwl_params function."""

    @pytest.fixture
    def full_analysis(self) -> Analysis:
        """Analysis with various value types."""
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
                    "test_size": {
                        "label": "Test Size",
                        "type": "parameter",
                        "default": "split_20",
                        "options": {
                            "split_20": {"label": "20%", "value": 0.2},
                        },
                    },
                    "scaling": {
                        "label": "Scaling",
                        "type": "method",
                        "default": "standard",
                        "options": {
                            "standard": {
                                "label": "Standard",
                                "value": {"method": "standard", "with_mean": True},
                            },
                        },
                    },
                    "model": {
                        "label": "Model",
                        "type": "method",
                        "default": "rf",
                        "options": {
                            "rf": {"label": "Random Forest"},
                        },
                    },
                },
            }
        )

    def test_generate_mixed_params(self, full_analysis: Analysis):
        """Generate params with mixed value types."""
        universe = Universe.model_validate(
            {
                "id": "test",
                "decisions": {
                    "test_size": "split_20",
                    "scaling": "standard",
                    "model": "rf",
                },
            }
        )
        params = generate_cwl_params(full_analysis, universe)

        # Simple value
        assert params["test_size"] == 0.2

        # Dict value flattened
        assert params["scaling_method"] == "standard"
        assert params["scaling_with_mean"] is True

        # No value field - uses option_id
        assert params["model"] == "rf"
