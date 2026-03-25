"""Tests for schema generation."""

import json
from pathlib import Path

from astra.validation.schema import get_analysis_schema, get_insights_schema, get_universe_schema


class TestSchemaGeneration:
    """Tests for JSON schema generation from Pydantic models."""

    def test_get_analysis_schema(self):
        schema = get_analysis_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "version" in schema["properties"]
        assert "decisions" in schema["properties"]

    def test_get_universe_schema(self):
        schema = get_universe_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "id" in schema["properties"]
        assert "decisions" in schema["properties"]

    def test_get_insights_schema(self):
        schema = get_insights_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "insights" in schema["properties"]

    def test_analysis_schema_has_defs(self):
        schema = get_analysis_schema()
        assert "$defs" in schema
        # Should have definitions for nested models
        defs = schema["$defs"]
        assert "Analysis" in defs
        assert "Input" in defs
        assert "Output" in defs
        assert "Decision" in defs
        assert "Option" in defs
        assert "Recipe" in defs
        assert "Resources" in defs

    def test_schema_is_valid_json(self):
        # Schemas should be JSON-serializable
        analysis_schema = get_analysis_schema()
        universe_schema = get_universe_schema()
        insights_schema = get_insights_schema()

        # Should not raise
        json.dumps(analysis_schema)
        json.dumps(universe_schema)
        json.dumps(insights_schema)

    def test_export_schemas(self, tmp_path: Path):
        """Test that schemas can be written to files."""
        schemas = {
            "analysis.schema.json": get_analysis_schema(),
            "universe.schema.json": get_universe_schema(),
            "insights.schema.json": get_insights_schema(),
        }

        for name, schema_data in schemas.items():
            with open(tmp_path / name, "w") as f:
                json.dump(schema_data, f, indent=2)

        analysis_path = tmp_path / "analysis.schema.json"
        universe_path = tmp_path / "universe.schema.json"

        assert analysis_path.exists()
        assert universe_path.exists()

        # Load and verify they're valid JSON
        with open(analysis_path) as f:
            analysis_schema = json.load(f)
        assert "properties" in analysis_schema

        with open(universe_path) as f:
            universe_schema = json.load(f)
        assert "properties" in universe_schema

    def test_export_schemas_creates_directory(self, tmp_path: Path):
        nested_path = tmp_path / "nested" / "schemas"
        nested_path.mkdir(parents=True, exist_ok=True)

        schemas = {
            "analysis.schema.json": get_analysis_schema(),
            "universe.schema.json": get_universe_schema(),
        }

        for name, schema_data in schemas.items():
            with open(nested_path / name, "w") as f:
                json.dump(schema_data, f, indent=2)

        assert nested_path.exists()
        assert (nested_path / "analysis.schema.json").exists()

    def test_analysis_schema_metadata(self):
        schema = get_analysis_schema()
        # Check that schema metadata from json_schema_extra is present
        assert schema.get("$schema") == "http://json-schema.org/draft-07/schema#"
        assert schema.get("$id") == "https://astra-spec.org/v1/analysis.schema.json"
        assert schema.get("title") == "ASTRA Analysis Specification"

    def test_universe_schema_metadata(self):
        schema = get_universe_schema()
        assert schema.get("$schema") == "http://json-schema.org/draft-07/schema#"
        assert schema.get("$id") == "https://astra-spec.org/v1/universe.schema.json"
        assert schema.get("title") == "ASTRA Universe Specification"

    def test_schema_has_descriptions(self):
        schema = get_analysis_schema()
        # Check that fields have descriptions
        version_prop = schema["properties"]["version"]
        assert "description" in version_prop

    def test_decision_options_in_schema(self):
        schema = get_analysis_schema()
        decision_def = schema["$defs"]["Decision"]
        assert "options" in decision_def["properties"]
        # Options should allow additional properties (dynamic option IDs)
        options_prop = decision_def["properties"]["options"]
        # Options is now Optional[dict[str, Option]], so it uses anyOf with object | null
        if "anyOf" in options_prop:
            obj_schema = next(s for s in options_prop["anyOf"] if s.get("type") == "object")
            assert "additionalProperties" in obj_schema
        else:
            assert "additionalProperties" in options_prop
