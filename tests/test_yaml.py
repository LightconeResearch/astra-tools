"""Tests for YAML loading, validation, and helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from astra.helpers import (
    generate_default_universe,
    get_decision,
    get_decisions,
    get_input,
    get_local_decisions,
    get_option,
    get_output,
    get_output_dependencies,
    get_sub_analysis,
    get_universe,
    get_universe_selections,
    is_condition_met,
    walk_decisions,
)
from astra.loader import load_analysis, load_yaml, validate_yaml

EXAMPLES = Path(__file__).parent.parent / "examples"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


class TestLoading:
    def test_load_iris(self) -> None:
        data = load_yaml(EXAMPLES / "iris")
        assert data["name"] == "iris_classification"
        assert data["astra_version"] == "1.0"
        assert len(data["inputs"]) == 2
        assert len(data["outputs"]) == 6
        assert len(data["decisions"]) == 4
        assert len(data["universes"]) == 2

    def test_load_pipeline(self) -> None:
        data = load_yaml(EXAMPLES / "iris_pipeline")
        assert data["name"] == "iris_pipeline"
        assert "feature_extraction" in data["analyses"]
        assert "classification" in data["analyses"]

    def test_load_pydantic(self) -> None:
        analysis = load_analysis(EXAMPLES / "iris")
        assert analysis.name == "iris_classification"
        assert len(analysis.inputs) == 2
        assert len(analysis.decisions) == 4


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_iris(self) -> None:
        data = load_yaml(EXAMPLES / "iris")
        errors = validate_yaml(data)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_valid_pipeline(self) -> None:
        data = load_yaml(EXAMPLES / "iris_pipeline")
        errors = validate_yaml(data)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_invalid_output_type(self) -> None:
        data = {
            "name": "test",
            "astra_version": "1.0",
            "outputs": [{"name": "x", "type": "INVALID"}],
        }
        errors = validate_yaml(data)
        assert any("INVALID" in e for e in errors)

    def test_invalid_id_pattern(self) -> None:
        data = {"name": "BadName", "astra_version": "1.0"}
        errors = validate_yaml(data)
        assert len(errors) > 0

    def test_invalid_version(self) -> None:
        data = {"name": "test", "astra_version": "abc"}
        errors = validate_yaml(data)
        assert len(errors) > 0

    def test_missing_required(self) -> None:
        data = {"name": "test"}  # missing astra_version
        errors = validate_yaml(data)
        assert any("astra_version" in e for e in errors)


# ---------------------------------------------------------------------------
# Helpers: entity accessors
# ---------------------------------------------------------------------------


class TestEntityAccessors:
    @pytest.fixture
    def iris(self) -> dict:
        return load_yaml(EXAMPLES / "iris")

    @pytest.fixture
    def pipeline(self) -> dict:
        return load_yaml(EXAMPLES / "iris_pipeline")

    def test_get_input(self, iris: dict) -> None:
        inp = get_input(iris, "iris_data")
        assert inp is not None
        assert inp["type"] == "data"
        assert inp["source"] == "sklearn.datasets.load_iris"

    def test_get_input_missing(self, iris: dict) -> None:
        assert get_input(iris, "nonexistent") is None

    def test_get_output(self, iris: dict) -> None:
        out = get_output(iris, "accuracy")
        assert out is not None
        assert out["type"] == "metric"

    def test_get_decision(self, iris: dict) -> None:
        dec = get_decision(iris, "scaling")
        assert dec is not None
        assert dec["label"] == "Feature Scaling"
        assert "standard" in dec["options"]

    def test_get_option(self, iris: dict) -> None:
        opt = get_option(iris, "scaling", "standard")
        assert opt is not None
        assert opt["label"] == "StandardScaler"

    def test_get_option_missing(self, iris: dict) -> None:
        assert get_option(iris, "scaling", "nonexistent") is None
        assert get_option(iris, "nonexistent", "a") is None

    def test_get_universe(self, iris: dict) -> None:
        u = get_universe(iris, "baseline")
        assert u is not None
        assert u["description"] == "Default configuration using standard practices"

    def test_get_sub_analysis(self, pipeline: dict) -> None:
        fe = get_sub_analysis(pipeline, "feature_extraction")
        assert fe is not None
        assert fe["label"] == "Feature Extraction"

    def test_local_decisions_excludes_delegated(self, pipeline: dict) -> None:
        fe = get_sub_analysis(pipeline, "feature_extraction")
        assert fe is not None
        all_decs = get_decisions(fe)
        local = get_local_decisions(fe)
        assert "seed" in all_decs  # delegated
        assert "seed" not in local  # excluded
        assert "method" in local


# ---------------------------------------------------------------------------
# Tree walking
# ---------------------------------------------------------------------------


class TestTreeWalking:
    def test_walk_flat(self) -> None:
        data = load_yaml(EXAMPLES / "iris")
        results = list(walk_decisions(data))
        names = [name for _, name, _ in results]
        assert "scaling" in names
        assert "model" in names
        assert all(path == "" for path, _, _ in results)

    def test_walk_nested(self) -> None:
        data = load_yaml(EXAMPLES / "iris_pipeline")
        results = list(walk_decisions(data))
        paths_and_names = [(p, n) for p, n, _ in results]
        # Root decisions
        assert ("", "test_split") in paths_and_names
        assert ("", "random_seed") in paths_and_names
        # Sub-analysis decisions (delegated excluded)
        assert ("feature_extraction/", "method") in paths_and_names
        assert ("feature_extraction/", "n_components") in paths_and_names
        assert ("classification/", "classifier") in paths_and_names
        # Delegated should NOT appear
        delegated = [n for _, n, _ in results if n in ("seed", "split")]
        assert delegated == []


# ---------------------------------------------------------------------------
# Universe helpers
# ---------------------------------------------------------------------------


class TestUniverseHelpers:
    def test_get_selections(self) -> None:
        data = load_yaml(EXAMPLES / "iris")
        sels = get_universe_selections(data, "baseline")
        assert sels["scaling"] == "standard"
        assert sels["model"] == "random_forest"

    def test_get_selections_pipeline(self) -> None:
        data = load_yaml(EXAMPLES / "iris_pipeline")
        sels = get_universe_selections(data, "baseline")
        assert sels["test_split"] == "twenty_pct"
        assert sels["feature_extraction/method"] == "pca"
        assert sels["classification/classifier"] == "logistic"

    def test_generate_default(self) -> None:
        data = load_yaml(EXAMPLES / "iris")
        universe = generate_default_universe(data)
        sels = {s["decision"]: s["option"] for s in universe["selections"]}
        assert sels["scaling"] == "standard"
        assert sels["model"] == "random_forest"
        assert sels["test_size"] == "small"
        assert sels["random_seed"] == "seed_42"

    def test_generate_default_pipeline(self) -> None:
        data = load_yaml(EXAMPLES / "iris_pipeline")
        universe = generate_default_universe(data)
        sels = {s["decision"]: s["option"] for s in universe["selections"]}
        assert sels["test_split"] == "twenty_pct"
        assert sels["feature_extraction/method"] == "pca"
        assert sels["feature_extraction/n_components"] == "two"
        assert sels["classification/classifier"] == "logistic"

    def test_missing_universe(self) -> None:
        data = load_yaml(EXAMPLES / "iris")
        assert get_universe_selections(data, "nonexistent") == {}


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------


class TestConditions:
    def test_none_always_met(self) -> None:
        assert is_condition_met(None, {}) is True

    def test_positive_match(self) -> None:
        assert is_condition_met("scaling.standard", {"scaling": "standard"})

    def test_positive_mismatch(self) -> None:
        assert not is_condition_met("scaling.minmax", {"scaling": "standard"})

    def test_negation(self) -> None:
        assert is_condition_met("~scaling.minmax", {"scaling": "standard"})

    def test_list_and(self) -> None:
        sels = {"scaling": "standard", "model": "svm"}
        assert is_condition_met(["scaling.standard", "model.svm"], sels)
        assert not is_condition_met(["scaling.standard", "model.rf"], sels)


# ---------------------------------------------------------------------------
# Output dependencies
# ---------------------------------------------------------------------------


class TestOutputDependencies:
    def test_deps(self) -> None:
        data = load_yaml(EXAMPLES / "iris")
        deps = get_output_dependencies(data)
        assert deps["trained_output"] == []
        assert "trained_output" in deps["accuracy"]

    def test_no_recipe(self) -> None:
        data = {
            "name": "test",
            "astra_version": "1.0",
            "outputs": [{"name": "x", "type": "metric"}],
        }
        deps = get_output_dependencies(data)
        assert deps["x"] == []
