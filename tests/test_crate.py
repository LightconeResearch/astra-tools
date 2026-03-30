"""Tests for the ASTRA RO-Crate SDK (astra.crate)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from astra.crate import ASTRACrate
from astra.vocabulary import (
    ASTRA_PROFILE_URL,
    PROP_ACTIVE_WHEN,
    PROP_DEFAULT_OPTION,
    PROP_DELEGATES_TO,
    PROP_EXCLUDED_REASON,
    PROP_INCOMPATIBLE_WITH,
    PROP_IS_EXCLUDED,
    PROP_OUTPUT_FROM,
    PROP_REQUIRES_OPTION,
    TYPE_ANALYSIS,
    TYPE_INPUT,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_crate() -> ASTRACrate:
    """A minimal crate with inputs, outputs, decisions."""
    c = ASTRACrate("Iris Classification", version="1.0")
    c.add_input("iris_data", "data", source="sklearn.datasets.load_iris")
    c.add_output("accuracy", "metric", recipe_command="python src/evaluate.py")
    c.add_output(
        "trained_model",
        "data",
        recipe_command="python src/train.py",
        description="Trained classifier",
    )
    c.add_output(
        "confusion_matrix",
        "figure",
        recipe_command="python src/evaluate.py",
        recipe_inputs=["trained_model"],
    )
    c.add_decision(
        "scaling",
        "Feature Scaling",
        {
            "standard": {"label": "StandardScaler"},
            "minmax": {
                "label": "MinMaxScaler",
                "incompatible_with": ["model.svm"],
            },
        },
        default="standard",
    )
    c.add_decision(
        "model",
        "Classification Model",
        {
            "svm": {"label": "SVM", "requires": ["scaling.standard"]},
            "random_forest": {"label": "Random Forest"},
        },
        default="random_forest",
    )
    return c


@pytest.fixture
def pipeline_crate() -> ASTRACrate:
    """A nested crate with subcrates."""
    c = ASTRACrate("Iris Pipeline", version="1.0")
    c.add_input("iris_data", "data", source="sklearn.datasets.load_iris")
    c.add_output("accuracy", "metric", output_from="classification.accuracy")
    c.add_decision(
        "test_split",
        "Test Split",
        {"twenty_pct": {"label": "20%"}, "thirty_pct": {"label": "30%"}},
        default="twenty_pct",
    )

    fe = c.add_subcrate("feature_extraction", analysis_name="Feature Extraction")
    fe.add_input("raw_features", "data", input_from="iris_data")
    fe.add_output("features", "data", recipe_command="python src/extract.py")
    fe.add_decision(
        "method",
        "Extraction Method",
        {"pca": {"label": "PCA"}, "mlp": {"label": "MLP Encoder"}},
        default="pca",
    )

    cl = c.add_subcrate("classification", analysis_name="Classification")
    cl.add_input("features", "data", input_from="feature_extraction.features")
    cl.add_output("accuracy", "metric", recipe_command="python src/classify.py")
    cl.add_decision(
        "classifier",
        "Classifier",
        {"logistic": {"label": "Logistic"}, "svm": {"label": "SVM"}},
        default="logistic",
    )

    return c


# ---------------------------------------------------------------------------
# Phase 0: Creation and basic structure
# ---------------------------------------------------------------------------


class TestCrateCreation:
    def test_new_crate_metadata(self) -> None:
        c = ASTRACrate("Test Analysis", version="2.0", description="A test")
        assert c.name == "Test Analysis"
        assert c.astra_version == "2.0"
        assert c.description == "A test"

    def test_root_dataset_type(self) -> None:
        c = ASTRACrate("Test")
        root_type = c.crate.root_dataset.type
        assert isinstance(root_type, list)
        assert "Dataset" in root_type
        assert TYPE_ANALYSIS in root_type

    def test_profile_conformance(self) -> None:
        c = ASTRACrate("Test")
        profile = c.crate.dereference(ASTRA_PROFILE_URL)
        assert profile is not None
        assert "Profile" in profile.type

    def test_write_and_load(self, tmp_path: Path) -> None:
        c = ASTRACrate("Roundtrip", version="1.0")
        c.add_input("data", "data")
        c.write(tmp_path / "crate")

        loaded = ASTRACrate.load(tmp_path / "crate")
        assert loaded.name == "Roundtrip"
        assert loaded.astra_version == "1.0"
        assert len(loaded.get_inputs()) == 1

    def test_valid_json_ld(self, tmp_path: Path) -> None:
        c = ASTRACrate("JSON-LD Test")
        c.write(tmp_path / "crate")
        meta = json.loads((tmp_path / "crate" / "ro-crate-metadata.json").read_text())
        assert "@context" in meta
        assert "@graph" in meta
        # ASTRA context is included
        ctx = meta["@context"]
        assert isinstance(ctx, list)
        assert len(ctx) == 2
        assert "astra" in ctx[1]

    def test_authors(self) -> None:
        c = ASTRACrate("Test", authors=["Alice", "Bob"])
        author_prop = c.crate.root_dataset.get("author")
        assert author_prop is not None


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class TestInputs:
    def test_add_data_input(self, simple_crate: ASTRACrate) -> None:
        inputs = simple_crate.get_inputs()
        assert len(inputs) == 1
        inp = inputs[0]
        assert inp["name"] == "iris_data"
        assert inp["inputType"] == "data"
        assert inp["identifier"] == "sklearn.datasets.load_iris"

    def test_get_input_by_name(self, simple_crate: ASTRACrate) -> None:
        inp = simple_crate.get_input("iris_data")
        assert inp is not None
        inp_type = inp.type
        assert TYPE_INPUT in (inp_type if isinstance(inp_type, list) else [inp_type])

    def test_get_nonexistent_input(self, simple_crate: ASTRACrate) -> None:
        assert simple_crate.get_input("nonexistent") is None

    def test_invalid_input_type(self) -> None:
        c = ASTRACrate("Test")
        with pytest.raises(ValueError, match="input_type"):
            c.add_input("data", "invalid_type")

    def test_input_from(self) -> None:
        c = ASTRACrate("Test")
        c.add_input("raw", "data", input_from="parent_input")
        inp = c.get_input("raw")
        assert inp is not None
        assert inp["inputFrom"] == "parent_input"

    def test_analysis_input(self) -> None:
        c = ASTRACrate("Test")
        c.add_input(
            "ref_analysis",
            "analysis",
            analysis_ref="other_analysis",
            ref_version="1.0",
            use_outputs=["output_a", "output_b"],
        )
        inp = c.get_input("ref_analysis")
        assert inp is not None
        assert inp["inputType"] == "analysis"
        based_on = inp["isBasedOn"]
        actual_id = based_on["@id"] if isinstance(based_on, dict) else str(based_on)
        assert actual_id == "other_analysis"


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


class TestOutputs:
    def test_add_output(self, simple_crate: ASTRACrate) -> None:
        outputs = simple_crate.get_outputs()
        assert len(outputs) == 3

    def test_output_types(self, simple_crate: ASTRACrate) -> None:
        acc = simple_crate.get_output("accuracy")
        assert acc is not None
        assert acc["outputType"] == "metric"

    def test_invalid_output_type(self) -> None:
        c = ASTRACrate("Test")
        with pytest.raises(ValueError, match="output_type"):
            c.add_output("x", "invalid_type")

    def test_output_with_recipe(self, simple_crate: ASTRACrate) -> None:
        acc = simple_crate.get_output("accuracy")
        assert acc is not None
        assert acc.get("producer") is not None

    def test_recipe_inputs(self, simple_crate: ASTRACrate) -> None:
        cm = simple_crate.get_output("confusion_matrix")
        assert cm is not None
        recipe_ref = cm.get("producer")
        recipe = simple_crate.crate.dereference(recipe_ref["@id"])
        assert recipe is not None
        assert recipe["description"] == "python src/evaluate.py"

    def test_output_dependencies(self, simple_crate: ASTRACrate) -> None:
        deps = simple_crate.get_output_dependencies()
        assert "confusion_matrix" in deps
        assert "trained_model" in deps["confusion_matrix"]
        assert deps["accuracy"] == []

    def test_outputs_with_recipes(self, simple_crate: ASTRACrate) -> None:
        with_recipes = simple_crate.get_outputs_with_recipes()
        assert len(with_recipes) == 3  # all have recipes

    def test_output_from(self, pipeline_crate: ASTRACrate) -> None:
        acc = pipeline_crate.get_output("accuracy")
        assert acc is not None
        assert acc.get(PROP_OUTPUT_FROM) == "classification.accuracy"

    def test_conditional_output(self) -> None:
        c = ASTRACrate("Test")
        c.add_output("svm_plot", "figure", active_when="model.svm")
        out = c.get_output("svm_plot")
        assert out is not None
        assert out.get(PROP_ACTIVE_WHEN) == "model.svm"


# ---------------------------------------------------------------------------
# Decisions & Options
# ---------------------------------------------------------------------------


class TestDecisions:
    def test_add_decision(self, simple_crate: ASTRACrate) -> None:
        decisions = simple_crate.get_decisions()
        assert len(decisions) == 2

    def test_decision_properties(self, simple_crate: ASTRACrate) -> None:
        scaling = simple_crate.get_decision("scaling")
        assert scaling is not None
        assert scaling["name"] == "scaling"
        assert scaling["alternateName"] == "Feature Scaling"

    def test_decision_options(self, simple_crate: ASTRACrate) -> None:
        opts = simple_crate.get_options("scaling")
        assert len(opts) == 2
        names = {o["name"] for o in opts}
        assert names == {"standard", "minmax"}

    def test_get_option(self, simple_crate: ASTRACrate) -> None:
        opt = simple_crate.get_option("scaling", "standard")
        assert opt is not None
        assert opt["alternateName"] == "StandardScaler"

    def test_default_option(self, simple_crate: ASTRACrate) -> None:
        scaling = simple_crate.get_decision("scaling")
        assert scaling is not None
        default = scaling.get(PROP_DEFAULT_OPTION)
        assert default is not None
        assert default["@id"] == "#decision/scaling/option/standard"

    def test_incompatible_with(self, simple_crate: ASTRACrate) -> None:
        minmax = simple_crate.get_option("scaling", "minmax")
        assert minmax is not None
        incompat = minmax.get(PROP_INCOMPATIBLE_WITH)
        assert incompat is not None
        ids = [r["@id"] for r in incompat]
        assert "#decision/model/option/svm" in ids

    def test_requires_option(self, simple_crate: ASTRACrate) -> None:
        svm = simple_crate.get_option("model", "svm")
        assert svm is not None
        requires = svm.get(PROP_REQUIRES_OPTION)
        assert requires is not None
        ids = [r["@id"] for r in requires]
        assert "#decision/scaling/option/standard" in ids

    def test_excluded_option(self) -> None:
        c = ASTRACrate("Test")
        c.add_decision(
            "method",
            "Method",
            {
                "a": {"label": "A"},
                "b": {
                    "label": "B",
                    "excluded": True,
                    "excluded_reason": "Too slow",
                },
            },
        )
        opt_b = c.get_option("method", "b")
        assert opt_b is not None
        assert opt_b.get(PROP_IS_EXCLUDED) is True
        assert opt_b.get(PROP_EXCLUDED_REASON) == "Too slow"

    def test_delegated_decision(self) -> None:
        c = ASTRACrate("Test")
        c.add_delegated_decision("seed", "../#decision/random_seed")
        dec = c.get_decision("seed")
        assert dec is not None
        assert dec.get(PROP_DELEGATES_TO) is not None

    def test_local_decisions_excludes_delegated(self) -> None:
        c = ASTRACrate("Test")
        c.add_decision("method", "Method", {"a": {"label": "A"}})
        c.add_delegated_decision("seed", "../#decision/random_seed")
        local = c.get_local_decisions()
        assert len(local) == 1
        assert local[0]["name"] == "method"

    def test_conditional_decision(self) -> None:
        c = ASTRACrate("Test")
        c.add_decision(
            "optimizer",
            "Optimizer",
            {"adam": {"label": "Adam"}, "sgd": {"label": "SGD"}},
            active_when="model.neural_net",
        )
        dec = c.get_decision("optimizer")
        assert dec is not None
        assert dec.get(PROP_ACTIVE_WHEN) == "model.neural_net"

    def test_decision_tags(self) -> None:
        c = ASTRACrate("Test")
        c.add_decision(
            "scaling",
            "Scaling",
            {"a": {"label": "A"}},
            tags=["preprocessing", "normalization"],
        )
        dec = c.get_decision("scaling")
        assert dec is not None
        assert "preprocessing" in dec.get("keywords", "")


# ---------------------------------------------------------------------------
# Subcrates
# ---------------------------------------------------------------------------


class TestSubcrates:
    def test_add_subcrate(self, pipeline_crate: ASTRACrate) -> None:
        subcrates = pipeline_crate.get_subcrates()
        assert len(subcrates) == 2
        assert "feature_extraction" in subcrates
        assert "classification" in subcrates

    def test_subcrate_is_astra_crate(self, pipeline_crate: ASTRACrate) -> None:
        fe = pipeline_crate.get_subcrate("feature_extraction")
        assert fe is not None
        assert isinstance(fe, ASTRACrate)
        assert fe.name == "Feature Extraction"

    def test_subcrate_decisions(self, pipeline_crate: ASTRACrate) -> None:
        fe = pipeline_crate.get_subcrate("feature_extraction")
        assert fe is not None
        decisions = fe.get_decisions()
        assert len(decisions) == 1
        assert decisions[0]["name"] == "method"

    def test_subcrate_write(self, pipeline_crate: ASTRACrate, tmp_path: Path) -> None:
        pipeline_crate.write(tmp_path / "pipeline")
        assert (tmp_path / "pipeline" / "ro-crate-metadata.json").exists()
        assert (tmp_path / "pipeline" / "feature_extraction" / "ro-crate-metadata.json").exists()
        assert (tmp_path / "pipeline" / "classification" / "ro-crate-metadata.json").exists()

    def test_nonexistent_subcrate(self, pipeline_crate: ASTRACrate) -> None:
        assert pipeline_crate.get_subcrate("nonexistent") is None


# ---------------------------------------------------------------------------
# Universes
# ---------------------------------------------------------------------------


class TestUniverses:
    def test_add_universe(self, simple_crate: ASTRACrate) -> None:
        simple_crate.add_universe(
            "baseline",
            {
                "#decision/scaling": "#decision/scaling/option/standard",
                "#decision/model": "#decision/model/option/random_forest",
            },
        )
        universes = simple_crate.get_universes()
        assert len(universes) == 1
        assert universes[0]["name"] == "baseline"

    def test_universe_selections(self, simple_crate: ASTRACrate) -> None:
        simple_crate.add_universe(
            "baseline",
            {
                "#decision/scaling": "#decision/scaling/option/standard",
                "#decision/model": "#decision/model/option/random_forest",
            },
        )
        sels = simple_crate.get_universe_selections("baseline")
        assert len(sels) == 2
        dec_ids = {s[0] for s in sels}
        assert "#decision/scaling" in dec_ids
        assert "#decision/model" in dec_ids

    def test_cross_crate_selections(self, pipeline_crate: ASTRACrate) -> None:
        fe_method = "feature_extraction/#decision/method"
        cl_classifier = "classification/#decision/classifier"
        pipeline_crate.add_universe(
            "baseline",
            {
                "#decision/test_split": "#decision/test_split/option/twenty_pct",
                fe_method: f"{fe_method}/option/pca",
                cl_classifier: f"{cl_classifier}/option/logistic",
            },
        )
        sels = pipeline_crate.get_universe_selections("baseline")
        assert len(sels) == 3
        dec_ids = {s[0] for s in sels}
        assert "feature_extraction/#decision/method" in dec_ids

    def test_generate_default_universe(self, simple_crate: ASTRACrate) -> None:
        simple_crate.generate_default_universe("defaults")
        sels = simple_crate.get_universe_selections("defaults")
        assert len(sels) == 2
        opt_ids = {s[1] for s in sels}
        assert "#decision/scaling/option/standard" in opt_ids
        assert "#decision/model/option/random_forest" in opt_ids

    def test_generate_default_universe_with_subcrates(self, pipeline_crate: ASTRACrate) -> None:
        pipeline_crate.generate_default_universe("defaults")
        sels = pipeline_crate.get_universe_selections("defaults")
        assert len(sels) == 3
        dec_ids = {s[0] for s in sels}
        assert "#decision/test_split" in dec_ids
        assert "feature_extraction/#decision/method" in dec_ids
        assert "classification/#decision/classifier" in dec_ids

    def test_nonexistent_universe(self, simple_crate: ASTRACrate) -> None:
        assert simple_crate.get_universe("nonexistent") is None
        assert simple_crate.get_universe_selections("nonexistent") == []


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------


class TestConditions:
    def test_none_is_always_met(self) -> None:
        assert ASTRACrate.is_condition_met(None, {}) is True

    def test_positive_match(self) -> None:
        assert ASTRACrate.is_condition_met("scaling.standard", {"scaling": "standard"})

    def test_positive_mismatch(self) -> None:
        assert not ASTRACrate.is_condition_met("scaling.minmax", {"scaling": "standard"})

    def test_negation_match(self) -> None:
        assert ASTRACrate.is_condition_met("~scaling.minmax", {"scaling": "standard"})

    def test_negation_mismatch(self) -> None:
        assert not ASTRACrate.is_condition_met("~scaling.standard", {"scaling": "standard"})

    def test_list_and_all_met(self) -> None:
        decisions = {"scaling": "standard", "model": "svm"}
        assert ASTRACrate.is_condition_met(["scaling.standard", "model.svm"], decisions)

    def test_list_and_partial_met(self) -> None:
        decisions = {"scaling": "standard", "model": "rf"}
        assert not ASTRACrate.is_condition_met(["scaling.standard", "model.svm"], decisions)

    def test_missing_decision(self) -> None:
        assert not ASTRACrate.is_condition_met("missing.option", {})


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------


class TestInsights:
    def test_add_prior_insight(self) -> None:
        c = ASTRACrate("Test")
        c.add_insight(
            "compute_scaling",
            "Standard scaling improves SVM convergence.",
            [
                {
                    "id": "ev1",
                    "doi": "10.48550/arXiv.1706.03762",
                    "version": 7,
                    "quote": {
                        "exact": "Standard scaling leads to faster convergence",
                        "prefix": "In our experiments, ",
                    },
                    "location": {"page": 5},
                }
            ],
        )
        insights = c.get_prior_insights()
        assert len(insights) == 1
        assert insights[0]["text"] == "Standard scaling improves SVM convergence."

    def test_add_finding(self) -> None:
        c = ASTRACrate("Test")
        c.add_output("accuracy", "metric")
        c.add_insight(
            "scaling_result",
            "StandardScaler achieves best accuracy.",
            [{"id": "ev1", "artifact": "accuracy"}],
            is_finding=True,
        )
        findings = c.get_findings()
        assert len(findings) == 1

    def test_insight_evidence_with_selectors(self) -> None:
        c = ASTRACrate("Test")
        c.add_insight(
            "test_insight",
            "A claim.",
            [
                {
                    "id": "ev1",
                    "doi": "10.1234/test",
                    "quote": {"exact": "quoted text"},
                    "figure": {"label": "Figure 3a", "caption": "Performance"},
                    "table": {
                        "label": "Table 2",
                        "region": "row 3",
                    },
                    "location": {"page": 7},
                }
            ],
        )
        insight = c.get_prior_insight("test_insight")
        assert insight is not None


# ---------------------------------------------------------------------------
# Success Criteria
# ---------------------------------------------------------------------------


class TestSuccessCriteria:
    def test_add_criterion(self) -> None:
        c = ASTRACrate("Test")
        c.add_output("accuracy", "metric")
        c.add_success_criterion("Accuracy above 0.95", output="accuracy", condition="value > 0.95")
        criteria = c.get_success_criteria()
        assert len(criteria) == 1
        assert criteria[0]["text"] == "Accuracy above 0.95"

    def test_criterion_without_output(self) -> None:
        c = ASTRACrate("Test")
        c.add_success_criterion("Model should generalize well")
        criteria = c.get_success_criteria()
        assert len(criteria) == 1


# ---------------------------------------------------------------------------
# Serialization roundtrip
# ---------------------------------------------------------------------------


class TestRoundtrip:
    def test_full_roundtrip(self, simple_crate: ASTRACrate, tmp_path: Path) -> None:
        simple_crate.add_universe(
            "baseline",
            {
                "#decision/scaling": "#decision/scaling/option/standard",
                "#decision/model": "#decision/model/option/random_forest",
            },
        )
        simple_crate.write(tmp_path / "crate")
        loaded = ASTRACrate.load(tmp_path / "crate")

        assert loaded.name == "Iris Classification"
        assert len(loaded.get_inputs()) == 1
        assert len(loaded.get_outputs()) == 3
        assert len(loaded.get_decisions()) == 2
        assert len(loaded.get_universes()) == 1
        assert len(loaded.get_universe_selections("baseline")) == 2

    def test_pipeline_roundtrip(self, pipeline_crate: ASTRACrate, tmp_path: Path) -> None:
        pipeline_crate.write(tmp_path / "pipeline")

        # Verify subcrate files exist
        assert (tmp_path / "pipeline" / "ro-crate-metadata.json").exists()
        fe_meta = tmp_path / "pipeline" / "feature_extraction" / "ro-crate-metadata.json"
        assert fe_meta.exists()

        # Load subcrate independently
        fe = ASTRACrate.load(tmp_path / "pipeline" / "feature_extraction")
        assert fe.name == "Feature Extraction"
        assert len(fe.get_decisions()) == 1
