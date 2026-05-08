"""Tests for schema validation using astra-spec Pydantic models."""

from unittest.mock import patch

from astra.validation.schema import (
    check_spec_version,
    validate_analysis_data,
    validate_universe_data,
)


class TestAnalysisValidation:
    """Tests that analysis data validates correctly via Pydantic models."""

    def test_valid_analysis_passes(self):
        data = {
            "version": "0.0.10",
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
            "version": "0.0.10",
            "name": "test",
            "inputs": [{"id": "x", "type": "INVALID"}],
        }
        errors = validate_analysis_data(data)
        assert len(errors) > 0

    def test_extra_fields_rejected(self):
        data = {
            "version": "0.0.10",
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


class TestCheckSpecVersion:
    """Tests for the spec-version compatibility warning."""

    def test_match_returns_none(self):
        with patch("astra.validation.schema.installed_spec_version", return_value="0.0.10"):
            assert check_spec_version({"version": "0.0.10"}) is None

    def test_two_part_normalizes_to_three(self):
        with patch("astra.validation.schema.installed_spec_version", return_value="1.0.0"):
            assert check_spec_version({"version": "1.0"}) is None

    def test_mismatch_returns_warning(self):
        with patch("astra.validation.schema.installed_spec_version", return_value="0.1.0"):
            warning = check_spec_version({"version": "0.0.10"})
            assert warning is not None
            assert "0.0.10" in warning
            assert "0.1.0" in warning

    def test_missing_declared_version_returns_none(self):
        with patch("astra.validation.schema.installed_spec_version", return_value="0.0.10"):
            assert check_spec_version({}) is None

    def test_unknown_installed_version_returns_none(self):
        with patch("astra.validation.schema.installed_spec_version", return_value=None):
            assert check_spec_version({"version": "0.0.10"}) is None

    def test_unparseable_declared_version_returns_none(self):
        with patch("astra.validation.schema.installed_spec_version", return_value="0.0.10"):
            assert check_spec_version({"version": "not-a-version"}) is None
