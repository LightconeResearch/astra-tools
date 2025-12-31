"""Tests for Insight models."""

import pytest
from pydantic import ValidationError

from asp.models.insight import (
    AnalysisSource,
    EquationEvidence,
    FigureEvidence,
    Insight,
    InsightCollection,
    MetricEvidence,
    OutputEvidence,
    PaperSource,
    QuoteEvidence,
    ResultEvidence,
    TableEvidence,
)


class TestPaperSource:
    """Tests for PaperSource model."""

    def test_valid_doi(self):
        source = PaperSource(doi="10.1038/s41586-023-06221-2")
        assert source.doi == "10.1038/s41586-023-06221-2"

    def test_valid_arxiv_doi(self):
        source = PaperSource(doi="10.48550/arXiv.2001.08361")
        assert source.doi == "10.48550/arXiv.2001.08361"

    def test_invalid_doi_pattern(self):
        with pytest.raises(ValidationError):
            PaperSource(doi="not-a-doi")

    def test_invalid_doi_missing_prefix(self):
        with pytest.raises(ValidationError):
            PaperSource(doi="1038/s41586-023-06221-2")


class TestAnalysisSource:
    """Tests for AnalysisSource model."""

    def test_basic_analysis_source(self):
        source = AnalysisSource(analysis="org/my-analysis")
        assert source.analysis == "org/my-analysis"
        assert source.version is None

    def test_analysis_source_with_version(self):
        source = AnalysisSource(analysis="org/my-analysis", version="1.0.0")
        assert source.version == "1.0.0"

    def test_analysis_source_with_universe(self):
        source = AnalysisSource(analysis="org/my-analysis", version="1.0", universe="baseline")
        assert source.universe == "baseline"


class TestEvidenceTypes:
    """Tests for evidence type models."""

    def test_figure_evidence(self):
        ev = FigureEvidence(figure="Figure 3a", caption="Convergence curves")
        assert ev.figure == "Figure 3a"
        assert ev.caption == "Convergence curves"

    def test_quote_evidence(self):
        ev = QuoteEvidence(quote="We find L(C) ∝ C^{−0.050}", location="Section 2.1, p.3")
        assert ev.quote == "We find L(C) ∝ C^{−0.050}"
        assert ev.location == "Section 2.1, p.3"

    def test_table_evidence(self):
        ev = TableEvidence(table="Table 1", location="row 3", value="0.92")
        assert ev.table == "Table 1"
        assert ev.value == "0.92"

    def test_equation_evidence(self):
        ev = EquationEvidence(equation="Equation 7", expression="L = (C_c/C)^α")
        assert ev.equation == "Equation 7"
        assert ev.expression == "L = (C_c/C)^α"

    def test_result_evidence(self):
        ev = ResultEvidence(result="accuracy improvement", location="p.5", value=0.15)
        assert ev.result == "accuracy improvement"
        assert ev.value == 0.15

    def test_metric_evidence(self):
        ev = MetricEvidence(metric="accuracy", value=0.94)
        assert ev.metric == "accuracy"
        assert ev.value == 0.94

    def test_output_evidence(self):
        ev = OutputEvidence(output="figures/comparison.png")
        assert ev.output == "figures/comparison.png"


class TestInsight:
    """Tests for Insight model."""

    def test_paper_insight_with_figure(self):
        insight = Insight(
            claim="Model loss scales as a power law with compute",
            source=PaperSource(doi="10.48550/arXiv.2001.08361"),
            evidence=[FigureEvidence(figure="Figure 1")],
        )
        assert insight.claim == "Model loss scales as a power law with compute"
        assert isinstance(insight.source, PaperSource)
        assert len(insight.evidence) == 1

    def test_paper_insight_with_multiple_evidence(self):
        insight = Insight(
            claim="Scaling law applies to language models",
            source=PaperSource(doi="10.1038/s41586-023-06221-2"),
            evidence=[
                FigureEvidence(figure="Figure 1"),
                QuoteEvidence(quote="We observe power law scaling"),
                TableEvidence(table="Table 1"),
            ],
            scope="Transformer models on language tasks",
        )
        assert len(insight.evidence) == 3
        assert insight.scope == "Transformer models on language tasks"

    def test_analysis_insight_with_metrics(self):
        insight = Insight(
            claim="StandardScaler outperforms MinMaxScaler",
            source=AnalysisSource(analysis="org/preprocessing-study", version="1.0"),
            evidence=[
                MetricEvidence(metric="accuracy", value={"standard": 0.94, "minmax": 0.89}),
                OutputEvidence(output="figures/comparison.png"),
            ],
        )
        assert isinstance(insight.source, AnalysisSource)
        assert len(insight.evidence) == 2

    def test_paper_insight_rejects_analysis_evidence(self):
        with pytest.raises(ValidationError) as exc_info:
            Insight(
                claim="Test claim",
                source=PaperSource(doi="10.1038/s41586-023-06221-2"),
                evidence=[MetricEvidence(metric="accuracy", value=0.9)],
            )
        assert "MetricEvidence" in str(exc_info.value)

    def test_analysis_insight_allows_figure_evidence(self):
        # Analysis outputs can include figures, so this should work
        insight = Insight(
            claim="Our analysis shows improvement",
            source=AnalysisSource(analysis="org/study"),
            evidence=[FigureEvidence(figure="output/fig1.png")],
        )
        assert len(insight.evidence) == 1

    def test_insight_from_dict(self):
        data = {
            "claim": "Test claim",
            "source": {"doi": "10.1234/test"},
            "evidence": [{"figure": "Figure 1"}],
        }
        insight = Insight.model_validate(data)
        assert insight.claim == "Test claim"
        assert isinstance(insight.source, PaperSource)


class TestInsightCollection:
    """Tests for InsightCollection model."""

    def test_empty_collection(self):
        collection = InsightCollection()
        assert len(collection.insights) == 0

    def test_collection_with_insights(self):
        collection = InsightCollection(
            insights={
                "scaling_law": Insight(
                    claim="Scaling applies",
                    source=PaperSource(doi="10.1234/test"),
                ),
                "preprocessing": Insight(
                    claim="StandardScaler is better",
                    source=AnalysisSource(analysis="org/study"),
                ),
            }
        )
        assert len(collection.insights) == 2
        assert "scaling_law" in collection.insights

    def test_get_insight(self):
        collection = InsightCollection(
            insights={
                "test_insight": Insight(
                    claim="Test",
                    source=PaperSource(doi="10.1234/test"),
                )
            }
        )
        insight = collection.get_insight("test_insight")
        assert insight is not None
        assert insight.claim == "Test"

        missing = collection.get_insight("nonexistent")
        assert missing is None

    def test_collection_from_dict(self):
        data = {
            "insights": {
                "my_insight": {
                    "claim": "Important finding",
                    "source": {"doi": "10.1234/paper"},
                    "evidence": [
                        {"figure": "Figure 2"},
                        {"quote": "Key quote", "location": "p.5"},
                    ],
                }
            }
        }
        collection = InsightCollection.model_validate(data)
        assert "my_insight" in collection.insights
        insight = collection.insights["my_insight"]
        assert len(insight.evidence) == 2

    def test_collection_to_yaml(self, tmp_path):
        collection = InsightCollection(
            insights={
                "test": Insight(
                    claim="Test claim",
                    source=PaperSource(doi="10.1234/test"),
                    evidence=[FigureEvidence(figure="Figure 1")],
                )
            }
        )
        path = tmp_path / "insights.yaml"
        collection.to_yaml(path)
        assert path.exists()

        # Load it back
        loaded = InsightCollection.from_yaml(path)
        assert "test" in loaded.insights
        assert loaded.insights["test"].claim == "Test claim"
