"""Tests for schema validation using astra-spec Pydantic models."""

from astra.validation.schema import (
    validate_analysis_data,
    validate_universe_data,
)


class TestAnalysisValidation:
    """Tests that analysis data validates correctly via Pydantic models."""

    def test_valid_analysis_passes(self):
        data = {
            "version": "0.1",
            "name": "test",
            "inputs": [{"id": "data", "type": "data"}],
            "outputs": [{"id": "result", "type": "metric"}],
            "decisions": {
                "method": {
                    "label": "Method",
                    "default": "a",
                    "options": {"a": {"label": "A"}},
                }
            },
        }
        errors = validate_analysis_data(data)
        assert errors == []

    def test_invalid_type_caught(self):
        data = {"version": 123, "name": "test"}  # version should be string
        errors = validate_analysis_data(data)
        assert any("version" in e for e in errors)

    def test_invalid_enum_caught(self):
        data = {
            "version": "0.1",
            "name": "test",
            "inputs": [{"id": "x", "type": "INVALID"}],
        }
        errors = validate_analysis_data(data)
        assert len(errors) > 0

    def test_extra_fields_rejected(self):
        data = {
            "version": "0.1",
            "name": "test",
            "bogus_field": "should fail",
        }
        errors = validate_analysis_data(data)
        assert any("bogus_field" in e for e in errors)


class TestUniverseValidation:
    """Tests that universe data validates correctly via Pydantic models."""

    def test_valid_universe_passes(self):
        data = {
            "id": "baseline",
            "decisions": {"method": "a"},
        }
        errors = validate_universe_data(data)
        assert errors == []

    def test_missing_id_caught(self):
        data = {"decisions": {"method": "a"}}
        errors = validate_universe_data(data)
        assert any("id" in e for e in errors)
