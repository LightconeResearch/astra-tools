"""Tests for schema validation using astra-spec Pydantic models."""

import copy

from astra.validation.schema import (
    _inject_ids_inplace,
    _inject_nested_analysis_ids,
    _remap_from_field,
    validate_analysis_data,
    validate_universe_data,
)


# =============================================================================
# Preprocessing unit tests
# =============================================================================


class TestRemapFromField:
    """Tests for the ``from`` → ``from_ref`` keyword remapping."""

    def test_renames_from_to_from_ref(self):
        obj: dict = {"from": "../parent_input"}
        _remap_from_field(obj)
        assert "from" not in obj
        assert obj["from_ref"] == "../parent_input"

    def test_noop_when_no_from(self):
        obj: dict = {"id": "x", "type": "data"}
        _remap_from_field(obj)
        assert obj == {"id": "x", "type": "data"}

    def test_does_not_overwrite_existing_from_ref(self):
        obj: dict = {"from": "new_value", "from_ref": "existing_value"}
        _remap_from_field(obj)
        assert obj["from_ref"] == "existing_value"
        assert "from" not in obj


class TestInjectIdsInplace:
    """Tests for injecting dict keys as ``id`` fields before Pydantic validation."""

    def test_injects_decision_ids(self):
        data: dict = {
            "decisions": {
                "method": {"label": "Method", "options": {"a": {"label": "A"}}},
            }
        }
        _inject_ids_inplace(data)
        assert data["decisions"]["method"]["id"] == "method"

    def test_injects_decision_option_ids(self):
        data: dict = {
            "decisions": {
                "method": {
                    "label": "Method",
                    "options": {"a": {"label": "A"}, "b": {"label": "B"}},
                },
            }
        }
        _inject_ids_inplace(data)
        assert data["decisions"]["method"]["options"]["a"]["id"] == "a"
        assert data["decisions"]["method"]["options"]["b"]["id"] == "b"

    def test_injects_prior_insight_ids(self):
        data: dict = {
            "prior_insights": {
                "smith2024": {"claim": "Some claim"},
            }
        }
        _inject_ids_inplace(data)
        assert data["prior_insights"]["smith2024"]["id"] == "smith2024"

    def test_injects_finding_ids(self):
        data: dict = {
            "findings": {
                "result1": {"claim": "A result"},
            }
        }
        _inject_ids_inplace(data)
        assert data["findings"]["result1"]["id"] == "result1"

    def test_injects_analysis_ids_and_recurses(self):
        data: dict = {
            "analyses": {
                "sub": {
                    "inputs": [{"id": "x", "from": "../y"}],
                    "decisions": {
                        "inner": {"label": "Inner", "options": {"c": {"label": "C"}}},
                    },
                }
            }
        }
        _inject_ids_inplace(data)
        assert data["analyses"]["sub"]["id"] == "sub"
        # Recursion: inner decision gets id injected
        assert data["analyses"]["sub"]["decisions"]["inner"]["id"] == "inner"
        assert data["analyses"]["sub"]["decisions"]["inner"]["options"]["c"]["id"] == "c"

    def test_remaps_from_on_inputs(self):
        data: dict = {
            "inputs": [{"id": "x", "from": "../parent_input"}],
        }
        _inject_ids_inplace(data)
        assert data["inputs"][0]["from_ref"] == "../parent_input"
        assert "from" not in data["inputs"][0]

    def test_remaps_from_on_outputs(self):
        data: dict = {
            "outputs": [{"id": "y", "from": "../parent_output"}],
        }
        _inject_ids_inplace(data)
        assert data["outputs"][0]["from_ref"] == "../parent_output"
        assert "from" not in data["outputs"][0]

    def test_remaps_from_on_decisions(self):
        data: dict = {
            "decisions": {
                "scaling": {"from": "../parent_scaling"},
            }
        }
        _inject_ids_inplace(data)
        assert data["decisions"]["scaling"]["from_ref"] == "../parent_scaling"
        assert "from" not in data["decisions"]["scaling"]

    def test_remaps_from_on_sub_analysis_inputs(self):
        """``from`` on inputs inside nested analyses should be remapped."""
        data: dict = {
            "analyses": {
                "sub": {
                    "inputs": [{"id": "a", "from": "../b"}],
                    "outputs": [{"id": "out", "from": "../other"}],
                }
            }
        }
        _inject_ids_inplace(data)
        assert data["analyses"]["sub"]["inputs"][0]["from_ref"] == "../b"
        assert data["analyses"]["sub"]["outputs"][0]["from_ref"] == "../other"

    def test_does_not_overwrite_existing_ids(self):
        data: dict = {
            "decisions": {
                "method": {"id": "custom_id", "label": "Method", "options": {}},
            }
        }
        _inject_ids_inplace(data)
        assert data["decisions"]["method"]["id"] == "custom_id"

    def test_does_not_mutate_original(self):
        """validate_analysis_data deep-copies before calling _inject_ids_inplace,
        but verify _inject_ids_inplace itself mutates only the passed dict."""
        original: dict = {
            "decisions": {"m": {"label": "M", "options": {"a": {"label": "A"}}}},
        }
        data = copy.deepcopy(original)
        _inject_ids_inplace(data)
        # Original should be untouched
        assert "id" not in original["decisions"]["m"]

    def test_handles_empty_data(self):
        data: dict = {}
        _inject_ids_inplace(data)
        assert data == {}

    def test_handles_non_dict_values_in_keyed_fields(self):
        """String values in decisions (e.g. universe format) should be skipped."""
        data: dict = {
            "decisions": {"method": "option_a"},
        }
        _inject_ids_inplace(data)
        assert data["decisions"]["method"] == "option_a"


class TestInjectNestedAnalysisIds:
    """Tests for universe-style nested analysis ID injection."""

    def test_injects_analysis_ids(self):
        node: dict = {
            "analyses": {
                "sub1": {"decisions": {"a": "x"}},
                "sub2": {"decisions": {"b": "y"}},
            }
        }
        _inject_nested_analysis_ids(node)
        assert node["analyses"]["sub1"]["id"] == "sub1"
        assert node["analyses"]["sub2"]["id"] == "sub2"

    def test_recurses_into_nested_analyses(self):
        node: dict = {
            "analyses": {
                "outer": {
                    "analyses": {
                        "inner": {"decisions": {"a": "x"}},
                    }
                }
            }
        }
        _inject_nested_analysis_ids(node)
        assert node["analyses"]["outer"]["id"] == "outer"
        assert node["analyses"]["outer"]["analyses"]["inner"]["id"] == "inner"

    def test_noop_when_no_analyses(self):
        node: dict = {"decisions": {"a": "x"}}
        _inject_nested_analysis_ids(node)
        assert node == {"decisions": {"a": "x"}}

    def test_noop_when_analyses_is_not_dict(self):
        node: dict = {"analyses": "not_a_dict"}
        _inject_nested_analysis_ids(node)
        assert node["analyses"] == "not_a_dict"


# =============================================================================
# Integration tests (full validation pipeline)
# =============================================================================


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
