"""Tests for Pydantic models."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from asp.models.analysis import (
    Analysis,
    AnalysisContent,
    Checksum,
    Decision,
    Evidence,
    Input,
    Option,
    Output,
    Source,
)
from asp.models.universe import Universe


class TestChecksum:
    """Tests for Checksum model."""

    def test_valid_checksum(self):
        checksum = Checksum(algorithm="sha256", value="abc123")
        assert checksum.algorithm == "sha256"
        assert checksum.value == "abc123"

    def test_invalid_algorithm(self):
        with pytest.raises(ValidationError):
            Checksum(algorithm="invalid", value="abc123")


class TestSource:
    """Tests for Source model."""

    def test_url_source(self):
        source = Source(type="url", url="https://example.com/data.csv")
        assert source.type == "url"
        assert source.url == "https://example.com/data.csv"

    def test_s3_source(self):
        source = Source(type="s3", bucket="my-bucket", key="data/file.csv")
        assert source.type == "s3"
        assert source.bucket == "my-bucket"

    def test_sklearn_source(self):
        source = Source(type="sklearn", dataset="iris")
        assert source.type == "sklearn"
        assert source.dataset == "iris"

    def test_invalid_source_type(self):
        with pytest.raises(ValidationError):
            Source(type="invalid")


class TestInput:
    """Tests for Input model."""

    def test_data_input(self):
        inp = Input(id="test_data", type="data", description="Test data")
        assert inp.id == "test_data"
        assert inp.type == "data"

    def test_analysis_input(self):
        inp = Input(id="ref_study", type="analysis", ref="analyses/study", version="v1.0")
        assert inp.type == "analysis"
        assert inp.ref == "analyses/study"

    def test_literature_input(self):
        inp = Input(id="paper", type="literature", description="A paper")
        assert inp.type == "literature"

    def test_invalid_id_pattern(self):
        with pytest.raises(ValidationError):
            Input(id="Invalid-ID", type="data")  # Must be lowercase with underscores

    def test_invalid_input_type(self):
        with pytest.raises(ValidationError):
            Input(id="test", type="invalid")


class TestOutput:
    """Tests for Output model."""

    def test_metric_output(self):
        out = Output(id="accuracy", type="metric", dtype="float", range=(0, 1), primary=True)
        assert out.id == "accuracy"
        assert out.type == "metric"
        assert out.dtype == "float"
        assert out.range == (0, 1)
        assert out.primary is True

    def test_figure_output(self):
        out = Output(id="plot", type="figure", formats=["png", "svg"])
        assert out.type == "figure"
        assert out.formats == ["png", "svg"]

    def test_all_output_types(self):
        for out_type in ["metric", "figure", "table", "data", "model", "report"]:
            out = Output(id="test", type=out_type)
            assert out.type == out_type

    def test_invalid_output_type(self):
        with pytest.raises(ValidationError):
            Output(id="test", type="invalid")


class TestEvidence:
    """Tests for Evidence model."""

    def test_evidence(self):
        ev = Evidence(ref="inputs.study", finding="Shows improvement")
        assert ev.ref == "inputs.study"
        assert ev.finding == "Shows improvement"


class TestOption:
    """Tests for Option model."""

    def test_simple_option(self):
        opt = Option(label="Test Option")
        assert opt.label == "Test Option"

    def test_option_with_value(self):
        opt = Option(label="Test", value={"param": 0.5})
        assert opt.value == {"param": 0.5}

    def test_option_with_constraints(self):
        opt = Option(
            label="Test",
            incompatible_with=["other.opt"],
            requires=["required.opt"],
        )
        assert opt.incompatible_with == ["other.opt"]
        assert opt.requires == ["required.opt"]

    def test_option_with_evidence(self):
        opt = Option(
            label="Test",
            evidence=[Evidence(ref="inputs.study", finding="Good results")],
        )
        assert len(opt.evidence) == 1


class TestDecision:
    """Tests for Decision model."""

    def test_simple_decision(self):
        dec = Decision(
            label="Test Decision",
            type="method",
            options={"a": Option(label="A"), "b": Option(label="B")},
        )
        assert dec.label == "Test Decision"
        assert dec.type == "method"
        assert len(dec.options) == 2

    def test_decision_with_default(self):
        dec = Decision(
            label="Test",
            type="parameter",
            default="a",
            options={"a": Option(label="A"), "b": Option(label="B")},
        )
        assert dec.default == "a"

    def test_invalid_default_raises_error(self):
        with pytest.raises(ValidationError) as exc_info:
            Decision(
                label="Test",
                type="method",
                default="nonexistent",
                options={"a": Option(label="A")},
            )
        assert "not found in options" in str(exc_info.value)

    def test_importance_range(self):
        dec = Decision(
            label="Test",
            type="method",
            importance=1,
            options={"a": Option(label="A")},
        )
        assert dec.importance == 1

        with pytest.raises(ValidationError):
            Decision(
                label="Test",
                type="method",
                importance=0,  # Must be >= 1
                options={"a": Option(label="A")},
            )

        with pytest.raises(ValidationError):
            Decision(
                label="Test",
                type="method",
                importance=6,  # Must be <= 5
                options={"a": Option(label="A")},
            )


class TestAnalysis:
    """Tests for Analysis model."""

    def test_load_minimal(self, minimal_analysis_path: Path):
        analysis = Analysis.from_yaml(minimal_analysis_path)
        assert analysis.version == "1.0"
        assert analysis.analysis.name == "Minimal Analysis"

    def test_load_full(self, full_analysis_path: Path):
        analysis = Analysis.from_yaml(full_analysis_path)
        assert analysis.version == "1.0"
        assert analysis.analysis.name == "Full Analysis"
        assert len(analysis.analysis.inputs) == 3
        assert len(analysis.analysis.outputs) == 6
        assert len(analysis.decisions) == 4

    def test_from_dict(self, minimal_analysis_data: dict):
        analysis = Analysis.model_validate(minimal_analysis_data)
        assert analysis.analysis.name == "Test Analysis"

    def test_get_input(self, full_analysis_path: Path):
        analysis = Analysis.from_yaml(full_analysis_path)
        inp = analysis.get_input("primary_data")
        assert inp is not None
        assert inp.type == "data"

        missing = analysis.get_input("nonexistent")
        assert missing is None

    def test_get_output(self, full_analysis_path: Path):
        analysis = Analysis.from_yaml(full_analysis_path)
        out = analysis.get_output("accuracy")
        assert out is not None
        assert out.primary is True

        missing = analysis.get_output("nonexistent")
        assert missing is None

    def test_get_decision(self, full_analysis_path: Path):
        analysis = Analysis.from_yaml(full_analysis_path)
        dec = analysis.get_decision("preprocessing")
        assert dec is not None
        assert dec.label == "Preprocessing Method"

        missing = analysis.get_decision("nonexistent")
        assert missing is None

    def test_get_default_universe(self, full_analysis_path: Path):
        analysis = Analysis.from_yaml(full_analysis_path)
        defaults = analysis.get_default_universe()
        assert defaults == {
            "preprocessing": "standard",
            "model": "rf",
            "test_split": "split_20",
            "seed": "seed_42",
        }

    def test_to_yaml(self, minimal_analysis_data: dict, tmp_path: Path):
        analysis = Analysis.model_validate(minimal_analysis_data)
        output_path = tmp_path / "output.yaml"
        analysis.to_yaml(output_path)

        # Reload and verify
        reloaded = Analysis.from_yaml(output_path)
        assert reloaded.analysis.name == analysis.analysis.name


class TestUniverse:
    """Tests for Universe model."""

    def test_load_universe(self, baseline_universe_path: Path):
        universe = Universe.from_yaml(baseline_universe_path)
        assert universe.id == "baseline"
        assert "preprocessing" in universe.decisions

    def test_from_dict(self, baseline_universe_data: dict):
        universe = Universe.model_validate(baseline_universe_data)
        assert universe.id == "baseline"

    def test_from_defaults(self, full_analysis_path: Path):
        analysis = Analysis.from_yaml(full_analysis_path)
        universe = Universe.from_defaults(analysis, "test", "Test universe")
        assert universe.id == "test"
        assert universe.description == "Test universe"
        assert universe.decisions["preprocessing"] == "standard"

    def test_to_yaml(self, baseline_universe_data: dict, tmp_path: Path):
        universe = Universe.model_validate(baseline_universe_data)
        output_path = tmp_path / "universe.yaml"
        universe.to_yaml(output_path)

        # Reload and verify
        reloaded = Universe.from_yaml(output_path)
        assert reloaded.id == universe.id

    def test_invalid_id_pattern(self):
        with pytest.raises(ValidationError):
            Universe(id="Invalid ID", decisions={"a": "b"})  # No spaces allowed
